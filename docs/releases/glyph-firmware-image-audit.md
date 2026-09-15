# Glyph 3059 firmware image and component target audit

This audit follows the unresolved image/container boundary from the existing
[workflow](glyph-firmware-workflow-audit.md) and [class trace](glyph-firmware-class-audit.md).
It is a static source audit only: no vendor executable, network request,
firmware image, device write, or bootloader operation was used. Offsets are
zero-based UTF-8 byte offsets verified with `read_bytes().find()`.

## Source evidence

| Role | Windows source / SHA-256 | macOS source / SHA-256 |
| --- | --- | --- |
| Main bundle | `index.feaf50e4.js`, 2,556,505 bytes / `72fb76b3c19e013d81e450d5245bc62bb5a275fcf6623530a5a652b9c7182be5` | `index.5af2e057.js`, 2,565,198 bytes / `06c91320e6e5b0249fa9f80f055aa5e19099aa5762402cf7098ef8752a832286` |
| Glyph class | `ff90dc0d.js` / `ecec1279c4d681c8c673e3efc8156bffe720a2b69587659be5a612e2a5d465be` | `b774daff.js` / `088c4a668e7eceda8bb4df1923a755e038f2b754d431ffb75846dc8e4d8c6da2` |
| Glyph USB helper | `c6c9152c.js` / `0fc084e085e4a98f3e43031ace986e6d5afcf3c15e2fb76297920f420776510f` | `2cea305b.js` / `2ae032a805ea728b43466eb8f08a0ffa84d4b8c338f9edf2ff38451a0d4d4078` |
| YC3123 controller | `17dc9c62.js` / `eb9f34119b3467a209723f43d8d468a69e3bfa7f9ad45c0d27a37d66d22ccc68` | `623d2d52.js` / `e4f4ca92f999856242fae8ac6d527bf930a44223d03a5e9665993718f965a6c6` |
| OLED/flash helper | `eca87394.js` / `08c363a6023ee97399a7e04ccf98f3688fe6b676789488c5df5b11cffe09e23d` | `84fa03f2.js` / `240af911d8a386249aa58d47946062be4b1655ef0c8b9a3a4862c1d05a049129` |

The main bundle's Glyph catalog record is byte **896,116** (`id:3059`), with
`other.isYC3123:true`, `layer:3`, and screen metadata. The existing class audit
establishes that the model loader selects `ff90dc0d.js`/`b774daff.js`, which
inherits the YC3123 controller and uses the Glyph USB helper. These are routing
facts; shared component names and protocol routines do not prove that every
component exists on Glyph.

## Container and member selection

The unique `downloadAllDevUpgradeFile` declaration is Windows byte **1,254,549**
(macOS **1,259,990**). Its complete inspected body names the archive members:

```text
firmwareFile.bin, firmwareRFFile.bin, firmwareOledFile.bin,
firmwareMledFile.bin, firmwareNordicFile.bin, firmwareFlashFile.bin
```

It splits the service `version_str` on `_`. When more than one token exists, it
opens the downloaded archive and looks up those fixed member names; when there
is only one token, it raw-inflates the downloaded response as the main `fw`
payload. The returned object is `{fw, fwRF, fwOled, fwMled, fwNordic, fwFlash}`.
This is the only image/container contract established by the source. No local
filename convention, archive manifest, model field, or signature is shown in
this loader body.

The selection declaration `getFirmwareUpgradeListFromServer` is Windows byte
**1,825,366** (macOS **1,834,178**). It requires `connect === "usb"`, requests
metadata by runtime `deviceType.id`, and compares hexadecimal numeric portions
of version tokens to runtime component versions. Token 0 selects `fw` as USB;
later tokens containing `rfv`, `nordicv`, `mledv`, `oledv`, or `flashv` select the
corresponding archive member when present and newer. The source explicitly
checks that the main `fw` exists before returning candidates. This maps names to
targets, but the bundle contains no captured model-3059 service response to
prove which candidates the service actually returns for Glyph.

