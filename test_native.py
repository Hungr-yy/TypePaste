"""Native API contracts, simulated on every host. No real input is emitted."""
import ctypes
from contextlib import nullcontext
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from typepaste.backends.base import BackendError
from typepaste.backends.windows import INPUT, WindowsBackend, keyboard_inputs
from typepaste.backends.macos import MacOSBackend
from typepaste.backends.linux_x11 import LinuxX11Backend


class WindowsTests(unittest.TestCase):
    def test_input_abi_includes_mouse_union_padding(self):
        self.assertEqual(ctypes.sizeof(INPUT), 40 if ctypes.sizeof(ctypes.c_void_p) == 8 else 28)

    def test_unicode_pairs_and_supplementary_plane(self):
        for char, units in [('A', [65]), ('é', [233]), ('🙂', [0xD83D, 0xDE42])]:
            events = keyboard_inputs(char)
            self.assertEqual([e.ki.wScan for e in events], [u for unit in units for u in (unit, unit)])
            self.assertEqual([e.ki.dwFlags for e in events], [4, 6] * len(units))
            self.assertTrue(all(e.ki.wVk == 0 for e in events))

    def test_only_explicit_enter_tab_are_virtual_keys(self):
        for char, key in [('\n', 13), ('\t', 9)]:
            events = keyboard_inputs(char)
            self.assertEqual([e.ki.wVk for e in events], [key, key])
            self.assertEqual([e.ki.dwFlags for e in events], [0, 2])

    def backend(self):
        api = Mock()
        api.GetAsyncKeyState.return_value = 0
        return WindowsBackend(user32=api, kernel32=Mock(), build=22631), api

    def test_sendinput_short_write_is_error_and_releases_keys(self):
        backend, api = self.backend()
        api.SendInput.side_effect = [1, 1]
        with self.assertRaises(BackendError):
            backend._send_character('A')
        self.assertEqual(api.SendInput.call_count, 2)
        releases = api.SendInput.call_args.args[1]
        self.assertTrue(all(e.ki.dwFlags & 2 for e in releases))

    def test_physical_modifier_prevents_shortcuts(self):
        backend, api = self.backend()
        api.GetAsyncKeyState.return_value = 0x8000
        with self.assertRaises(BackendError):
            backend._send_character('a')
        api.SendInput.assert_not_called()

    def test_older_windows_unavailable(self):
        backend = WindowsBackend(user32=Mock(), kernel32=Mock(), build=19045)
        self.assertFalse(backend.capabilities().available)


class MacTests(unittest.TestCase):
    def backend(self, trusted=True):
        q, ax, workspace, cf = Mock(), Mock(), Mock(), Mock()
        ax.AXIsProcessTrusted.return_value = trusted
        ax.kAXTrustedCheckOptionPrompt = 'prompt'
        q.kCGSessionEventTap = 1
        q.kCGEventSourceStateCombinedSessionState = 0
        q.CGEventSourceFlagsState.return_value = 0
        q.kCGEventFlagMaskShift = 1 << 17
        q.kCGEventFlagMaskControl = 1 << 18
        q.kCGEventFlagMaskAlternate = 1 << 19
        q.kCGEventFlagMaskCommand = 1 << 20
        api = SimpleNamespace(q=q, ax=ax, workspace=workspace, cf=cf, pool=nullcontext)
        return MacOSBackend(api), api

    def test_permission_is_never_prompted_implicitly(self):
        backend, api = self.backend(False)
        self.assertFalse(backend.capabilities().available)
        self.assertIsNone(backend.get_active_target())
        api.ax.AXIsProcessTrustedWithOptions.assert_not_called()
        backend.request_permission()
        api.ax.AXIsProcessTrustedWithOptions.assert_called_once_with({'prompt': True})

    def test_unicode_uses_utf16_length_and_key_pairs(self):
        backend, api = self.backend()
        backend._send_character('🙂')
        self.assertEqual(api.q.CGEventKeyboardSetUnicodeString.call_count, 2)
        self.assertEqual(api.q.CGEventKeyboardSetUnicodeString.call_args.args[1:], (2, '🙂'))
        self.assertEqual(api.q.CGEventPost.call_count, 2)

    def test_enter_tab_use_real_keycodes(self):
        for char, code in [('\n', 36), ('\t', 48)]:
            backend, api = self.backend()
            backend._send_character(char)
            self.assertEqual([c.args[1:] for c in api.q.CGEventCreateKeyboardEvent.call_args_list],
                             [(code, True), (code, False)])
            api.q.CGEventKeyboardSetUnicodeString.assert_not_called()

    def test_permission_revocation_blocks_input(self):
        backend, api = self.backend(False)
        with self.assertRaises(BackendError):
            backend._send_character('a')
        api.q.CGEventPost.assert_not_called()

    def test_ax_failure_has_no_app_only_fallback(self):
        backend, api = self.backend()
        app = api.workspace.frontmostApplication.return_value
        app.processIdentifier.return_value = 42
        app.bundleIdentifier.return_value = 'org.mozilla.firefox'
        api.ax.AXUIElementCopyAttributeValue.return_value = (1, None)
        self.assertIsNone(backend.get_active_target())


