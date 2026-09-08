# Migration status

Baseline: EPOMAKER Driver v4 3.2.22, Windows and macOS installers recorded in
[source-releases.json](source-releases.json). The objective is greater than 95%
feature parity. It has not been achieved, and there is no defensible overall
percentage until the inventory and weighting have been completed.

The [model inventory](model-inventory.md) records all 46 EPOMAKER catalog rows,
per-model feature gates and loader matches from both installers. Glyph, [RT85 CLI features](rt85.md) and [RT75 CLI configuration](rt75.md) are
enabled, plus [five RY6602 models](ry6602.md) with core configuration support.
[Two older YC3121 models](yc3121.md), RT100 and Dynatab75X-UK, additionally have
USB keymap/profile/macro/lighting/custom-picture/sleep/debounce/automatic-OS configuration.
[RT100 PRO](rt100pro.md) uses the shared modern YC3123 protocol and has its own
three-profile matrices and five-bank RGB565 display workflow.
[Both HE60 Lite variants](he60-lite-research.md) add two profiles with four
normal submodes each, Fn maps, macros, magnetic reads/actuation updates, OS controls,
main lighting and custom pictures, plus model-gated debounce/sleep.
[H60](ry5088-h60.md) additionally migrates the first RY5088 model with four
profiles and firmware-dependent magnetic precision.
[Three HE68 Lite IDs](ry5088-he68.md) add their own matrices and lossless
switch-type reads and selection to the same backend.
[Four additional wired RY5088 models](ry5088-wired.md) add model-specific Fn and
side-lighting gates. [Four wireless-capable models](ry5088-wireless.md) add USB
configuration with model-specific sleep timers and RF version handling.
[HE60 model 3746](ry5088-he60.md) adds its switch codes and catalog travel limits. [HE108 ID 3365](ry5088-he108.md) adds enabled partial USB support with source-confirmed matrices, side lighting, magnetic controls, and model-specific sleep/travel limits. [G84 HE Pro](g84-he-pro.md) adds its model-specific switch and limits. [HE65 V2](he65-v2.md) adds four-profile magnetic USB support, seven switch types, normal 24G/Bluetooth sleep timers and three knob slots. [HE75 V2](he75-v2.md) adds IDs 3518 and 3883 with model-specific profiles, four-effect `ei` side lighting and magnetic controls. [TMR model 3613](he75-tmr-3613.md) adds its two-profile variant. [HE75 Mag](he75-mag.md) adds four-profile magnetic USB support with a Windows Fn layer and model-specific switch codes. Thirty-eight
models are counted as partial backends; their feature coverage differs substantially.
[Magnetic recovery](he-recovery.md) adds backup and restore for all twenty-two
enabled magnetic IDs, including inactive fields and unreferenced macros.
[Five CH585 mice](ch585-protocol.md) add USB profiles, raw button mappings,
named button bindings and 50 macro slots, DPI and report-rate writes,
sleep/debounce/scroll timing, LOD, correction and
firmware-gated low latency, with verified readback.
[Mouse recovery](mouse-recovery.md) adds complete snapshots of supported settings,
eight profile observations and all 50 macro slots.
None has been verified against physical hardware. Shared vendor/product
IDs do not establish that another model speaks the same protocol.

