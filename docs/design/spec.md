# Control interface design

Reference: [generated concept](concept.png), produced with the built-in imagegen tool.
The concept is the implementation reference selected for this migration; no user design
approval was requested or implied. Prompt: a complete flat, light EPOMAKER Linux control
application, with six navigation sections, an offline Glyph keymap editor, connection
controls and an assignment inspector. White main surface, cool-gray sidebar, blue
selection, readable system sans typography, no marketing content or hardware imagery.

Design tokens: white main surface; sidebar #e9eef4; canvas #f2f4f7; key #e2e7ec;
text #111827; muted #687487; border #d0d8e2; accent #365df5. System sans typography:
42px desktop main title (30px narrow), 20px section title, 14–18px controls and body, 12px secondary text.
Desktop sidebar scales from 224px to 274px; main padding from 28px to 51px; 8px radii on controls and panels; 16–24px gaps.
Outline navigation icons: keyboard, lightbulb, play, monitor, settings, database.

Implement the concept's main hierarchy, labels, spacing, profile/layer toolbar,
keyboard canvas and assignment panels. Buttons, fields, sidebar items and panels share
components and tokens. No concept pixels are shipped as interactive UI.

Intentional functional adaptations: actual key geometry and legends come from the
recovered Glyph metadata, which differs from the generated illustrative keyboard.
Device errors and successful operations add transient live status text. Connected
state replaces Offline preview and enables write controls. The other five sections
use the same form/panel system for their real driver operations. Below 900px, navigation
becomes a horizontal strip and assignment panels stack; the keyboard remains scrollable
instead of shrinking labels beyond legibility. API data never implies that offline
preview changes were written to hardware.

Required workflows: device discovery/connect/disconnect; main/Fn key assignment;
main/side lighting and custom colors; editable macros; still/animated display uploads
and clock/statistics; sleep/debounce/profile/OS settings; backup download and restore
upload with a recovery copy. Unknown key actions remain visible as raw values.

## Fidelity verification — 2026-09-08

The generated concept and final [desktop screenshot](implementation.png) were inspected
with `view_image` in the same QA pass. [Narrow screenshot](narrow.png) records the 390px
layout. Both screenshots came from the Codex in-app browser, using the built application
and the explicit simulation harness, with device writes disabled in offline preview.

| Anchor | Result |
| --- | --- |
| Shell and hierarchy | Cool-gray left navigation, white main surface, six sections and lower device card match the reference. |
| Color and typography | Blue selection, pale keys, dark system typography and muted support text retained. |
| Keymap and toolbar | Profile and three-layer controls retained; recovered physical layout and three knob actions intentionally replace the illustrative layout. |
| Assignment area | Two desktop panels retain editable action/key/modifiers, current value and disabled offline apply action. |
| Runtime and responsive behavior | A disconnect status adds a notice; at 390px navigation and keymap scroll locally and inspector panels stack without document overflow. |

The desktop check used a 1586 × 992 viewport to compare the generated reference at its
native width; full-page screenshots include content below the viewport. Browser workflows
verified connection, key reassignment and lighting through simulated readback. The automated
Playwright suite additionally covers main/Fn changes, settings, pattern painting, macro
readback and invalid imports, image transfer, backup download and restore with a recovery
copy. These checks validate the implementation against the design and simulation, not
compatibility with physical hardware.
