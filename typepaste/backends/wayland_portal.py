"""Keyboard-only, nonpersistent XDG RemoteDesktop portal session."""
import threading
import unicodedata
import uuid

from .base import BackendError
from .wayland_bus import PORTAL, PORTAL_PATH, REMOTE

SESSION = 'org.freedesktop.portal.Session'


def keysym_for(character):
    if character == '\n':
        return 0xff0d
    if character == '\t':
        return 0xff09
    if len(character) != 1 or unicodedata.category(character) in ('Cc', 'Cs', 'Zl', 'Zp'):
        raise BackendError('Unsupported control character. Nothing was typed.')
    code = ord(character)
    return code if code <= 0xff else 0x01000000 | code


class PortalKeyboard:
    def __init__(self, bus):
        self.bus = bus
        self.session = None
        self.ready = False
        self.subscription = None
        self.lock = threading.RLock()
        self.closed = False

    def start(self, cancelled):
        try:
            result = self.bus.request('CreateSession', '(a{sv})', (),
                                     {'session_handle_token': 'typepaste_' + uuid.uuid4().hex}, cancelled)
            with self.lock:
                self.session = result['session_handle']
                if self.closed or cancelled.is_set():
                    raise BackendError('Wayland setup cancelled.')
                self.subscription = self.bus.subscribe(PORTAL, self.session, SESSION, 'Closed', self._revoked)
            self.bus.request('SelectDevices', '(oa{sv})', (self.session,),
                             {'types': 1, 'persist_mode': 0}, cancelled)
            result = self.bus.request('Start', '(osa{sv})', (self.session, ''), {}, cancelled)
            with self.lock:
                if result.get('devices') != 1 or self.closed or cancelled.is_set():
                    raise BackendError('Keyboard-only permission was not granted. Nothing was enabled.')
                self.ready = True
        except Exception:
            self.close()
            raise

    def _revoked(self, *_):
        # Do not acquire the key-pair lock from a D-Bus callback: a worker may
        # be waiting on the same bus. Revocation must immediately disable input.
        self.ready = False
        self.closed = True

    def send(self, character):
        symbol = keysym_for(character)
        with self.lock:
            if not self.ready or self.closed:
                raise BackendError('Keyboard permission ended. Enable Wayland again.')
            try:
                try:
                    self._key(symbol, 1)
                finally:
                    # Release even if the down-call timed out after delivery.
                    self._key(symbol, 0)
            except Exception:
                self.close()
                raise BackendError('Wayland keyboard failed. Stopped; check the VM and keyboard state.') from None

    def _key(self, symbol, state):
        self.bus.call(PORTAL, PORTAL_PATH, REMOTE, 'NotifyKeyboardKeysym',
                      '(oa{sv}iu)', (self.session, {}, symbol, state))

    def close(self):
        with self.lock:
            self.ready = False
            self.closed = True
            session, self.session = self.session, None
            if session:
                try:
                    self.bus.call(PORTAL, session, SESSION, 'Close')
                except Exception:
                    pass
            if self.subscription is not None:
                self.bus.unsubscribe(self.subscription)
                self.subscription = None
