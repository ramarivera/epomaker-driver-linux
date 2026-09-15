# Glyph battery, charging, and online audit

This is a static comparison of the existing Linux transport with the archived
EPOMAKER Windows bundle. No vendor executable, network request, HID write, or
hardware operation was used.

## Evidence

The inspected Windows bundle is
`index.feaf50e4.js`, SHA-256
`72fb76b3c19e013d81e450d5245bc62bb5a275fcf6623530a5a652b9c7182be5`.

Its Bluetooth decoder is `___decodeBtInputData` at byte offset **1,713,630**.
It removes the HID report prefix with `t.slice(1)`, then reads the status byte
at the resulting offset zero:

| Status byte | Vendor state update |
| --- | --- |
| `0x77` (119) | `isOnline: true`, `battery: report byte 1` |
| `0x88` (136) | `isOnline: false`, battery retains its previous value |
| `0x55` (85) | Appends report data to a read buffer; it is not a battery result |
| `0x66` (102) | Decodes a separate vendor notification; it is not a battery result |

The decoder has no charging field or charging status branch. A battery value
is therefore a vendor battery value only when the status byte is `0x77`; the
source does not establish that `100` means charging, nor does it provide a
charger-state bit. The source also does not define `0xff` as a sentinel in
this Bluetooth branch. Linux should preserve the distinction and avoid
inventing charging state.

The vendor UI's `BatteryIcon` formatter is in `8ac3162d.js` at byte offset
**4,016**. It consumes `status ?? battery ?? 0`, treats `-1` as a special
leaf icon, and selects battery icons at thresholds 20, 40, 60, 80, and 100
(with values at or above 100 using the full icon). This proves that the UI
uses the field on a percentage scale; it does not render a numeric percent
suffix or establish charging semantics. The formatter is a visual bucket,
not evidence that every transport's battery value has the same validity.

The Bluetooth class initializes `isOnline` false and `battery` 0, then at
offset **1,711,224** sets USB devices to online with battery 100. Bluetooth
uses a slower read/write cadence (`SEND_TIME=100`, `READ_TIME=200`) and starts
status polling after an initial delay; the recurring interval is five seconds
at offset **1,715,155**. Disconnect handling at the `___eventSubscribe` body
sets Bluetooth online false while retaining the last battery value.

The status poll calls `___write(new Uint8Array([119]))` directly; it does not
go through `sendMsg` or `___encodeCmd`. The native HID wrapper at byte offset
**1,695,159** passes that one-byte payload, the selected output report ID,
the report's `reportCount` (default 64), and the exclusivity flag to the
bridge's `write` method. The bundle does not expose the native bridge's
padding or report framing, so the exact on-wire packet must not be inferred
from the separate command encoder. The response is then received by the
decoder above; the periodic poll is an active status request rather than
passive-only telemetry.

Device discovery emits a newly recognized device as online at offset
**2,009,264**, with its reported battery (defaulting to zero); removal at
offset **2,011,636** sets it offline and destroys its tasks. This is lifecycle
state, not proof that a radio is enabled or that a battery reading is fresh.
The vendor's 2.4 GHz path separately checks status byte fields at offset
**1,705,017**: byte 3 equal to zero means online, byte 5 equal to one means
send-ready, and byte 8 equal to one means RF boot. Those fields apply to the
receiver status response and must not be generalized to Bluetooth.

## Linux mapping

The existing transport decoder in `src/epomaker_driver/transport.py` handles
the same compact Bluetooth status shape: `[6, 0x77, battery]` sets the raw
battery and online true, while `[6, 0x88]` sets online false and keeps the
previous battery. Device public dictionaries expose `battery` and `online`
through `src/epomaker_driver/device.py`; they do not expose charging.

An absent or disconnected device should be represented as offline, with an
unknown battery when no trustworthy reading exists. A stale last battery value
must not be presented as a fresh measurement merely because the device remains
in a list. USB's initialization value of 100 is transport behavior, not a
charging indication.

The vendor UI creates visible device state when discovery emits an add event
and updates it on status notifications. It does not establish a separate
charging indicator for Glyph. The archived source contains no evidence that
online radio state alone should make a battery control visible. Any future UI
should label the transport and freshness where available, show battery only
for a valid status report, and keep charging unavailable unless a distinct
protocol field is captured.

These findings support a percentage-scale battery presentation and online
state for the compact Bluetooth status response. They do not establish
charging, a universal `0xff` sentinel, battery semantics for every receiver
path, or freshness timestamps. Those require additional captured reports or
hardware validation.
