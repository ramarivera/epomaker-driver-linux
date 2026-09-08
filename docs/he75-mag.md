# HE75 Mag (internal model 2520)

HE75 Mag (catalog name `ry5088_x87a_he75mag_8k_8k_002`) has an enabled partial
USB backend at VID/PID `0x3151:0x502f`. It has four profiles, magnetic keys,
main lighting, replaceable switches, and an explicit Windows Fn layer. The
catalog exposes no Mac Fn layer, side lighting, or knobs. Hardware remains
unverified.

Mac loader `6f31d22e.js` imports `f1e42ed8.js`; Windows loader `d915b681.js`
imports `7e630160.js`. Both child modules inherit the modern RY5088 base and
contain matching 512-byte arrays:

| Array | SHA-256 |
| --- | --- |
| `defaultMatrix` | `0ad2185b921b3e8aec91873426f1af38c60e82e49a2be5c3ae8f736808590ffb` |
| `defaultFnMatrix` | `1270f37cf7ffcbd3773454547d7013d346dec66ff0486ba11a604867a8f4e9c7` |

Neither child declares `defaultFnMacMatrix`; Mac Fn behavior is not established
by the model data.

The canonical switch gate has seven names and codes: `磁白轴` 8, `高特` 0,
`磁玉` 1, `磁玉pro` 2, `磁玉gaming` 3, `天王` 4, and `万磁王` 5. The backend
supports magnetic reads, actuation and mode/snap workflows, main lighting,
profiles, keymaps, macros, OS controls, calibration, and schema 7 raw recovery.
Recovery preserves inactive magnetic fields and other raw configuration subject
to exact identity and firmware matching.

Catalog UI bounds are travel 0.1–4 mm with step 0.02, bottom deadzone 0–1 mm
with step 0.02 and default 0.3, and rapid press/lift 0.01–2 mm. The rapid
fields omit a catalog step; the vendor UI falls back to active RF/USB precision:
0.1 below firmware `0x0300`, 0.01 at `0x0300`, and 0.005 at `0x0500`. For
old effective firmware below `0x0300`, the shared UI's maximum 4 mm rule for
travel and bottom deadzone takes precedence over catalog maxima; newer firmware
uses the catalog maxima. Normal 24G and Bluetooth sleep timers are 0–64800
seconds, with deep Bluetooth 10–64800 seconds. These are source/UI and wire
limits, not hardware verification.

No side-light, knob, receiver, firmware-management, GUI, or physical-device
support is claimed for this model. USB is the supported transport.

Evidence: Mac/Windows catalog records and model blocks at
`mac-main.pretty.js:45853` / `win-main.pretty.js:45853`; child modules
`evidence/models/f1e42ed8.js` and `/tmp/epomaker-analysis/win-app/resources/app/dist/js/7e630160.js`;
shared UI precision and old-firmware bounds at macOS main UI lines
`107677–107859`; the Windows bundle carries equivalent shared logic.
