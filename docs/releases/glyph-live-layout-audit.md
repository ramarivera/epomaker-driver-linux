# Glyph screen live-light layout audit

This audit is limited to the screen mode in the extracted host light-sync
bundle. Offsets are true UTF-8 byte offsets obtained with
`Path.read_bytes().find(...)`; no vendor code was executed and no hardware or
network operation was attempted.

## Sources

- Windows host light-sync bundle:
  `/tmp/epomaker-analysis/win-app/resources/app/dist/js/57cfa1b3.js`,
  130,747 bytes, SHA-256
  `9b9e81be794a543617eec5a125c9efd55004c78d6a4c17ea30318c5aa9a6cd22`.
- macOS equivalent:
  `/tmp/epomaker-analysis/mac/EPOMAKER Driver v4 3.2.22/EPOMAKER Driver v4.app/Contents/Resources/app/dist/js/13da2307.js`,
  130,753 bytes, SHA-256
  `e58f558ab99d02de0c74c7febed4e8624064106cd0dd55339b82c4f6ce583d31`.

The relevant offsets and control flow are identical in these two chunks.

## Screen capture crop and persistence

The screen service lists displays and accepts a thumbnail stream request. The
request schema at byte **27115** contains `screen_id`, `x`, `y`, `width`,
`height`, `thumbnail_width`, and `thumbnail_height`. The host singleton starts
that stream at byte **33216** with `thumbnailWidth:21` and
`thumbnailHeight:6`. It converts each incoming RGBA pixel to RGB, multiplying
each channel by alpha, at bytes **33216–33500** and stores the flattened output
in `outputs`.

Screen selection is held in the `hi` controller instance: `selectedScreenId`
and `selectedScreenRatioKey` are initialized at byte **34597**. The available
ratio choices, including `original`, `16:9`, `16:10`, `4:3`, `1:1`, `1.37:1`,
`1.85:1`, and `2.35:1`, begin at byte **34132**. The crop calculation at byte
**34359** is centered and deterministic:

```js
if (ratio === -1) return { x: 0, y: 0, width, height };
sourceRatio = width / height;
if (ratio > sourceRatio) { widthOut = width; heightOut = round(width / ratio); }
else { heightOut = height; widthOut = round(height * ratio); }
x = round((width - widthOut) / 2);
y = round((height - heightOut) / 2);
```

`start()` applies that rectangle in the stream request at bytes **34667–35000**.
Changing the display or ratio stops the current stream, updates the in-memory
selection, waits 100 ms, and starts again (controller methods around bytes
**35500–36050**). `reset()` restores ratio `2.35:1` and selects the first
listed display at byte **36599**. No storage write or export of these choices
is present in this chunk, so the evidence supports session-local selection,
not persistent crop settings.

## Screen-specific controls

The screen tab renders two controls: display selection and active screen ratio;
the JSX is at byte **80315**. It also renders an explanatory screen-mode note.
The layout tab is explicitly disabled whenever the selected mode is `screen`
at byte **74637**. Therefore the following controls are rhythm-only in the
vendor UI: position X/Y, width/height, rotation, reset position, reset size,
reset rotation, and reset-all-layout. Their handlers are visible at bytes
**78273–78900** and mutate the selected rhythm painter.

The rhythm painter defaults and bounds are concrete: `DEFAULT_WIDTH=315`,
`DEFAULT_HEIGHT=90`, `MIN_WIDTH=90`, `MIN_HEIGHT=60`, and rotation defaults to
zero at byte **38893**. `setPos`, `setSize`, and `setRotation` clamp against
the painter canvas and rotated bounding box at bytes **39673**, **39844**, and
**40469**. `resetLayout` restores size, rotation, and centered position at byte
**41315**. Its `draw()` and `rotateDraw()` paths sample the painter canvas after
these transformations.

Screen mode bypasses those painter layout transformations. `updateScreen()` at
byte **43140** sends the shared screen singleton's already-generated `outputs`
directly to its callback; it does not read `sx`, `sy`, `sw`, `sh`, or
`rotation`. The stream-service crop above is consequently the screen mode's
actual crop/fit mechanism.

## Frame cadence and common entry hook

The screen controller redraws the 21×6 thumbnail canvas every 30 ms after a
stream starts (bytes **34667–35500**), while `updateScreen()` schedules its
callback again after each awaited send with an 8 ms timeout (byte **43140**).
The latter is a scheduling interval, not a guaranteed 125 Hz wire rate because
the transport send is awaited and paced separately.

A common light-sync entry effect at byte **46908** assigns the current light model’s type
from `LightMusicFollow2` or `LightScreenColor` to `LightAlwaysOn`; the same common
hook initializes the audio plugin defaults (`numBands:32`, `fftSize:512`) at
byte **47172**. These are shared light-sync entry behaviors, not additional
screen crop controls, and this bundle does not prove a Glyph-specific Linux
replacement for the capture service.

The actionable screen workflow established by the source is therefore:
select a display → choose a centered aspect-ratio crop → stream it to a fixed
21×6 RGB buffer → send that buffer through the existing Glyph live-light
transport. A Linux UI can expose those two screen controls without claiming
that rhythm position/size/rotation controls apply to screen mode.
