# CommonMSCH585 mouse protocol notes

This document records the independently derived wire facts for the five
catalogued EPOMAKER mouse models that load `CommonMSCH585`: IDs 3961, 3303,
3304, 3929, and 3919. The Linux backend implements USB identification, status, eight profiles, raw
button mapping, DPI-level editing and report-rate selection. This is not a
claim of hardware validation. The catalog marks all five
`hardware_verified: false`.

## Model routing

All five models use VID `0x3151`. The catalog PIDs are `0x503a` for IDs 3961,
3304, and 3929, and `0x5043` for IDs 3303 and 3919. PID routing is therefore
ambiguous; a backend must identify the internal device before applying the
model's matrix and DPI limits.

The Mac model modules are `992565be.js`, `866bc238.js`, `d777fc2c.js`,
`471d3b2c.js`, and `68da517f.js`. Their Windows counterparts are
`9d45578e.js`, `40c18e23.js`, `60ed2dbd.js`, `7a3f640b.js`, and `9d67ecdd.js`.
Each module is an otherwise empty subclass containing only `defaultMatrix`.
They all import `CommonMSCH585` from Mac `5d75ced3.js` or Windows
`78e397ff.js`; the implementations are functionally identical apart from
the bundle runtime import.

## 64-byte command layout

The base class sends and receives vendor reports through its common HID
transport. The source allocates 64-byte set reports and parses 64-byte get
responses. The response methods below return the raw response when the
higher-level method does not decode it. Every request/write uses the shared transport’s Bit7 checksum: byte 7 is
255 minus the sum of bytes 0–6 modulo 256. Successful writes settle for
100 ms before readback. USB uses feature reports; the common transport sends
and receives with 10 ms delays.

| Operation | Get | Set | Get response / set payload |
|---|---:|---:|---|
| identity/version | `0x8f` (143) | — | ID is little-endian uint32 at bytes 1–4; USB version is uint16 at bytes 5–6; zero version is unavailable; boot state has no established response bit |
| current profile | `0x82` (130) | `0x02` | profile value at byte 1 |
| all key matrix | `0x81` (129) | `0x01`, `0x00` | get request byte 1 is profile and byte 2 is 1; set-all uses profile at byte 1 and two 56-byte chunks; set-single uses key index at byte 1 and four matrix bytes at 8–11 |
| macro | `0x83` (131) | `0x03` | get request uses slot byte 1 and chunk byte 2; set uses slot byte 1, chunk byte 2, byte 3 length, byte 4 final flag, data at byte 8 |
| DPI levels | `0x90` (144) | `0x10` | request/set byte 1 is level group (values above 7 become 0); byte 2 is current level; byte 3 is count; eight X uint16 values at 8–23, eight Y uint16 values at 24–39, eight RGB triplets at 40–63 |
| report rate | `0x88` (136) | `0x08` | encoded rate at byte 1; values map 125/250/500/1000/2000/4000/8000 Hz to 8/4/2/1/132/130/129 |
| debounce | `0x84` (132) | `0x04` | value at byte 1 |
| 2.4 GHz sleep | `0x86` (134) | `0x06` | little-endian uint16 at bytes 1–2 |
| Bluetooth sleep | `0x87` (135) | `0x07` | little-endian uint16 at bytes 1–2 |
| silent height | `0x91` (145) | `0x11` | value at byte 1 |
| line repair | `0x92` (146) | `0x12` | boolean byte 1 (`1` is enabled) |
| wave repair | `0x93` (147) | `0x13` | boolean byte 1 |
| motion sync | `0x94` (148) | `0x14` | boolean byte 1 |
| aggregate parameters | `0x9f` (159) | `0x1f` | get values begin at byte 8; set fields begin at byte 8 |
| battery | `0x8a` (138) | — | command exists in the base constants; response decoding needs a separate battery-state source check |

The aggregate response decodes profile at byte 8, debounce at 9, scroll-up
time at 10, 2.4 GHz sleep as little-endian bytes 11–12, Bluetooth sleep as
bytes 13–14, encoded report rate at 15, silent height at 16, line/wave/motion
booleans at 17–19, eight encoded report-rate entries at 20–27, FPS-20000 at
28, and button low-latency at 40. The aggregate setter writes the same
fields at those offsets and also accepts an optional byte-40 low-latency
value.

The source adds a vendor sleep after successful writes. A Linux implementation
should preserve that ordering and verify readback before reporting success.

## Catalog-specific limits

The catalog values are descriptive limits, not inferred wire behavior:

