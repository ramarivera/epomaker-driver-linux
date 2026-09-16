# Keyboard display images and animation

```sh
epomaker --device /dev/hidrawN screen still.png --fit --bank 5
epomaker --device /dev/hidrawN display-language-toggle
epomaker --device /dev/hidrawN animation moving.gif --fit
epomaker --device /dev/hidrawN animation moving.gif --fit --delay-ms 80
```

Without `--fit`, frames must be exactly 428×142 pixels for Glyph, 320×172 for RT85, 240×240 for RT75, 162×173 for RT100, or 60×9 for Dynatab75X-UK. With it, the image is scaled
with preserved aspect ratio and black borders. Transparency is composited onto black.
The CLI opens the selected HID device and reads its identity to choose the dimensions;
all frames are then decoded, converted and validated before any display writes. GIF
frames are composed sequentially using Pillow's disposal/transparency handling.

## Graphical preparation

Choose an image and select **Prepare preview** before uploading. Preparation works
without a keyboard connected and uses the same conversion as the uploader. Its
428×142 preview reconstructs every frame from the actual RGB565 wire pixels,
including black borders and color quantization. Animation preparation validates
all frames and reports their count, total pixel bytes and the single effective
frame delay. Use the frame selector or Previous/Next controls to inspect individual
frames, or Play/Pause to preview at the effective delay. Desktop timing is approximate
and does not verify keyboard playback. Zero-delay animations allow manual inspection
only because their hardware timing is unknown. Changing the draft, leaving the
Display page, or hiding the browser stops playback.

Changing the source, upload type or delay invalidates the prepared draft. Changing
a still-image destination bank keeps the pixels. **Upload to display** sends the
prepared source and effective timing only after an explicit click and connection;
preparation itself performs no device access. Glyph still-image and animation uploads require a
wired USB connection; Bluetooth, receiver or unknown transports cannot upload pixels.
This follows the vendor UI gate, documented in
[the display workflow audit](releases/glyph-display-workflow-audit.md). Both rendered vendor upload buttons carry that restriction. Inputs remain locked during either
operation. The graphical file limit is 14 MiB; normal server request limits also
apply. The [local asset library](glyph-display-assets.md) retains original files
for reuse. Screen-image integration into device backup remains open work.

The offline API is `POST /api/display_prepare` with `content` (base64 image),
`kind` (`screen` or `animation`) and optional `delay_ms`. It returns `width`,
`height`, `frame_count`, `pixel_bytes`, `delay_ms` (null for stills) and
`preview_frames` (an array of base64 PNGs). The legacy `preview_png` field retains
the first frame for compatibility. It uses the same loopback authentication as other API
operations. Implementation: `src/epomaker_driver/media.py`,
`src/epomaker_driver/server.py`, `ui/src/display.jsx` and
`ui/src/display-preview.jsx`. Regression coverage: `tests/test_display_prepare.py`
and `ui/tests/display-animation-preview.spec.js`.

## Offline frame editing

After preparation or library loading, insert a black frame after the selection,
copy the previous frame into it, delete it, clear it, or clear all frames. The last
frame cannot be deleted; clear-all leaves one black frame. Frame operations affect
the draft only. Upload and library save remain explicit. A single remaining frame
becomes a still image; adding to a still starts an animation at 80 ms per frame.
Existing animation delays, including zero, remain unchanged.

Undo/redo restores complete drafts. Each direction retains at most ten drafts and
32 MiB of encoded source/preview data; older entries are dropped when either limit
is exceeded. Loading or preparing another draft, choosing a source, or changing
kind/delay resets history. Changing the destination still bank retains history.
Pending edits lock controls; rejected edits leave the source and history intact.

`POST /api/display_edit` accepts base64 `content`, `kind`, `delay_ms`, zero-based
`index`, and `operation` (`add`, `copy_previous`, `delete`, `clear`, `clear_all`).
The result includes preparation metadata, the edited base64 `content`, resulting
`kind` and `selected_index`. Input is bounded to 14 MiB and 46 frames. Editing
uses the converted RGB565 pixels, not an unquantized source image. One-frame drafts
serialize as PNG; animations serialize as lossless multi-page raw TIFF with delay
stored separately. This avoids GIF palette loss and APNG duplicate-frame merging.
A full 46-frame TIFF is about 8.01 MiB, within the existing upload/library limits.
Re-preparing, saving, exporting and loading retain those edited frames.

The paint dialog adds brush/eraser editing of selected frames; device screen-clearing
behavior remains open; image-import placement is available below. See [the rendered-control evidence](releases/glyph-display-workflow-audit.md).
Implementation: `src/epomaker_driver/display_edit.py`, `src/epomaker_driver/server.py`,
`ui/src/display.jsx`, `ui/src/display-preview.jsx`. Tests: `tests/test_display_edit.py`,
`tests/test_display_prepare.py`, `ui/tests/display-edit.spec.js`.

