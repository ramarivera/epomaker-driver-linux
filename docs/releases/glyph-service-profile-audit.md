# Glyph 3059 account, cloud, and local-profile workflow audit

This audit traces the account and service gates around the Glyph configuration
and macro/profile surfaces. It builds on the [child-profile](glyph-child-profile-audit.md)
and [config interchange](glyph-config-interchange-audit.md) audits. No vendor
code was executed and no network request was made. Offsets are zero-based UTF-8
byte offsets verified with `read_bytes().find()` against unique declarations.

## Sources

| Source | Size / SHA-256 | Relevant declarations |
| --- | --- | --- |
| Windows `resources/app/dist/js/index.feaf50e4.js` | 2,556,505 / `72fb76b3c19e013d81e450d5245bc62bb5a275fcf6623530a5a652b9c7182be5` | `e.getList=async` 1,153,375; `getIOTSwitch=async` 1,719,943; `handleShareMacro(` 1,752,032; `handleShareConfig=` 1,752,686; `handleSaveConfig=` 1,845,395; `saveLocalStorageMacroToIotDb=` 1,508,578; `createMacro=async` 1,880,217 |
| Windows local-config chunk `resources/app/dist/js/6a8dfe90.js` | 6,386 / `f6a37264f77f77fd21c7fa36d156ce645ecc0d2b7a0b5a0ebea08a52c161de41` | DB load 819; rename/save 1,851; delete 4,555; share menu 6,027 |
| macOS main bundle | 2,565,198 / `06c91320e6e5b0249fa9f80f055aa5e19099aa5762402cf7098ef8752a832286` | Matching class and service paths are recorded in the config interchange audit; minifier offsets differ. |

The Glyph catalog record at Windows byte 896,116 identifies model 3059. The
service paths below are shared application code selected by the driver’s runtime
IoT/service switch; their presence alone is not a Glyph-specific cloud mandate.

## Local configuration and profile operations

`handleSaveConfig` (1,845,395) reads the current device’s local DB snapshot,
constructs a `Ty` record containing the selected `value`,
`configValuesForAllSonProfiles`, device identity, and (for Fn) the selected
system’s action array, then calls `Ws.saveConfig`. It has no
`currentUser === void 0` guard. `Ws.saveConfig` JSON-serializes/compresses the
record and stores it through the local IndexedDB helper; the record’s `user`
field is assigned from the current user but is not required by this save call.
This establishes that local named configuration save is account-independent
when the local-config surface is enabled.

The local-config page chunk `6a8dfe90.js` loads records with `getAllItems` at
byte 819 only when `e.isUseIotSDK`, renames them through `saveItemToDb` at byte
1,851, and deletes them through `deleteItem` at byte 4,555. These handlers do
not check the login user. The page exposes a `share` menu only when the company
configuration permits it (menu construction at byte 6,027). The service toggle
itself is local state: `getIOTSwitch=async` (1,719,943) reads the `IOTSwitch`
local-storage flag, with platform handling; it is not an account check.

`handleWriteConfig` at byte 1,754,335 calls `Ws.writeConfig` for a selected local
record and likewise has no login gate. The writer applies the selected `value`
to the current profile; the outer child arrays are not a multi-profile write
command. Therefore local save, rename, delete, and device write are distinct
from cloud account operations.

## Macro library persistence versus cloud sync

`createMacro` (1,880,217) creates a named macro, stores it in local storage, and
only then conditionally calls `oc.saveLocalStorageMacroToIotDb` when
`isUseIotSDK` is true. The macro editor’s save path similarly writes local
storage first and conditionally attempts the DB upload. Neither local creation
nor local editing requires `currentUser`.

The optional DB upload helper (1,508,578) compresses the macro JSON and writes a
local `MACRO`/`MACRO_BUFFER` record through the local DB helper. Its complete
body checks device id and macro id, but has no login check. `syncIotDbMacrosToLocalStorage`
(1,509,264) reads those local DB records and merges them into the local macro
list. This is local persistence/synchronization, not proof of authenticated
cloud access. A Linux implementation should keep named macro storage usable
without an account and may expose vendor cloud synchronization only as a
separate optional feature.

## Account-gated sharing and community data

`handleShareMacro` (1,752,032) begins with the explicit guard
`if(this.currentUser===void 0){..."请先登录"...;return}` before calling
`Po.shareMacro`. `handleShareConfig` (1,752,686) has the same guard before
loading an existing record and calling `ac.shareConfig`. These are the concrete
account requirements for cloud macro/config sharing.

The service list helper `e.getList=async` (1,153,375) obtains a session and
calls `/list`; the adjacent user-list helpers call `/user_likes` and
`/user_bit_image_list`. The delete-shared-item path uses `deleteBitImage` at
1,154,703. These community operations are account/service workflows and are
separate from local DB configuration management. Login itself stores the user
and web session cookie in the account helper (`userLogin` byte 1,259,234); a
session-expired response clears that state.

`isUseIotSDK` controls whether the sharing/local-DB UI is enabled and is
initialized from the local `IOTSwitch` setting at byte 2,550,530. It does not
convert a local save into a cloud request. The examined share handlers reach cloud sharing through explicit user actions
and account guards; this does not enumerate all network requests in the app.

## Glyph-applicable scope

The evidence supports these implementation decisions for Glyph 3059:

1. Provide local named configuration save, rename, delete, and write without
   requiring login. Preserve the complete selected action array. Retain outer child-array metadata
   when round-tripping vendor records, without treating it as additional Glyph banks.
2. Provide local named macro create/edit/persistence without requiring login;
   keep optional vendor DB synchronization separate from cloud sharing.
3. Gate cloud config sharing, cloud macro sharing, community listing, likes,
   and shared-item deletion on an authenticated account/session. Surface session
   expiry as an account reauthentication error.
4. If a Linux client offers vendor-compatible cloud sharing, preserve the
   model/device identity and compressed JSON envelope, but require explicit
   parent profile and Fn OS mapping. The vendor share envelope drops Fn OS
   labels from its outer arrays.
5. Treat `isUseIotSDK` as an application/service feature toggle, not evidence
   that login is required for local operations or that cloud access is enabled.

The source does not establish a portable export-file format, an offline account
mode, the server’s complete authorization policy, or whether every service
endpoint accepts unauthenticated sessions. It also does not prove that cloud
sharing is required for any Glyph device-management function: local profile and
macro operations have independent local persistence paths. The remaining
cloud-facing work is a separate user-visible integration with explicit login,
session handling, service errors, and profile/Fn target selection.
