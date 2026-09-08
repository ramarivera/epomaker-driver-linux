# Wireless-capable RY5088 models over USB

Four additional models use the supported USB interface `3151:5030`. Their
Bluetooth and receiver connections remain unimplemented.

| Model | Internal ID | Fn banks | Side lighting | Switch codes |
| --- | --- | --- | --- | --- |
| HE60 Wireless | 3692 | Windows, Mac | None | 0–5 |
| G84 HE JIS | 3703 | Windows, Mac | Q | 0–5 |
| HE68 Lite 3M | 2761 | Windows only | None | 0–5, 33 |
| G84 HE | 2959 | Windows, Mac | Q | 0–5 |

The CLI provides four profiles with four normal submodes, Fn mapping, macros,
OS options, main lighting, five custom RGB pictures, magnetic state and actuation,
rapid trigger, DKS/mod-tap/toggle modes, snap pairing/removal, switch selection,
and [timed USB calibration](calibration.md). Firmware-dependent magnetic bounds
follow the [H60 defaults](ry5088-h60.md). The Q side effects use the constraints
documented for the [additional wired models](ry5088-wired.md).

## Sleep and RF firmware

Three sleep timers are exposed: Bluetooth and receiver idle time are 0–64800
seconds, and Bluetooth deep sleep is 10–64800 seconds. For example:
`epomaker --device /dev/hidrawN sleep 300 300 600`.

The inherited wire commands read with `91` and write with `11`. Four little-endian
16-bit words occupy bytes 8–15, but the model catalogs omit `sleep24.deep`.
The CLI therefore preserves the hidden fourth word at bytes 14–15 and verifies
all three requested values plus that hidden word after writing. It rejects a
fourth public argument. HE60 Lite ID 3759 retains its separate 60–3600 bounds.

RF firmware version uses `80` over the active USB transport. Both `status` and
magnetic reads query it. Magnetic scaling uses the RF version when available,
falling back to USB when RF is missing; firmware versions also select the
supported actuation increments and top-dead-zone field. The vendor's device
initialization requests RF version before its separate receiver-only queries
(macOS main lines 117468–117487; Windows lines 116380–116399).

The Linux codec scales decimal values exactly before truncating fractional wire
units. This deliberately avoids the vendor base’s binary-floating-point artifact:
its multiplication and bitwise conversion can encode 2.01 mm as 200 rather than
201 units at multiplier 100. Valid UI increments retain their requested value in
Linux; nonintegral wire units still truncate. This applies to every magnetic
travel field, including the one-byte top dead zone.

## Source evidence

Baseline hashes are in [source-releases.json](source-releases.json). Each model
directly inherits the modern base `623d2d52.js` on macOS / `17dc9c62.js` on Windows
and declares matrices without method overrides:

| ID | macOS child | Windows child |
| --- | --- | --- |
| 3692 | bf16d6e2.js | dcf3221c.js |
| 3703 | bef100cb.js | 2b9202b4.js |
| 2761 | 378242d7.js | 1e042e9e.js |
| 2959 | 5891d33a.js | 2ab2a55a.js |

All declared matrices match byte for byte across installers. HE68 Lite 3M
declares no Mac Fn matrix; its inherited base matrix is retained as research
data, while Mac Fn reads/writes are rejected by its Windows-only catalog gate.
G84 HE JIS retains its Japanese layout and its own default bindings. Snap removal
uses each model's defaults. Tests pin extracted matrix hashes independently of
the backend gates.

Sleep controls follow catalog `other.sleepBT` and `other.sleep24`; the UI tests
for `sleep24.deep` explicitly (macOS main lines 111729–111734). G84 HE omits
`supportedSwitchTypes` and uses the vendor UI's six-name fallback.

## Verification limits

Simulated USB tests cover model/PID identity, profile/submode addressing, Fn
gates, switch choices, RF-dependent precision, sleep limits and readback,
side-lighting packets, snap default restoration and calibration dispatch.
No physical device comparison has been completed. Recovery, firmware management,
wireless transports, reconnect and GUI integration remain unfinished. These
models count as partial backends in the [full inventory](model-inventory.md).