| ID | Sensor | Layout | DPI levels / limits | Other catalog data |
|---:|---|---|---|---|
| 3961 | PAW3955 | RongYuan 7 | 6; 50–65000; step 50 | defaults 800, 1600, 3600, 8000, 12000, 40000 |
| 3303 | PAW3311 | RongYuan 9 | 6; 50–12000; step 50 | defaults 800, 1600, 2400, 3200, 5000, 12000 |
| 3304 | PAW3950 | RongYuan 9 | 6; 50–30000; step 50 | catalog default list ends at 42000 despite max 30000; preserve this discrepancy for review |
| 3929 | PAW3395 | RongYuan 7 | 7; 50–30000; step 50 | low-latency value 799; defaults 400, 800, 1200, 1600, 3200, 5600, 26000 |
| 3919 | PAW3315 | RongYuan 7 | 6; 50–32000; step 50 | low-latency 99; DPI step ranges change at 10000 and 16000 |

All five have eight profiles. The 64-byte model matrices were compared byte
for byte across installers and are retained as functional data in
`data/ch585-matrices.json`. Nonzero default slots identify exposed physical
controls; raw button edits reject padding slots. The single-key setter writes
the active profile, so an explicitly requested profile must already be selected.

## HID and identity evidence

Both extracted HID catalogs list usage page `ffff`, usage `2`, interface 2
for PIDs `503a` and `5043`, with maximum report rates 8000 and 1000 Hz respectively.
Linux discovery additionally requires USB bus 3 and a descriptor declaring a
64-byte feature payload on report 0. Bluetooth and receiver routing are not
currently enabled. Bootloader PIDs `503b` and `5044` are excluded.

The shared `whoAmI` path reads the internal ID as little-endian uint32 at byte 1
(macOS main lines 105122–105130). The mouse override reads USB firmware at byte 5,
unlike the keyboard offset of 7. Its `getDeviceIsBoot` method returns a constant
false; the Linux result uses null to avoid inventing a boot-status bit.

Primary local evidence: Mac `5d75ced3.js` / Windows `78e397ff.js`, their five
model modules above, and the common transport in each main bundle. All command
methods use the shared Bit7 checksum encoder. The matrix reply is a raw 64-byte
array, without an echoed opcode. DPI/status replies retain their full raw bytes.

## Linux controls and preservation

```text
epomaker --device /dev/hidrawN status
epomaker --device /dev/hidrawN profile 2
epomaker --device /dev/hidrawN mouse-matrix --profile 2
epomaker --device /dev/hidrawN mouse-key 0 0100f000 --profile 2
epomaker --device /dev/hidrawN get-mouse-dpi --profile 2
epomaker --device /dev/hidrawN mouse-dpi --profile 2 --slot 1 --x 1600 --y 1600 --rgb ff0000
epomaker --device /dev/hidrawN mouse-dpi --profile 2 --current 1
epomaker --device /dev/hidrawN mouse-rate 1000
```

Mouse actions use their own raw four-byte format. Keyboard semantic binding
commands are rejected for mice. The sample `0100f000` is the vendor's left-button
binding; matrix reads expose each slot for inspection.

DPI writes preserve all eight X/Y/RGB entries, including hidden levels and
untouched out-of-range defaults. Reserved header bytes 4–6 are zeroed, matching
the vendor setter; response status bytes are not replayed as request flags.
Only explicitly edited values are validated.
The write sets the catalog level count (six, or seven for EM3 PRO); current/edited
slots must be within that count. Setting both axes to zero disables a stage.
At least one stage must remain enabled; disabling the current stage selects the
first remaining enabled stage, matching the vendor UI behavior.

DPI increments follow the vendor's sensor-aware UI (`3a52dd56.js`): PAW3311 uses
50 below 10000, 100 below 12000, then 200; PAW3395 uses 50 below 26000 then 100;
PAW3315 uses its explicit 50/100/200 ranges. PAW3950/3955 double their 50-unit
step at half the catalog maximum. `dpiDoubleStartValue` is a UI step threshold,
not a wire-unit multiplier. X and Y remain ordinary uint16 DPI values.

The three read/write workflows verify full button matrices, the complete DPI
payload, or the returned rate. A wrong internal ID, wrong product, unsupported
transport, profile mismatch or readback corruption fails explicitly. Physical
hardware behavior is unverified.

## Remaining work

Macro and semantic action editing, lighting writes, sensor/sleep/debounce
writes, battery interpretation, backup/restore, reset, firmware upgrades,
Bluetooth/receiver routing and GUI integration are unfinished. The `lowLatency`
catalog values are preserved as metadata, not interpreted as byte-valued settings.
The PAN1080/PAN1080-8K mouse families require separate protocol implementations.
