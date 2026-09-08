# RT100 PRO (internal ID 3152)

The RT100 PRO is a three-profile YC3123 keyboard with the shared modern
configuration protocol. The macOS and Windows 3.2.22 installers use matching
normal, Windows Fn, and declared Mac Fn matrices (512 bytes each). The runtime
Mac default requires the capitalization distinction explained below.

The migrated backend supports normal and Fn keymaps, macros, profile selection,
debounce, sleep timers, automatic OS selection, OS options, lighting, language
and system-information display settings, clock sync, configuration snapshots,
factory reset with recovery, and display still images and animations.

The vendor names the Mac declaration `defaultFnMACMatrix`; the Linux data keeps
that source spelling. The case-sensitive runtime reads `defaultFnMacMatrix`
from the shared base instead, so that key contains the inherited generic matrix
(the same base value recorded for RT75), not a renamed model declaration. This
is observed software behavior, not a claim about intended factory defaults. Mac `d58e4de1.js` and Windows `28a3a7ca.js` match
for all three matrices. Their shared `lightLayout:S` has no side-light or
explicit-off mode.

Its display is 240×240 RGB565 with five banks. Both installer catalog entries
omit `memorySize`; the shared vendor drawing-board code defaults that field to
7 MiB. With the vendor block rounding this allows 56 animation frames. The
catalog and source comparison support the protocol claim, but no physical
RT100 PRO has been hardware-validated yet.
