"""Safety contracts. These tests are deliberately independent of Tk and native OS APIs."""
import threading
import unittest
from unittest.mock import patch

from typepaste.core import Controller, normalize_text
from typepaste.backends.base import Backend, BackendError, Capabilities, Target
from typepaste.backends import Host, choose_backend, identify_host_os


class FakeBackend(Backend):
    name = 'Fake'

    def __init__(self):
        super().__init__()
        self.current = Target('10', 123, 'firefox')
        self.sent = []
        self.after_character = lambda: None

    def capabilities(self):
        return Capabilities(True, 'Fake ready')

    def get_active_target(self):
        return self.current

    def _send_character(self, character):
        self.sent.append(character)
        self.after_character()


class TextTests(unittest.TestCase):
    def test_preserves_unicode_case_and_shell_metacharacters(self):
        text = 'AbC é 漢字 🙂 " \' $HOME $(id) `id` | & ; > < \\ %'
        self.assertEqual(normalize_text(text, False), (text, None))

    def test_no_final_enter(self):
        for value in ('hello\n', 'hello\r\n', 'hello\r', 'hello\n\n'):
            self.assertEqual(normalize_text(value, False), ('hello', None))

    def test_multiline_and_tab_opt_in(self):
        for value in ('one\ntwo', 'one\ttwo'):
            self.assertIsNone(normalize_text(value, False)[0])
            self.assertEqual(normalize_text(value, True), (value, None))
        self.assertEqual(normalize_text('one\r\ntwo', True), ('one\ntwo', None))

    def test_controls_always_rejected(self):
        for char in ('\x00', '\x1b', '\b', '\x7f', '\x85', '\u2028', '\u2029', '\ud800', '\r'):
            with self.subTest(char=repr(char)):
                self.assertIsNone(normalize_text('a' + char + 'b', True)[0])

    def test_empty_and_size_limit(self):
        for value in ('', '\n\r\n', 'a' * 20001):
            self.assertIsNone(normalize_text(value, True)[0])


class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.backend = FakeBackend()
        self.target = self.backend.link_target(self.backend.current)

    def test_exact_window_process_and_app(self):
        for target in (Target('11', 123, 'firefox'), Target('10', 124, 'firefox'),
                       Target('10', 123, 'terminal'), None):
            self.assertFalse(self.target.matches(target))
        self.assertTrue(self.target.matches(Target('10', 123, 'firefox')))

    def test_only_firefox_links(self):
        for app in ('terminal', 'notfirefox', 'firefox-helper'):
            with self.assertRaises(BackendError):
                self.backend.link_target(Target('12', 2, app))

    def test_wrong_focus_sends_nothing(self):
        self.backend.current = Target('11', 123, 'firefox')
        with self.assertRaises(BackendError):
            self.backend.send_keystrokes('secret', self.target, 20, threading.Event())
        self.assertEqual(self.backend.sent, [])

    def test_focus_loss_stops_before_next_character(self):
        self.backend.after_character = lambda: setattr(self.backend, 'current', None)
        with self.assertRaises(BackendError):
            self.backend.send_keystrokes('abc', self.target, 20, threading.Event())
        self.assertEqual(self.backend.sent, ['a'])

    def test_cancel_stops_mid_transfer(self):
        stopped = threading.Event()
        self.backend.after_character = stopped.set
        self.assertEqual(self.backend.send_keystrokes('abc', self.target, 20, stopped), 1)
        self.assertEqual(self.backend.sent, ['a'])

    def test_pre_cancel_and_invalid_delay(self):
        stopped = threading.Event()
        stopped.set()
        self.assertEqual(self.backend.send_keystrokes('abc', self.target, 40, stopped), 0)
        with self.assertRaises(BackendError):
            self.backend.send_keystrokes('abc', self.target, 0, threading.Event())
        self.assertEqual(self.backend.sent, [])


class PlatformTests(unittest.TestCase):
    def test_host_detection(self):
        self.assertEqual(identify_host_os('Linux', 'manjaro'), 'Manjaro Linux')
        self.assertEqual(identify_host_os('Linux', 'pop', 'ubuntu debian'), 'Ubuntu')
        self.assertEqual(identify_host_os('Darwin'), 'macOS')
        self.assertEqual(identify_host_os('Windows'), 'Windows 11')
        self.assertEqual(identify_host_os('Linux', 'debian'), 'Linux (other)')

    def test_mismatch_cannot_load_backend(self):
        backend = choose_backend('Windows 11', Host('Linux', 'Manjaro Linux', 'x11', ':1'))
        self.assertFalse(backend.capabilities().available)
        self.assertIn('Choose Auto', backend.capabilities().reason)

    def test_wayland_fails_closed_even_with_display(self):
        backend = choose_backend('Auto (recommended)', Host('Linux', 'Ubuntu', 'wayland', ':1'))
        self.assertFalse(backend.capabilities().available)
        self.assertIn('Wayland', backend.capabilities().reason)

    def test_no_display_and_missing_xdotool(self):
        for display, executable in (('', '/usr/bin/xdotool'), (':1', None)):
            with patch('typepaste.backends.shutil.which', return_value=executable):
                backend = choose_backend('Auto (recommended)', Host('Linux', 'Ubuntu', 'x11', display))
            self.assertFalse(backend.capabilities().available)

    def test_unknown_override_fails_closed(self):
        backend = choose_backend('anything', Host('Linux', 'Ubuntu', 'x11', ':1'))
        self.assertFalse(backend.capabilities().available)

    def test_linux_adapter_selected(self):
        with patch('typepaste.backends.shutil.which', return_value='/usr/bin/xdotool'):
            backend = choose_backend('Ubuntu', Host('Linux', 'Ubuntu', 'x11', ':1'))
        self.assertEqual(backend.name, 'Linux X11 / xdotool')


