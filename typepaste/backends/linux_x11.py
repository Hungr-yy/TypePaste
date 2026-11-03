"""Preserves XTEST/xdotool typing with stdin, checking focus for each character."""
import subprocess
import threading

from .base import Backend, BackendError, Capabilities, Target


class LinuxX11Backend(Backend):
    name = 'Linux X11 / xdotool'

    def __init__(self, executable='xdotool'):
        self.executable = executable
        self._process = None
        self._lock = threading.Lock()

    def capabilities(self):
        return Capabilities(True, 'Ready: Linux X11 + xdotool. STEPfwd validation still required.')

    def _query(self, *args):
        try:
            result = subprocess.run([self.executable, *args], capture_output=True,
                                    text=True, timeout=0.8, check=False)
        except (OSError, subprocess.TimeoutExpired):
            return None
        return result.stdout.strip() if result.returncode == 0 else None

    def get_active_target(self):
        window = self._query('getactivewindow')
        if not window or not window.isdecimal():
            return None
        # search --class is supported by Ubuntu's older xdotool;
        # getwindowclassname is only present in newer releases.
        matches = self._query('search', '--class',
                              '^(firefox|firefox-esr|firefox-developer-edition|firefox-nightly)$')
        app = 'firefox' if matches and window in matches.splitlines() else None
        pid = self._query('getwindowpid', window)
        if not app or not pid or not pid.isdecimal():
            return None
        # A focus change during the metadata queries invalidates the snapshot.
        if self._query('getactivewindow') != window:
            return None
        return Target(window, int(pid), app.lower())

    def _send_character(self, character):
        try:
            # Allow X clients to consume temporary Unicode key mappings before
            # xdotool restores them; a zero delay can drop non-ASCII characters.
            with self._lock:
                process = subprocess.Popen(
                    [self.executable, 'type', '--clearmodifiers', '--delay', '20', '--file', '-'],
                    stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                self._process = process
            try:
                process.communicate(input=character.encode('utf-8'), timeout=1.0)
            except subprocess.TimeoutExpired:
                process.kill()
                process.communicate()
                raise BackendError('xdotool timed out. Stopped; check the VM for partial input.') from None
            if process.returncode:
                raise BackendError('xdotool stopped. Check the VM for partial input.')
        except OSError:
            raise BackendError('Could not run xdotool. Check the Linux installation.') from None
        finally:
            with self._lock:
                self._process = None

    def abort(self):
        with self._lock:
            if self._process is not None and self._process.poll() is None:
                try:
                    self._process.terminate()
                except OSError:
                    pass
