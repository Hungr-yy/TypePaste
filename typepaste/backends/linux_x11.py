"""Preserves XTEST/xdotool typing with stdin, checking focus for each character."""
import subprocess

from .base import Backend, BackendError, Capabilities, Target


class LinuxX11Backend(Backend):
    name = 'Linux X11 / xdotool'

    def __init__(self, executable='xdotool'):
        self.executable = executable

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
        # Finish one bounded key pair even if cancellation arrives during it.
        # Killing xdotool mid-character could strand a key or cleared modifier.
        # The shared cancellation event prevents the next character from starting.
        try:
            # A nonzero delay lets X clients consume temporary Unicode mappings
            # before xdotool restores them; zero delay dropped accented text.
            process = subprocess.run(
                [self.executable, 'type', '--clearmodifiers', '--delay', '20', '--file', '-'],
                input=character.encode('utf-8'), stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, timeout=1.0, check=False)
        except subprocess.TimeoutExpired:
            raise BackendError('xdotool timed out. Check the VM and keyboard state before continuing.') from None
        except OSError:
            raise BackendError('Could not run xdotool. Check the Linux installation.') from None
        if process.returncode:
            raise BackendError('xdotool stopped. Check the VM for partial input.')
