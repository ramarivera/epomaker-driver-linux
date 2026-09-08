# HE65 Mag (internal model 2376)

HE65 Mag (catalog name `ry5088_fq_x83_soc_8k_002`) has an enabled partial USB
backend at VID/PID `0x3151:0x502f`. It has four profiles, Windows and Mac Fn
banks, magnetic reads/actuation/mode/snap workflows, main lighting, five custom
picture banks, and generic USB sleep controls. The catalog marks
`isSwitchReplaceable: false`, so switch-type writes are deliberately rejected.
Hardware remains unverified.

Mac loader `6f31d22e.js` imports `70ef82d4.js`; Windows loader `d915b681.js`
imports `ea4b1f5f.js`. Both inherit the modern RY5088 base and declare matching
512-byte normal, Windows Fn and Mac Fn arrays:

| Array | SHA-256 |
| --- | --- |
| `defaultMatrix` | `17ab3f0d34a5cad247d4a40e4f593153d03eff23342e312f5372673cbad1773c` |
| `defaultFnMatrix` | `9d494f055b99b54f970292bde77dd6bfa590eea13c1860726b3685d16fc74771` |
| `defaultFnMacMatrix` | `9d494f055b99b54f970292bde77dd6bfa590eea13c1860726b3685d16fc74771` |

The matrix's normal-layer knob actions map volume-up to slot 90, volume-down to
slot 91 and mute to slot 92. Knob bindings are excluded from magnetic-slot
selection and held-macro playback.

The catalog screen is 128×128 RGB565 with 6 MiB memory and five still banks.
The drawing-board formula permits 165 animation frames. Clock synchronization
and language toggle are exposed by the USB display protocol; system-information
display, side lighting and debounce are not advertised. Display pixels, clock
state and language state are excluded from schema 7 configuration backups.

Travel is 0.1–4 mm with step 0.02; deadzone is 0–1 mm with default 0.3 and step
0.02; rapid press/lift are 0.01–2 mm with firmware-precision fallback. Sleep
ranges are 0–64800 seconds for Bluetooth/dongle and 10–64800 for deep Bluetooth.
The [shared old-firmware exceptions](magnetic-protocol.md) take precedence over
catalog maxima. These are catalog and wire limits, not physical verification. USB is the only
supported transport; firmware management, reconnect monitoring and GUI support
remain outside this partial backend.

Evidence: catalog records in `docs/model-inventory.json`, Mac/Windows loaders and
child modules above, and the shared base protocol at
`exports/20260908-epomaker-linux-research/evidence/protocol/623d2d52.js`.

Display transfer uses RGB565 prepare/status `0xa5` and 56-byte payload chunks
under `0x25`. Preparation must receive status byte 1 before any chunks are
sent; there is no pixel readback. The clock command is `0x28`, with a big-endian
year at bytes 8–9 and month/day/hour/minute/second at 10–14. Language toggle
sends `0x27, 1`. Shared-base evidence: pretty lines 314–365, 367–418 and
436–443 respectively.
