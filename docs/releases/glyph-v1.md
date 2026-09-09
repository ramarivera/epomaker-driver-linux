# Glyph v1 release scope

Decision: 2026-09-09. The next release targets **complete Linux management of the
EPOMAKER Glyph**, internal model 3059. Work on other keyboards, mice and standalone
receiver products is deferred. This replaces the multi-model >95% target for v1;
it does not claim that the existing implementation is complete.

The reference is the Glyph behavior exposed by EPOMAKER Driver v4 3.2.22 on
Windows and macOS, using the exact installers in
[the source manifest](../source-releases.json). Where those applications differ,
record both behaviors and implement the applicable Glyph functionality. Native
Linux mechanisms may replace OS-specific vendor mechanisms.

## What “100%” means

Every applicable Glyph management workflow must be usable through the Linux
application, with a tested backend and a physical-device verification record.
Selecting an effect without its required host service, encoding a packet without
completing the workflow, and preserving a setting without being able to manage it
are not completion. Existing CLI operations can support testing and automation;
CLI-only implementation does not finish a vendor graphical workflow.

The supported connection matrix must include wired USB, Bluetooth, and Glyph's
2.4 GHz receiver. Determine the vendor's actual per-connection restrictions first:
a vendor feature that requires USB may require USB here too, with a clear UI
explanation. The receiver is in scope as part of Glyph management; unrelated
receiver products are not.

No Glyph feature may disappear from the release checklist because it is difficult,
undocumented, dependent on a service, or not yet available for hardware testing.
An unresolved applicability question remains open until source/UI/device evidence
settles it. A shared protocol method alone does not prove Glyph applicability.

The [provisional feature inventory](glyph-v1-features.md) breaks these areas into
individual workflows and records unresolved applicability.

## Release checklist

These are acceptance areas, not equally weighted percentages. Each must be split
into individual vendor controls and workflows during the feature audit. “Partial”
means some code exists; **none is physically verified end to end yet**.

| ID | Acceptance area | Existing foundation | Remaining v1 acceptance work |
| --- | --- | --- | --- |
| G01 | Discover and connect over every applicable Glyph transport | USB/Bluetooth descriptors and transport code; observed Bluetooth descriptor | Query the real internal ID; verify USB/Bluetooth; identify and integrate the actual Glyph receiver and its restrictions |
| G02 | Connection lifecycle and status | Identity, firmware fields, battery/online parsing, disconnect errors | Accurate UI status, battery/charging where exposed, hotplug, sleep/wake, reconnect and transport changes; no stale device state |
| G03 | Keys, Fn layers and knob actions | Three profiles, Windows/Mac Fn maps, named/raw bindings and readback | Audit every vendor-exposed action and restriction; verify physical key/knob mapping and playback behavior; expose applicable actions graphically |
| G04 | Profile and keyboard settings | Profile selection, OS selection, automatic OS, WASD swap and sleep timers | Audit remaining Glyph option fields, limits and defaults; implement missing controls; verify persistence and transport-specific behavior |
| G05 | Macro management | Persistent named library, JSON editor, keyboard/mouse-button recording, encoding/decoding, storage and playback bindings | Library-to-assignment workflow verification, remaining editing workflows, delays/repeats/playback modes, mouse motion semantics, import/export compatibility and real execution |
| G06 | Onboard main and side lighting | Main/side effects, colors, brightness, speed and options | Audit all 22 main and six side choices and their conditional controls; verify effects, off behavior, persistence and any firmware-gated light sync |
| G07 | Custom per-key lighting | Five picture banks; 126 writable RGB slots, readback, offline painting and JSON import/export | Correct key/LED correspondence, full visual editing/import/export workflows, bank selection and physical color verification |
| G08 | Host-driven lighting | Effect selection and protocol research | Determine which Glyph music/screen/reactive modes require host processing; implement applicable Linux capture, streaming, start/stop and cleanup workflows |
| G09 | Display images and animation | 428×142 RGB565 conversion, five still banks, bounded transfers and animation capacity | Audit display selection/clear/settings/editor workflows; complete asset management; verify rendering, frame timing, capacity and interruption handling |
| G10 | Clock, display language and host statistics | Clock/language commands and foreground Linux statistics | Graphical/background refresh, settings and sensor selection where applicable; verify physical output and suspend/resume behavior |
| G11 | Backup, restore and vendor configuration files | Versioned snapshots including all 256 Glyph macro slots, validation, recovery copies, vendor-file inspection | Verify complete manageable-state recovery; vendor import/export workflows; retain original screen assets for replay when pixel readback is unavailable; document inherently unreadable state |
| G12 | Factory reset and recovery | CLI and GUI reset with pre-reset backup and identity recheck | Verified factory state, physical reconnect after reset, failed-operation recovery and restoration of the saved configuration |
| G13 | Firmware management | Source research and version/bootloader awareness | Audit all Glyph firmware components and vendor update paths; validate images/identity, implement update/progress/reconnect and supported recovery; verify on appropriate hardware |
| G14 | Service-dependent Glyph management | Source research | Audit whether any Glyph profile, firmware or configuration workflow requires vendor services; implement the workflow or a functionally equivalent supported path; unresolved cases block a 100% claim |
| G15 | Install, run and maintain on Linux | Python package, CLI and loopback React interface | Usable installation/launch/update/uninstall, least-privilege device permissions, persistence of user settings/assets, background-service lifecycle and error reporting |
| G16 | Complete desktop workflows | Glyph visual panels and browser tests | Integrate remaining controls; keyboard accessibility, responsive layout, clear unsupported-transport states, no hidden CLI-only essentials; audit vendor language/accessibility differences |
| G17 | Release verification | Packet fixtures, simulated firmware, CI and high code coverage | Trace each applicable feature to source evidence, implementation, automated tests and USB/Bluetooth/receiver hardware results; fix regressions and publish limitations |