class ControllerTests(unittest.TestCase):
    def setUp(self):
        self.backend = FakeBackend()
        self.now = 0.0
        self.controller = Controller(self.backend, clock=lambda: self.now)

    def link(self):
        self.controller.begin_link()
        self.controller.tick()
        self.assertIsNotNone(self.controller.target)

    def finish(self):
        self.controller.worker.join(timeout=2)
        self.assertFalse(self.controller.worker.is_alive())
        self.controller.tick()

    def test_never_sends_without_arm(self):
        self.link()
        self.controller.tick()
        self.assertEqual(self.backend.sent, [])

    def test_unlinked_cannot_arm(self):
        self.assertFalse(self.controller.arm('abc', False, 40))
        self.assertEqual(self.backend.sent, [])

    def test_arm_settle_and_complete(self):
        self.link()
        self.assertTrue(self.controller.arm('abc\n', False, 20))
        self.controller.tick()
        self.assertEqual(self.backend.sent, [])
        self.now = 0.23
        self.controller.tick()
        self.finish()
        self.assertEqual(self.backend.sent, list('abc'))
        self.assertEqual(self.controller.mode, 'idle')
        self.assertEqual(self.controller.pending_text, '')

    def test_arm_expires_including_settling(self):
        self.link()
        self.controller.arm('abc', False, 40)
        self.controller.tick()
        self.now = 36
        self.controller.tick()
        self.assertEqual(self.controller.mode, 'idle')
        self.assertEqual(self.backend.sent, [])
        self.assertEqual(self.controller.pending_text, '')

    def test_link_timeout(self):
        self.backend.current = None
        self.controller.begin_link()
        self.now = 46
        self.controller.tick()
        self.assertEqual(self.controller.mode, 'idle')
        self.assertIsNone(self.controller.target)

    def test_tab_and_multiline_require_confirmation(self):
        self.link()
        for text in ('a\nb', 'a\tb'):
            self.assertFalse(self.controller.arm(text, True, 40))
            self.assertTrue(self.controller.arm(text, True, 40, confirmed=True))
            self.controller.cancel()

    def test_cancel_and_profile_change_disarm_and_unlink(self):
        self.link()
        self.controller.arm('abc', False, 40)
        self.controller.set_backend(FakeBackend())
        self.assertEqual(self.controller.mode, 'idle')
        self.assertIsNone(self.controller.target)
        self.assertEqual(self.controller.pending_text, '')
        self.controller.tick()
        self.assertEqual(self.backend.sent, [])

    def test_focus_error_fails_closed(self):
        self.link()
        self.controller.arm('abc', False, 40)
        with patch.object(self.backend, 'get_active_target', side_effect=RuntimeError('secret')):
            self.controller.tick()
        self.assertEqual(self.controller.mode, 'idle')
        self.assertNotIn('secret', self.controller.status)
        self.assertEqual(self.backend.sent, [])

    def test_focus_settle_restarts_for_other_window(self):
        self.link()
        self.controller.arm('abc', False, 40)
        self.controller.tick()
        self.backend.current = None
        self.now = 0.3
        self.controller.tick()
        self.backend.current = self.controller.target
        self.controller.tick()
        self.assertEqual(self.backend.sent, [])
        self.controller.cancel()

    def test_no_rearm_until_cancelled_worker_finishes(self):
        self.link()
        entered, release = threading.Event(), threading.Event()
        def blocked_character():
            entered.set()
            release.wait(2)
        self.backend.after_character = blocked_character
        self.controller.arm('abc', False, 20)
        self.controller.tick()
        self.now = 0.23
        self.controller.tick()
        self.assertTrue(entered.wait(1))
        self.controller.cancel()
        self.assertFalse(self.controller.arm('again', False, 40))
        release.set()
        self.finish()
        self.assertEqual(self.backend.sent, ['a'])
        self.assertIn('partial', self.controller.status.lower())


if __name__ == '__main__':
    unittest.main()
