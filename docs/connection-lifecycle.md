# Connection disappearance and reconnect

The control interface refreshes device metadata and connection state while idle.
If the selected command collection disappears or its descriptor/transport changes,
the controller closes the session, invalidates pending vendor-import previews,
cancels live lighting, and stops audio capture and system-information refresh.
It sends no restoration/configuration packets to a vanished device.

A device operation that raises `DeviceUnavailable` also closes the session.
A failed attempt to connect a different device preserves the existing connection;
protocol errors do not by themselves prove a physical disconnect. Each successful
connection receives a new session identity so the UI can discard stale state even
when the same path is selected again.

After reconnecting the cable, waking the device, or switching transport, choose
its available command collection and click Connect. The application does not
replay writes or restart streaming automatically. Device enumeration does not
send HID commands or wake a sleeping keyboard. A sleeping device that remains in
sysfs can still appear connected; reliable sleep/wake telemetry and automatic
resume remain unverified.

Implementation: `src/epomaker_driver/server.py` and `ui/src/main.jsx`.
Regression evidence: `tests/test_connection_lifecycle.py` and
`ui/tests/connection-lifecycle.spec.js`. Simulated disappearance and stale-response
checks are not physical hotplug, suspend, or receiver validation. A removed and
replaced device with identical metadata between polls cannot be distinguished
by metadata polling alone; transport I/O errors remain necessary evidence.
