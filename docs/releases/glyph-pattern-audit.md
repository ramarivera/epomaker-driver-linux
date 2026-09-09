# Glyph custom pattern audit

Baseline: [pinned installer manifest](../source-releases.json), Windows/macOS
v4 3.2.22. These are source findings; physical LED correspondence and persistence
are not verified.

The Glyph model 3059 references the `Ur` main-light catalog, which exposes five
`LightUserPicture` choices. See Windows `index.feaf50e4.js`, around bytes
895939–896500 for the model and 570281–571900 for the light catalog. The five
choices select banks; `maxValue:4` is the brightness range. The matching functional
metadata is retained in
[`glyph-lighting-capabilities.json`](../../src/epomaker_driver/data/glyph-lighting-capabilities.json).

The custom editor stores frames with an `allKey` array of key/color records and a
delay. The static path uses its first frame. The UI converts each key through a
HID code and duplicate-occurrence index before `setLightPic` (Windows index bytes
1938700–1940000). Readback reverses the mapping through HID plus occurrence
(1936900–1938000). A HID usage alone is insufficient when keys share an identity.

The sender in `17dc9c62.js`, bytes 6453–7512, resolves those identities against
the default matrix and places each RGB triple at `matrixSlot * 3`. Its packet
sender writes seven chunks: six of 56 bytes and a final 42 meaningful bytes,
totalling 378 bytes or 126 RGB triples. Bank indices are zero based. The reader
omits triples whose mapped HID is zero or undefined; this does not establish that
all raw slots correspond to physical LEDs. The Linux raw-slot editor preserves
every one of the 126 positions.

The shared saved-record workflow serializes `framesJson`, generates a preview,
compresses the record, and passes it to IOT DB helpers (Windows index bytes
1861500–1867000). The reviewed code does not establish a portable Glyph pattern
file contract. Linux JSON import/export is therefore an independent format, not
vendor database-file compatibility. See [the format](../glyph-patterns.md).

The same editor also has undo/redo and dynamic frames. Their precise Glyph
applicability, saved-record management, and local/service dependencies need further
control-level tracing. They are not considered complete merely because raw bank
read/write or portable JSON now exists.

The [candidate key-to-slot crosswalk](glyph-pattern-key-slots.json) resolves all
86 layout entries, including Fn and the three knob actions, against their exact
default-matrix records. Each resolves to the first matching occurrence, consistent
with the current Linux keymap. The vendor lookup scans matching four-byte records
and uses an occurrence index (`17dc9c62.js`, byte 13823). This is source-derived
correspondence, not a physical LED test.

The matrix contains 37 all-zero records. The final two slots, 126 and 127, are
zero and outside the transmitted 126-triple payload. Five nonzero records are not
represented by the visual layout: 75, 102, 103, 114 and 115. Slots 102 and 103 are
second occurrences of Backspace and Enter. Their electrical meaning is not
established; retain raw colors rather than silently attaching them to visible keys.

Remaining work includes validating the crosswalk against physical LEDs, testing all
five banks and their activation/persistence across supported transports, and
finishing applicable saved-pattern/editor workflows. No vendor code or assets
are included in this document.