## Glyph USB image header and upload

The Glyph USB helper's unique declarations are in `c6c9152c.js`:
`checkIsCanStartUpgrade=` byte **116**, `checkUpgradeIsSuccess=` **334**,
`upgrade_usb=` **603**, and exported `upgrade=async` **927**. The inspected
wrapper calls the inherited uploader as:

```text
s.upgrade_usb(e, 65536, 10, progress)
```

The shared uploader is `upgradeFirmware=async` at main-bundle byte **1,924,429**.
Its full body rejects only when `image.length <= headerOffset`, slices the image
at that offset, sends the remainder in 64-byte chunks, and computes a checksum
over the sliced remainder. The checksum helper `zo` at Windows main-bundle byte
**219,141** sums byte values (`reduce` from zero); the completion packet
serializes the sum modulo 2^32 as a little-endian uint32. This is an additive
checksum, not a cryptographic integrity check. The Glyph wrapper therefore treats the first **65,536
bytes** as a non-uploaded header/prefix; it does not establish what fields that
prefix contains or validate its contents. The `BA C0` start packet puts the
little-endian chunk count at byte 8; the `BA C2` completion packet puts chunk
count at byte 8 and checksum at byte 12, and accepts reply byte 2 equal to
`0x55`. These are protocol acknowledgements, not image authenticity checks.

The same `c6c9152c.js` body sets `setUint8(0,186)` and `setUint8(1,192)` for
start, and `setUint8(0,186)`/`setUint8(1,194)` for completion. It does not parse a
model identifier, version header, length field, CRC header, or signature before
upload. A safe Linux parser must therefore treat the 65,536-byte prefix as
opaque and require independently captured fixtures before attempting to
interpret or rewrite it.

## OLED, flash, RF, MLED, and Nordic distinctions

The YC3123 controller dispatch declaration is at `17dc9c62.js` byte **37,105**.
Its selected methods are `upgrade` for USB, `rfUpgrade` for RF,
`oledUpgrade` for OLED, `flashUpgrade` for flash, while the shared dispatcher
returns false for Nordic and MLED. The Glyph USB helper is a distinct override;
it must not be generalized to the other archive members.

The OLED/flash helper's `upgrade=async` declaration is `eca87394.js` byte
**1,050**. Its complete body independently requires `image.length > 65,536`,
slices at 65,536, sends 64-byte chunks, computes a checksum over the sliced
payload, and checks an OLED boot acknowledgement. Its `flashUpgrade` declaration
at byte **1,830** uses 56-byte chunks and a separate `FEA_CMD_GETTFTFLASHDATA`
handshake. These two paths establish different framing and offsets; neither
proves that the Glyph catalog's screen metadata implies an available OLED or
flash firmware image.

The existing class trace records runtime version queries for USB, RF, MLED, and
OLED (with flash sharing the OLED reply), but zero fields mean unavailable
version data. Runtime getters and archive member names are not proof of physical
component presence. No static routing record in the inspected Glyph catalog
adds a boot PID, image header schema, or component-specific model override.

## Actionable parser boundary

The source supports a conservative Linux implementation boundary:

1. Validate the service/container envelope, member names, decompression result,
   and non-empty main member before exposing candidates.
2. For Glyph USB, preserve and hash the complete image, treat bytes 0–65,535 as
   opaque, and validate only the uploader-level payload length/chunk/checksum
   contract until an authentic fixture establishes header semantics.
3. Keep USB, RF, OLED, flash, MLED, and Nordic members separate. Do not route an
   archive member solely because its name exists.
4. Require runtime model 3059, wired USB, matching component version metadata,
   and an explicit component target before any future write path.

The bundle does **not** establish a cryptographic checksum/signature, model ID
inside the image, archive manifest schema, bootloader PID for Glyph, or a
service response proving which of USB/RF/OLED/MLED/Nordic/flash targets Glyph
actually exposes. Those require captured vendor metadata/images or hardware
validation before implementation.
