# Per-key RGB slots and dynamic lighting records

This static audit separates keyboard-resident RGB slots from the application's
saved dynamic-lighting records. They are also separate from OLED screen assets.
It does not establish hardware behavior or complete dynamic-editor applicability
to Glyph. Source hashes match `docs/releases/glyph-account-boundary-audit.md`.

Verified UTF-8 byte offsets in the pinned main bundles:

| Declaration | Windows | macOS |
| --- | ---: | ---: |
| `createState_灯效编辑` | 1493864 | 1502676 |
| `readSeletedCustomizationLayer` | 1494221 | 1503033 |
| `writeSelectedCustomizationLayer` | 1494631 | 1503443 |
| `checkLightEdit` | 1938124 | 1946936 |
| `getLightPic` call | 1938295 | 1947107 |
| `setLightPic` call | 1939114 | 1947926 |
| `ai_light_effects_local_db` | 2393666 | 2402509 |

The ordinary `LightUserPicture` workflow selects a keyboard-resident layer and
reads/writes RGB triplets through the device protocol. Linux already exposes
those banks in `ui/src/custom-pattern.jsx`. Its `epomaker-glyph-pattern` JSON is
an independent interchange format; this audit establishes no vendor file format
for those static slots.

The separate dynamic-lighting database uses object store `ai_light_effects`.
Windows record builder `Tte` at byte 2393988 receives a title, static/dynamic type,
frames and a keyboard capture SVG. Its output metadata contains `id`, `title`,
`describe`, `screen_type`, `create_at`, `company`, `data`, `width` and `height`.
It selects `keyboard_light_png` or `keyboard_light_gif`, serializes the frames,
combines them with an image using `c5` with `aiGenerated: true`, then raw-deflates
that result into `data`.

The image separator declaration is at byte 221067 in both main bundles and uses
`|||IMG_DATA_START|||`. This alone does not establish the complete inner grammar:
the serializer also receives the generation flag. A parser must trace that full
serializer/deserializer before claiming vendor compatibility. Earlier working
notes that used character offsets or named `JSON_IMAGE_SOURCE` were incorrect;
that claimed delimiter does not occur in these main bundles.

Next evidence needed is the dynamic editor's rendered Glyph entry point, frame
schema, full serialized envelope and playback route. Do not reinterpret these
records as the static 126-color slot format or as OLED images. The feature inventory
remains provisional; a reachable dynamic workflow must be accounted for separately
if confirmed, rather than silently excluded from Glyph parity.
