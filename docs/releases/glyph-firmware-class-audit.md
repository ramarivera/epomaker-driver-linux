# Glyph firmware class and component version trace

Baseline: [pinned installers](../source-releases.json). All offsets below are raw
UTF-8 byte offsets. No vendor firmware image or physical device was used.

## Raw sources

Windows main bundle:
`dist/js/index.feaf50e4.js`
(2,556,505 bytes), SHA-256
`72fb76b3c19e013d81e450d5245bc62bb5a275fcf6623530a5a652b9c7182be5`.

macOS main bundle:
`Contents/Resources/app/dist/js/index.5af2e057.js`
(2,565,198 bytes), SHA-256
`06c91320e6e5b0249fa9f80f055aa5e19099aa5762402cf7098ef8752a832286`.

The relevant dynamically loaded chunks are parallel across platforms:

| role | Windows file / SHA-256 | macOS file / SHA-256 |
|---|---|---|
| keyboard finder loader | `d915b681.js` / `881d3f587f1a6eab1986580775cd4232719cd86c44a889c94436e90b572bfa8d` | `6f31d22e.js` / `4f6d1831b2b29a6d4a7d322970c6e5ae44a549793c6a10230446b3e30356467e` |
| Glyph class | `ff90dc0d.js` / `ecec1279c4d681c8c673e3efc8156bffe720a2b69587659be5a612e2a5d465be` | `b774daff.js` / `088c4a668e7eceda8bb4df1923a755e038f2b754d431ffb75846dc8e4d8c6da2` |
| YC3123 controller | `17dc9c62.js` / `eb9f34119b3467a209723f43d8d468a69e3bfa7f9ad45c0d27a37d66d22ccc68` | `623d2d52.js` / `e4f4ca92f999856242fae8ac6d527bf930a44223d03a5e9665993718f965a6c6` |
| YC3123 boot/update helper | `c6c9152c.js` / `0fc084e085e4a98f3e43031ace986e6d5afcf3c15e2fb76297920f420776510f` | `2cea305b.js` / `2ae032a805ea728b43466eb8f08a0ffa84d4b8c338f9edf2ff38451a0d4d4078` |
| OLED/flash helper imported by controller | `eca87394.js` / `08c363a6023ee97399a7e04ccf98f3688fe6b676789488c5df5b11cffe09e23d` | `84fa03f2.js` / `240af911d8a386249aa58d47946062be4b1655ef0c8b9a3a4862c1d05a049129` |


## Confirmed runtime inheritance

Model 3059 at main-bundle byte 896116 selects the exact catalog name
`yc3123_hf_kf107_3m_oled_1k_rgb_kb_soc_v100`. Windows loader `d915b681.js`
byte 121920 maps it to `ff90dc0d.js`; macOS loader `6f31d22e.js` byte 120812
maps it to `b774daff.js`. The Glyph class defines matrices and extends the imported
YC3123 helper. That helper extends the controller in `17dc9c62.js` /
`623d2d52.js`. Glyph therefore inherits the controller's version getters, while
its intermediate helper overrides USB upgrade behavior.

For non-boot devices, the main initialization handler calls USB, RF, MLED and OLED
getters. The Windows RF call is at byte 2010438 and OLED at 2010520; corresponding
macOS calls are at 2019250 and 2019332. There is no USB-only condition around these
version reads. Firmware *updates* retain the separate USB gate described in
[the update workflow audit](glyph-firmware-workflow-audit.md).

The controller getters are anchored at byte 4080 (USB), 4328 (RF), 4574 (MLED)
and 4809 (OLED) in both platform chunks. They use the following **little-endian**
unsigned 16-bit fields; shifting the higher-index byte left by eight does not
make the wire format big-endian.

| Component | Query | Response bytes |
| --- | --- | --- |
| USB | `8F` | 7–8 |
| RF | `80` | 1–2 |
| MLED | `AE` | 1–2 |
| OLED | `AD` | 1–2 |
| Flash | same `AD` reply | 3–4 |

Zero fields represent an unavailable version. They do not establish that a
component is physically absent. The initializer does not invoke a Nordic getter
on this path. No physical response or transport reliability has been verified.

## USB helper correction

In `c6c9152c.js` / `2cea305b.js`, the exported controller helper overrides USB
upgrade and passes 65536 as the shared uploader's image offset. The shared routine
rejects images no longer than the offset, slices the image there, and divides the
remaining data into 64-byte chunks. This is not a 65536-byte transfer chunk size.

The helper's `checkIsCanStartUpgrade` receives chunk count and remaining byte
length, but places only chunk count in the `BA C0` packet at byte 8. Its
`checkUpgradeIsSuccess` receives chunk count, checksum and byte length; it writes
the count at byte 8 and checksum at byte 12 in `BA C2`, then checks reply byte 2
for `55`. These fields correct the earlier byte-length interpretation in
[glyph-protocol.md](../glyph-protocol.md). Checksums, accepted image format,
boot-device selection, interruptions and recovery still need verified fixtures.

## Linux component reads

Settings provides **Read component versions**, implemented by
`Keyboard.read_firmware_versions()` and the `firmware_versions` API read section.
It refreshes identity and queries all components under one transport transaction,
requires normal Glyph mode, and returns raw numeric codes or null for zero fields.
Malformed replies and timeouts fail the read; the interface clears the previous
result before a new query and on reconnect. It adds no automatic probes to normal
status/connection handling and no firmware writes.

Tests: `tests/test_glyph_versions.py`, `tests/test_versions.py`, and
`ui/tests/glyph-versions.spec.js`. Hardware component identification, update-image
validation and the complete update/recovery workflow remain unfinished.
