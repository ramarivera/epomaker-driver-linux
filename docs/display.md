# Glyph and RT85 display images and animation

```sh
epomaker --device /dev/hidrawN screen still.png --fit --bank 5
epomaker --device /dev/hidrawN display-language-toggle
epomaker --device /dev/hidrawN animation moving.gif --fit
epomaker --device /dev/hidrawN animation moving.gif --fit --delay-ms 80
```

Without `--fit`, frames must be exactly 428×142 pixels for Glyph or 320×172 for RT85. With it, the image is scaled
with preserved aspect ratio and black borders. Transparency is composited onto black.
The CLI opens the selected HID device and reads its identity to choose the dimensions;
all frames are then decoded, converted and validated before any display writes. GIF
frames are composed sequentially using Pillow's disposal/transparency handling.

## Timing and memory evidence

The shipped `composeGifFrames` multiplies GIF centiseconds by ten, caps each delay at
255, and `gif2Canvas` rounds the mean of those delays. The uploader passes this single
delay value to every frame. The Linux implementation follows that same conversion,
including rounding .5 upward. It does not preserve different durations per frame,
because the vendor's upload path uses one averaged delay. `--delay-ms` overrides the
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


## RT85 limits

RT85 uses the same transfer layout with a 320×172 RGB565 display. Its identical
6 MiB allocation and five still banks give 51 animation frames:

```text
floor((6*1024*1024 - 4096) / ((floor(320*172*2 / 4096) + 1)*4096)) - 5 = 51
```

Each full frame is 110,080 bytes in 1,966 chunks. `models.display_spec` derives both
models' dimensions and frame limits from the catalog; media conversion and the
high-level uploader use the same values. Python conversion functions default to
Glyph for compatibility and accept `model_id=2895` for RT85. The CLI detects the
model automatically. The graphical interface continues to support Glyph only.

The memory formula comes from `memoryForEachFrame` / `maxImageFrameCount` in the
macOS main bundle (pretty lines 110112–110148). RT85's date and language flags enable
clock and language operations; system-information display remains Glyph-only.
