# Glyph v1 feature inventory

Source of truth: [glyph-v1-features.json](glyph-v1-features.json). This is a **provisional workflow checklist**, not a closed vendor feature inventory or a completion percentage. It refines the [17 release acceptance areas](glyph-v1.md).

The 62 rows include two evidence-backed exclusions (configurable polling rate and debounce). Applicability and source mapping remain open for several workflows. All hardware results remain unverified. “Implemented” describes offline implementation only; “partial” is not a percentage.

Audit pointers in the JSON are starting points for source review, not claims that every referenced behavior has been verified. Do not use the row count as the denominator for a 100% claim until the individual Windows/macOS Glyph controls and connection restrictions have been reconciled.

| ID | Workflow | Implementation | Applicability |
| --- | --- | --- | --- |
| G01.1 | Wired USB discovery and connect | partial | expected |
| G01.2 | Bluetooth discovery and connect | partial | expected |
| G01.3 | 2.4G receiver discovery and connect | unresolved | pending-audit |
| G02.1 | Identity and firmware display | partial | expected |
| G02.2 | Battery and online state | partial | expected |
| G02.3 | Disconnect, reconnect, and stale-state reset | partial | expected |
| G02.4 | Sleep/wake or transport-change continuity | missing | pending-audit |
| G03.1 | Read and edit normal keymap | partial | expected |
| G03.2 | Fn Windows layer keymap | partial | expected |
| G03.3 | Fn Mac layer keymap | partial | expected |
| G03.4 | Knob/encoder actions | partial | expected |
| G03.5 | Action validation, restrictions, and readback | partial | expected |
| G04.1 | Select and persist profile | partial | expected |
| G04.2 | Keyboard options/system-WASD settings | partial | expected |
| G04.3 | Automatic OS selection | partial | expected |
| G04.4 | Sleep timer settings | partial | expected |
| G04.5 | Debounce setting and bounds | not-applicable | excluded |
| G04.6 | Report-rate selection | not-applicable | excluded |
| G05.1 | Macro slot storage and read/write | partial | expected |
| G05.2 | Macro editor/import/export | partial | expected |
| G05.3 | Macro delays, repeats, and playback modes | partial | expected |
| G05.4 | Mouse-motion macro semantics | partial | expected |
| G05.5 | Macro recording and playback verification | partial | expected |
| G05.6 | Named macro library and local persistence | partial | expected |
| G06.1 | Main lighting effect catalog and controls | partial | expected |
| G06.2 | Side lighting effect catalog and controls | partial | expected |
| G06.3 | Lighting persistence, off, and readback | partial | expected |
| G06.4 | Conditional brightness, speed, RGB, rainbow, and music controls | partial | expected |
| G07.1 | Select and persist picture bank | partial | expected |
| G07.2 | Edit per-key RGB picture pixels | partial | expected |
| G07.3 | Picture import/export and full bank correspondence | missing | expected |
| G08.1 | Host live-light USB gating | unresolved | pending-audit |
| G08.2 | Live-light capture/stream lifecycle | missing | expected |
| G09.1 | Still-image conversion and screen upload | partial | expected |
| G09.2 | Animation conversion, timing, and frame capacity | partial | expected |
| G09.3 | Display bank selection, clear, and asset editor | partial | expected |
| G09.4 | Display transfer interruption and retry handling | partial | expected |
| G10.1 | Clock synchronization and physical display | partial | expected |
| G10.2 | Display language toggle | partial | expected |
| G10.3 | Host statistics/system information | partial | expected |
| G10.4 | Background refresh, suspend, and lifecycle updates | missing | expected |
| G11.1 | Backup managed keyboard state | partial | expected |
| G11.2 | Preserve unreferenced macro slots | implemented | expected |
| G11.3 | Vendor snapshot import/export | missing | expected |
| G11.4 | Screen asset backup and readback limits | partial | expected |
| G12.1 | Factory reset command and safety backup | partial | expected |
| G12.2 | GUI reset/reconnect workflow | partial | expected |
| G12.3 | Recovery restore after interrupted operation | partial | expected |
| G13.1 | Firmware version and bootloader awareness | partial | expected |
| G13.2 | Firmware update and recovery | missing | expected |
| G14.1 | Vendor account/cloud/profile workflows applicable to Glyph | unresolved | pending-audit |
| G14.2 | Firmware retrieval and update-service dependencies | unresolved | pending-audit |
| G15.1 | Install and launch desktop application | partial | expected |
| G15.2 | USB permissions and access errors | partial | expected |
| G15.3 | Persistence, update, and uninstall | missing | expected |
| G15.4 | Background lifecycle and tray behavior | missing | expected |
| G16.1 | Integrated desktop pages for keymap/light/macros/display/settings | partial | expected |
| G16.2 | Responsive/accessibility behavior | partial | expected |
| G16.3 | Clear unsupported-feature explanations | partial | expected |
| G17.1 | Source evidence and protocol traceability | partial | expected |
| G17.2 | Simulated end-to-end workflow coverage | partial | expected |
| G17.3 | Physical USB/Bluetooth/receiver verification | missing | expected |

The [settings source audit](glyph-settings-audit.md) records the debounce gate and compatibility behavior.
