# Glyph host rhythm audit

This audit covers the rhythm renderer and its host audio-analysis controls in
the extracted Windows and macOS light-sync chunks. No vendor code was executed,
and no audio, network, HID, or hardware operation was attempted. All offsets
are true UTF-8 byte offsets from `Path.read_bytes().find(...)`.

## Sources

- Windows:
  `/tmp/epomaker-analysis/win-app/resources/app/dist/js/57cfa1b3.js`,
  130,747 bytes, SHA-256
  `9b9e81be794a543617eec5a125c9efd55004c78d6a4c17ea30318c5aa9a6cd22`.
- macOS:
  `/tmp/epomaker-analysis/mac/EPOMAKER Driver v4 3.2.22/EPOMAKER Driver v4.app/Contents/Resources/app/dist/js/13da2307.js`,
  130,753 bytes, SHA-256
  `e58f558ab99d02de0c74c7febed4e8624064106cd0dd55339b82c4f6ce583d31`.

The rhythm renderer, control defaults, and service calls have matching offsets
in both chunks.

## Rhythm modes and update path

The rhythm service response schema is `rhythm_analysis.StreamDataResponse` with
repeated float `spectrum_data`; its protobuf reader begins at byte **18716**.
The host service object starts/stops the stream at byte **24244**. It selects
one renderer for each response at bytes **24521–25360**:

| UI key | Renderer | Evidence |
| --- | --- | --- |
| `spectrum` | `drawSpectrum` | dispatch byte 25108; renderer byte 9428 |
| `circle` | `drawCircle` | dispatch byte 25180; renderer byte 9829 |
| `tri-cicle` | `drawTripleCircle` | dispatch byte 25212; renderer byte 10134 |
| `matrix` | `drawMatrix` | dispatch byte 25301; renderer byte 10839 |
| `triangle` | `drawTriangle` | dispatch byte 25359; renderer byte 11100 |

The service starts with `playMode="spectrum"` at byte **24521**. A three-second
watchdog stops the stream when no response arrives. Renderer output is sampled
from the host canvas by the shared painter and then sent through the existing
Glyph live-light callback; this is host-side canvas processing, not evidence of
native firmware DSP.

## Canvas scale, origin, and colors

The renderer canvas and 100%-scale geometry are initialized around byte
**7388**. `setScale(scale)` sets `dw=canvasWidth*scale`,
`dh=canvasHeight*scale`, and centers the drawing rectangle with
`dx=(canvasWidth-dw)/2`, `dy=(canvasHeight-dh)/2`. The UI's background scale is
percentage based, with range 0–100, step 1, default 100 (control table byte
**44331**); the effect applies `setScale(backgroundScale/100)` at byte
**49308**.

Each renderer clears the canvas, chooses a fill color, and draws inside
`[dx,dy,dw,dh]`. The default color cycle updates three channel values from
`(255,0,0)` through green and blue, then uses three interpolated RGB stops in a
horizontal gradient; that code begins at byte **8355**. The solid-color option
switches to a single custom CSS color at byte **49187**. A Linux implementation
can reproduce these host colors without claiming that the firmware computes
them.

## Renderer formulas and input assumptions

`drawSpectrum` begins at byte **9428**. It reorders the incoming array as:

```text
reverse(data[29:33]) + data[0:29] + data[37:] + reverse(data[33:37])
```

Each reordered value is used directly as a normalized bar height (`value*dh`),
with bar width `dw/data.length`; the source does not clamp values. These slices partition the input at indices 29, 33 and 37; other renderers
below use a slice ending at 41. The JavaScript does not assert an exact length. The native service is configured for 32 bands below; the actual
stream length and any native expansion remain unverified. Do not infer a normal
41-bin stream from these slice expressions alone.

