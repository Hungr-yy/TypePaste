"""Fresh focus snapshots from an ephemeral, read-only KWin 6 script.

The script returns only window UUID, PID and application class, never titles,
contents, keystrokes or clipboard data. Each request has a unique nonce and
accepts replies only from the KWin connection that loaded the script.
"""
import json
from pathlib import Path
import tempfile
import threading
import uuid

from .base import BackendError, Target

PATH = '/org/typepaste/Focus'
INTERFACE = 'org.typepaste.Focus'
XML = '''<node><interface name="org.typepaste.Focus">
<method name="Next"><arg type="s" direction="out"/></method>
<method name="Report"><arg type="s" direction="in"/><arg type="s" direction="in"/>
<arg type="s" direction="in"/><arg type="s" direction="in"/></method>
</interface></node>'''
# Long-poll a local method. There is no cached focus and no periodic window scan.
# The host replies "wait" every 5 seconds when idle to avoid D-Bus timeouts.
SCRIPT = '''
function next() {
    callDBus(DESTINATION, "/org/typepaste/Focus", "org.typepaste.Focus", "Next", function(nonce) {
        if (!nonce) return;
        if (nonce === "wait") { next(); return; }
        var w = workspace.activeWindow;
        var valid = w && w.active && !w.deleted && !w.minimized && !w.popupWindow;
        callDBus(DESTINATION, "/org/typepaste/Focus", "org.typepaste.Focus", "Report",
                 nonce, valid ? String(w.internalId) : "",
                 valid ? String(w.pid) : "", valid ? String(w.resourceClass).toLowerCase() : "", next);
    });
}
next();
'''


class FocusReply:
    def __init__(self, sender, nonce):
        self.sender, self.nonce = sender, nonce
        self.target = None
        self.done = threading.Event()

    def accept(self, sender, nonce, window_id, pid, application):
        if sender != self.sender or nonce != self.nonce or self.done.is_set():
            return False
        try:
            identifier = uuid.UUID(window_id.strip('{}'))
            process = int(pid)
            if identifier.int and process > 0 and application:
                self.target = Target(window_id, process, application)
        except (ValueError, TypeError, AttributeError):
            pass
        self.done.set()
        return True


class KWinFocus:
    def __init__(self, bus):
        self.bus = bus
        self.owner = None
        self.name = 'typepaste_' + uuid.uuid4().hex
        self.script_id = None
        self.directory = None
        self.registration = None
        self.next_call = None
        self.reply = None
        self.lock = threading.RLock()
        self.query_lock = threading.Lock()
        self.closed = False
        self.idle_timer = None

    def start(self):
        self.owner = self.bus.owner('org.kde.KWin')
        # Missing lock-screen detection is a hard failure, not an unlocked default.
        self._locked()
        self.node = self.bus.Gio.DBusNodeInfo.new_for_xml(XML)
        self.registration = self.bus.dispatch(lambda: self.bus.connection.register_object(
            PATH, self.node.interfaces[0], self._method, None, None))
        self.directory = tempfile.TemporaryDirectory(prefix='typepaste-focus-')
        script = Path(self.directory.name) / 'focus.js'
        script.write_text(SCRIPT.replace('DESTINATION', json.dumps(self.bus.connection.get_unique_name())), encoding='utf-8')
        script.chmod(0o600)
        self.script_id = self.bus.call(self.owner, '/Scripting', 'org.kde.kwin.Scripting',
                                       'loadScript', '(ss)', (str(script), self.name))[0]
        if self.script_id < 0:
            raise BackendError('KDE could not load the focus helper. Wayland remains disabled.')
        self.bus.call(self.owner, f'/Scripting/Script{self.script_id}', 'org.kde.kwin.Script', 'run')
        # A real round trip is required before permission can enable input.
        self.get_active_target()

    def _locked(self):
        return self.bus.call('org.freedesktop.ScreenSaver', '/ScreenSaver',
                             'org.freedesktop.ScreenSaver', 'GetActive')[0]

    def _method(self, _connection, sender, _path, _interface, method, parameters, invocation):
        if sender != self.owner:
            invocation.return_dbus_error('org.typepaste.Error', 'Only the current KWin helper may reply.')
            return
        with self.lock:
            if method == 'Next':
                if self.closed:
                    invocation.return_value(self.bus.GLib.Variant('(s)', ('',)))
                    return
                if self.next_call:
                    invocation.return_dbus_error('org.typepaste.Error', 'A request is already pending.')
                    return
                self.next_call = invocation
                self._answer_next()
                if not self.next_call:
                    return
                # Keep only this invocation alive; an old timer cannot answer a newer call.
                def idle(*_):
                    with self.lock:
                        if self.next_call is invocation:
                            self.next_call = None
                            self.idle_timer = None
                            invocation.return_value(self.bus.GLib.Variant('(s)', ('wait',)))
                    return False
                timer = self.bus.GLib.timeout_source_new(5000)
                self.idle_timer = timer
                timer.set_callback(idle)
                timer.attach(self.bus.context)
            elif method == 'Report':
                if self.reply and not self.closed:
                    self.reply.accept(sender, *parameters.unpack())
                invocation.return_value(self.bus.GLib.Variant('()', ()))

    def _answer_next(self):
        if self.next_call and self.reply and not self.reply.done.is_set():
            if self.idle_timer:
                self.idle_timer.destroy()
                self.idle_timer = None
            invocation, self.next_call = self.next_call, None
            invocation.return_value(self.bus.GLib.Variant('(s)', (self.reply.nonce,)))

    def get_active_target(self):
        with self.query_lock:
            try:
                if self.closed or self.bus.owner('org.kde.KWin') != self.owner:
                    raise BackendError('KDE focus helper disconnected. Enable Wayland again.')
                if self._locked():
                    raise BackendError('Screen is locked. Nothing was typed.')
                reply = FocusReply(self.owner, uuid.uuid4().hex)
                with self.lock:
                    self.reply = reply
                    self._answer_next()
                if not reply.done.wait(.7) or self.closed:
                    raise BackendError('KDE focus check timed out. Stopped; enable Wayland again.')
                if self._locked():
                    raise BackendError('Screen is locked. Stopped.')
                return reply.target
            except BackendError:
                raise
            except Exception:
                raise BackendError('KDE focus could not be verified. Stopped; enable Wayland again.') from None
            finally:
                with self.lock:
                    if self.reply:
                        self.reply.done.set()  # Late responses cannot revive a timed-out query.
                    self.reply = None

    def close(self):
        with self.lock:
            self.closed = True
            if self.idle_timer:
                self.idle_timer.destroy()
                self.idle_timer = None
            if self.reply:
                self.reply.done.set()
            if self.next_call:
                self.next_call.return_value(self.bus.GLib.Variant('(s)', ('',)))
                self.next_call = None
        if self.script_id is not None:
            try:
                self.bus.call(self.owner, '/Scripting', 'org.kde.kwin.Scripting',
                              'unloadScript', '(s)', (self.name,))
            except Exception:
                pass
            self.script_id = None
        if self.registration:
            self.bus.connection.unregister_object(self.registration)
            self.registration = None
        if self.directory:
            self.directory.cleanup()
            self.directory = None
