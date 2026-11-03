"""Private session D-Bus connection with a dedicated GLib dispatch thread.

PyGObject is loaded only when the user enables KDE Wayland. No shell commands,
network transport, clipboard access or persistent permission tokens are used.
"""
import threading
import uuid

from .base import BackendError

PORTAL = 'org.freedesktop.portal.Desktop'
PORTAL_PATH = '/org/freedesktop/portal/desktop'
REMOTE = 'org.freedesktop.portal.RemoteDesktop'
REQUEST = 'org.freedesktop.portal.Request'


class GioBus:
    def __init__(self):
        from gi.repository import Gio, GLib
        self.Gio, self.GLib = Gio, GLib
        self.closed = threading.Event()
        self.started = threading.Event()
        self.connection = None
        self.context = GLib.MainContext.new()
        self.loop = GLib.MainLoop.new(self.context, False)
        self.thread = threading.Thread(target=self._run, name='typepaste-dbus', daemon=True)
        self.thread.start()
        if not self.started.wait(3) or self.connection is None:
            self.close()
            raise BackendError('Cannot connect to the desktop session. Close and reopen TypePaste.')

    def _run(self):
        self.context.push_thread_default()
        try:
            address = self.Gio.dbus_address_get_for_bus_sync(self.Gio.BusType.SESSION, None)
            self.connection = self.Gio.DBusConnection.new_for_address_sync(
                address, self.Gio.DBusConnectionFlags.AUTHENTICATION_CLIENT |
                self.Gio.DBusConnectionFlags.MESSAGE_BUS_CONNECTION, None, None)
            self.connection.set_exit_on_close(False)
            self.connection.connect('closed', lambda *_: self.closed.set())
            self.started.set()
            if not self.closed.is_set():
                self.loop.run()
        except Exception:
            self.started.set()
        finally:
            if self.connection and not self.connection.is_closed():
                self.connection.close_sync(None)
            self.closed.set()
            self.context.pop_thread_default()

    def dispatch(self, function):
        """Register callbacks on the dispatch context, never Tk's thread."""
        if threading.current_thread() is self.thread:
            return function()
        done, result = threading.Event(), []
        def invoke(*_):
            try:
                result.append((True, function()))
            except Exception as exc:
                result.append((False, exc))
            finally:
                done.set()
            return False
        source = self.GLib.idle_source_new()
        source.set_callback(invoke)
        source.attach(self.context)
        if not done.wait(2):
            source.destroy()
            raise BackendError('Desktop service did not respond. Try enabling Wayland again.')
        okay, value = result[0]
        if not okay:
            raise value
        return value

    def call(self, destination, path, interface, method, signature='()', args=()):
        if self.closed.is_set():
            raise BackendError('Desktop connection closed. Enable Wayland again.')
        response = self.connection.call_sync(destination, path, interface, method,
            self.GLib.Variant(signature, args), None, self.Gio.DBusCallFlags.NONE, 700, None)
        return response.unpack() if response else ()

    def owner(self, name):
        return self.call('org.freedesktop.DBus', '/org/freedesktop/DBus',
                         'org.freedesktop.DBus', 'GetNameOwner', '(s)', (name,))[0]

    def subscribe(self, destination, path, interface, signal, callback):
        def connect():
            return self.connection.signal_subscribe(destination, interface, signal, path, None,
                self.Gio.DBusSignalFlags.NONE,
                lambda _bus, _sender, _path, _interface, _signal, params: callback(*params.unpack()))
        return self.dispatch(connect)

    def unsubscribe(self, subscription):
        self.connection.signal_unsubscribe(subscription)

    def request(self, method, signature, args, options, cancelled):
        token = 'typepaste_' + uuid.uuid4().hex
        sender = self.connection.get_unique_name()[1:].replace('.', '_')
        path = f'/org/freedesktop/portal/desktop/request/{sender}/{token}'
        response, done = [], threading.Event()
        def receive(code, values):
            response.append((code, values))
            done.set()
        subscription = self.subscribe(PORTAL, path, REQUEST, 'Response', receive)
        options = {key: self.GLib.Variant('s' if isinstance(value, str) else 'u', value)
                   for key, value in options.items()}
        options['handle_token'] = self.GLib.Variant('s', token)
        returned_path = path
        try:
            returned_path = self.call(PORTAL, PORTAL_PATH, REMOTE, method,
                                      signature, (*args, options))[0]
            if returned_path != path:
                raise BackendError('Desktop portal returned an unexpected request. Nothing was enabled.')
            # The permission UI is asynchronous. Cancellation closes the request.
            import time
            deadline = time.monotonic() + 120
            while not done.wait(.1):
                if cancelled.is_set() or self.closed.is_set() or time.monotonic() >= deadline:
                    raise BackendError('Wayland permission cancelled or timed out. Try Enable Wayland again.')
            if cancelled.is_set() or response[0][0] != 0:
                raise BackendError('Keyboard permission was not granted. Use Enable Wayland to try again.')
            return response[0][1]
        finally:
            self.unsubscribe(subscription)
            if not done.is_set() or returned_path != path:
                try:
                    self.call(PORTAL, returned_path, REQUEST, 'Close')
                except Exception:
                    pass

    def close(self):
        self.closed.set()
        try:
            if self.connection and not self.connection.is_closed():
                self.connection.close_sync(None)
        except self.GLib.Error:
            pass  # The connection may have closed concurrently.
        finally:
            self.loop.quit()
