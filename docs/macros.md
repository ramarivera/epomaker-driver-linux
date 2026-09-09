# Macros and key bindings

Macro storage, macro playback bindings and normal key combinations are separate.
Writing a macro slot does not assign a key to it. Use physical matrix slots for the
binding commands; these are not USB key usages or positions in a printed layout.

```sh
epomaker actions
epomaker --device /dev/hidrawN bind-key 10 c --modifier ctrl
epomaker --device /dev/hidrawN bind-key 10 a --second b
epomaker --device /dev/hidrawN bind-media 10 volume-up
epomaker --device /dev/hidrawN bind-mouse 10 left
epomaker --device /dev/hidrawN bind-macro 10 3 --mode held
epomaker --device /dev/hidrawN disable-key 10
epomaker --device /dev/hidrawN matrix --decoded
```

Keyboard bindings accept `--profile`, `--fn` and `--os-mode` as the raw `key` command does.
[CH585 mice](ch585-protocol.md) support 50 macro slots and shared binding commands,
but reject Fn/OS/submode banks. Mouse buttons use their model-specific slots;
use `mouse-matrix` to inspect them and `mouse-bind` for additional mouse actions.
Macro playback modes are `count`, `toggle` and `held`. Repeat count is stored in the
macro itself. Binding writes use the existing model gate and readback verification.
The `key` command remains available for four-byte actions not represented by a
semantic command. Decoded matrices retain every original action as `raw`.

## Editable macro files

```json
{
  "repeat": 1,
  "events": [
    {"hid_usage": 4, "down": true, "delay_ms": 10},
    {"hid_usage": 4, "down": false, "delay_ms": 10},
    {"type": "mouse_button", "button": "left", "down": true, "delay_ms": 20},
    {"type": "mouse_button", "button": "left", "down": false, "delay_ms": 20},
    {"type": "mouse_move", "dx": 20, "dy": -10, "delay_ms": 50}
  ]
}
```

Keyboard events may explicitly specify `"type":"keyboard"`; omitting it preserves
compatibility with the first CLI release. Mouse buttons are `left`, `right`, `middle`,
`back` and `forward`. Movement coordinates are signed integers from -128 to 127.
Delays are 1–65535 milliseconds. Repeat count is 0–65535, preserving the firmware
field without assigning an unverified meaning to zero. Entire encoded macros must
fit 256 bytes, including the two-byte repeat field.

```sh
epomaker --device /dev/hidrawN macro 3 macro.json
epomaker --device /dev/hidrawN get-macro 3 --decoded > editable.json
epomaker --device /dev/hidrawN get-macro 3 > raw.json
```

The vendor's compact mouse-motion encoder and decoder disagree on delay scaling.
New movement events always use the explicit 16-bit delay form, including short
delays. Decoding an existing compact-motion event fails with an explanation instead
of guessing its timing. Zero-delay and unknown events also fail semantic decoding;
raw export and configuration snapshots preserve their bytes without interpreting
them. The decoder processes events at the end of a completely full macro buffer.

The Macro page's raw export is a snapshot of the last successful load, with its
original slot number. Changing the destination slot or editing the decoded sequence
does not change that snapshot. New, successful JSON import, and accepted recordings
clear it. Use Export JSON for the current editable sequence; a raw export is not an
editable-macro JSON file and cannot be imported through that control.

This is based on the shipped `macroEventToByte`, `buffToMacroEvents`, `configToMatrix`
and mouse action table, documented in [the protocol reference](glyph-protocol.md).
Physical-device playback acceptance remains unverified.

## Named macro library

The Macro page can keep named entries on the Linux host independently of the
keyboard's numeric slots. Library operations work while disconnected. Each entry
contains an editable sequence and a preferred playback mode: count, toggle, or
held. Saving a library entry does not write the keyboard or assign a key; deleting
an entry does not erase a device slot.

Load an entry into the editor, choose its destination macro slot, then use Save
macro to write that slot. Assign the slot and its playback mode in Keymap. The
library's playback preference is metadata; loading it does not change an existing
key assignment. Editing a loaded sequence does not persist changes until the
library update action is used.

Names must be nonblank and at most 20 characters. Entries have stable generated
identifiers, so renaming does not change their identity. Updates and deletion use
revision checks: a stale browser tab must refresh before replacing newer saved
content. Errors preserve the existing saved entry and editor draft.

`epomaker serve` stores entries under
`~/.local/share/epomaker-driver-linux/macros`. Set `serve --library-dir PATH` to
choose another location. This directory is independent of `--backup-dir`, browser
storage, and the server's port or session token. Back up the library directory as
well as device snapshots: the keyboard backup does not contain host-side names or
library entries. Semantic JSON export contains the sequence only, not its library
identity or playback preference.

The library supports up to 4096 entries, each bounded to 1 MiB on disk and the
existing 256-byte encoded macro capacity. It uses private atomic JSON files and validates stored sequences before
returning them. Corrupt entries produce an error rather than being silently
discarded. This is an independent local library; vendor cloud synchronization and
vendor file compatibility remain open audit items.


## Focused input recording

The Macro page records keyboard events and mouse-button presses in its focused
capture pad. It supports left, right, middle, back and forward buttons. Releases
for buttons pressed inside the pad are tracked even when released outside it.
Start a recording, type the sequence, then stop or press Escape. Losing focus also
stops capture. Escape is reserved for leaving recording; add an Escape action in
the editor when needed. Browser/OS-reserved shortcuts and keys not delivered as
keyboard events cannot be captured. Pointer movement remains editable manually; continuous motion and wheel capture
are not included.

A recording creates a separate draft. Review and explicitly replace the editor to
use it; cancel/discard preserves the existing macro. Saving to a device and assigning
the macro slot remain separate actions. The backend validates the draft before it
replaces the editor. Oversized macros, unsupported keys and out-of-range measured
delays are reported instead of silently altering the saved editor sequence.

Measured timing records the interval between accepted actions on the preceding
action. Fixed timing uses the selected interval (1–65535 ms). Measured recordings
end with a 50 ms trailing delay; fixed recordings end with the selected delay.
Repeated keydown events are ignored. Held keys and mouse buttons receive generated release actions
when recording stops; review these actions before accepting the draft.

Vendor evidence: Windows `fd19495c.js` and macOS `918febcc.js` append each new
inter-event delay before the next action; the first action has no leading delay.
The index-bundle `stopRecording` appends a trailing measured 50 ms/fixed delay.
Adapters pair each action with the following delay when calling `macroEventToByte`.
Thus a sequence is action A, gap A-to-B, action B, trailing delay. This source
convention does not establish physical firmware playback timing.

The vendor rejects unmatched held inputs and saturates long gaps; this recorder
instead adds explicit releases and rejects unrepresentable timing. These are
intentional recording-workflow differences, not claims of verified device behavior.
Source files belong to [the pinned installer baseline](source-releases.json).


The same vendor recorder chunks install only `keydown`, `keyup`, `mousedown` and
`mouseup` listeners (around byte offsets 21520–21860 in both Windows `fd19495c.js`
and macOS `918febcc.js`). They contain no `mousemove` or `wheel` recording listener.
This identifies the audited recorder path; it is not proof that no other vendor
workflow can configure motion. Existing explicit motion events retain the long
16-bit delay encoding described above.
