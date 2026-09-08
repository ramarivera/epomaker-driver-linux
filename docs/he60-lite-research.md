# HE60 Lite variants: migration evidence

These findings come from the two installers in
[source-releases.json](source-releases.json). Both catalog entries have the
same display name but must be selected by internal identity and USB metadata.
Both now have partial USB backend support; neither has hardware validation.

The CLI supports identity/status, two normal profiles with submodes 0–3,
one Fn layer for each of Windows and Mac, raw/semantic macro reads and writes,
active profile selection, magnetic-parameter reads and actuation/rapid-trigger
updates, OS options, automatic OS selection and main lighting/custom pictures.
Wired 3727 additionally exposes debounce; wireless 3759 exposes three sleep
timers. `--profile` selects a
normal profile; for `--fn` it must be 0, and `--os-mode` selects Windows (0) or
Mac (1). Fn commands do not accept a nonzero submode. For example, after
selecting the actual command collection from `epomaker discover`:

```sh
epomaker --device /dev/hidrawN matrix --profile 1 --submode 3
epomaker --device /dev/hidrawN matrix --fn --os-mode 1
epomaker --device /dev/hidrawN get-magnetic
```

Magnetic reads describe the current profile and retain raw field bytes and
unknown mode values. These reads are not a complete restorable backup.
[Timed USB calibration](calibration.md) now provides start/stop sequencing, raw
telemetry and cleanup. Recovery and firmware upgrades remain outside the gate.

## Actuation and rapid-trigger updates

`magnetic-key` patches one physical matrix slot in the current device state:

```sh
epomaker --device /dev/hidrawN magnetic-key 9 --travel 1.2 --deadzone 0.3
epomaker --device /dev/hidrawN magnetic-key 9 --fire --rapid-press 0.2 --rapid-lift 0.2
epomaker --device /dev/hidrawN magnetic-key 9 --no-fire
```

Travel, lift, dead zone and top dead zone may be changed for an existing normal
or snap-mode key. Rapid-trigger thresholds and `--fire`/`--no-fire` apply to
every recognized existing mode and preserve its lower seven mode bits. This
command does not convert the key to another base mode or change a snap partner.
Unknown mode values are readable but are rejected for writes.

All numeric inputs use 0.1 mm steps. The UI setters, rather than just the static
catalog, establish these bounds:

| Setting | Allowed range |
| --- | --- |
| Travel | 0.1–3.3 mm; nonzero main firmware below `0300` uses a 4 mm maximum |
| Lift | At least 0.1 mm and at most the travel maximum minus the resulting dead zone |
| Dead zone | 0–1 mm; main firmware below `0300`, including unavailable version, allows 0–4 mm |
| Top dead zone | 0–1 mm, only when USB or RF firmware is at least `0400` |
| Rapid press/lift | 0.1–2 mm, requiring rapid trigger to be enabled after the patch |

The main UI version is RF when present, otherwise USB, otherwise zero. Evidence
is in macOS main pretty lines 105586–105589 (`getMainControlVersion`),
107169–107180 (selected travel maximum), 107725–107915 (limits and steps),
108098–108151 (press/lift setters). The static catalog's travel minimum of zero
does not override the UI setter's 0.1 mm minimum. The wire multiplier remains
the independently documented 10/100/200 conversion; it is not the input step.

`src/epomaker_driver/he_settings.py` validates the patch and plans commands from
raw field bytes. Omitted values and other slots are preserved. Before enabling
rapid trigger, the backend reads inactive thresholds; invalid stored values
must be replaced explicitly with valid `--rapid-press` and `--rapid-lift` values.
A no-op emits no write. Mode updates precede changed parameters and only the
last command carries the commit bit. `src/epomaker_driver/he.py` checks the
profile before writing, reads back complete involved field arrays, and detects
profile changes, lost writes or modifications to neighboring slots. A failed
transfer can leave partial state; this is not an atomic hardware transaction.

| Fact | Internal ID 3759 | Internal ID 3727 |
| --- | --- | --- |
| Catalog name | `yc3123_hf_k1_v2_3m_1k_1k` | `yc3121_hf_k1_1m_1k` |
| USB vendor/product | `3151:502e` | `3151:502c` |
| Normal profiles | 2 | 2 |
| Fn catalog | one Windows, one Mac | one Windows, one Mac |
| Magnetic flag | true | true |
| macOS model chunk | `83b9b413.js` | `a2674888.js` |
| Windows model chunk | `96bb6751.js` | `fd9b8328.js` |
| macOS immediate parent | `2cea305b.js` | `95b381df.js` |
| Windows immediate parent | `c6c9152c.js` | `d249f8ae.js` |