## Painting a frame

Choose **New blank draft** to start without a file, or prepare/load an image and
select **Paint this frame**. The modal editor supports brush and eraser with 1, 3,
or 5-pixel square stamps, an RGB color picker, and ten stroke undo/redo entries.
Use the zoom selector or wheel for 1–5× magnification; focus the canvas, hold Space
and drag to pan. **Reset canvas view** restores the initial view.

**Apply painting to draft** replaces only the selected frame and creates an entry
in the whole-draft undo history. **Cancel painting** or Escape discards the modal's
changes. A rejected apply retains the drawing for retry. No painting action uploads
or saves an asset. Input colors are quantized to RGB565 on apply; the returned
preview displays those actual wire pixels. Pending applies lock the modal controls.

The `display_edit` operation `replace` takes an additional `replacement` field:
base64 PNG, exactly 428×142, one frame, at most 1 MiB. Unexpected replacement data
on other operations is rejected. Strict image validation precedes serialization.
See [painting evidence and implementation](releases/glyph-display-paint-audit.md).

## Importing with image placement

Prepare a source or choose **New blank draft**, then select a file using **Import
image with placement**. Scale ranges from 20% to 300% in 20-point increments.
Scaling recenters the image; drag or enter X/Y coordinates to move it afterward.
The viewport clips pixels outside the display. Cancel leaves the draft unchanged.

Apply replaces only the selected frame for a still image. GIF and multi-frame
imports replace the whole frame list and select frame zero; a single-frame GIF
also replaces the list. Animation imports average delays capped at 255 ms and use
60 ms when the rounded average is zero. Direct **Prepare preview** retains its
existing zero-delay behavior. Undo restores the previous draft and source label.

The dialog uses the browser's original-image preview. Apply transforms original
pixels with Pillow bicubic sampling, then displays the converted RGB565 draft.
Sampling may differ from the browser preview; hardware output remains unverified.
See [the import audit](releases/glyph-display-import-audit.md) for evidence and bounds.
The offline APIs are `POST /api/display_import_inspect` (base64 `content`) and
`POST /api/display_import_transform` (`content`, integer `scale`, finite `x`/`y`).
Neither performs device access. The UI applies the result through the existing
frame replacement or whole-draft path before any explicit save/upload.

## Timing and memory evidence

The shipped `composeGifFrames` multiplies GIF centiseconds by ten, caps each delay at
255, and `gif2Canvas` rounds the mean of those delays. The uploader passes this single
delay value to every frame. The Linux implementation follows that same conversion,
including rounding .5 upward. It does not preserve different durations per frame,
because the vendor's upload path uses one averaged delay. The vendor's separate
[image-import dialog](releases/glyph-display-import-audit.md) substitutes 60 ms when
its rounded average is zero; Linux's direct preparation still preserves zero; the image-placement workflow
uses the dialog's 60 ms fallback. `--delay-ms` overrides the
average with an integer from 0 to 255; zero is preserved as a protocol value, without
a hardware-verified playback meaning.

The vendor's drawing-board memory calculation resolves Glyph's `memorySize: 6` as
6 MiB. It reserves a 4 KiB header, rounds each full-size RGB565 image to 30 blocks of
4 KiB, and reserves five still images. This yields 46 animation frames:

```text
floor((6*1024*1024 - 4096) / ((floor(428*142*2 / 4096) + 1)*4096)) - 5 = 46
```

The animation command accepts 2–46 frames and rejects excess frames before device
writes. It sends complete frames; it does not currently crop to a shared nonblack
bounding box as the vendor UI can. Each frame contains 121,552 pixel bytes, encoded
as RGB565 high-byte-first, column-major, in 2,171 packets.

## Transfer sequence

The vendor's `___gifToDevice` prepares the entire animation once using the first
frame's byte length, total count, delay and common bounds. It then sends each frame,
starting that frame's chunk index at zero. The Linux driver follows this sequence;
it does not repeat the preparation handshake between frames. Preparation failures
or timeouts are retried up to ten times after the initial request. Once accepted,
the driver waits 100 ms before sending pixels.

There is no implemented screen readback command. Completion confirms that the host
sent all packets, not that the device displayed or persisted every frame. Hardware
acceptance, timing, firmware persistence and visual comparison remain outstanding. Screen images are not part of configuration backups.

## Still banks and language

The CLI `--bank 1..5` and interface Bank 1–5 select the destination still-image bank;
the default is Bank 1. This chooses where the image is written, not an independently
verified command to switch the currently displayed bank. API `bank` and Python `frame`
are zero-based. The wire header has `frameNum=1` and `currentFrame=0..4`. For animations,
that same byte is a frame index and must remain below the frame count.

