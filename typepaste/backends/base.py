"""Small native adapter boundary. No UI, clipboard, storage or network access."""
from dataclasses import dataclass
import threading
import time


class BackendError(Exception):
    """A user-safe message; never include payloads or native exception text."""


@dataclass(frozen=True)
class Capabilities:
    available: bool
    reason: str
    focus_detection: bool = True
    unicode: bool = True
    permission_request: bool = False


@dataclass(frozen=True)
class Target:
    window_id: object
    pid: int
    application: str

    def matches(self, other):
        return (other is not None and self.window_id == other.window_id
                and self.pid == other.pid and self.application == other.application)


class Backend:
    name = 'Unavailable'

    def capabilities(self):
        raise NotImplementedError

    def get_active_target(self):
        raise NotImplementedError

    def link_target(self, target):
        if not self.capabilities().available:
            raise BackendError(self.capabilities().reason)
        if target is None or target.pid <= 0 or not target.window_id or target.application not in (
                'firefox', 'firefox.exe', 'org.mozilla.firefox', 'org.mozilla.firefoxdeveloperedition',
                'firefox-esr', 'firefox-developer-edition', 'firefox-nightly'):
            raise BackendError('Click the STEPfwd Firefox window to link it.')
        return target

    def send_keystrokes(self, text, target, delay_ms, stopped: threading.Event):
        if delay_ms not in (20, 40, 70, 120):
            raise BackendError('Choose a typing delay of 20, 40, 70 or 120 ms.')
        if not self.capabilities().available:
            raise BackendError(self.capabilities().reason)
        sent = 0
        for character in text:
            started = time.monotonic()
            if stopped.is_set():
                break
            if not target.matches(self.get_active_target()):
                raise BackendError('Focus lost. Stopped; check the VM for partial input.')
            if stopped.is_set():
                break
            self._send_character(character)
            sent += 1
            if stopped.wait(max(0, delay_ms / 1000 - (time.monotonic() - started))):
                break
        return sent

    def _send_character(self, character):
        raise NotImplementedError

    def abort(self):
        """Called after the transfer's cancellation event is set."""

    def request_permission(self):
        return False


class UnavailableBackend(Backend):
    def __init__(self, reason):
        self.reason = reason

    def capabilities(self):
        return Capabilities(False, self.reason, focus_detection=False, unicode=False)

    def get_active_target(self):
        return None
