# Connection disappearance and reconnect

The control interface refreshes device metadata and connection state while idle.
For an open Bluetooth transport it also consumes at most 32 queued reports per
poll under the same lock as configuration transfers. Only recognized status
notifications update telemetry; keyboard input and stale command reports are
discarded without logging. Bluetooth telemetry also sends a status request at
most once every five seconds, under that same lock. USB telemetry sends no
commands. Requests do not wait for a reply or interrupt configuration transfers.
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


## Battery and device reports

For a connected Bluetooth Glyph, the sidebar shows the last received battery
report (only integer values 0–100) and the last reported online/offline state,
with separate report ages. A `0x88` offline notification retains the previous
battery and its original age; it does not turn that value into a new reading.
An absent report, an invalid battery value, or USB transport does not become a
synthetic 100% reading. No charging status is inferred.

These values are the last device reports, distinct from whether the application
still has an open connection. The timestamp is when Linux received a report,
not a device clock. A missing reply leaves the last value and its age intact;
it does not establish a disconnect or create a fresh reading. Request framing
is traced to the vendor macOS bridge, but physical responses remain unverified.

See [battery evidence](releases/glyph-battery-audit.md) and
[receiver applicability](releases/glyph-receiver-audit.md).