Evidence: bundled `index.5af2e057.js` (pretty research copy lines 62378–62410) declares
five Glyph screen layers; screen state defaults to layer zero (line 9963). The generic
`___pngToDevice` at line 115182 passes that layer to `currentFrame` while setting
`frameNum: 1`. Protocol `623d2d52.js`, lines 314–366, writes those values unchanged to
both the preparation and chunk headers. The earlier Linux validation incorrectly
required `currentFrame < frameNum` for stills and consequently rejected banks 2–5.

Glyph declares `canSwitchLanguage: true`. The UI's Chinese/English switch handler
calls `setOLEDLanguageSwitch(true)`; protocol `623d2d52.js`, lines 435–442, sends
command 0x27 with byte 1 set to 1, followed by the usual vendor settling delay.
The Linux toggle emits `27 01 00 00 00 00 00 d7`, then 56 zero bytes. No language query
or reliable mapping from command values to an absolute language was found; therefore
this is exposed as a toggle, not an English/Chinese setter. Repeating it may reverse
the prior change. Confirm the resulting language on the physical display.


## HE65 Mag limits

HE65 Mag (internal model 2376) uses the inherited modern RY5088 display protocol with a 128×128 RGB565 screen, 6 MiB memory and five still banks. `models.display_spec` derives a maximum of 165 animation frames from those catalog values. The model exposes clock synchronization and a language toggle; system-information display is not advertised. Screen pixels, clock state and language state remain outside schema 7 backups. Hardware acceptance and persistence remain unverified.

## RT85 limits

RT85 uses the same transfer layout with a 320×172 RGB565 display. Its identical
6 MiB allocation and five still banks give 51 animation frames:

```text
floor((6*1024*1024 - 4096) / ((floor(320*172*2 / 4096) + 1)*4096)) - 5 = 51
```

Each full frame is 110,080 bytes in 1,966 chunks. `models.display_spec` derives the supported
models' dimensions and frame limits from the catalog; media conversion and the
high-level uploader use the same values. Python conversion functions default to
Glyph for compatibility and accept `model_id=2895` for RT85. The CLI detects the
model automatically. The graphical interface continues to support Glyph only.

The memory formula comes from `memoryForEachFrame` / `maxImageFrameCount` in the
macOS main bundle (pretty lines 110112–110148). RT85's date and language flags enable
clock and language operations; system-information display is available on Glyph and RT75, but not RT85.


## RT75 limits

RT75 uses 240×240 RGB565 frames, five banks from the vendor's default bank list,
and the same 6 MiB allocation. This gives 47 animation frames; each full frame
contains 115,200 bytes in 2,058 chunks. The CLI detects its dimensions automatically.
See [rt75.md](rt75.md) for the bank fallback, allocation formula and capability flags.


## RY6602 RGB24 screens

SN020 (33×7), TH80 V3 MAX (7×7) and TH65 Max (7×7) use column-major RGB24,
three bytes per pixel and `a9`/`29` preparation/data opcodes. Media conversion and
upload select the format from `display_spec.pixel_bytes`. All three have five
still banks. SN020/TH80 V3 MAX allow 255 animation frames; TH65 Max allows 16
because of its special byte-sized allocation. See [ry6602.md](ry6602.md) for
the source paths, formulas and missing physical verification.

## YC3121 screens

RT100 uses the inherited RGB565 transfer (`a5`/`25`) at 162×173 with six MiB of
display memory and five still banks. Dynatab75X-UK uses RGB24 (`a9`/`29`) at 60×9
with five still banks. The vendor catalog omits Dynatab's memory size; its drawing
board defaults an omitted value to 7 MiB, which `models.display_spec` follows.
Both support clock and system-information writes; only RT100 advertises the language
toggle. As with other migrated displays, uploads have no pixel readback and physical
rendering remains unverified.

The 7 MiB fallback is explicit in both installers' drawing-board initialization:
macOS `f2896358.js` and `5b38b4bd.js` assign
`deviceType.other?.screen?.size.memorySize ?? 7`; Windows `c0b36d47.js` and
`a9d6b129.js` do the same. The model catalog still supplies Dynatab's dimensions,
mode and five layers; only `memorySize` is absent. The Linux fallback is therefore
restricted to model ID 1723 rather than applied to arbitrary incomplete catalog
entries.

The older parent/model pair and the newer shared display class were compared for
the fields used here. Both use the same clock payload (`0x28`, big-endian year at
byte 8 and month through second at bytes 10–14), system-info payload (`0x22`, four
little-endian GiB values, CPU/temperature bytes and two network values), and display
prepare/chunk metadata (current frame, frame count, delay, byte length, bounds,
chunk index and chunk length). Format-specific opcodes remain `0xA5/0x25` for
RGB565 and `0xA9/0x29` for RGB24. This is why the existing shared codec is reused.
