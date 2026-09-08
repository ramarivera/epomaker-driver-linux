# Migration status

Baseline: EPOMAKER Driver v4 3.2.22, Windows and macOS installers recorded in
[source-releases.json](source-releases.json). The objective is greater than 95%
feature parity. It has not been achieved, and there is no defensible overall
percentage until the inventory and weighting have been completed.

The catalog contains 46 EPOMAKER models. Glyph, [RT85 CLI features](rt85.md) and [RT75 CLI configuration](rt75.md) are
enabled, plus [five RY6602 models](ry6602.md) with core configuration support.
[Two older YC3121 models](yc3121.md), RT100 and Dynatab75X-UK, additionally have
USB keymap/profile/macro/lighting/custom-picture/sleep/debounce/automatic-OS configuration. Ten models have
some backend support; their feature coverage differs substantially.
None has been verified against physical hardware. Shared vendor/product
IDs do not establish that another model speaks the same protocol.

| Capability | Implemented | Remaining validation or work |
| --- | --- | --- |
| Linux HID discovery | Sysfs descriptors and command collection classification | More hardware descriptors |
| USB and Bluetooth transport | Feature reports, Bluetooth envelopes, status filtering, timeouts | Physical device round trips |
| Model identification | Internal firmware ID and bootloader gate | Other protocol families |
| Key remapping | Glyph, RT85, RT75, five RY6602 models and RT100/Dynatab75X-UK migrated Fn layer 0 slots, named keyboard/media/mouse/macro bindings, matrix decoding, readback checks | Remaining action types and other families |
| Profiles | Per-model three/four matrices; active profile selection; model-checked configuration restore for eight migrated models | Vendor export semantics, other models |
| Lighting | Glyph/RT85 main and side modes, RT75 main modes, RY6602 model-specific modes and color flags; five custom pictures with readback and per-slot editing; RT100/Dynatab75X-UK custom picture index 0 with readback and per-slot editing | Hardware comparison and model-specific capabilities |
| Sleep and debounce | Glyph settings, RT85 sleep timers, RT75 sleep/debounce, RY6602 three-timer configuration; sleep readback checks | Hardware limits and persistence |
| Macros | Keyboard/mouse/motion JSON editing, semantic decoding, raw export, playback bindings and verified readback | Recording, ambiguous legacy motion timing and hardware comparison |
| Screen | Glyph, RT85, RT75, RT100 and Dynatab75X-UK, plus three RY6602 screens: still-image and animation CLI, RGB565/RGB24 conversion, memory limits, bounded transfer, five still banks, model-gated language/system-info and clock sync | Hardware comparison and remaining display settings |
| Backups | Eight migrated models' key/Fn maps, referenced macros, lighting, custom RGB pictures, sleep, debounce, OS options; RT100/Dynatab schema 6 recovery with physical Fn layer 0 and atomic pre-restore copies | Unreferenced macros, screen pixels, and YC3121 manual OS options/OS-specific Fn banks |
| OS controls | Glyph, RT85 and RT75 Windows/Mac selection, automatic selection, WASD swap with unrelated bytes preserved | Hardware behavior and other model capabilities |
| Receiver routing | Internal F6/F7/FC adapter, shared keyboard/mouse routing, status and bounded readiness; simulated integration tests | Verified descriptors, discovery integration, physical round trips, pairing and monitoring |
| Other keyboard families | RY6602 core key/Fn/macro, profile and OS controls; two older YC3121 models with normal maps and migrated Fn layer 0 addressing, profiles, macros, sleep, debounce, automatic OS selection, custom picture index 0 and display workflows | OS-specific YC3121 Fn banks and recovery; other model-specific protocols |
| Mice | Research only | DPI, buttons, sensors, lighting, polling and other vendor controls |
| Device lifecycle | Disconnect errors | Reconnect, background monitoring, battery UI |
| System-information display | Linux CPU, memory, disk, network and temperature collection; bounded foreground refresh | Background integration, more sensor selection and physical display comparison |
| Desktop application | Local React interface: visual keymap, lighting, macros, display, settings and backups; loopback API and browser tests | Native packaging, localization, broader accessibility audit and remaining vendor workflows |
| Factory reset | Eight migrated models: explicit CLI reset after saving settings and all 256 macro slots | GUI integration, factory-state and reconnect hardware comparison |
| Firmware management | Research only | Image validation, upgrade transport and recovery |
| Vendor online services | Research only | Accounts, community, cloud profiles and supported service integrations |
| Installation | Python package and CLI | Desktop packaging, permissions integration and upgrades |

Shared protocol methods are filtered by [vendor capability gates](capability-gates.md); Glyph polling-rate configuration is not a vendor UI feature.

The graphical interface is documented in [control-interface.md](control-interface.md).

Tests cover independently authored packet fixtures, simulated firmware round trips,
malformed responses, disconnects and file handling. CI requires at least 98% combined
statement/branch coverage for the implemented Python package. This is a regression
gate, not a feature-parity score or proof of hardware compatibility.

For a capability to count toward verified parity, record the corresponding vendor
behavior, Linux implementation, offline tests and a successful hardware or service
comparison. Keep unavailable or unimplemented features in the denominator rather
than silently removing them.
