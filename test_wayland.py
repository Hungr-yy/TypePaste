"""Wayland safety contracts; no access to the user's bus, compositor or keyboard."""
import threading
import unittest
from unittest.mock import Mock, patch

from typepaste.backends import Host, choose_backend
from typepaste.backends.base import BackendError, Target
from typepaste.backends.linux_wayland import WaylandBackend, keysym_for
from typepaste.backends.wayland_portal import PortalKeyboard
from typepaste.backends.kwin_focus import FocusReply, KWinFocus


class FakeBus:
    def __init__(self):
        self.calls = []
        self.responses = [{'session_handle': '/session/test'}, {}, {'devices': 1}]
        self.callbacks = {}
        self.closed = False

    def request(self, method, signature, args, options, cancelled):
        self.calls.append((method, args, options))
        return self.responses.pop(0)

    def call(self, destination, path, interface, method, signature='()', args=()):
        self.calls.append((method, args, {}))
        return ()

    def subscribe(self, destination, path, interface, signal, callback):
        self.callbacks[signal] = callback
        return 1

    def unsubscribe(self, subscription):
        pass


class PortalTests(unittest.TestCase):
    def setUp(self):
        self.bus = FakeBus()
        self.portal = PortalKeyboard(self.bus)
        self.cancelled = threading.Event()

    def test_keyboard_only_explicit_nonpersistent_grant(self):
        self.assertFalse(self.portal.ready)
        self.assertEqual(self.bus.calls, [])
        self.portal.start(self.cancelled)
        self.assertTrue(self.portal.ready)
        self.assertEqual([c[0] for c in self.bus.calls], ['CreateSession', 'SelectDevices', 'Start'])
        options = self.bus.calls[1][2]
        self.assertEqual(options, {'types': 1, 'persist_mode': 0})
        self.assertEqual(self.bus.calls[2][1], ('/session/test', ''))

    def test_missing_keyboard_grant_closes_session(self):
        for grant in (0, 2, 3):
            with self.subTest(grant=grant):
                self.setUp()
                self.bus.responses[-1] = {'devices': grant}
                with self.assertRaises(BackendError):
                    self.portal.start(self.cancelled)
                self.assertFalse(self.portal.ready)
                self.assertEqual(self.bus.calls[-1][0], 'Close')

    def test_permission_denial_does_not_leak_session(self):
        with patch.object(self.bus, 'request', side_effect=[{'session_handle': '/session/test'}, BackendError('Denied')]):
            with self.assertRaises(BackendError):
                self.portal.start(self.cancelled)
        self.assertFalse(self.portal.ready)
        self.assertEqual(self.bus.calls[-1][0], 'Close')

    def test_revocation_disables_input(self):
        self.portal.start(self.cancelled)
        self.bus.callbacks['Closed']()
        with self.assertRaises(BackendError):
            self.portal.send('x')
        self.assertFalse(self.portal.ready)
        self.assertFalse(any(c[0].startswith('Notify') for c in self.bus.calls))

    def test_unicode_key_pairs_and_no_extra_enter(self):
        self.portal.start(self.cancelled)
        text = 'aA$|é漢🙂'
        for character in text:
            self.portal.send(character)
        keys = [c[1][2:] for c in self.bus.calls if c[0] == 'NotifyKeyboardKeysym']
        self.assertEqual(keys, [(keysym_for(c), state) for c in text for state in (1, 0)])
        self.assertNotIn((0xff0d, 1), keys)
        self.assertEqual(keysym_for('\n'), 0xff0d)
        self.assertEqual(keysym_for('\t'), 0xff09)
        for c in ('\x1b', '\x00', '\ud800', '\u2028'):
            with self.assertRaises(BackendError):
                keysym_for(c)

    def test_failed_key_down_attempts_release_then_closes(self):
        self.portal.start(self.cancelled)
        original = self.bus.call
        def failed(destination, path, interface, method, signature='()', args=()):
            original(destination, path, interface, method, signature, args)
            if method == 'NotifyKeyboardKeysym' and args[-1] == 1:
                raise RuntimeError('PRIVATE NATIVE DETAILS')
        self.bus.call = failed
        with self.assertRaisesRegex(BackendError, 'Stopped') as raised:
            self.portal.send('a')
        self.assertNotIn('PRIVATE', str(raised.exception))
        self.assertEqual([c[0] for c in self.bus.calls[-3:]],
                         ['NotifyKeyboardKeysym', 'NotifyKeyboardKeysym', 'Close'])
        self.assertFalse(self.portal.ready)

    def test_close_is_idempotent_and_disables_input(self):
        self.portal.start(self.cancelled)
        self.portal.close()
        self.portal.close()
        self.assertEqual(sum(c[0] == 'Close' for c in self.bus.calls), 1)
        with self.assertRaises(BackendError):
            self.portal.send('a')