`drawCircle` at byte **9829** filters values greater than zero, computes their
average with the imported summation helper, and uses `average*dw` as the circle
radius (the source expression is `average*2*dw/2`). `drawTripleCircle` at byte
**10134** averages positive values from slices `0:8`, `9:17`, and `36:41`, then
draws circles at the center, left and right thirds respectively, with per-circle
scale factors 1.5, 1.2 and 1.5. Each radius is the smaller of half a third-width
and the group average times half a third-width times its factor.

`drawMatrix` at byte **10839** averages positive values across the input, clamps
`average*2.5` to 1, and fills a horizontal rectangle of that fraction of `dw`.
`drawTriangle` at byte **11100** uses the same three positive slices as the
triple-circle renderer, computes their averages, and draws three adjacent
triangles with heights scaled by 0.8, 1.3 and 1.5 respectively, without clamping
their height to the scaled drawing rectangle. Empty positive sets are not guarded in
the source; a defensive Linux implementation should define its zero-input
behavior explicitly.

## Audio-analysis controls

The complete host control table is initialized at byte **44331**:

| Control | Minimum | Maximum | Step | Default | Service field |
| --- | ---: | ---: | ---: | ---: | --- |
| gain | 1 | 20 | 1 | 10 | `gain` |
| tilt | 0 | 2 | 0.01 | 0.5 | `tiltFactor` |
| contrast | 0.5 | 4 | 0.01 | 2 | `contrastFactor` |
| release | 0.5 | 0.99 | 0.01 | 0.85 | `releaseFactor` |
| min dB | -80 | -20 | 0.1 | -60 | `minDb` |
| max dB | -20 | 20 | 0.1 | 0 | `maxDb` |
| attack frames | 1 | 20 | 1 | 5 | `attackFrames` |

On entry, the host starts the rhythm plugin and, when configuration is missing,
sets `audioDeviceId=""`, `numBands=32`, `fftSize=512`, and the table defaults;
that initialization is at byte **47172**. Existing configuration is read back
at byte **48767**. Changes to the seven visible controls call the service
configuration method with the mapped field names at byte **49385**. The update
does not send `audioDeviceId`, `numBands`, or `fftSize`, so those remain service
configuration rather than visible live controls here.

The service schema supports `audioDeviceId`, `numBands`, `fftSize`, and all
analysis fields (reader byte **18716**, writer beginning around **19304**).
`getAudioDevices()` is exposed by the host service wrapper at byte **24244**,
but no invocation of it appears in this chunk. The source therefore proves an
audio-device API exists, but does not prove a vendor UI for selecting a device
or a Linux device-ID mapping.

## State reset and boundaries

The light-sync context reset at bytes **49820–50650** restores spectrum mode,
gradient color, 100% scale, and all table defaults, then resets each painter's
layout. The reset is host UI state management. The source does not expose a
native DSP implementation, a firmware-side meaning for the analysis fields,
or a persisted per-device audio-device selection in this chunk.

The actionable Linux rhythm workflow is: obtain a float spectrum stream,
select one of the five renderer keys, apply the documented host formulas and
control ranges, convert the canvas into the existing 21×6 RGB output, and send
it through the Glyph live-light transport. Audio capture and DSP quality remain
separate implementation work; the vendor bundle alone does not establish
equivalence for those layers.

## Linux implementation boundary

`ui/src/rhythm-renderer.js` follows these host geometry formulas, with empty
positive groups defined as zero. Its independent DSP returns exactly 32 bands:
the vendor's `36:41` group therefore remains empty, so the rightmost shape in
Triple circle and Triangle is inactive. The app labels this limitation. Native
stream length/expansion must be verified before these two modes count as parity.
The gradient advances before each render, using the default color speed of one
channel step, with RGB, GBR and BRG stops on a horizontal axis. Its duration in
seconds depends on the Linux render cadence and is not vendor timing parity.

A subsequent [native format audit](glyph-spectrum-format-audit.md) found 42-float
working vectors in the macOS processor. Its output-to-serializer path remains
untraced, so this evidence does not yet change the Linux 32-band implementation.
