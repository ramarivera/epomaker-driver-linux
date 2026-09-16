# Glyph display image import audit

This records the vendor’s screen-image import dialog for Glyph’s 428×142
mode-16 display. No vendor source is copied here; offsets are zero-based UTF-8
byte offsets in the minified renderer bundles.

| Bundle | SHA-256 | Dialog / screen-toolbar offsets |
| --- | --- | --- |
| Win `resources/app/dist/js/a9d6b129.js` | `f37fba7b4eb24eb152b91e64fff1f44f9ff475018207d30d7656e52e0e52aab0` | `i$` 149,058; toolbar mount 167,470 |
| Mac `Contents/Resources/app/dist/js/5b38b4bd.js` | `a7e76a5ca33907771c8af72107fef0fef27eb2a944630198c1ca500d8621dfb5` | `i$` 149,058; toolbar mount 167,489 |

The dialog initially fits and centers the image. Its wheel control changes
scale in steps of 20 percentage points, bounded from 20% through 300%.
Every wheel change also recenters the scaled image. Pointer dragging changes
the position without bounds; the image is clipped by the preview canvas.

Cancel leaves the frame list unchanged. For a still image, confirm renders the
transformed image into one black 428×142 canvas and returns a PNG data URL;
the parent applies that result to the current frame. For a GIF, confirm
renders every decoded frame with the same position and scale, replaces the
entire frame list, selects frame zero, and redraws it. The GIF frame delay is
the rounded arithmetic mean of decoded frame delays, with **60 ms** used when
that rounded result is zero. The direct file-to-canvas fallback has separate
decoding behavior and does not imply this dialog’s transform semantics.

The dialog has no crop rectangle, rotate, horizontal-flip, or vertical-flip
control.

## Linux implementation

On a prepared or blank draft, **Import image with placement** opens a modal with
20–300% scale, drag positioning and numeric coordinates. Scale changes recenter;
Cancel preserves the draft. Apply imports a still into the selected frame, or
replaces the entire frame list for GIF/multi-frame sources. A one-frame GIF also
replaces the list. Multi-frame imports use the capped/rounded mean delay and 60 ms
zero fallback. The direct Prepare preview workflow continues to preserve zero.

Each import starts from the original source pixels and applies a single inverse
affine transform into 428×142, then RGB565 conversion. Fractional position and
scaled dimensions are retained. Pillow bicubic sampling is independent of browser
sampling; identical resampling pixels are not claimed. The modal previews the
original image in the browser; the resulting draft preview shows actual wire
pixels. GIF disposal is decoded sequentially, JPEG EXIF orientation is honored,
and transformed frames serialize losslessly to preserve duplicates.

Input is bounded to 14 MiB, 16 million source pixels per frame and 46 frames.
Sources decode sequentially, with only small transformed output frames retained.
Completely offscreen finite coordinates produce black output without allocating
offscreen canvases. Invalid or failed imports leave the previous draft intact.
Successful imports participate in whole-draft undo/redo, including source labels;
asset save and device upload remain explicit.

Implementation: `src/epomaker_driver/display_import.py`,
`src/epomaker_driver/server.py`, `ui/src/display-import.jsx`,
`ui/src/display.jsx` and `ui/src/display-preview.jsx`.
Tests: `tests/test_display_import.py`, `tests/test_display_prepare.py`,
`ui/tests/display-import.spec.js`. This evidence remains offline; physical display
appearance and firmware persistence have not been verified.