class X11Tests(unittest.TestCase):
    def test_ubuntu_legacy_xdotool_class_search(self):
        backend = LinuxX11Backend()
        def legacy_query(*args):
            return {'getactivewindow': '123', 'getwindowpid': '42',
                    'search': '123\n456'}.get(args[0])
        with patch.object(backend, '_query', side_effect=legacy_query):
            target = backend.get_active_target()
        self.assertIsNotNone(target)
        self.assertEqual((target.window_id, target.pid, target.application), ('123', 42, 'firefox'))

    def test_snapshot_must_be_stable(self):
        backend = LinuxX11Backend()
        with patch.object(backend, '_query', side_effect=['123', '123', '42', '456']):
            self.assertIsNone(backend.get_active_target())

    def test_pid_and_class_required(self):
        backend = LinuxX11Backend()
        with patch.object(backend, '_query', side_effect=['123', '123', None]):
            self.assertIsNone(backend.get_active_target())

    def test_payload_only_goes_to_stdin(self):
        backend = LinuxX11Backend()
        with patch('typepaste.backends.linux_x11.subprocess.run') as run:
            run.return_value.returncode = 0
            backend._send_character('$')
            self.assertNotIn('$', run.call_args.args[0])
            self.assertNotIn('shell', run.call_args.kwargs)
            self.assertEqual(run.call_args.kwargs['input'], b'$')
            self.assertEqual(run.call_args.kwargs['timeout'], 1.0)

    def test_abort_does_not_kill_an_inflight_key_pair(self):
        backend = LinuxX11Backend()
        backend._process = Mock()
        backend._process.poll.return_value = None
        backend.abort()
        backend._process.terminate.assert_not_called()


class NativeHostSmokeTests(unittest.TestCase):
    """Load the real native bridge on CI without posting any keyboard events."""
    @unittest.skipUnless(__import__('sys').platform == 'win32', 'Windows native API only')
    def test_windows_native_bindings_load(self):
        backend = WindowsBackend()
        self.assertIsInstance(backend.capabilities().available, bool)
        self.assertEqual(backend.user32.SendInput.restype, ctypes.c_uint32)
        self.assertEqual(backend.user32.GetForegroundWindow.restype, ctypes.c_void_p)

    @unittest.skipUnless(__import__('sys').platform == 'darwin', 'macOS native API only')
    def test_macos_native_unicode_event_creation_without_posting(self):
        backend = MacOSBackend()
        self.assertIsInstance(backend.capabilities().available, bool)
        q = backend.api.q
        event = q.CGEventCreateKeyboardEvent(None, 0, True)
        self.assertIsNotNone(event)
        q.CGEventKeyboardSetUnicodeString(event, 2, '🙂')


if __name__ == '__main__':
    unittest.main()
