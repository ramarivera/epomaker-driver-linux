# CH585 mouse backup and restore

Schema 8 covers the five USB CH585 mice described in [ch585-protocol.md](ch585-protocol.md).
These are independently implemented configuration snapshots, not vendor cloud
profiles, firmware images, or a hardware compatibility guarantee.

```text
epomaker --device /dev/hidrawN backup mouse.json
epomaker --device /dev/hidrawN restore mouse.json --backup before-restore.json
```

Both commands use the existing bounded JSON/profile loader and atomic private
file writer. Backup files have mode 0600. Existing files are preserved unless
`backup --overwrite` is requested; restore's mandatory backup never overwrites.

## Recorded configuration

The document contains exactly these fields:

| Field | Contents |
|---|---|
| `schema_version` | Integer 8 |
| `identity` | Exact internal device ID and USB firmware version |
| `profile` | Original active profile, 0–7 |
| `profiles` | Eight entries in profile order, each with `matrix`, `dpi`, `settings` |
| `macros` | All 50 macro slots, canonical string keys `0`–`49`, each 256 bytes of hex |
| `limitations` | Human-readable exclusions |

Matrices preserve all 16 four-byte slots, including padding, unknown actions and
inactive assignments. DPI records retain all 64 reply bytes for inspection,
including eight X/Y/RGB entries even when a model exposes only six or seven.
Settings are observations taken after selecting each profile. This does not
assume that firmware stores independent copies of every setting per profile;
global settings are expected to appear identically in multiple observations.

Settings include debounce, scroll-up timing, both sleep timers, line/wave
correction, sensor-gated LOD, firmware-gated low latency and raw report-rate
codes. Snapshot validation enforces wire widths rather than ordinary UI ranges,
so a currently out-of-range numeric setting can be preserved. Ordinary editing
commands continue to enforce their UI bounds. Boolean flags must be actual JSON
booleans. Unsupported model settings are rejected, not silently ignored.

## Capture and recovery ordering

Capture temporarily selects all eight profiles and reads their matrices, DPI
and settings. It reads every macro, including unreferenced slots. It checks
identity, firmware and profile consistency and attempts to return to the original
profile even when capture fails. Cleanup failures are reported alongside the
original error.

Restore validates the entire document before device access and requires the
same internal model and exact firmware version. It captures the current state
and saves the mandatory backup before configuration payload writes. Capture's
temporary profile selections can occur before that file is saved.

A complete matrix uses two opcode `01` packets: profile and chunk indices in
the header, 56 data bytes at offset 8, and 48 padding zeros after the final eight
matrix bytes. This is the vendor full-matrix writer. It permits exact restoration
of padding slots that ordinary single-button editing intentionally rejects.

DPI restore sets the request's profile index, zeroes reserved header bytes 4–6
and regenerates the checksum. It compares current/count and all X/Y/RGB bytes;
reply echo/status/checksum bytes are retained in the file but are not replayed
as command flags or required to remain identical. Scalar settings use individual
setters. Macros use the five-chunk full replacement documented in the protocol
notes. Every write is followed by readback, and a final capture compares all
recorded configuration fields.

A failed restore reports the backup path and possible partial state, and attempts
to restore the previously active profile. It does not automatically roll back
configuration data. Restore is not atomic, and a disconnect can leave some
settings changed. No physical device writes were used to validate this feature.

## Exclusions and model gates

Firmware, device calibration, receiver/Bluetooth routing, vendor account/cloud
state and application-local preferences are excluded. Hidden motion-sync/FPS
controls are not part of the supported settings schema. Hardware comparisons
remain outstanding.

All five mouse catalog entries omit `lightLayout` in both supplied installers.
The mouse controller's `getLight` returns immediately without that metadata
(Mac main bundle around lines 115672–115693). Shared opcode `17`/`97` lighting
methods therefore do not establish a vendor lighting feature for these models.
No mouse lighting state is included or written.
