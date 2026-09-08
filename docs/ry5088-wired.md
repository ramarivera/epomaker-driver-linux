# Additional wired RY5088 models

The CLI enables four more internal IDs through their supported USB interfaces:

| Model | Internal ID | USB VID:PID | Fn banks | Side lighting | Switch choices |
| --- | --- | --- | --- | --- | --- |
| HE68 Mag | 2465 | 3151:5029 | Windows, Mac | None | Codes 0–5 and 33 |
| KIIBOOM-68C | 2586 | 3151:502d | Windows only | Q layout | Codes 0–5 |
| Epomaker 65 | 2870 | 3151:502d | Windows, Mac | Q layout | Codes 0–5 |
| HE60 Wired | 3691 | 3151:5030 | Windows, Mac | None | Codes 0–5 |

Each supports four normal profiles with four submodes, normal/Fn key mapping,
macros, OS options, main lighting, five custom RGB pictures, magnetic state,
actuation and rapid trigger, DKS/mod-tap/toggle modes, snap pairing/removal,
switch-type selection and [timed USB calibration](calibration.md). Their
firmware-dependent magnetic bounds match the [H60 defaults](ry5088-h60.md).
None declares sleep, debounce, a display, or a model-specific travel override.

Internal firmware ID and USB product must both match the explicit model groups.
Unimplemented siblings sharing a product ID remain rejected. The newly accepted
PIDs `502d` and `5030` still require the actual USB HID descriptor's feature
report 0 with 64 payload bytes and usage page `ffff`, usage `2`.

## Source comparison

The baseline hashes are in [source-releases.json](source-releases.json).
The following modules directly inherit the modern command base
`623d2d52.js` on macOS / `17dc9c62.js` on Windows, with matrix declarations
and no child method overrides:

| Internal ID | macOS child | Windows child |
| --- | --- | --- |
| 2465 | 9a1ffe97.js | edaaf558.js |
| 2586 | c9e3984d.js | 17319deb.js |
| 2870 | abed2600.js | 072be23b.js |
| 3691 | 66d72914.js | 8b45ed1f.js |

The functional catalog fields match across installers. All declared normal/Fn
matrices also match byte for byte. KIIBOOM-68C declares no Fn-Mac matrix; its
inherited base default is retained as research data, but its catalog advertises
only a Windows Fn bank, so Mac Fn reads and writes are rejected. Other models
use their own declared matrices. Snap removal restores the correct model's
normal bindings, not a shared layout guessed from the product ID.

The vendor UI uses its six-entry fallback switch list when `supportedSwitchTypes`
is omitted. KIIBOOM-68C and Epomaker 65 use that fallback; HE60 Wired explicitly
lists the same six names. HE68 Mag additionally lists 冰玉, code 33. Status
reports only the selected model's available names/codes, and numeric selection
is subject to the same model check as a name. See [switch selection](ry5088-he68.md).

## Q-layout side lighting

KIIBOOM-68C and Epomaker 65 have the `Q` side layout, independently of their
`S` main layout. Side writes use opcode `08`; reads use `88`. The side effects
are off, solid, breathing, neon, wave and snake. Wave, snake, breathing and neon
have speed 0–3; solid and off have no speed control. No effect exposes an option
selector. Off has no brightness/RGB/rainbow controls; neon has brightness and
speed but no RGB/rainbow controls. The other effects support RGB and rainbow.

Commands retain normal color flag 7 and rainbow flag 8; side speed is encoded
directly. Writes verify all light-state bytes on readback. Other migrated
magnetic models reject side commands. These constraints come from the identical
`Q` definitions in both main bundles (macOS lines 43302–43312), not from the
wider set of values accepted by the common packet codec.

For example, use `epomaker --device /dev/hidrawN light wave --side --speed 3`.
`status` includes side-light state only for models with that layout.

## Remaining work

Hardware behavior, firmware management, reconnect and
GUI integration remain unfinished. Source equivalence and simulated tests do
not establish physical compatibility or overall parity. See the complete
[model inventory](model-inventory.md) and [migration status](parity.md).

## Schema 7 recovery

[Magnetic backup and restore](he-recovery.md) now covers all migrated
configuration domains, including inactive magnetic fields and all macro slots.
It requires USB and exact firmware versions. Physical hardware verification
and persistent sensor calibration recovery remain outstanding.
