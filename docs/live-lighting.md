# Glyph live lighting

The Lighting page includes **Live screen lighting** for a connected wired USB
Glyph whose firmware reports live-light support. Choose **Start screen lighting**
and select a screen, window or tab in the browser's capture chooser. The selected
source is cropped, resized to a 21×6 RGB grid and sent to the keyboard. Captured images are
processed in memory; neither images nor frames are saved.

The browser selects sources using
[`getDisplayMedia`](https://www.w3.org/TR/screen-capture/). Available source choices
and permissions depend on the browser and desktop. This workflow requests video
only. It does not start a microphone or desktop-audio capture.

**Screen crop ratio** offers the vendor's eight choices: Original, 16:9, 16:10,
4:3, 1:1, 1.37:1, 1.85:1 and 2.35:1. The default and reset value is 2.35:1.
Original uses the whole selected source; the other choices produce the largest
centered rectangle with that ratio, using the vendor's rounding rules. Changes
apply to the next frame without starting a second capture. The crop recalculates
if the source dimensions change, and the panel shows both source and crop sizes.
A live 21×6 preview shows the RGB values from successfully sent frames; it is
cleared on stop and is not a verified physical LED layout.

The chosen ratio survives page navigation and reconnect within the open app.
Reloading the browser resets it; no capture selection or images are persisted.
To choose another source, stop and start capture again through the browser
chooser. Resetting the ratio does not change the captured source. The vendor
also resets to its first display; browser capture permissions require source
selection through the chooser instead. See the
[screen layout audit](releases/glyph-live-layout-audit.md). Rhythm position,
size and rotation controls do not apply to the vendor's screen mode.

One frame request completes before the next is scheduled, with a 100 ms pause.
This caps the browser at 10 frames/second before transfer time; actual rate is
lower. It deliberately retains the existing 10 ms USB packet pacing. The vendor
waits 8 ms **after** its awaited frame callback; that is not evidence of a sustained
125 frames/second hardware rate.

Explicit stop reapplies the main-light parameters read at session start and checks
readback. Leaving the Lighting page, ending screen sharing or a frame error stops
capture and requests the same cleanup. Disconnect and connection replacement
invalidate the server session, so late requests cannot write to a new connection.
A normal settings write also ends the session before proceeding; reset/restore
invalidate it without replaying old lighting. If the browser crashes or cannot
reach the server, restoration is not guaranteed: the keyboard may retain the
last visible frame until another lighting setting is applied. No host frame
processing or capture is owned by the server for this workflow.
If an abandoned session prevents a new start, apply a lighting setting or
disconnect to clear it.

The authenticated API is `POST /api/live_light_start` with `{}`, returning a
`session`; `POST /api/live_light_frame` with that `session` and exactly 756 hex
characters in `colors`; and `POST /api/live_light_stop` with the `session`.
Only one session can run per server. A stale stop cannot cancel a newer session.
Frames have 378 meaningful RGB bytes and seven HID packets; the final 14 payload
bytes are padding. See the [vendor audit](releases/glyph-live-light-audit.md) and
[native helper audit](releases/glyph-light-native-audit.md) for source evidence.
Implementation: `src/epomaker_driver/live_lighting.py`,
`src/epomaker_driver/live_light_session.py` and `ui/src/live-lighting.jsx`.

The Lighting page also offers **Audio preview**, usable without a connected
keyboard. Choose **Refresh audio outputs** to discover playback sinks, select
an output (or Automatic output), adjust the seven analysis controls, then choose
**Start audio preview**. **Stop audio preview** ends capture; changing pages also
stops it. Analysis settings can be adjusted while stopped and reset to the audited defaults.

The five rhythm modes (Spectrum, Circle, Triple circle, Matrix and Triangle) render
an RGB preview. Triple circle and Triangle currently leave the rightmost shape
inactive because the audited vendor renderer references bands absent from the
32-band DSP; these modes remain incomplete pending native-stream verification.
See the [rhythm audit](releases/glyph-rhythm-audit.md). Scale, animated gradient/solid color and mode can change while
running. **Reset rhythm settings** restores Spectrum, 100% scale and gradient.
To stream the visualization, connect a wired USB Glyph with light-sync support
and explicitly enable **Send rhythm to keyboard** before starting. Without this
option, preview does not acquire or write a keyboard session. Audio and screen
lighting share the same exclusive live-light session: stop one before starting
the other. Frames render into a fixed 640×360 workspace, then the selected
sampling rectangle is transformed into 21×6 RGB. Each transfer finishes before
the next sample request is scheduled.

**Rhythm position X/Y**, **Rhythm width/height**, and **Rhythm rotation** change
which part of the visualization reaches the keyboard. The layout preview shows
the sampling rectangle. Edits apply to the next frame without restarting capture;
offline edits do not start capture or write to a keyboard. The default rectangle
is 315×90 at (147,147), with no rotation. Position clamps to the available bounds,
size has a 90×60 minimum and scales to fit, and rotation accepts −180…180 degrees.
A rotation that would not fit reports an error and preserves the previous layout.
Separate reset buttons center the position, restore size, or clear rotation;
**Reset rhythm layout** restores all defaults. These choices last while the
Lighting page is open and reset when it is reopened.

The geometry follows the [painter audit](releases/glyph-rhythm-layout-audit.md),
including its 24-pixel top and 32-pixel right margins and inverse rotation through
a diagonal scratch canvas. The fixed Linux workspace replaces the vendor's
viewport-dependent canvas. Rhythm scale changes the drawing itself; layout
changes the region sampled from that drawing. Neither affects screen lighting.

Stopping, leaving the page, a capture/transfer error, or losing the supported
keyboard connection ends both sessions and requests lighting restoration. Late
start responses are cleaned up and stale frame callbacks cannot affect a newer
run. The audio polling lease ends forgotten capture; after a browser crash,
keyboard restoration has the same limitation as screen lighting above.

`PipeWireCapture` in `src/epomaker_driver/audio_capture.py` provides bounded,
in-memory float PCM from a PipeWire output monitor using
[`pw-cat`](https://docs.pipewire.org/page_man_pw-cat_1.html). `AudioPreview` applies the seven vendor-bounded controls to the
independent 32-band DSP in `src/epomaker_driver/audio_spectrum.py`, with a
five-second polling lease that stops and cleans up capture when the browser
stops polling. Tests use fake processes and synthetic PCM only; no real capture
was performed. PCM is not saved. Keyboard writes require the explicit streaming option.
The host needs both `pw-dump` for output discovery and `pw-cat` for the monitor
stream; missing tools or an unavailable monitor are reported as capture errors.

The authenticated API exposes `GET /api/audio_outputs` for discovered output
monitors and `GET /api/audio_config`, which returns the seven shared defaults and
per-control `{min, max, step}` limits. Start a preview with
`POST /api/audio_preview_start` and `{target, settings}` (both fields optional),
then poll `POST /api/audio_preview_sample` with `{session}` for 32 normalized
bands. End it with `POST /api/audio_preview_stop` and `{session}`; the five-second
lease also ends abandoned previews and closes capture.

Physical LED correspondence, real desktop capture, USB throughput and restoration
remain unverified. The DSP is an independent implementation, not a reconstruction
of the vendor native DSP. Persistent host-service behavior and suspend/resume
remain unfinished. Rendered geometry and DSP still require
comparison with the vendor runtime and physical output.
The screen workflow and audio capture component do not establish full live-light
parity.
