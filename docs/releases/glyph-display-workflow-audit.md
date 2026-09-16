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
The generic WebHID callback constructs a report-ID-prefixed array (Windows byte
1696816 / macOS 1705628). Vendor receive strips that first byte (1699373 / 1708185)
and passes the data to the event decoder. Its clear-completion predicate is an
exact three-byte prefix `2C 00 00` (1698556 / 1707368), independently of the rest
of the payload. `AC AA AA 55 55` is not the completion event.

The desktop native adapter provides stronger path evidence than the WebHID
callback alone. Windows class `WP` at byte 1694396 (macOS class `lM` at 1703208)
uses one `devicePath` for feature reads, feature writes, output writes and report
listening. The proto constructor selects that adapter at Windows byte 1697273.
The native report stream routes responses by that same path (Windows 1693440).
It does not open a separate event device in this adapter. This resolves the
previous same-path question; concrete input report IDs still come from the device
descriptor rather than a guessed constant.

Bluetooth additionally routes notifications through marker `66`:
`___decodeBtInputData` (Windows 1713630 / macOS 1722442) removes report ID and marker
before decoding the vendor data. With the observed report-6 descriptor, a complete
Linux input report is 66 bytes and starts `06 66 2C 00 00`. A `06 55` command reply
must not be mistaken for completion.

Linux discovery now tracks collections for **Input main items separately** from
feature/output items. A vendor feature report alone cannot label ordinary keyboard
input as a vendor event. On the verified USB command path, input reports belonging
only to vendor-defined usage pages are eligible; their report IDs and payload sizes
come from that descriptor. The bridge does not establish a fixed USB input usage
or report ID, so Linux does not invent one. Unnumbered Linux input contains only
the payload; numbered input must have the matching ID and exact descriptor length.
Bluetooth requires report 6 in vendor collection FF55/0202 with its 65-byte payload
and `66` routing marker. Reports mixing standard and vendor input collections are
ineligible. A device without an eligible report cannot start the complete erase
transaction.

`Keyboard.request_screen_erase()` implements only the immediate ACK. The new
`Keyboard.erase_screen()` holds transport ownership from stale-input draining
through one erase request, ACK validation and completion reception. Timeout defaults
to 90 seconds and is bounded to at most 300; it is a host failure deadline, not an
inferred completion. Cancellation and expiry leave the outcome uncertain and never
resend the command. Progress callbacks report elapsed seconds only. Completion
received during Bluetooth ACK handling is retained for the pending wait.

The complete transaction returns explicit acknowledgement/completion flags and
`pixels_verified: false`. It does not inspect flash contents or prove visual output.
The app-owned background operation, global device-access exclusion across HTTP
requests, progress UI and interruption recovery are still required before exposing
clear-screen through the GUI. No clear command has been sent to hardware.
Implementation: `src/epomaker_driver/discovery.py`, `src/epomaker_driver/transport.py`
and `src/epomaker_driver/device.py`. Tests: `tests/test_discovery.py`,
`tests/test_glyph_screen_erase.py`, `tests/test_screen_erase_transport.py` and
`tests/test_screen_erase_transaction.py`.

Weather is excluded for this baseline. The weather visibility getter reads
`other.screen.canWeather` (Windows byte 1844615, macOS 1853427), while its unit
selector reads `canweatherUnit` (1844729 / 1853541). Glyph's model record at byte
896116 contains neither flag. The renderer binds its weather visibility at byte
160365 and conditionally renders the weather section at byte 174589. The shared YC3123 weather
method at byte 2065 is also a false-returning stub. A weather workflow on another
model does not establish Glyph support. No weather credentials or API requests
are needed to determine this exclusion.
