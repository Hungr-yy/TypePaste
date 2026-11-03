"""Real XTEST typing into disposable Tk widgets on an explicitly enabled Xvfb display.

Never enable this on a user's desktop: the test creates its own focus metadata.
"""
import os
import gc
import subprocess
import threading
import time
import tkinter as tk
import unittest

from typepaste.backends.base import BackendError
from typepaste.backends.linux_x11 import LinuxX11Backend


@unittest.skipUnless(os.environ.get('TYPEPASTE_X11_TEST') == '1', 'Requires isolated Xvfb opt-in')
class X11IntegrationTests(unittest.TestCase):
    def setUp(self):
        # Validate the server, not just DISPLAY's number, before any focus mutation.
        info = subprocess.run(['xdpyinfo'], capture_output=True, text=True, check=True).stdout
        self.assertIn('X.Org', info)
        processes = subprocess.run(['ps', '-eo', 'args'], capture_output=True, text=True, check=True).stdout.splitlines()
        display = os.environ['DISPLAY'].split('.')[0]
        self.assertTrue(any(line.split()[:2] in (['Xvfb', display], ['/usr/bin/Xvfb', display])
                            for line in processes), 'Run this test with xvfb-run -a')
        self.root = tk.Tk(className='Firefox')
        self.root.title('TypePaste isolated test target')
        self.editor = tk.Text(self.root)
        self.editor.pack()
        self.root.update()
        windows = subprocess.run(['xdotool', 'search', '--pid', str(os.getpid()), '--class', 'Firefox'],
                                 capture_output=True, text=True).stdout.splitlines()
        if not windows:
            windows = subprocess.run(['xdotool', 'search', '--class', 'Firefox'],
                                     capture_output=True, text=True, check=True).stdout.splitlines()
        self.window = windows[-1]
        subprocess.run(['xprop', '-id', self.window, '-f', '_NET_WM_PID', '32c', '-set',
                        '_NET_WM_PID', str(os.getpid())], check=True, capture_output=True)
        subprocess.run(['xprop', '-root', '-f', '_NET_SUPPORTED', '32a', '-set',
                        '_NET_SUPPORTED', '_NET_ACTIVE_WINDOW'], check=True, capture_output=True)
        subprocess.run(['xprop', '-root', '-f', '_NET_ACTIVE_WINDOW', '32x', '-set',
                        '_NET_ACTIVE_WINDOW', hex(int(self.window))], check=True, capture_output=True)
        self.editor.focus_force()
        self.root.update()
        self.backend = LinuxX11Backend()
        self.target = self.backend.link_target(self.backend.get_active_target())

    def tearDown(self):
        self.backend.abort()
        self.root.destroy()
        self.editor = self.root = None
        gc.collect()

    def transfer(self, text, stopped=None):
        errors = []
        def send():
            try:
                self.backend.send_keystrokes(text, self.target, 20, stopped or threading.Event())
            except Exception as exc:
                errors.append(exc)
        worker = threading.Thread(target=send)
        worker.start()
        deadline = time.monotonic() + 8
        while worker.is_alive() and time.monotonic() < deadline:
            self.root.update()
            time.sleep(0.005)
        worker.join(timeout=1)
        self.root.update()
        self.assertFalse(worker.is_alive())
        return errors

    def test_real_xdotool_preserves_case_punctuation_unicode_no_enter(self):
        text = 'AbC "hi" | $x; \\ & < > é'
        self.assertEqual(self.transfer(text), [])
        self.assertEqual(self.editor.get('1.0', 'end-1c'), text)

    def test_real_focus_loss_stops(self):
        def change_focus():
            subprocess.run(['xprop', '-root', '-f', '_NET_ACTIVE_WINDOW', '32x',
                            '-set', '_NET_ACTIVE_WINDOW', '0x0'], check=True, capture_output=True)
        self.root.after(100, change_focus)
        errors = self.transfer('a' * 100)
        self.assertTrue(errors)
        self.assertIsInstance(errors[0], BackendError)
        self.assertLess(len(self.editor.get('1.0', 'end-1c')), 100)

    def test_real_stop(self):
        stopped = threading.Event()
        self.root.after(100, stopped.set)
        self.assertEqual(self.transfer('a' * 100, stopped), [])
        self.assertLess(len(self.editor.get('1.0', 'end-1c')), 100)


if __name__ == '__main__':
    unittest.main()