| Capability | Implemented | Remaining validation or work |
| --- | --- | --- |
| Linux HID discovery | Sysfs descriptors and command collection classification | More hardware descriptors |
| USB and Bluetooth transport | Feature reports, Bluetooth envelopes, status filtering, timeouts | Physical device round trips |
| Model identification | Internal firmware ID and bootloader gate | Other protocol families |
| Key remapping | Glyph, RT85, RT75, five RY6602 models and RT100/Dynatab75X-UK migrated Fn layer 0 slots, named keyboard/media/mouse/macro bindings, matrix decoding, readback checks | Remaining action types and other families |
| Profiles | Model-specific profile counts and active selection; HE60 has four normal submodes per profile; model-checked configuration restore for 33 migrated keyboards and five mice; eight-profile support for five mice | Vendor export semantics and application-local magnetic caches, other models |
| Lighting | Glyph/RT85 main and side modes, RT75 main modes, RY6602 model-specific modes and color flags; five custom pictures with readback and per-slot editing; RT100/Dynatab75X-UK custom picture index 0; HE60 21 effects and three/five picture banks, with readback and per-slot editing | Hardware comparison and model-specific capabilities |
| Sleep and debounce | Glyph settings, RT85 sleep timers, RT75 sleep/debounce, RY6602 three-timer configuration; HE60 wired debounce and wireless three-timer sleep; sleep readback checks | Hardware limits and persistence |
| Macros | Keyboard/mouse/motion JSON editing, semantic decoding, raw export, playback bindings and verified readback | Recording, ambiguous legacy motion timing and hardware comparison |
| Screen | Glyph, RT85, RT75, RT100, Dynatab75X-UK and RT100 PRO, plus three RY6602 screens: still-image and animation CLI, RGB565/RGB24 conversion, memory limits, bounded transfer, five still banks, model-gated language/system-info and clock sync | Hardware comparison and remaining display settings |
| Backups | Nine modern models' key/Fn maps, referenced macros, lighting, custom RGB pictures, sleep, debounce, OS options; RT100/Dynatab schema 6 recovery with physical Fn layer 0; twenty-two magnetic models have schema 7 complete raw configuration and all 256 macros, with atomic pre-restore copies | Unreferenced macros on nonmagnetic models, screen pixels, and YC3121 manual OS options/OS-specific Fn banks |
| Magnetic keyboards | HE60 Lite, H60 and HE68 Lite magnetic-field reads, per-key actuation/rapid-trigger writes with complete-field readback, firmware-dependent scaling, normal/DKS/MT/toggle mode definitions and reciprocal snap pairing/removal with action readback, raw mode preservation, four submodes per profile and timed USB calibration with telemetry/cleanup | Persistent sensor calibration recovery, hardware comparison and GUI integration |
| OS controls | Glyph, RT85, RT75 and HE60 Windows/Mac selection, automatic selection, WASD swap with unrelated bytes preserved | Hardware behavior and other model capabilities |
| Receiver routing | Internal F6/F7/FC adapter, shared keyboard/mouse routing, status and bounded readiness; simulated integration tests | Verified descriptors, discovery integration, physical round trips, pairing and monitoring |
| Other keyboard families | RY6602 core key/Fn/macro, profile and OS controls; two older YC3121 models with normal maps and migrated Fn layer 0 addressing, profiles, macros, sleep, debounce, automatic OS selection, custom picture index 0 and display workflows; RT100 PRO full modern YC3123 backend | OS-specific YC3121 Fn banks and recovery; other model-specific protocols |
| Mice | Five CH585 models: USB identity/status, eight profiles, named/raw button bindings, 50 macro slots, model-specific DPI changes, report rate, sleep/debounce/scroll settings, sensor-gated LOD/correction and firmware-gated low latency | PAN1080 families, additional action types, motion-sync/FPS controls, battery and wireless routing |
| Device lifecycle | Disconnect errors | Reconnect, background monitoring, battery UI |
| System-information display | Linux CPU, memory, disk, network and temperature collection; bounded foreground refresh | Background integration, more sensor selection and physical display comparison |
| Desktop application | Local React interface: visual keymap, lighting, macros, display, settings and backups; loopback API and browser tests | Native packaging, localization, broader accessibility audit and remaining vendor workflows |
| Factory reset | Nine modern models: explicit CLI reset after saving settings and all 256 macro slots; five CH585 mice: schema-8 backup, reset and post-reset reads | Other backends, GUI integration, factory-state and reconnect hardware comparison |
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
