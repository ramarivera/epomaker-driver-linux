# Vendor desktop lifecycle and Linux mapping

Both archived applications contain the same 26,743-byte `dist-electron/main.js`,
SHA-256 `de8233dfc29c302fa491a37f4df0a8cdd7e7d19b1b3dca225689d3ebf63002c6`.
The following offsets are zero-based UTF-8 bytes, checked against those files.
No vendor executable was run.

| Evidence | Offset | Behavior |
| --- | --- | --- |
| Ready-to-show handler | 23,591 | Shows the initial window |
| Single-instance lock | 23,757 | A second launch restores/shows/focuses the existing window |
| All windows closed | 24,406 | Quits except on macOS |
| Tray menu array | 24,552 | Show, hide, and exit actions |
| Login preference setter | 25,145 | OS-backed startup setting with hidden-start preference |
| Tray construction | 26,597 | Clicking the icon shows the window; menu uses the same actions |

The renderer localizes the menu labels. The startup preference is read from
Electron's login-item settings, not established by a default-setting call in
this main bundle. Renderer `isAutoHide` is separate: custom window exit may hide
instead of quitting, while the tray exit notification quits. The renderer
behavior was located in the Windows/macOS main bundles; it does not establish
Linux window-manager behavior.

Linux currently uses a browser for its controls and a separate server process.
Closing a controls tab leaves the server running, and opening controls from a
tray reuses that server. It can open another tab rather than focus an existing
one. The driver does not own arbitrary browser windows and cannot implement the
vendor's native-window Hide action by closing or minimizing them. That native
window behavior remains a parity difference; do not claim identical tray/window
lifecycle behavior.

The existing systemd user service supplies explicit startup enable/disable and
single-instance service activation. Those commands do not yet provide the
vendor's graphical startup/hide-preference controls. See
[background service](../background-service.md) and [tray controls](../tray.md).
