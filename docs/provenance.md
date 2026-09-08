# Protocol evidence and provenance

The interoperability analysis used these user-provided releases:

- EPOMAKER_Driver_v43.2.22_MAC2026072.zip
- EPOMAKER_v4_setup_3.2.22_WIN2026071.zip

Both advertise application version 3.2.22. Their device catalog literal metadata and generated
protobuf schemas agreed after build-specific names were normalized. Native executables were
not launched. The analysis identified multiple independent controller protocols, so opcodes
must not be treated as universal EPOMAKER commands.

The repository contains independently authored Python code, functional device descriptors,
key matrices, and test packet vectors. Vendor executable/JavaScript/UI assets stay outside
this public repository. The source release hashes are in source-releases.json.

Glyph identity is 3059; USB 3151:5002; Bluetooth 3151:5004. Its packet checksum is an additive
header complement at byte 7 or 8. Its 428x142 screen uses RGB565, high-byte first, column-major.
The packet fixture file records six cases generated from isolated encoder methods with fake
transports: identity, key write, sleep times, white lighting, screen preparation, screen chunks.
These are algorithm-level fixtures, not captured hardware responses.

Linux transport behavior was checked against primary documentation/source:

- https://docs.kernel.org/hid/hidraw.html
- https://github.com/torvalds/linux/blob/master/drivers/hid/hidraw.c
- https://github.com/libusb/hidapi/blob/master/linux/hid.c

The implementation does not assume that the vendor's qmk.top domain implies QMK/VIA support.
