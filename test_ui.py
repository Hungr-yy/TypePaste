"""UI smoke checks; run under Xvfb on Linux, native Tk on Windows/macOS."""
import os
import gc
from pathlib import Path
import tempfile
import tkinter as tk
import unittest
from unittest.mock import patch

from test_core import FakeBackend
from typepaste.backends.base import Capabilities
from stepfwd_sidecar import TypePaste
from typepaste.preferences import load_prefs, save_prefs


class PreferenceTests(unittest.TestCase):
    def test_allowlist_and_corrupt_preferences(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'prefs.json'
            save_prefs({'geometry': '230x465+1+2', 'host_os': 'Ubuntu', 'delay_ms': 40,
                        'clipboard': 'SECRET', 'multiline': True}, path)
            self.assertNotIn('SECRET', path.read_text())
            self.assertNotIn('multiline', load_prefs(path))
            path.write_text('not json')
            self.assertEqual(load_prefs(path), {})


class UISmokeTests(unittest.TestCase):
    def setUp(self):
        self.prefs = patch('stepfwd_sidecar.load_prefs', return_value={})
        self.prefs.start()
        try:
            self.app = TypePaste(backend=FakeBackend())
        except tk.TclError as exc:
            self.prefs.stop()
            if os.environ.get("TYPEPASTE_REQUIRE_GUI") == "1":
                raise
            self.skipTest(f'Tk display unavailable: {exc}')
        self.app.update()

    def tearDown(self):
        if hasattr(self, 'app'):
            self.app.controller.cancel()
            self.app.after_cancel(self.app.tick_id)
            self.app.destroy()
            del self.app
            self.prefs.stop()
            # Tk finalizers must run on the thread that created the interpreter.
            # Otherwise later worker allocations can collect old UI test cycles.
            gc.collect()

    def test_simple_layout_and_settings(self):
        self.assertEqual(self.app.winfo_width(), 230)
        self.app.open_settings()
        self.app.update()
        self.assertTrue(self.app.settings_window.winfo_exists())
        self.assertTrue(self.app.settings_button.winfo_ismapped())
        self.assertFalse(self.app.multiline_var.get())

    def test_settings_disarms_and_cancels(self):
        self.app.controller.begin_link()
        self.app.controller.tick()
        self.app.controller.arm('hello', False, 40)
        self.app.open_settings()
        self.assertEqual(self.app.controller.mode, 'idle')
        self.assertEqual(self.app.controller.pending_text, '')

    def test_tab_confirmation_declined_sends_nothing(self):
        self.app.controller.begin_link()
        self.app.controller.tick()
        self.app.editor.insert('1.0', 'a\tb')
        self.app.multiline_var.set(True)
        with patch('stepfwd_sidecar.messagebox.askyesno', return_value=False) as confirm:
            self.app.arm()
        confirm.assert_called_once()
        self.assertEqual(self.app.controller.mode, 'idle')
        self.assertEqual(self.app.controller.backend.sent, [])

    def test_permission_action_appears_after_profile_refresh(self):
        self.app.open_settings()
        self.app.update()
        self.assertFalse(self.app.permission_button.winfo_ismapped())
        backend = FakeBackend()
        with patch.object(backend, 'capabilities', return_value=Capabilities(
                False, 'Accessibility required', permission_request=True)):
            with patch('stepfwd_sidecar.choose_backend', return_value=backend):
                self.app.refresh_backend()
            self.app.update()
            self.assertTrue(self.app.permission_button.winfo_ismapped())

    def test_profile_change_invalidates_link_and_disables_arm(self):
        self.app.controller.begin_link()
        self.app.controller.tick()
        self.app.host_os_var.set('Windows 11' if os.name != 'nt' else 'macOS')
        self.app.refresh_backend()
        self.assertIsNone(self.app.controller.target)
        self.assertEqual(str(self.app.arm_button['state']), 'disabled')


if __name__ == '__main__':
    unittest.main()