Each model chunk pair is identical after imported chunk filenames are normalized.
The `95b381df.js` / `d249f8ae.js` parent pair also matches under that normalization.
It inherits the modern keyboard base (`623d2d52.js` / `17dc9c62.js`) and overrides
only firmware upgrading. The YC3121 name on ID 3727 therefore must not route it
to the older RT100/CommonKbYc500 implementation. Its upgrade override calls the
USB upgrader with allocation argument 65536 and retry argument 10; this is not
sufficient evidence to enable firmware writes.

Both catalogs specify travel 0–3.3 mm in 0.1 mm increments, rapid-trigger press
and lift travel 0.1–2 mm in 0.1 mm increments, and dead zone 0–1 mm in 0.1 mm
increments. Only 3727 advertises the debounce control. The wireless 3759 entry
exposes ordinary Bluetooth/receiver sleep and Bluetooth deep sleep, all
60–3600 seconds; receiver deep sleep is absent. The wired 3727 entry has no
sleep controls. Do not infer these capabilities from shared base methods.

## Firmware-dependent magnetic encoding

The modern base's `get磁轴行程步进倍数` (macOS pretty module lines 129–139) selects
RF version when truthy, otherwise USB version. The travel multiplier is 10
below `0300`, 100 from `0300` through `04ff`, and 200 from `0500` onward; absent
version defaults to 10. The advertised UI increment is not itself the wire
multiplier. Top dead zone is gated separately: either RF or USB version at
least `0400` enables it (lines 124–128).

`setMagnetismInfoSimple` selects fields for each key and delegates to
`_sendMagnetismInfoSimpleCMD`. Its field IDs include press travel 0, lift travel
1, rapid-trigger press/lift 2/3, dynamic travel 4, MT time 5, dead zone 6,
mode/rapid-trigger option 7, trigger modes 8, and top dead zone 251. The mode
write may precede field writes, with the final write carrying commit state.
A Linux implementation needs the complete read/modify/write encoding and
firmware-version queries before exposing these controls; this list alone is
not a ready-to-send packet specification.

The independent `src/epomaker_driver/versions.py` codec now covers the modern
version queries. USB uses `8f` with a little-endian uint16 at reply offsets 7–8;
RF uses `80` at offsets 1–2. MLED uses `ae` at offsets 1–2. OLED uses `ad`, with
OLED version at offsets 1–2 and flash version at 3–4. Zero is unavailable,
independently for each component. Requests have the normal checksum at offset
7 and are padded to 64 bytes. This follows macOS `623d2d52.js` lines 150–189
and the matching Windows `17dc9c62.js` methods. These offsets are not the old
YC3121 version protocol. The HE60 backend uses the USB query for both models
and the RF query for wireless model 3759; MLED/OLED queries remain codec-only.

Both installers' HID filters agree on USB products `502c` and `502e`: vendor
`3151`, interface number 2, usage page `ffff`, usage 2. The filter records do
not contain physical report descriptors; Linux discovery additionally
requires report ID 0 with a 64-byte feature payload. Both lighting layouts
omit side lighting. The complete layouts (`S` for 3759, `ce` on Mac / `ue` on
Windows for 3727) establish the controls documented below.

Normal keymap addressing uses the modern base: `8a` reads profile at byte 1,
`ff` at byte 2, page at byte 3 and submode at byte 4. Single-key `0a` writes
profile at byte 1, slot at byte 2, commit at byte 5 and submode at byte 6, with
four action bytes beginning at byte 8 (lines 752–790). Migration must preserve
magnetic submodes instead of treating the default submode as the complete
keyboard configuration.

The macOS main bundle's `___获取所有按键信息` (pretty lines 113019–113036)
reads four submodes, numbered 0–3, for every normal profile when the magnetic
flag exists. For either HE60 Lite that means eight 512-byte normal matrices,
not two. Magnetic parameter reads have no profile selector in their `e5`
headers, while the application caches magnetic settings by profile and can
restore cached values on switching. A future backup must distinguish the
device's currently readable magnetic state from application-managed profiles;
it must not invent per-profile wire storage from the catalog layer count.

Remaining evidence work includes physical USB command descriptors, magnetic
calibration results, recovery and hardware comparisons.


