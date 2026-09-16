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
The Linux backend now requires a transport classified as wired USB for Glyph
animation, including the multi-frame screen entry point. Bluetooth and unknown
transport kinds are rejected before the preparation handshake or pixel transfer.
The interface uses the actual connected transport, not the device-menu selection,
to enable animation upload. Offline preparation remains available, and single-frame
still uploads retain their existing behavior. Tests: `tests/test_glyph_animation_transport.py`
and `ui/tests/display-transport.spec.js`.

These findings do not prove that every shared editor control is exposed for Glyph.
Canvas editing, retained assets, screen clearing, transport behavior, firmware
persistence and physical rendering remain open acceptance work. Source evidence
is not a hardware verification result.

## Rendered frame controls

The screen toolbar is in code-split renderer bundles:

| Platform | Bundle | Bytes | SHA-256 |
| --- | --- | ---: | --- |
| Windows | `a9d6b129.js` | 192389 | `f37fba7b4eb24eb152b91e64fff1f44f9ff475018207d30d7656e52e0e52aab0` |
| macOS | `5b38b4bd.js` | 192389 | `a7e76a5ca33907771c8af72107fef0fef27eb2a944630198c1ca500d8621dfb5` |

Both raw bundles render add, remove, copy-previous, undo, redo, clear-current and
clear-all controls in bytes 177750–179100. Each carries the screen-settings page
identifier and invokes the drawing board. The parent mounts this toolbar beside
the frame counter near byte 167470. Together with Glyph's screen metadata, this
supports applicability to the Glyph screen editor. This does not establish every
control in its separate image-import dialog or paint tools.

The main renderer methods have these exact byte offsets (including `async` where
present):

| Method | Windows | macOS | Behavior |
| --- | ---: | ---: | --- |
| `addFrame` | 1838434 | 1847246 | Insert black after selection, select inserted frame; enforce maximum |
| `copyPrevious` | 1838744 | 1847556 | Replace selection with previous frame; first frame is unchanged |
| `reduceFrame` | 1838956 | 1847768 | Remove selection, retain nearest valid index; never remove the last frame |
| `clearCurrentFrame` | 1839187 | 1847999 | Replace selected canvas with black |
| `cleanAll` | 1839244 | 1848056 | Retain one black frame at index zero |
| `addUndoList` | 1840248 | 1849060 | Retain up to ten canvas snapshots per frame |

Linux now implements these five frame mutations through an offline draft API and
explicit UI controls. Undo/redo restores complete frame drafts with separate
bounded stacks, rather than emulating the vendor's per-canvas history. It does not
claim paint-tool or complete editor parity. Clearing a draft does not send a
screen-clear command: the user must explicitly upload the resulting image.
Implementation and limits: [display.md](../display.md),
`src/epomaker_driver/display_edit.py`, `ui/src/display.jsx` and
`ui/src/display-preview.jsx`. Tests: `tests/test_display_edit.py`,
`tests/test_display_prepare.py` and `ui/tests/display-edit.spec.js`.
