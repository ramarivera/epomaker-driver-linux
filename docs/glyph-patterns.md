# Glyph custom color patterns

The Glyph custom-color editor manages five device banks, numbered Pattern 1–5
in the interface. Each bank contains 126 RGB triples (378 bytes). The numbered
color slots preserve wire order; the grid is not a verified drawing of the
keyboard's physical LED positions.

Use New pattern to start with all slots black, or load a bank from a connected
Glyph. Paint individual slots with Paint color, or use Fill all. Creating,
editing, importing, and exporting a draft work offline. Save pattern is the
separate device write and verifies readback. Selecting a different bank clears
the current draft; export changes first if they need to be retained.

Saving colors does not activate their bank. To display a saved pattern, select
the main User picture effect and the matching Pattern 1–5 option, then apply
lighting. This selection is distinct from the Custom colors destination bank.

## Portable JSON format

The independent Linux pattern format is an object with exactly these fields:

| Field | Required value |
| --- | --- |
| `schema` | `"epomaker-glyph-pattern"` |
| `version` | `1` |
| `model_id` | `3059` |
| `colors` | An array of exactly 126 strings, each six hexadecimal RGB digits without `#` |

Colors are normalized to lowercase. For example, a slot color `"12abef"` means
red `0x12`, green `0xab`, and blue `0xef`. Array position zero is color slot zero.
All positions, including black and otherwise unused slots, are retained.

Import validates the complete file before replacing the draft. Wrong models,
unknown fields, unsupported versions, invalid colors/counts, and files larger
than 64 KiB are rejected without altering it. Import preserves the selected
destination bank; the file does not choose a bank or activate an effect.

Export writes the current editable draft as `glyph-pattern-N.json`, where N is
the selected destination bank's UI number. This is not a raw snapshot whose
filename claims an original source bank. The same pattern can be imported into
any of the five banks.

This format is not advertised as compatible with vendor configuration or cloud
files. Vendor file compatibility, physical key/LED correspondence, and real
color/persistence behavior remain verification work. See the
[Glyph protocol](glyph-protocol.md) and
[release inventory](releases/glyph-v1-features.md).