## Everyday controls and lighting

Both models use modern OS options (`09` / `89`) and automatic OS selection
(`17` / `97`). Partial OS-option updates preserve unrelated bytes and compare
readback. Wired 3727 exposes debounce (`06` / `86`) from 1 through 10 ms.
The UI chunk `7cdd7654.js` selects default slider bounds 1 and 10 when
`deBounceUI` is absent, as it is for this catalog entry. Wireless 3759 rejects
debounce commands. Its three public sleep timers use `11` / `91`, each from
60 through 3600 seconds; the fourth, hidden uint16 at offsets 14–15 is preserved
and verified, even when outside public bounds. Wired 3727 rejects sleep commands.

Both main-light layouts expose 21 effects: wave, ripple, raindrop, snake,
reactive, convergence, sine, kaleidoscope, reactive-off, line-wave, laser,
circle-wave, dazzling, rain, meteor, solid, breathing, neon, picture, music
and screen. Neither exposes side lighting or an explicit off effect.
Adjustable speed is 0–4 on both models, encoded as `4 - speed`. Solid,
picture, music and screen have no speed control. Neon, picture and screen
have no RGB/rainbow selector. Wave has four direction options; snake,
kaleidoscope, line-wave and circle-wave have two; music has three options.
The public backend rejects controls absent from these layouts.

The meaningful layout difference is custom-picture selection: wired 3727 has
three banks (0–2), wireless 3759 has five (0–4). Each bank reads six raw
64-byte pages with `8c`; only 126 RGB slots (378 bytes) are writable using
seven `0c` chunks. The final six read bytes remain reserved. Whole-picture
and individual-slot edits verify complete writable-picture readback.

Evidence: both installer main bundles, pretty lines 42302–42386 (`S`) and
42554–42638 (`ce` / `ue`), match after the declaration name is normalized.
Modern base `623d2d52.js` / `17dc9c62.js` supplies picture methods and lighting
encoding; neither model nor its immediate parent overrides `MAXSPEED`,
`NORMAL` or `DAZZLE`. These facts supersede the earlier unverified suggestion
that the two HE layouts might differ in speed range. Implementation lives in
`src/epomaker_driver/he.py` and `src/epomaker_driver/he_lighting.py`.

```sh
epomaker --device /dev/hidrawN options --system mac
epomaker --device /dev/hidrawN auto-os on
epomaker --device /dev/hidrawN light wave --speed 2 --rgb 123456
# Wired 3727 only:
epomaker --device /dev/hidrawN debounce 5
# Wireless 3759 only:
epomaker --device /dev/hidrawN sleep 600 600 1200
```

Selecting music or screen lighting sets the device effect; it does not implement
continuous host audio/screen sampling. All validation remains simulated, with
no physical HE60 reports captured or writes attempted.


## Magnetic modes and action bindings

`magnetic-mode SLOT PATH` installs a complete mode definition from JSON in the
current profile. It supports normal, DKS, MT, toggle hold and toggle dots on
both HE60 variants. Actions are four-byte hex bindings, using the same format
as the existing `key` command. The definition must explicitly supply the
mode's action slots and parameters:

| Mode | `actions` order | Required parameters |
| --- | --- | --- |
| `normal` | One normal action | `travel`, `lift`, `deadzone`; same version limits as actuation updates |
| `dks` | Four actions, submodes 0–3 | `dynamic_travel` 0.5–2.5 mm in 0.01 mm steps; `trigger_modes` four bytes |
| `mt` | Hold, then tap | `mt_time` 10–1000 ms, integer |
| `tgl_hold` | One toggle action | None |
| `tgl_dots` | One toggle action | None |

Optional `fire`, `rapid_press` and `rapid_lift` use the existing rapid-trigger
rules. Omitted rapid-trigger state is preserved; enabled thresholds must be
valid or explicitly replaced. Normal mode also accepts `top_deadzone` on
supported firmware. Definitions reject unknown fields, invalid actions, and
unsupported parameter combinations before writes. Existing snap and unknown
modes cannot be replaced by this command, because pairing cleanup uses the dedicated `snap-clear` operation.

For example, save this as `tap-hold.json`, then run
`epomaker --device /dev/hidrawN magnetic-mode 5 tap-hold.json`:

```json
{"mode":"mt","actions":["01000000","00000400"],"mt_time":200}
```

