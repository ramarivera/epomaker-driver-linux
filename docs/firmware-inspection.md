# Offline firmware inspection

`epomaker inspect-firmware download.bin --version 'v1'` inspects a local vendor
container and emits JSON. Supply the exact service `version_str`: multiple
nonempty underscore-separated tokens select ZIP; otherwise the vendor expects
raw DEFLATE. The filename does not select the format.

The command never opens a HID device, downloads firmware, or flashes it.
It reports structural facts and hashes, with `write_ready: false`. A valid
container is not evidence that an image is authentic or belongs to Glyph.
The 65,536-byte main/OLED prefix remains opaque. Payload chunk counts and the
additive uint32 checksum describe the recovered uploader, not a signature.

ZIP members use the exact root filenames recorded in the
[image audit](releases/glyph-firmware-image-audit.md). The inspector requires a
main image and rejects unknown/duplicate members, malformed streams and excessive
input or decompression sizes. This is deliberately stricter than the vendor
loader's silent handling of missing components. Nothing is extracted to disk.
RF, MLED and Nordic component presence does not establish applicability; their
image metadata alone cannot authorize an update. Flash uses distinct framing.

The implementation and synthetic adversarial fixtures are in
`src/epomaker_driver/firmware.py` and `tests/test_firmware.py`; CLI integration is
in `src/epomaker_driver/cli.py` and `tests/test_firmware_cli.py`.
Authentic model-3059 service metadata and image fixtures, component applicability,
bootloader discovery, physical validation, and update/recovery remain unfinished.
