"""Arming and transfer lifecycle. All controller methods run on the UI thread."""
import queue
import threading
import time
import unicodedata

from .backends.base import BackendError


MAX_CHARACTERS = 20000


def normalize_text(text, allow_multiline):
    text = text.replace('\r\n', '\n').rstrip('\r\n')
    if not text:
        return None, 'Paste some text first.'
    if len(text) > MAX_CHARACTERS:
        return None, 'Limit: 20,000 characters per transfer.'
    if not allow_multiline and ('\n' in text or '\t' in text):
        return None, 'Multiple lines/tabs blocked. Enable Multiline only in an editor.'
    for character in text:
        if character not in ('\n', '\t') and unicodedata.category(character) in ('Cc', 'Cs', 'Zl', 'Zp'):
            return None, 'Control characters are blocked; use normal text and line feeds.'
    return text, None


class Controller:
    ARM_TIMEOUT = 35.0
    LINK_TIMEOUT = 45.0

    def __init__(self, backend, clock=time.monotonic):
        self.backend = backend
        self.clock = clock
        self.mode = 'idle'
        self.target = None
        self.pending_text = ''
        self.status = 'Link to your STEPfwd Firefox first.'
        self.level = 'info'
        self.deadline = 0
        self.delay_ms = 40
        self.worker = None
        self.stopped = threading.Event()
        self.results = queue.Queue()
        self.generation = 0

    def message(self, text, level='info'):
        self.status, self.level = text, level

    def _busy(self):
        return self.worker is not None and self.worker.is_alive()

    def _ready(self):
        if self._busy():
            self.message('Previous transfer is still stopping. Check the VM for partial input.', 'warning')
            return False
        caps = self.backend.capabilities()
        if not caps.available:
            self.message(caps.reason, 'error')
        return caps.available

    def begin_link(self):
        if not self._ready():
            return False
        self.cancel()
        self.target = None
        self.mode = 'binding'
        self.deadline = self.clock() + self.LINK_TIMEOUT
        self.message('Click inside the STEPfwd Firefox window.', 'active')
        return True

    def arm(self, text, allow_multiline, delay_ms, confirmed=False):
        if not self._ready():
            return False
        self.cancel(quiet=True)  # A failed new arm must not leave an old payload armed.
        if self.target is None:
            self.message('Link STEPfwd Firefox first.', 'error')
            return False
        text, error = normalize_text(text, allow_multiline)
        if error:
            self.message(error, 'error')
            return False
        if delay_ms not in (20, 40, 70, 120):
            self.message('Choose a valid typing delay.', 'error')
            return False
        if ('\n' in text or '\t' in text) and not confirmed:
            self.message('Confirm multiline/tab input before arming.', 'warning')
            return False
        self.pending_text, self.delay_ms = text, delay_ms
        self.mode = 'armed'
        self.deadline = self.clock() + self.ARM_TIMEOUT
        self.message('Click the linked VM to start. Cancels after 35s.', 'warning')
        return True

    def cancel(self, quiet=False):
        previous = self.mode
        self.stopped.set()
        self.backend.abort()
        self.generation += 1  # Stale worker results must not change a newer UI state.
        self.pending_text = ''
        self.mode = 'idle'
        if not quiet:
            self.message('Stopped. Check the VM for partial input.' if self._busy() or previous == 'typing'
                         else 'Transfer cancelled.', 'warning' if self._busy() or previous == 'typing' else 'info')

    def set_backend(self, backend):
        self.cancel(quiet=True)
        self.backend = backend
        self.target = None
        caps = backend.capabilities()
        self.message(caps.reason, 'info' if caps.available else 'warning')

    def tick(self):
        while True:
            try:
                generation, sent, error, stopped = self.results.get_nowait()
            except queue.Empty:
                break
            if generation != self.generation:
                continue
            self.mode = 'idle'
            self.pending_text = ''
            if error:
                self.message(error, 'error')
            elif stopped:
                self.message('Stopped. Check the VM for partial input.', 'warning')
            else:
                self.message(f'Sent {sent} characters. Ready again.', 'success')
        if self.mode not in ('binding', 'armed'):
            return
        now = self.clock()
        if now >= self.deadline:
            binding = self.mode == 'binding'
            self.cancel(quiet=True)
            self.message('Link timed out. Try again.' if binding else 'Arming timed out. Nothing was typed.', 'warning')
            return
        try:
            current = self.backend.get_active_target()
        except Exception:
            self.cancel(quiet=True)
            self.message('Focus could not be read. Nothing was typed.', 'error')
            return
        if self.mode == 'binding':
            try:
                target = self.backend.link_target(current)
            except BackendError:
                return
            self.target = target
            self.mode = 'idle'
            self.message('Linked! Paste text, arm, then click the VM.', 'success')
        elif self.target.matches(current):
            # A click into the linked VM brings its Firefox window into focus.
            # Start on that observation; there is no timed start/countdown.
            # The worker rechecks the target before sending the first character.
            self._start_typing()

    def _start_typing(self):
        self.stopped = threading.Event()
        self.mode = 'typing'
        self.message(f'Typing {len(self.pending_text)} characters…', 'success')
        self.worker = threading.Thread(target=self._transfer, args=(
            self.backend, self.pending_text, self.target, self.delay_ms, self.stopped, self.generation), daemon=True)
        self.pending_text = ''
        self.worker.start()

    def _transfer(self, backend, payload, target, delay, stopped, generation):
        sent, error = 0, ''
        try:
            sent = backend.send_keystrokes(payload, target, delay, stopped)
        except BackendError as exc:
            error = str(exc)
        except Exception:
            error = 'Keyboard backend failed. Stopped; check the VM for partial input.'
        finally:
            self.results.put((generation, sent, error, stopped.is_set()))
