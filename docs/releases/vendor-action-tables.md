# Vendor action lookup tables

`src/epomaker_driver/data/vendor-action-tables.json` records functional name/code
mappings used by the shared action serializer. The Windows and macOS Driver v4
3.2.22 tables were parsed independently as data and compared for equality. No
vendor code was executed. Only the names/numeric identifiers and byte arrays are
retained, not vendor JavaScript or assets.

Sources are the main bundles listed in `docs/source-releases.json`:

- Windows `index.feaf50e4.js`, SHA-256
  `72fb76b3c19e013d81e450d5245bc62bb5a275fcf6623530a5a652b9c7182be5`.
- macOS `index.5af2e057.js`, SHA-256
  `06c91320e6e5b0249fa9f80f055aa5e19099aa5762402cf7098ef8752a832286`.

The following zero-based UTF-8 byte offsets point to opening object braces in
both bundles. Their surrounding minified variable names can differ.

| Table | Offset | Entries | Representation |
| --- | ---: | ---: | --- |
| Function base | 211,728 | 80 | Named function to byte array |
| Function addition | 213,603 | 1 | Countdown function |
| Gamepad | 213,630 | 54 | Named input to byte array |
| Mouse | 214,671 | 49 | Numeric enum value to byte array |

The mouse object uses computed enum members, whose numbers are resolved from
its preceding enum declaration. Negative identifiers such as `-1000` are stored
as JSON object keys; action records carry the identifier as an integer.
The extraction rejects unparsed entries and duplicate keys instead of silently
skipping them. Exact decoded mappings, including empty arrays, match across both
platforms.

The function table needs one subtlety: `zu = Object.assign(xk, {})` and
`Ek = Object.assign(xk, Hv)` share the `xk` object. The latter assignment adds
countdown to the object returned by `$v(false)` too. The merged table therefore
contains 81 entries. The inverse parser's previously computed array of function
values is a separate matter; these mappings support encoding, not a promise of
lossless vendor inverse parsing.

An empty array is an unresolved placeholder, not a four-byte disabled action.
The codec rejects the sniper placeholder and the two empty mouse key placeholders.
The gamepad table contains sentinel values beginning `ff ff ff`; retaining those
values does not prove that Glyph accepts them. Other surprising values (for
example the mouse DPI decrement tuple and the function F13 tuple) are retained
exactly rather than normalized into inferred behavior.

See `docs/releases/glyph-action-serializer-audit.md` for byte formulas. The pure
codec in `src/epomaker_driver/vendor_actions.py` does not perform HID I/O or decide
whether a shared-driver action is applicable to Glyph. A record importer still
needs model/target validation, physical-slot mapping, replacement semantics and
explicit handling of external macro or host-service dependencies.
