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

A separate `PipeWireCapture` component in `src/epomaker_driver/audio_capture.py`
provides bounded, in-memory float PCM from a PipeWire output monitor using
[`pw-cat`](https://docs.pipewire.org/page_man_pw-cat_1.html). It is not connected
to an app audio effect yet. Tests use fake processes and synthetic PCM; no real
capture was performed during this implementation.

Physical LED correspondence, real desktop capture, USB throughput and restoration
remain unverified. Rhythm layout controls, visualization and its DSP
settings, persistent host-service behavior, and suspend/resume remain unfinished.
The screen workflow and audio capture component do not establish full live-light
parity.
