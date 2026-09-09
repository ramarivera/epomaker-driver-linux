# Vendor capability gates

Protocol methods are not sufficient evidence of a feature being supported by a
particular model or connection. The application also gates controls by model metadata,
firmware version, and connection type. These conditions belong in the parity inventory.

## Glyph polling rate

The recovered base protocol `623d2d52.js`, lines 1708–1762, implements query 0x83
and setter 0x03, using byte 2 codes 0–6 for 8000, 4000, 2000, 1000, 500, 250,
and 125 Hz. This is a shared keyboard-family method, not a Glyph capability claim.

In `index.5af2e057.js` (pretty research copy lines 111575–111580),
`isSupportReportRate` rejects Bluetooth and keyboard models whose declared rate is
missing or at most 1000 Hz. Glyph is the 1k YC3123 model, with no higher polling-rate
override in its catalog entry (lines 62378–62410). Its vendor UI consequently does not
expose that setter. The Linux implementation retains the reported value in status
without adding a configuration control or claiming a missing Glyph parity feature.

Higher-rate models need their own metadata, firmware gate, protocol validation and
hardware comparison before enabling this shared setter. A command that can be encoded
must not automatically become a writable capability for every catalog entry.

## Glyph debounce

Both vendor builds require `other.deBounce` before exposing this control. Glyph
does not declare that property. See [the source audit](releases/glyph-settings-audit.md).
Glyph status and backups therefore leave debounce null without querying `86`; the
setter rejects Glyph before writing `06`. Legacy numeric Glyph snapshot values are
validated and ignored on restore, with an explicit limitation in the result. Other
models retain their existing debounce behavior.

## Factory reset

The Glyph base protocol's `reset(true)` sends opcode 0x01 and waits two seconds.
The vendor application exposes factory reset separately from firmware upgrade. The
Linux CLI and Glyph interface implement that operation with a recovery snapshot saved first;
see [snapshots.md](snapshots.md). Sending the command and verifying actual factory
state remain separate outcomes.
