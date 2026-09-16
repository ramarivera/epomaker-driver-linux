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
The rendered buttons provide an additional restriction that the handler-only audit
missed: **both still and animation uploads require wired USB**. In both code-split
renderer bundles listed below, UTF-8 byte 171997 begins the still button's text,
handler and disabled predicate. The predicate disables it for keyboard connections
`24g` or `bt`; the adjacent animation button has the same predicate plus its minimum
frame count. Bytes 171950–172260 match across platforms. Glyph is a keyboard in the
catalog, so this restriction applies to its still uploads too.

Linux now enforces this at both the backend and the graphical upload button.
A connection positively classified as USB is required; an unknown transport cannot
bypass the gate. Changing only the device dropdown does not change the connected
transport. Preparation, painting, imports and library operations stay available
offline and on wireless connections. This corrects the earlier statement that still
uploads retained unrestricted behavior. It does not prove that firmware cannot
accept wireless pixel transfers; it follows the exposed vendor workflow.
Tests: `tests/test_glyph_animation_transport.py`, `tests/test_glyph_still_transport.py`
and `ui/tests/display-transport.spec.js`.

These findings do not prove that every shared editor control is exposed for Glyph.
Canvas editing and retained assets now have offline implementations. Device screen
clearing, physical transport behavior, firmware persistence and rendering remain
open acceptance work. Source evidence
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

## Clear-screen action and weather applicability

The Other settings panel contains an unconditional clear-screen button, following
separately gated clock, language and system-information controls. In both renderer
bundles its `onClick` is at byte 175800 and the handler starts at byte 165575.
It queues a screen-clear event; it does not paint or upload a black frame.
Glyph's screen metadata makes the screen settings page available.

The YC3123 protocol method `setFlashChipErase` starts at byte 10375 in Windows
`17dc9c62.js` and macOS `623d2d52.js`. Both files are 38628 bytes, with SHA-256
`eb9f34119b3467a209723f43d8d468a69e3bfa7f9ad45c0d27a37d66d22ccc68` and
`e4f4ca92f999856242fae8ac6d527bf930a44223d03a5e9665993718f965a6c6`, respectively.
The command constant at byte 2695 is `AC`. It sends a zero-filled 64-byte request
with that opcode and the normal byte-7 checksum, and checks reply prefix
`AC AA AA 55 55`. The implementation range matches across platforms.

Glyph uses the keyboard task (`lM` in Windows), rather than the dongle screen
task. The keyboard class starts at Windows byte 1935644, and its screen dispatcher
starts at 1948517 (macOS 1957329). After the immediate erase ACK it starts a
550 ms interval, incrementing progress by one percent per tick. **That estimated
55-second progress animation is not a completion deadline.** The event stays
in progress until an unsolicited clear-complete notification is received.
The completion handler is at Windows byte 1955921 / macOS 1964733; it ends the
screen-clear event and cancels the progress interval. Without that notification,
the vendor timer can continue beyond 100 percent. The keyboard branch contains
no separate erase-timeout failure path.

The other dispatcher at Windows byte 2006093 / macOS 2014905 belongs to the dongle
task and resets its event immediately after the call. It must not supply Glyph's
completion semantics. Linux must wait for the actual completion notification,
bound its wait, and retain an uncertain result after timeout or disconnection.
The generic input callback constructs a report-ID-prefixed array (Windows byte
1696816 / macOS 1705628). Vendor receive strips that first byte (1699373 / 1708185)
and passes the data to the event decoder. Its clear-completion predicate is an
exact three-byte prefix `2C 00 00` (1698556 / 1707368), independently of the rest
of the payload. `AC AA AA 55 55` is not the completion event.

This JavaScript callback does not constrain the report ID, descriptor length or
HID collection. Linux must establish which vendor input report carries the event
before consuming it: normal keyboard report data must not be interpreted as a
vendor completion marker. The known command feature collection alone does not
prove its input routing. Resolve this through the platform HID adapter/opening
path and the actual Glyph report descriptor. Do not strip a synthetic zero report
ID from an unnumbered Linux input report without descriptor evidence.

`Keyboard.request_screen_erase()` now implements only the acknowledged command:
it re-identifies a normal Glyph, sends one exact request and validates the
64-byte reply and signature. It does not retry on timeout or claim completion.
Tests: `tests/test_glyph_screen_erase.py`. This primitive is not exposed through
the GUI or CLI until the completion-wait and exclusive-operation lifecycle are
implemented. No clear command has been sent to hardware.

Weather is excluded for this baseline. The weather visibility getter reads
`other.screen.canWeather` (Windows byte 1844615, macOS 1853427), while its unit
selector reads `canweatherUnit` (1844729 / 1853541). Glyph's model record at byte
896116 contains neither flag. The renderer binds its weather visibility at byte
160365 and conditionally renders the weather section at byte 174589. The shared YC3123 weather
method at byte 2065 is also a false-returning stub. A weather workflow on another
model does not establish Glyph support. No weather credentials or API requests
are needed to determine this exclusion.
