"""Quartz events and Accessibility window identity. Permission is explicit."""
from .base import Backend, BackendError, Capabilities, Target


class AXWindow:
    """Compare AX elements using CFEqual, never a title or application-only match."""
    def __init__(self, element, equal):
        self.element, self.equal = element, equal

    def __eq__(self, other):
        return isinstance(other, AXWindow) and bool(self.equal(self.element, other.element))


class MacAPI:
    def __init__(self):
        import AppKit
        import ApplicationServices
        import CoreFoundation
        import Quartz
        import objc
        self.q = Quartz
        self.ax = ApplicationServices
        self.cf = CoreFoundation
        self.workspace = AppKit.NSWorkspace.sharedWorkspace()
        self.pool = objc.autorelease_pool


class MacOSBackend(Backend):
    name = 'macOS / Quartz (experimental)'

    def __init__(self, api=None):
        self.api = api or MacAPI()

    def capabilities(self):
        trusted = bool(self.api.ax.AXIsProcessTrusted())
        reason = ('Experimental: Quartz + Accessibility window focus. STEPfwd not yet tested; console Unicode support may vary.'
                  if trusted else 'Allow TypePaste in System Settings → Privacy & Security → Accessibility, then Refresh. No Screen Recording permission is needed.')
        return Capabilities(trusted, reason, permission_request=True)

    def request_permission(self):
        return bool(self.api.ax.AXIsProcessTrustedWithOptions({self.api.ax.kAXTrustedCheckOptionPrompt: True}))

    def get_active_target(self):
        api = self.api
        with api.pool():
            if not api.ax.AXIsProcessTrusted():
                return None
            app = api.workspace.frontmostApplication()
            if app is None:
                return None
            pid = int(app.processIdentifier())
            bundle = str(app.bundleIdentifier() or '')
            if bundle not in ('org.mozilla.firefox', 'org.mozilla.firefoxdeveloperedition'):
                return None
            element = api.ax.AXUIElementCreateApplication(pid)
            api.ax.AXUIElementSetMessagingTimeout(element, 0.25)
            error, window = api.ax.AXUIElementCopyAttributeValue(element, api.ax.kAXFocusedWindowAttribute, None)
            if error != 0 or window is None:
                return None
            current = api.workspace.frontmostApplication()
            if current is None or int(current.processIdentifier()) != pid:
                return None
            return Target(AXWindow(window, api.cf.CFEqual), pid, bundle)

    def _send_character(self, character):
        api = self.api
        with api.pool():
            if not api.ax.AXIsProcessTrusted():
                raise BackendError('Accessibility permission is unavailable. Enable it in Settings, then arm again.')
            q = api.q
            flags = q.CGEventSourceFlagsState(q.kCGEventSourceStateCombinedSessionState)
            if flags & (q.kCGEventFlagMaskShift | q.kCGEventFlagMaskControl |
                        q.kCGEventFlagMaskAlternate | q.kCGEventFlagMaskCommand):
                raise BackendError('Release Shift, Control, Option and Command keys, then arm again.')
            keycode = {'\n': 36, '\t': 48}.get(character, 0)
            down = q.CGEventCreateKeyboardEvent(None, keycode, True)
            up = q.CGEventCreateKeyboardEvent(None, keycode, False)
            if down is None or up is None:
                raise BackendError('macOS could not create keyboard events. Check Accessibility permission.')
            for event in (down, up):
                q.CGEventSetFlags(event, 0)
                if character not in ('\n', '\t'):
                    q.CGEventKeyboardSetUnicodeString(event, len(character.encode('utf-16-le')) // 2, character)
            try:
                q.CGEventPost(q.kCGSessionEventTap, down)
            finally:
                q.CGEventPost(q.kCGSessionEventTap, up)
