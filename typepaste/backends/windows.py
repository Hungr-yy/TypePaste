"""Windows 11 foreground HWND/PID and SendInput; no elevated helper or hooks."""
import ctypes as C
import ntpath
import sys

from .base import Backend, BackendError, Capabilities, Target

# Fixed-width types keep ABI tests meaningful even when run outside Windows.
DWORD, WORD, LONG, UINT = C.c_uint32, C.c_uint16, C.c_int32, C.c_uint32
ULONG_PTR = C.c_size_t


class KEYBDINPUT(C.Structure):
    _fields_ = [('wVk', WORD), ('wScan', WORD), ('dwFlags', DWORD), ('time', DWORD), ('dwExtraInfo', ULONG_PTR)]


class MOUSEINPUT(C.Structure):
    _fields_ = [('dx', LONG), ('dy', LONG), ('mouseData', DWORD), ('dwFlags', DWORD),
                ('time', DWORD), ('dwExtraInfo', ULONG_PTR)]


class HARDWAREINPUT(C.Structure):
    _fields_ = [('uMsg', DWORD), ('wParamL', WORD), ('wParamH', WORD)]


class INPUTUNION(C.Union):
    _fields_ = [('ki', KEYBDINPUT), ('mi', MOUSEINPUT), ('hi', HARDWAREINPUT)]


class INPUT(C.Structure):
    _anonymous_ = ('data',)
    _fields_ = [('type', DWORD), ('data', INPUTUNION)]


def keyboard_inputs(character):
    """Unicode avoids keyboard-layout translation and accidental Ctrl/Alt shortcuts.

    Consoles that only consume physical keycodes may ignore VK_PACKET. This must
    be tested against STEPfwd on Windows; never substitute clipboard pasting.
    """
    if character in ('\n', '\t'):
        key = 13 if character == '\n' else 9
        return [INPUT(type=1, ki=KEYBDINPUT(wVk=key)), INPUT(type=1, ki=KEYBDINPUT(wVk=key, dwFlags=2))]
    data = character.encode('utf-16-le')
    events = []
    for i in range(0, len(data), 2):
        unit = int.from_bytes(data[i:i + 2], 'little')
        events.extend((INPUT(type=1, ki=KEYBDINPUT(wScan=unit, dwFlags=4)),
                       INPUT(type=1, ki=KEYBDINPUT(wScan=unit, dwFlags=6))))
    return events


class WindowsBackend(Backend):
    name = 'Windows 11 / SendInput (experimental)'

    def __init__(self, user32=None, kernel32=None, build=None):
        native = user32 is None
        self.user32 = C.WinDLL('user32', use_last_error=True) if native else user32
        self.kernel32 = C.WinDLL('kernel32', use_last_error=True) if native else kernel32
        self.build = sys.getwindowsversion().build if build is None else build
        if native:
            signatures = [
                (self.user32.GetForegroundWindow, [], C.c_void_p),
                (self.user32.GetWindowThreadProcessId, [C.c_void_p, C.POINTER(DWORD)], DWORD),
                (self.user32.GetClassNameW, [C.c_void_p, C.c_wchar_p, C.c_int], C.c_int),
                (self.user32.GetAsyncKeyState, [C.c_int], C.c_int16),
                (self.user32.SendInput, [UINT, C.POINTER(INPUT), C.c_int], UINT),
                (self.kernel32.OpenProcess, [DWORD, C.c_int, DWORD], C.c_void_p),
                (self.kernel32.QueryFullProcessImageNameW, [C.c_void_p, DWORD, C.c_wchar_p, C.POINTER(DWORD)], C.c_int),
                (self.kernel32.CloseHandle, [C.c_void_p], C.c_int),
            ]
            for function, args, result in signatures:
                function.argtypes, function.restype = args, result

    def capabilities(self):
        if self.build < 22000:
            return Capabilities(False, 'This backend requires Windows 11 (build 22000 or newer).')
        return Capabilities(True, 'Experimental: SendInput + exact foreground window. STEPfwd not yet tested; Unicode may be ignored by its console.')

    def get_active_target(self):
        window = self.user32.GetForegroundWindow()
        if not window:
            return None
        pid = DWORD()
        if not self.user32.GetWindowThreadProcessId(window, C.byref(pid)) or not pid.value:
            return None
        class_name = C.create_unicode_buffer(256)
        if not self.user32.GetClassNameW(window, class_name, len(class_name)):
            return None
        if class_name.value != 'MozillaWindowClass':
            return None
        handle = self.kernel32.OpenProcess(0x1000, False, pid.value)  # QUERY_LIMITED_INFORMATION only
        if not handle:
            return None
        try:
            name = C.create_unicode_buffer(32768)
            length = DWORD(len(name))
            if not self.kernel32.QueryFullProcessImageNameW(handle, 0, name, C.byref(length)):
                return None
            application = ntpath.basename(name.value).lower()
        finally:
            self.kernel32.CloseHandle(handle)
        if self.user32.GetForegroundWindow() != window:
            return None
        return Target(window, pid.value, application)

    def _send_character(self, character):
        # Never release keys held by the user; ask them to release instead.
        if any(self.user32.GetAsyncKeyState(key) & 0x8000 for key in (0x10, 0x11, 0x12, 0x5B, 0x5C)):
            raise BackendError('Release Shift, Ctrl, Alt and Windows keys, then arm again.')
        events = keyboard_inputs(character)
        buffer = (INPUT * len(events))(*events)
        sent = self.user32.SendInput(len(events), buffer, C.sizeof(INPUT))
        if sent != len(events):
            # Release only injected down-events from the successful prefix.
            pending = []
            for event in events[:sent]:
                if event.ki.dwFlags & 2:
                    if pending:
                        pending.pop()
                else:
                    pending.append(event)
            if pending:
                releases = [INPUT(type=1, ki=KEYBDINPUT(wVk=e.ki.wVk, wScan=e.ki.wScan,
                                                       dwFlags=e.ki.dwFlags | 2)) for e in reversed(pending)]
                self.user32.SendInput(len(releases), (INPUT * len(releases))(*releases), C.sizeof(INPUT))
            raise BackendError('Windows blocked or only partly accepted input. Keep Firefox at normal privilege; check for partial input.')
