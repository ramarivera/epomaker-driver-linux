# Glyph display workflow evidence

Baseline: the installers in [the source manifest](../source-releases.json).
Offsets below are zero-based **UTF-8 byte offsets**, measured against raw bundles,
not decoded character positions or reformatted copies.

| Bundle | Bytes | SHA-256 | Glyph model record | Animation handler |
| --- | ---: | --- | ---: | ---: |
| Windows `dist/js/index.feaf50e4.js` | 2556505 | `72fb76b3c19e013d81e450d5245bc62bb5a275fcf6623530a5a652b9c7182be5` | 896116 | 1841766 |
| macOS `dist/js/index.5af2e057.js` | 2565198 | `06c91320e6e5b0249fa9f80f055aa5e19099aa5762402cf7098ef8752a832286` | 896116 | 1850578 |

Both model records identify internal ID 3059 as Epomaker Glyph, a keyboard with
VID 12625 and PID 20482. Its screen metadata specifies RGB565, 428×142 pixels,
six memory units, five screen layers, language switching, system information and
a clock. The memory interpretation is documented in [display.md](../display.md).
The separate `LightUserPicture` lighting effect describes per-key RGB colors;
it supplies no evidence about screen banks.

The shared `handleWriteGif` handler rejects keyboard connections designated `24g`
or `bt`, checks that the frame list has at least two frames and does not exceed
the calculated maximum, then queues the frames with their delay and the current
model's screen dimensions and pixel format. Both installers contain this gate.
This supports a wired-only restriction for the vendor animation workflow. It does
not establish the same restriction for still-image uploads.

The Linux animation conversion already validates frame capacity and timing without
silently dropping frames. Offline preparation now reports the converted result.
Explicit transport gating of the Glyph animation workflow remains a follow-up;
it must cover backend entry points and the graphical controls, while leaving
offline preparation available.

These findings do not prove that every shared editor control is exposed for Glyph.
Canvas editing, retained assets, screen clearing, transport behavior, firmware
persistence and physical rendering remain open acceptance work. Source evidence
is not a hardware verification result.
