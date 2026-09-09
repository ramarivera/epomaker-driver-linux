# Glyph firmware workflow audit

Scope: raw EPOMAKER Driver v4.3.2.22 bundles from the
[pinned installer manifest](../source-releases.json). No network,
firmware download, device write, or bootloader operation was attempted. Offsets
below were obtained with Python `Path.read_bytes().find(...)`; the bundles contain
UTF-8 strings, so these are raw byte offsets.

Source files:

- Windows `dist/js/index.feaf50e4.js`, 2,556,505 bytes, SHA-256 `72fb76b3c19e013d81e450d5245bc62bb5a275fcf6623530a5a652b9c7182be5`.
- macOS `Contents/Resources/app/dist/js/index.5af2e057.js`, 2,565,198 bytes, SHA-256 `06c91320e6e5b0249fa9f80f055aa5e19099aa5762402cf7098ef8752a832286`.

## Glyph identity and applicability boundary

`bytes.find(b"id:3059")` is **896116** in both bundles. The record identifies
`Epomaker Glyph`, VID 12625, PID 20482, type `keyboard`, and includes keyboard
layout, sleep, lighting, knob, and screen metadata. No firmware image names,
component list, bootloader PID, or update-specific model override appears in this
model record. The record's runtime version fields are supplied by the connected
device object, not a Glyph-specific firmware manifest.

Therefore the update path below is shared controller code whose applicability to
Glyph must be gated by the runtime identity and transport. It is not evidence that
all returned firmware components exist for Glyph.

## Service metadata and image selection

The firmware service helper begins at these raw offsets:

- Windows `bytes.find(b"getFwVersion")` = **1254143**;
  `bytes.find(b"downloadAllDevUpgradeFile")` = **1254549**.
- macOS: **1259584** and **1259990**, respectively.

The helper calls `/get_fw_version` with `{dev_id}`. The bundles hard-code the
metadata API and download base URLs:

- Windows API URL occurrence at **1260554**: `https://api2.qmk.top:3816/api/v2`;
  download base begins at **1260592** as `https://api2.qmk.top:3816/download`.
- macOS API URL occurrence at **1265995**; download base begins at **1266033**.

The helper downloads `file_path`, then either inflates a raw payload or opens an
archive and extracts these fixed names: `firmwareFile.bin`,
`firmwareRFFile.bin`, `firmwareOledFile.bin`, `firmwareMledFile.bin`,
`firmwareNordicFile.bin`, and `firmwareFlashFile.bin` (Windows around 1254549;
macOS around 1259990). This is a vendor service dependency and component naming
contract, not a local signed-image or Glyph-specific manifest.

## Version display, selection, and component distinction

The shared display formatter is at Windows **1823422** and macOS **1832234**.
It emits the runtime device ID and available version fields as `USB`, keyboard /
mouse / dongle RF, Nordic, OLED, and MLED labels; the `flash` field is skipped in
the display string. This distinguishes keyboard, mouse, and receiver version
fields by runtime `deviceType.type`, but does not prove that a given device has
all of them.

`getFirmwareUpgradeListFromServer` is at Windows **1825366** and macOS
**1834178**. Its verified gates and selection logic are:

- return immediately unless the current device connection is exactly `usb`;
- query the current runtime device ID with `/get_fw_version`;
- split `version_str` on `_` into component version tokens;
- compare numeric portions, interpreted as hexadecimal, against the runtime
  `deviceType.version` fields; and
- return upgrade records for USB, RF, Nordic, MLED, OLED, or flash only when a
  matching newer archive member exists. The initial file check also requires
  the main `firmwareFile.bin` payload to be present.

This function does not require `deviceType.type === "keyboard"`; a USB mouse or
dongle can enter the shared selection path. The model ID is sent to the service,
so Glyph applicability depends on the service response and runtime component
fields, which were not available offline.

## Image validation and update commands

The low-level shared `upgradeFirmware` routine begins at Windows **1924429** and macOS
**1933241**. It only rejects a payload when the supplied byte array is no longer
than the supplied header offset (`t.length <= i`). It then strips that offset,
calculates 64-byte chunks, waits for a start-ready response, sends each chunk,
and checks a final checksum/length response. The [class trace](glyph-firmware-class-audit.md) now identifies the Glyph USB override.
The shared routine does not establish a cryptographic signature, model ID inside the image, or a local firmware-file
format validator.

Method dispatch is explicit at Windows **1926451** and macOS **1935263**:

- `usb` calls `dev.upgrade`;
- `rf` calls `dev.rfUpgrade`;
- `oled` calls `dev.oledUpgrade`;
- `flash` calls `dev.flashUpgrade`; and
- `nordic` and `mled` return `false` in this shared dispatcher.

The USB boot transition is at Windows **1925174** and macOS **1933986**. It first
accepts an already-matching VID/PID/usage/usage-page device; otherwise it sends a
boot command containing `[127,85,170,85,170,...]`, waits, and searches for a boot
device. RF boot entry/exit polling is at Windows **1925480** and macOS **1934292**;
it sends a separate `[248,85,170,85,170,...]` command and polls up to ten times.
These are controller commands, not Glyph-specific evidence.

## Recovery, reconnect, and failure behavior

The firmware state worker starts at Windows **1917691** and macOS **1926503**.
Before updating it stops lighting for a non-boot device, clears local device
configuration, stops dongle status polling, and marks upgrade state/progress.
After the component sequence it waits, clears the upgrade state, reports failure
with “unplug and retry” messaging, removes the old device, and emits a device-add
notification to rediscover it. A successful USB component increments a success
counter; the source does not prove that a Glyph physically reconnects or that
configuration is restored after update.

The UI translation source includes the explicit wired requirement: Windows raw
bytes **1362995** and **1364087** (macOS bytes **1371807** and **1372899**)
state that firmware upgrade requires connecting the data cable / wired mode and,
for the general message, removing the 2.4 GHz receiver. This is a shared UI
restriction consistent with the USB-only list gate, not a Glyph-only transport
proof.

## Bounded follow-up

The concrete next step is a **read-only model-3059 firmware applicability check**:
feed a captured or simulator-provided `/get_fw_version` response into the Linux
identity layer, verify which `version_str` tokens and component files are actually
returned for Glyph, and expose version display only for runtime fields present.
Before any implementation of firmware writes, add strict model/component/image
validation and an interruption/reconnect state machine matching the vendor's
remove-and-rediscover behavior. Do not infer a Glyph firmware image URL, boot PID,
signature scheme, Nordic/MLED support, or successful recovery from this shared
bundle path alone.

## Linux status

The Settings interface now shows the internal model ID, actual connection
transport and raw USB firmware code from the existing connection response. It
does not present the code as a semantic version. An explicit component read now
queries the inherited version getters, as documented in the class trace. Reconnection is required to refresh this cached identity. The
simulator UI and package build were checked; no physical device was queried.

The loader, inherited version getters and USB override are now documented in
[the class trace](glyph-firmware-class-audit.md). Remaining work includes obtaining an
authentic model-3059 metadata/image fixture, checking component applicability and
image validation, implementing the update/reconnect workflow, and validating
recovery on appropriate hardware. The shared routine alone is insufficient to
implement Glyph flashing. See [the release scope](glyph-v1.md).
