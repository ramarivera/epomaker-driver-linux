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

Bindings accept `--profile`, `--fn` and `--os-mode` as the raw `key` command does.
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

This is based on the shipped `macroEventToByte`, `buffToMacroEvents`, `configToMatrix`
and mouse action table, documented in [the protocol reference](glyph-protocol.md).
No recording service or physical-device acceptance has been verified yet.