This assigns the first action to hold and the second to tap. A DKS definition
contains four bindings and four packed trigger bytes, for example:

```json
{"mode":"dks","actions":["00000400","00000500","00000600","00000700"],"dynamic_travel":0.71,"trigger_modes":[1,4,16,64]}
```

Each trigger byte packs four two-bit cells in increasing bit order. The raw
bytes retain the vendor representation; the vendor UI also uses linked spans
across cells. See [magnetic protocol](magnetic-protocol.md) for wire layout.

MT accepts the UI's 1 ms increments, but the vendor truncates `ms / 10` into
one byte: 201 ms writes 20 and reads back as 200 ms. DKS travel uses the existing
firmware multiplier and truncation, so old firmware may also quantize its
finer UI steps. The backend compares encoded bytes, not the unquantized input.

All four normal matrices are read before writes and compared afterwards,
including unused submodes and neighboring keys. It also preserves and verifies
complete magnetic fields read for the operation. The active profile is checked
before writing and after readback. No-op definitions emit no write. A failure
can leave partial state: action and magnetic groups have separate commits.
This command is not a factory reset and does not clear unused submodes.

Evidence: main pretty lines 108836–108846 define DKS bounds; macOS UI chunk
`7cdd7654.js` and Windows `3189ee15.js` supply its 0.01 slider step. Main lines
108998–109010 establish MT bounds and 1 ms UI step; the modern base's simple
field-5 writer divides by 10. The implementation is
`src/epomaker_driver/he_modes.py` plus `HEKeyboard.set_magnetic_mode` in
`src/epomaker_driver/he.py`. Tests exercise simulated USB reports, not hardware.


## Snap pairing and removal

```sh
epomaker --device /dev/hidrawN snap 9 21
epomaker --device /dev/hidrawN snap-clear 9
```

These are physical matrix slots: 9 is A and 21 is D on both HE60 layouts.
Only nonempty physical slots are accepted. Padding and the Fn slot (77) are
rejected, as are equal slots, unknown modes, keys already bound to a different
partner, and inconsistent references from another snap key.

Pairing writes mode field 7 for the first and second key, then reciprocal
field-9 links. Only the fourth magnetic command commits. Each mode byte retains
its key's rapid-trigger bit. Normal keys retain their current mappings. DKS,
MT and toggle keys first regain their default ordinary action at submode 0;
submodes 1–3 are cleared. Other keys, the other normal profile and Fn layers
are unchanged. Pairing an already reciprocal pair is a no-op.

`snap-clear` checks both sides of the relationship before changing anything.
It restores both ordinary action bindings, clears both keys' extra submodes,
and switches both mode bytes to normal while retaining each rapid-trigger bit.
Travel and other magnetic parameters are preserved, as are inactive field-9
bytes. A clear on an unpaired physical key is a no-op. This operation removes
the pair; it is not a factory reset or a repair tool for inconsistent firmware
state. `magnetic-key` can change the retained actuation parameters afterwards.

Both operations read all four normal matrices and the involved complete
magnetic fields, compare readback including neighboring keys, and check the
active profile before writes and after readback. A failed transfer can leave
partial state; subsequent operations reject a broken reciprocal relationship.
No hardware writes have been performed during development.

Packet evidence is the modern base's `setSnapKeySimple`, macOS
`623d2d52.js` pretty lines 1466–1482, matching Windows `17dc9c62.js`.
The main bundle's lines 113632–113682 restore advanced-key mappings before
pairing. `resetSnapKey` at 105706–105714 selects both keys for restoration;
113837–113862 restore the ordinary mapping and clear all extra submodes.
The Linux clear uses the existing simple mode writer instead of overwriting
unrelated slots through the vendor's bulk write path.

`src/epomaker_driver/he_snap.py` implements these operations. Default bindings
are functional data in `src/epomaker_driver/data/he60-matrices.json`, extracted
from and compared across both installers. Each normal/Fn matrix is 512 bytes;
the normal matrix has 61 nonempty slots including Fn. Both models share the
normal matrix but differ in Fn matrices.

The wireless model declares `defaultFnMACMatrix` with uppercase `MAC`, while
the runtime reads `defaultFnMacMatrix`. Its effective Mac Fn default therefore
comes from the modern base's inherited `Z` array. The data preserves both the
declared uppercase matrix and the effective lowercase matrix. Wired 3727
declares the correctly cased property. This is an installer discrepancy, not
a Linux decision to substitute one layout for another.