No Hall-effect/rapid-trigger/switch-calibration work belongs to Glyph v1: the Glyph
catalog explicitly disables magnetic switches. Configurable polling rate is also
not a Glyph vendor-UI feature; retain status reporting without inventing a missing
setting. Configurable debounce is also absent from both vendor Glyph controls;
the Linux control is gated and older backups skip that value, as recorded in [the settings audit](glyph-settings-audit.md).
See [capability gates](../capability-gates.md). Any other exclusion needs
similarly specific evidence.

## Execution order

1. **Freeze the feature inventory and connect real hardware.** Enumerate individual
   controls from both installers; record applicability by firmware and transport.
   Establish read-only identity/status traces and a recoverable baseline.
2. **Finish the existing Glyph workflows.** Complete action/settings/lighting gaps,
   macro editing and recording, comprehensive backups, and graphical reset/recovery.
3. **Implement the missing runtime services.** Receiver lifecycle, monitoring,
   reactive lighting, background display updates and retained display assets.
4. **Complete firmware and Linux delivery.** Research can proceed earlier; shipping
   firmware writes requires validated image and recovery behavior, not guessed commands.
5. **Run the release matrix.** Every applicable feature must pass; unresolved or
   unverified rows remain open. Keep the existing regression suite and >=98%
   combined Python line/branch coverage gate. Coverage is not feature completion.

## Git boundary and deferred work

- `codex/glyph-v1` is the focused release branch, starting at the last green commit
  `70ef1b23b51c3adaaa09d96996621bac080f203e`.
- `codex/multi-model-gui-wip` preserves the unfinished GUI expansion in commit
  `261deff`. Its focused API/contract tests and frontend build passed; complete
  coverage and browser regression verification are still outstanding.
- Existing non-Glyph backends remain in git. They are not v1 acceptance targets;
  new model migrations and broader GUI enablement are deferred. Existing regression
  tests remain useful and should continue to pass.
- The [multi-model inventory](../model-inventory.md) remains a record of previous
  work, not the v1 completion denominator. Reuse shared improvements when they help
  Glyph; do not spend v1 time enabling unrelated products.

A progress report must distinguish implementation, graphical workflow and hardware
verification. Do not report 39/46 models or 98% code coverage as “v1 percent done.”
Once the individual-feature inventory is complete, report verified features /
applicable features, alongside unresolved applicability items and blocking failures.
The v1 release label requires all applicable items, not rounding up to 100%.
