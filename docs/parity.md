# Migration status

Baseline: EPOMAKER Driver v4 3.2.22, Windows and macOS installers recorded in
[source-releases.json](source-releases.json). The objective is greater than 95%
feature parity. It has not been achieved, and there is no defensible overall
percentage until the inventory and weighting have been completed.

The catalog contains 46 EPOMAKER models. Only the Glyph implementation is currently
enabled; it has not been verified against physical hardware. Shared vendor/product
IDs do not establish that another model speaks the same protocol.

| Capability | Implemented | Remaining validation or work |
| --- | --- | --- |
| Linux HID discovery | Sysfs descriptors and command collection classification | More hardware descriptors |
| USB and Bluetooth transport | Feature reports, Bluetooth envelopes, status filtering, timeouts | Physical device round trips |
| Model identification | Internal firmware ID and bootloader gate | Other protocol families |
| Key remapping | Glyph key/Fn slots, named keyboard/media/mouse/macro bindings, matrix decoding, readback checks | Visual editor, remaining action types and other families |
| Profiles | Three Glyph matrices; active profile selection; versioned configuration restore | Vendor export semantics, other models |
| Lighting | Main and side modes; five custom pictures with readback and per-slot editing | Hardware comparison and interactive editor |
| Sleep and debounce | Read/write APIs and CLI | Hardware limits and persistence |
| Macros | Keyboard/mouse/motion JSON editing, semantic decoding, raw export, playback bindings and verified readback | Recording, visual editor, ambiguous legacy motion timing and hardware comparison |
| Screen | Still-image CLI, RGB565 conversion, bounded frame transfer, clock sync | Image/GIF UI, playback and display settings, hardware comparison |
| Backups | Key/Fn maps, referenced macros, lighting, custom RGB pictures, sleep, debounce, OS options; recovery copies and readback | Unreferenced macros and screen pixels |
| OS controls | Windows/Mac selection, automatic selection, WASD swap with unrelated bytes preserved | Hardware behavior and other model capabilities |
| Receiver routing | Research only | F6/F7/FC/FE transport and paired-device handling |
| Other keyboard families | Catalog only | Older YC3121 and model-specific protocols |
| Mice | Research only | DPI, buttons, sensors, lighting, polling and other vendor controls |
| Device lifecycle | Disconnect errors | Reconnect, background monitoring, battery UI |
| Desktop application | Not started | Layout editor, settings pages, localization, accessibility |
| Firmware management | Research only | Image validation, upgrade transport and recovery |
| Vendor online services | Research only | Accounts, community, cloud profiles and supported service integrations |
| Installation | Python package and CLI | Desktop packaging, permissions integration and upgrades |

Tests cover independently authored packet fixtures, simulated firmware round trips,
malformed responses, disconnects and file handling. CI requires at least 98% combined
statement/branch coverage for the implemented Python package. This is a regression
gate, not a feature-parity score or proof of hardware compatibility.

For a capability to count toward verified parity, record the corresponding vendor
behavior, Linux implementation, offline tests and a successful hardware or service
comparison. Keep unavailable or unimplemented features in the denominator rather
than silently removing them.
