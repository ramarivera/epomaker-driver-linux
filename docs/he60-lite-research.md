# HE60 Lite variants: migration evidence

These findings come from the two installers in
[source-releases.json](source-releases.json). Both catalog entries have the
same display name but must be selected by internal identity and USB metadata.
Both now have partial USB backend support; neither has hardware validation.

The CLI supports identity/status, two normal profiles with submodes 0–3,
one Fn layer for each of Windows and Mac, raw/semantic macro reads and writes,
active profile selection, magnetic-parameter reads and actuation/rapid-trigger
updates. `--profile` selects a
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
Magnetic mode switching, dynamic/MT edits, snap pairing, calibration,
lighting/settings, recovery and firmware upgrades remain outside this backend's
current operation gate.

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
omit side lighting, but 3759 references `S` and 3727 references `ce`; shared
base inheritance is insufficient to assume identical speed controls.

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

Remaining evidence work includes physical USB command descriptors, complete
model-specific lighting layouts, magnetic setting integration,
calibration and dynamic-action semantics, and hardware comparisons.
