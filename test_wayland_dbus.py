"""Real D-Bus transport against a fake portal on an isolated session bus.

Run with TYPEPASTE_DBUS_TEST=1 dbus-run-session -- python3 -m unittest -v test_wayland_dbus.py.
No real desktop permission prompt, clipboard access or input injection occurs.
"""
import os
import threading
import time
import unittest

from typepaste.backends.base import BackendError
from typepaste.backends.wayland_bus import GioBus, PORTAL, PORTAL_PATH, REMOTE, REQUEST
from typepaste.backends.wayland_portal import PortalKeyboard, SESSION

XML = '''<node><interface name="org.freedesktop.portal.RemoteDesktop">
<method name="CreateSession"><arg type="a{sv}" direction="in"/><arg type="o" direction="out"/></method>
<method name="SelectDevices"><arg type="o" direction="in"/><arg type="a{sv}" direction="in"/><arg type="o" direction="out"/></method>
<method name="Start"><arg type="o" direction="in"/><arg type="s" direction="in"/><arg type="a{sv}" direction="in"/><arg type="o" direction="out"/></method>
<method name="NotifyKeyboardKeysym"><arg type="o" direction="in"/><arg type="a{sv}" direction="in"/>
<arg type="i" direction="in"/><arg type="u" direction="in"/></method>
</interface></node>'''
CLOSE_XML = '<node><interface name="INTERFACE"><method name="Close"/></interface></node>'


@unittest.skipUnless(os.environ.get('TYPEPASTE_DBUS_TEST') == '1', 'isolated D-Bus opt-in required')
class PortalTransportTests(unittest.TestCase):
    def setUp(self):
        # Never replace or request ownership of a real desktop portal.
        self.server = GioBus()
        self.addCleanup(self.server.close)
        names = self.server.call('org.freedesktop.DBus', '/org/freedesktop/DBus',
                                 'org.freedesktop.DBus', 'ListNames')[0]
        if PORTAL in names or 'org.kde.KWin' in names:
            self.fail('Use dbus-run-session: a real desktop service is present.')
        reply = self.server.call('org.freedesktop.DBus', '/org/freedesktop/DBus',
                                 'org.freedesktop.DBus', 'RequestName', '(su)', (PORTAL, 4))
        self.assertEqual(reply, (1,))
        self.events = []
        self.code = 0
        self.respond = True
        self.seen = threading.Event()
        self.nodes = []
        self.registrations = []
        self.register(PORTAL_PATH, XML)
        self.register('/session/test', CLOSE_XML.replace('INTERFACE', SESSION))
        self.client = GioBus()
        self.addCleanup(self.client.close)
        self.keyboard = PortalKeyboard(self.client)
        self.addCleanup(self.keyboard.close)

    def register(self, path, xml):
        node = self.server.Gio.DBusNodeInfo.new_for_xml(xml)
        self.nodes.append(node)
        self.registrations.append(self.server.dispatch(lambda: self.server.connection.register_object(
            path, node.interfaces[0], self.method, None, None)))

    def method(self, connection, sender, path, interface, method, parameters, invocation):
        args = parameters.unpack()
        self.events.append((method, path, args))
        if method in ('Close', 'NotifyKeyboardKeysym'):
            invocation.return_value(self.server.GLib.Variant('()', ()))
            return
        options = args[-1]
        request = f"/org/freedesktop/portal/desktop/request/{sender[1:].replace('.', '_')}/{options['handle_token']}"
        self.register(request, CLOSE_XML.replace('INTERFACE', REQUEST))
        result = {}
        if method == 'CreateSession':
            result = {'session_handle': self.server.GLib.Variant('s', '/session/test')}
        elif method == 'Start':
            result = {'devices': self.server.GLib.Variant('u', 1)}
        # Deliberately send the signal before replying to the method.
        if self.respond:
            connection.emit_signal(sender, request, REQUEST, 'Response',
                                   self.server.GLib.Variant('(ua{sv})', (self.code, result)))
        invocation.return_value(self.server.GLib.Variant('(o)', (request,)))
        self.seen.set()

    def test_early_response_real_variants_and_revocation(self):
        self.keyboard.start(threading.Event())
        self.assertTrue(self.keyboard.ready)
        self.keyboard.send('🙂')
        selections = [e for e in self.events if e[0] == 'SelectDevices']
        self.assertEqual(selections[0][2][-1]['types'], 1)
        self.assertEqual(selections[0][2][-1]['persist_mode'], 0)
        keys = [e[2][-2:] for e in self.events if e[0] == 'NotifyKeyboardKeysym']
        self.assertEqual(keys, [(0x101f642, 1), (0x101f642, 0)])
        self.server.connection.emit_signal(None, '/session/test', SESSION, 'Closed',
                                          self.server.GLib.Variant('(a{sv})', ({},)))
        deadline = time.monotonic() + 2
        while self.keyboard.ready and time.monotonic() < deadline:
            time.sleep(.01)
        self.assertFalse(self.keyboard.ready)
        with self.assertRaises(BackendError):
            self.keyboard.send('x')

    def test_denied_request(self):
        self.code = 1
        with self.assertRaisesRegex(BackendError, 'not granted'):
            self.keyboard.start(threading.Event())
        self.assertFalse(self.keyboard.ready)

    def test_cancelled_pending_request_is_closed(self):
        self.respond = False
        cancelled = threading.Event()
        errors = []
        def start():
            try:
                self.keyboard.start(cancelled)
            except BackendError as exc:
                errors.append(str(exc))
        worker = threading.Thread(target=start)
        worker.start()
        self.assertTrue(self.seen.wait(2))
        cancelled.set()
        worker.join(2)
        self.assertFalse(worker.is_alive())
        self.assertEqual(len(errors), 1)
        self.assertTrue(any(e[0] == 'Close' and '/request/' in e[1] for e in self.events))


if __name__ == '__main__':
    unittest.main()
