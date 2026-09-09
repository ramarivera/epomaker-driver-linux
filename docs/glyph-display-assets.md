# Glyph display asset library

The Display page can retain a prepared still image or animation in a local library.
Prepare the source first, enter an asset name, and choose **Save prepared asset**.
Each save creates a separate entry; names may repeat and existing entries are not
overwritten. The library retains the original source bytes and the effective
animation delay, including a deliberate zero delay.

Loading an entry replaces the current local draft and its preview. The selected
still-image destination bank remains unchanged. Loading does not write to the
keyboard; use **Upload to display** explicitly. Loaded source files can be prepared
again after changing the upload type or timing. Animation uploads still require
wired USB. Deleting a local library entry does not erase the keyboard display or
clear the currently loaded draft.

The default storage directory is
`~/.local/share/epomaker-driver-linux/display-assets`. Override it with
`epomaker serve --assets-dir /absolute/path`. This directory is independent of the
device backup directory and survives server restarts. Back up this directory along
with device snapshots: screen pixels cannot currently be read back from the
keyboard, and saving a device snapshot does not capture its displayed images.

Library entries use private JSON files with opaque IDs, atomic creation and
process locking. Each source is bounded to 14 MiB; the library holds at most 256
entries. Names contain at most 80 Unicode codepoints. Invalid entries produce an
error rather than disappearing from the list. Loading reconverts and validates the
original source before it becomes a prepared draft.

This is an independent Linux asset library, not an import implementation for the
vendor database format. Frame editing, animation playback preview, screen-asset
integration into backup/restore and hardware verification remain open work.

Implementation: `src/epomaker_driver/display_library.py`,
`src/epomaker_driver/server.py`, `ui/src/display-library.jsx` and
`ui/src/display.jsx`. Conversion and transport behavior are documented in
[display.md](display.md).

The authenticated loopback API exposes `GET /api/display_library` for compact
summaries, `POST /api/display_asset_save` with `name`, `kind`, `delay_ms` and
base64 `content`, and `POST /api/display_asset_get` or
`POST /api/display_asset_delete` with an `id`. Save returns a summary; get returns
the original content and a newly computed preview. Library operations do not
require an active keyboard connection.
