"""Opt-in real KDE focus tests. These never request keyboard access or send keys.

TYPEPASTE_KWIN_TEST=1 python3 -m unittest -v test_wayland_focus.py
Only this test's temporary KWin script is loaded/unloaded. Window titles and
contents are never read. The desktop's current focus is left alone.
"""
import os
import unittest

from typepaste.backends import detect_host
from typepaste.backends.base import BackendError
from typepaste.backends.kwin_focus import KWinFocus
from typepaste.backends.wayland_bus import GioBus


@unittest.skipUnless(os.environ.get('TYPEPASTE_KWIN_TEST') == '1', 'real KDE read-only opt-in required')
class KWinFocusTests(unittest.TestCase):
    def setUp(self):
        host = detect_host()
        self.assertEqual(host.session, 'wayland')
        self.assertIn('kde', host.desktop.lower().split(':'))
        self.bus = GioBus()
        self.addCleanup(self.bus.close)
        self.focus = KWinFocus(self.bus)
        self.addCleanup(self.focus.close)
        self.focus.start()

    def test_fresh_snapshots_and_cleanup(self):
        for _ in range(5):
            target = self.focus.get_active_target()
            # No window is also valid when the user focuses the desktop.
            if target is not None:
                self.assertGreater(target.pid, 0)
                self.assertTrue(target.window_id)
        self.focus.close()
        loaded = self.bus.call(self.focus.owner, '/Scripting', 'org.kde.kwin.Scripting',
                               'isScriptLoaded', '(s)', (self.focus.name,))[0]
        self.assertFalse(loaded)

    def test_lost_helper_cannot_reuse_previous_snapshot(self):
        self.focus.get_active_target()
        self.bus.call(self.focus.owner, '/Scripting', 'org.kde.kwin.Scripting',
                      'unloadScript', '(s)', (self.focus.name,))
        with self.assertRaises(BackendError):
            self.focus.get_active_target()


if __name__ == '__main__':
    unittest.main()
