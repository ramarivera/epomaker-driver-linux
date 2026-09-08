# 2.4 GHz receiver adapter

`epomaker_driver.receiver` implements the shared feature-report routing sequence
recovered from both installers. It is an internal adapter, **not enabled by automatic
HID discovery**. No physical receiver descriptor or transport round trip has yet been
verified. This does not add a hardware support claim to any catalog entry.

## Wire sequence

The Mac application `yM` class (pretty research copy, lines 104513–104812) and the
Windows equivalent (lines 103429 onward) implement the same routing:

1. Before sending, poll raw F7 status up to five times, waiting 100 ms before each
   poll plus 10 ms before the feature write and 10 ms before reading its response.
2. When send-ready, send raw `F6 0A` for keyboard or `F6 05` for mouse if the selected
   destination changed. Wait 10 ms before selection and 10 ms afterward, followed
   by the requested device-command delay.
3. Send the device command with its existing checksum. Never checksum the routing
   messages as though they were device commands.
4. Before reading, poll F7 for read-ready with the same bounded sequence. Send raw
   FC, wait 10 ms, and fetch the device response. An optional expected opcode rejects
   mismatched command responses; raw matrix responses can omit that check.

Status bytes describe readability (0 equals 1), keyboard and mouse batteries (1/2),
online state (3/4 equal zero), send readiness (5 equals 1), paired-device mask
(6: none/keyboard/mouse/both = 0/1/2/3), and RF bootloader state (8 equals 1).
Absent devices have unknown battery, and stale state is not reported as online.
The adapter rejects bootloader mode and never sends a device command while offline.

The implementation additionally applies a readiness deadline and invalidates cached
routing after a failed endpoint operation. It never automatically resends a device
command after a read timeout. Linux feature ioctls themselves remain kernel calls;
the deadline bounds readiness sleeps and polling, not an in-flight kernel ioctl.

## Ownership and integration

A `ReceiverBus` owns one verified I/O handle, feature report ID, and reentrant lock.
`bus.endpoint("keyboard")` and `bus.endpoint("mouse")` share that lock and destination
state. Multi-page driver transactions cannot be interrupted by a different logical
endpoint changing the selected destination. Closing an endpoint leaves its sibling
usable; closing the bus closes the physical handle. The owning integration must close
the bus. Serialization applies within this process, not across unrelated applications.

The injected I/O interface is `set_feature(report_id + 64-byte payload)`,
`get_feature(report_id, 64)` returning a normalized payload, and `close()`, matching
`HidrawIO`. Do not construct it with an arbitrary node or add a guessed VID/PID to
`discovery.py`. Future integration must verify a receiver's actual report descriptor
and opened-device identity, route an identity query, gate the identified model, and
manage the bus lifetime separately from endpoint lifetime.

The recovered FE send-length helper is not called by this normal 64-byte command
path. F1 receiver identification is restricted to a separate vendor allowlist.
Neither helper is injected into ordinary traffic speculatively. Receiver firmware
upgrades, pairing management and background device monitoring remain separate work.

## Verification

`tests/test_receiver.py` checks raw routing bytes, request order, destination changes,
full Glyph keymap operations, all paired-device masks, readiness retries/deadlines,
malformed responses, bootloader refusal, endpoint/bus lifetime, nonzero report IDs,
and concurrent multi-page transactions. Its fake wire routes actual independently
authored device packets through the existing simulated firmware. These tests prove
software behavior under that model; they do not verify physical radio behavior.