class FocusTests(unittest.TestCase):
    def test_locked_screen_and_missing_lock_state_refuse_focus(self):
        bus = Mock()
        bus.owner.return_value = ':1.42'
        focus = KWinFocus(bus)
        focus.owner = ':1.42'
        bus.call.return_value = (True,)
        with self.assertRaisesRegex(BackendError, 'locked'):
            focus.get_active_target()
        bus.call.side_effect = RuntimeError('PRIVATE')
        with self.assertRaisesRegex(BackendError, 'could not be verified'):
            focus.get_active_target()

    def test_compositor_restart_refuses_old_focus_identity(self):
        bus = Mock()
        bus.owner.return_value = ':1.43'
        focus = KWinFocus(bus)
        focus.owner = ':1.42'
        with self.assertRaisesRegex(BackendError, 'disconnected'):
            focus.get_active_target()

    def test_only_matching_sender_and_fresh_nonce_can_resolve_focus(self):
        reply = FocusReply(':1.42', 'nonce')
        values = ('{12345678-1234-1234-1234-123456789abc}', '123', 'firefox')
        self.assertFalse(reply.accept(':1.43', 'nonce', *values))
        self.assertFalse(reply.accept(':1.42', 'old', *values))
        self.assertFalse(reply.done.is_set())
        self.assertTrue(reply.accept(':1.42', 'nonce', *values))
        self.assertEqual(reply.target, Target(values[0], 123, 'firefox'))
        self.assertFalse(reply.accept(':1.42', 'nonce', *values))

    def test_malformed_or_empty_focus_fails_closed(self):
        for values in (('', '', ''), ('not-a-uuid', '123', 'firefox'),
                       ('{12345678-1234-1234-1234-123456789abc}', '-1', 'firefox')):
            reply = FocusReply(':1.42', 'nonce')
            reply.accept(':1.42', 'nonce', *values)
            self.assertIsNone(reply.target)


class BackendTests(unittest.TestCase):
    def test_kde_selection_never_falls_back_to_xdotool(self):
        with patch('typepaste.backends.linux_wayland.WaylandBackend') as factory:
            selected = choose_backend(host=Host('Linux', 'Manjaro Linux', 'wayland', ':1', 'KDE'))
            self.assertIs(selected, factory.return_value)
        self.assertFalse(choose_backend(host=Host('Linux', 'Ubuntu', 'wayland', ':1', 'GNOME')).capabilities().available)

    def test_permission_is_explicit_and_start_is_nonblocking(self):
        backend = WaylandBackend(runtime_factory=Mock())
        self.assertFalse(backend.capabilities().available)
        self.assertTrue(backend.capabilities().permission_request)
        backend.runtime_factory.assert_not_called()
        backend.close()

    def ready_backend(self):
        runtime = Mock()
        runtime.focus.get_active_target.return_value = Target('uuid', 123, 'firefox')
        runtime.keyboard.ready = True
        backend = WaylandBackend(runtime_factory=lambda: runtime)
        backend.request_permission()
        backend.setup_worker.join(2)
        self.addCleanup(backend.close)
        self.assertTrue(backend.capabilities().available)
        return backend, runtime

    def test_per_character_focus_and_stop(self):
        backend, runtime = self.ready_backend()
        target = runtime.focus.get_active_target.return_value
        runtime.keyboard.send.side_effect = lambda _: setattr(runtime.focus.get_active_target, 'return_value', None)
        with self.assertRaises(BackendError):
            backend.send_keystrokes('abc', target, 20, threading.Event())
        runtime.keyboard.send.assert_called_once_with('a')

    def test_revocation_cannot_reuse_old_permission(self):
        backend, runtime = self.ready_backend()
        runtime.keyboard.ready = False
        self.assertFalse(backend.capabilities().available)
        self.assertTrue(backend.capabilities().permission_request)

    def test_focus_failure_revokes_keyboard_session(self):
        backend, runtime = self.ready_backend()
        runtime.focus.get_active_target.side_effect = RuntimeError('PRIVATE')
        with self.assertRaises(BackendError):
            backend.get_active_target()
        self.assertFalse(backend.capabilities().available)
        runtime.close.assert_called_once()

    def test_stop_sends_no_next_character(self):
        backend, runtime = self.ready_backend()
        stopped = threading.Event()
        runtime.keyboard.send.side_effect = lambda _: stopped.set()
        self.assertEqual(backend.send_keystrokes('abc', runtime.focus.get_active_target(), 20, stopped), 1)
        runtime.keyboard.send.assert_called_once_with('a')

    def test_close_during_permission_setup_cannot_enable_later(self):
        started, release = threading.Event(), threading.Event()
        runtime = Mock()
        runtime.keyboard.ready = True
        def start(_cancelled):
            started.set()
            release.wait(2)
        runtime.start.side_effect = start
        backend = WaylandBackend(runtime_factory=lambda: runtime)
        backend.request_permission()
        self.assertTrue(started.wait(1))
        backend.close()
        release.set()
        backend.setup_worker.join(2)
        self.assertFalse(backend.capabilities().available)
        runtime.close.assert_called()


if __name__ == '__main__':
    unittest.main()
