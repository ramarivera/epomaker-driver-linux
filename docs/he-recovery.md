# Magnetic configuration backup and restore

Schema 7 supports the fifteen migrated magnetic models through their USB command
interfaces. It includes all normal profiles and four submodes per profile, each
exposed Fn bank, all 256 macro slots, all supported custom RGB picture banks,
main/side lighting, OS options and automatic selection, model-specific sleep and
debounce settings, and complete magnetic configuration arrays.

```text
epomaker --device /dev/hidrawN backup keyboard.json
epomaker --device /dev/hidrawN restore keyboard.json --backup before-restore.json
```

The target snapshot is validated before opening the device. The model and exact
USB/RF firmware versions must match the connected keyboard. Raw magnetic units
are not translated across firmware versions. Restoration saves the current
configuration to the required new recovery file before writing configuration
payloads. Existing recovery files are never overwritten. Files are saved
atomically with mode 0600 through the shared profile writer.

## Capture and schema

Magnetic reads address the active profile. Capture temporarily selects each
profile, reads its four normal matrices and every applicable magnetic field,
then restores the original profile. These temporary profile-selection commands
are the only capture mutations. Capture runs under the transport's shared lock
and checks the active profile before/after reads. A failure still attempts to
restore the original profile; cleanup failures are reported explicitly.

Each profile entry records the bytes actually observed after selecting that
profile. It does not assert that firmware stores an independent magnetic array
for every profile. Global/shared fields produce identical observations; tests
cover both shared and profile-specific simulated storage. The vendor also
keeps application-local magnetic caches and copies switch types between cached
profiles (macOS main lines 113042–113063). This device backup does not import
those separate application caches.

All ordinary fields are retained, even when their associated mode is inactive:
0, 1, 2, 3, 4, 5, 6, 7, 9 and 10. Field 251 is included only when the firmware
supports top dead zone; field 252 only for migrated switch-replaceable models.
Arrays retain their raw bytes, including unknown switch codes and inactive
parameters. Every macro slot is included, even when no current binding refers
to it. HE60 Lite wired ID 3727 has three picture banks; other migrated magnetic
models have five. IDs 2586 and 2761 expose only a Windows Fn bank.

The JSON contains `identity`, `versions`, the original `profile`, a `profiles`
list of four matrices and raw field arrays each, `fn`, `macros`, `pictures`,
raw `light`, `side_light`, `options` and `sleep` responses, `auto_os`, `debounce`
and `limitations`. Unsupported optional settings must be null. Model, field
set, lengths, response opcodes, profile counts and Fn banks are validated.
Raw values are retained instead of being constrained to the UI's current
slider limits, so existing or older device settings can be backed up losslessly.

## Restore ordering and verification

The implementation writes changed macros, then each profile's normal matrices
and magnetic data. It sets the mode before its parameters, reapplying every
parameter when a mode changes so mode initialization cannot discard saved values. The four stage-major
arrays read through field 10 are transposed into each key's four-byte field-8
write. Changed axis types use separate commits. Unknown raw values are preserved;
restoration does not reinterpret sensor readings as actuation millimeters.

Fn matrices, custom pictures and global settings follow. The sleep response's
hidden fourth word is restored along with its three public timers. This differs
from a normal sleep edit, which preserves the current hidden word. Lighting and
OS writes carry only their established persistent payload bytes, not response
padding. Each domain is read back, and a complete final capture is compared
against the requested configuration before success is returned.

A failed write, readback mismatch or interruption reports that the keyboard may
be partially changed, retains the recovery file, and attempts to return to the
previous active profile. It does not automatically overwrite partially restored
data with the backup. Restoration is serialized, but it is not an atomic device
transaction; physical profile switching or another application can interfere.

## Limits and evidence

Firmware and persistent sensor calibration are not included. Calibration field
254 is live telemetry, not a recoverable configuration array. This feature does
not perform factory reset or firmware flashing. Bluetooth/receiver restoration
and compatibility across firmware versions remain unimplemented. No physical
keyboard round trip has been verified.

Protocol evidence is shared with [magnetic commands](magnetic-protocol.md),
[HE60 Lite](he60-lite-research.md), [H60](ry5088-h60.md), [HE68](ry5088-he68.md),
and the [wired](ry5088-wired.md) / [wireless-capable](ry5088-wireless.md) additions.
The independent Linux schema is implemented in `he_snapshot.py`; raw restoration
and final comparisons are in `he_recovery.py`. Profile-aware simulated tests
exercise all fifteen IDs, all domains, hidden data, recovery-file collisions,
firmware/model mismatch, capture cleanup and restoration failures.
