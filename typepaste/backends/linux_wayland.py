"""KDE Plasma Wayland: permission-based portal input and KWin focus identity."""
import importlib.util
import threading
from contextlib import suppress

from .base import Backend, BackendError, Capabilities
from .wayland_portal import PortalKeyboard, keysym_for


class WaylandRuntime:
    def __init__(self):
        from .wayland_bus import GioBus
        from .kwin_focus import KWinFocus
        self.bus = GioBus()
        self.focus = KWinFocus(self.bus)
        self.keyboard = PortalKeyboard(self.bus)
        self.lock = threading.RLock()

    def start(self, cancelled):
        with self.lock:
            if cancelled.is_set():
                return
            self.focus.start()
        if not cancelled.is_set():
            self.keyboard.start(cancelled)

    def close(self):
        with self.lock:
            # Always disconnect: portal sessions are also bound to this private
            # connection, including when the compositor/portal has disappeared.
            with suppress(Exception):
                self.keyboard.close()
            with suppress(Exception):
                self.focus.close()
            self.bus.close()


class WaylandBackend(Backend):
    name = 'KDE Wayland / desktop portal (preview)'

    def __init__(self, runtime_factory=None):
        self.runtime_factory = runtime_factory or WaylandRuntime
        self.dependencies = runtime_factory is not None or importlib.util.find_spec('gi') is not None
        self.runtime = None
        self.setup_worker = None
        self.closed = threading.Event()
        self.lock = threading.Lock()
        self.reason = 'Enable Wayland to allow keyboard input and check the focused Firefox window.'
        self.ready = False

    def capabilities(self):
        if not self.dependencies:
            return Capabilities(False, 'Install PyGObject (Manjaro: python-gobject; Ubuntu: python3-gi).', focus_detection=False)
        if self.closed.is_set():
            return Capabilities(False, 'Wayland connection closed.', focus_detection=False)
        pending = self.setup_worker is not None and self.setup_worker.is_alive()
        available = self.ready and self.runtime is not None and self.runtime.keyboard.ready
        reason = ('Ready. Keyboard access lasts until this app closes. KDE Wayland is a preview.' if available else
                  'Approve keyboard access in the desktop prompt…' if pending else
                  'Keyboard access ended. Enable Wayland again.' if self.ready else self.reason)
        return Capabilities(available, reason, permission_request=not available and not pending,
                            permission_label='Enable Wayland…')

    def request_permission(self):
        if not self.capabilities().permission_request:
            return False
        self.ready = False
        self.setup_worker = threading.Thread(target=self._enable, name='typepaste-wayland-setup', daemon=True)
        self.setup_worker.start()
        return True

    def _enable(self):
        runtime = None
        try:
            if self.runtime:
                self.runtime.close()
            runtime = self.runtime_factory()
            with self.lock:
                if self.closed.is_set():
                    return
                self.runtime = runtime
            runtime.start(self.closed)
            if not self.closed.is_set():
                self.ready = True
        except BackendError as exc:
            self.reason = str(exc)
        except Exception:
            self.reason = 'Could not enable KDE Wayland. Check PyGObject, KWin 6 and xdg-desktop-portal-kde.'
        finally:
            if runtime and (not self.ready or self.closed.is_set()):
                runtime.close()

    def get_active_target(self):
        if not self.capabilities().available:
            raise BackendError(self.capabilities().reason)
        try:
            return self.runtime.focus.get_active_target()
        except Exception:
            self.ready = False
            self.reason = 'Focus could not be verified. Stopped; enable Wayland again.'
            self.runtime.close()
            raise BackendError(self.reason) from None

    def _send_character(self, character):
        if not self.capabilities().available:
            raise BackendError(self.capabilities().reason)
        self.runtime.keyboard.send(character)

    def close(self):
        self.closed.set()
        self.ready = False
        with self.lock:
            runtime = self.runtime
        if runtime:
            runtime.close()
