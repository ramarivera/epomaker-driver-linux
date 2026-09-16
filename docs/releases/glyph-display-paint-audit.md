# Glyph display painting evidence

The code-split screen renderers are Windows `a9d6b129.js` and macOS
`5b38b4bd.js`, identified by SHA-256 in
[glyph-display-workflow-audit.md](glyph-display-workflow-audit.md). All offsets
below are zero-based UTF-8 bytes. The inspected ranges 836–5300,
177096–177600 and 180493–181800 are byte-identical across those two bundles.

The screen toolbar renders brush at 177096 and sets the eraser's packed color to
1 at 177394. Color 1 becomes black after RGB565 quantization. The size menu's
visual marker array at 180493 stores selected indices 0, 1, 2. The stamp helper
at 1404 expands index `s` to a filled square `2*s+1` pixels wide: **1, 3, 5**.
The line interpolator at 836 rounds evenly spaced sample positions. The board
paints the path between pointer samples using square stamps; its rendered toolbar
has no separate line, rectangle or flood-fill tool.

The canvas setup within 836–5300 creates one black frame when the frame list is
empty. Pointer mapping divides coordinates by canvas zoom and logical cell size.
The wheel bound at 4596 admits zoom 1 through 5. Space temporarily enables dragging
the viewport, and a reset control restores zoom/pan. Undo history is per frame,
limited to ten canvas snapshots; see the main-renderer evidence in the linked audit.

Linux provides brush/eraser, RGB color selection, 1/3/5-pixel squares, interpolated
strokes, ten stroke undo/redo entries, 1–5× zoom, wheel zoom, Space-drag panning and
view reset. It uses a native modal dialog and contiguous pixels, with explicit
Apply/Cancel. Apply replaces only the selected frame in the offline draft; upload
and asset saving are separate. A rejected apply retains the painting for retry.
Pointer cancellation restores the image preceding that stroke. Native diagonal
interpolation can omit the ending sample; Linux includes both endpoints rather
than copying that edge artifact.

`New blank draft` makes the blank starting canvas available without an image file.
Painting starts from the actual converted display pixels. The replacement endpoint
accepts only a single, valid 428×142 PNG up to 1 MiB, then applies the same RGB565
conversion as uploads. Other frames, their order and effective delay are preserved.

Implementation: `ui/src/display-paint.jsx`, `ui/src/display-preview.jsx`,
`ui/src/display.jsx`, `src/epomaker_driver/display_edit.py`,
`src/epomaker_driver/server.py`. Tests: `ui/tests/display-paint.spec.js`,
`tests/test_display_edit.py`, `tests/test_display_prepare.py`.

This is source and offline-test evidence, not hardware validation. Import-image
position/scale and its separate GIF timing behavior remain pending; see
[glyph-display-import-audit.md](glyph-display-import-audit.md).
