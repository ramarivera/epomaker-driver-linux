# Glyph 3059 child-profile and `configValuesForAllSonProfiles` audit

This audit follows creation, initialization, consumption, and ordering of the
unlabelled child-profile arrays in the Glyph vendor configuration envelope. It
does not execute vendor code or use the network. Offsets are zero-based UTF-8
byte offsets, verified with `read_bytes().find()` against unique declaration
strings.

## Sources

| Bundle | Size | SHA-256 | Relevant byte declarations |
| --- | ---: | --- | --- |
| Windows `resources/app/dist/js/index.feaf50e4.js` | 2,556,505 | `72fb76b3c19e013d81e450d5245bc62bb5a275fcf6623530a5a652b9c7182be5` | Glyph `id:3059` 896,116; share `configValuesForAllSonProfiles=` 1,753,460; local save `configValuesForAllSonProfiles=` 1,846,251; storage `___存储按键信息=` 1,893,631; normal read `___获取所有按键信息=` 1,894,216; Fn read `___获取所有Fn改键信息=` 1,895,474; reset initialization loop 1,897,396 |
| macOS `Contents/Resources/app/dist/js/index.5af2e057.js` | 2,565,198 | `06c91320e6e5b0249fa9f80f055aa5e19099aa5762402cf7098ef8752a832286` | Existing macOS audit identifies the matching save/write/profile path; the macOS class names and offsets differ. |

## Glyph model and actual child count

The model record at byte 896,116 is:

```text
{id:3059,...displayName:"Epomaker Glyph",type:"keyboard",company:"EPOMAKER",layer:3,fnSysLayer:{win:1,mac:1},...,other:{noMagneticSwitch:!0,isYC3123:!0,...}}
```

`layer:3` means three parent normal profiles, with `profile` values 0, 1,
and 2. `fnSysLayer:{win:1,mac:1}` means one Fn layer for each OS system.
The catalog has no `magnetism` property. The constructor at byte 1,893,408
sets magnetic support from the presence of that property, and the reader
chooses one child when it is absent. Thus Glyph has one normal child
(`sonProfile:0`) per parent;
there are no Glyph normal child slots 1–3. The child-slot count of four used
elsewhere is conditional on magnetic support and does not apply to Glyph.

The reset/initialization loop at byte 1,897,396 uses
`m=this.dev.deviceType.magnetism` and is structurally:

```text
for (let profile=0; profile<deviceType.layer; profile++)
  for (let son=0; son<(magnetism ? 4 : 1); son++)
    configs.push({profile, sonProfile:son, configs: son===0 ? normal : childDefaults})
```

For Glyph this produces exactly three normal records:

```text
(profile:0, sonProfile:0), (profile:1, sonProfile:0), (profile:2, sonProfile:0)
```

Fn initialization then iterates `Object.keys(fnSysLayer)` and each system's
layer count. For Glyph, the catalog order is `win`, then `mac`, each with one
record at `sonProfile:0`: `(profile:0, sonProfile:0, fnSys:"win")` and
`(profile:0, sonProfile:0, fnSys:"mac")`. The source does not establish any
additional Fn child slots.

## Creation and ordering of the outer array

The share path at byte 1,753,460 sets the selected normal record and then uses
the literal expression:

```text
o.configValuesForAllSonProfiles = o.configValuesForAllSonProfiles ??
  l.configs.filter(d=>d.profile===a.板载).map(d=>d.configs)
```

The local-save path at byte 1,846,251 does the same for normal records, while
the Fn branch uses:

```text
h.configValuesForAllSonProfiles = a.fnConfigs
  .filter(g=>g.profile===currentFnProfile).map(g=>g.configs)
```

The mapping strips `profile`, `sonProfile`, and (for Fn) `fnSys`; only the
ordered arrays of actions remain. For a Glyph normal profile, the filtered list
contains exactly one array, the selected parent profile's `sonProfile:0`
record. For a Glyph Fn profile, the filtered list contains two arrays in the
internal `fnConfigs` order: Windows first, macOS second, because initialization
enumerates the catalog's `{win:1,mac:1}` keys in that order. This order is an
implementation observation, not a portable OS label: the outer Fn arrays are
unlabelled and cannot safely identify which is Windows or macOS after transfer.

The selected `value` is created alongside the outer list. Normal save selects
`configs.find(profile===selected && sonProfile===0).configs`; Fn save selects
the record matching the current Fn profile and `fnSys`. Thus `value` carries
the target OS identity only implicitly through the operation that selected it;
the serialized envelope has `fn:true` but no explicit `fnSys` field.

## Consumption for Glyph key bindings

`writeConfig` (Windows byte 1,504,942; matching macOS path documented in the
config interchange audit) selects the current normal or Fn record and assigns
`y.configs = o.value ?? []`. The ordinary key configuration path does not apply the outer list as a
batch of matrices. The shared non-Fn importer does inspect that list when
reconstructing DKS and MT entries from `magnetismModes` (byte slice
1,505,600–1,507,400). Those magnetic modes are not supported by Glyph; claiming
that the function never reads the outer list would be incorrect. For Glyph
key bindings, the outer list is stored/share metadata, not a batch write
instruction. A Glyph normal import applies one
selected `value` array to the current parent profile's `sonProfile:0`; it does
not apply three parent profiles or any hypothetical child slots. A Glyph Fn
import applies one `value` to the current Fn profile/system, and `fn:true` alone
does not select Windows versus macOS.

The normal state reader at byte 1,894,216 loads cached records by parent
`profile`, then converts only the record matching `sonProfile:0` into the UI
state. The `sonProfile` records are retained in local storage by
`___存储按键信息` (1,893,631), whose normal replacement key is
`profile && sonProfile`. On Glyph, the retained normal set consequently has
one record per parent. The Fn reader at byte 1,895,474 filters by
`profile && fnSys`, then exposes the selected system; its replacement key also
includes `sonProfile && fnSys`.

## Supported conclusions and importer boundary

The evidence supports these concrete rules for Glyph 3059:

1. Normal parents are profiles 0–2; each has exactly one supported child,
   `sonProfile:0`.
2. A normal `configValuesForAllSonProfiles` list for a selected parent has one
   unlabelled action array, in the selected parent's storage order.
3. Fn has one `sonProfile:0` per system, with one Windows and one macOS record.
   An Fn outer list can contain two arrays, but its order is not a durable OS
   discriminator.
4. The ordinary Glyph key write consumes selected `value`; the shared
   magnetic-mode reconstruction uses the outer list for other models. A Linux importer should preserve the outer list as opaque metadata or
   require an explicit mapping before using it for multi-profile import.
5. Require an explicit target parent profile and, for Fn, explicit `win` or
   `mac`. Do not infer either from array position, `fn:true`, or `layer`.

The source does not prove that a shared/downloaded outer list is intended to
rewrite all three Glyph parent profiles at once, nor does it provide labels or
checksums for each child array. It also does not establish a portable mapping
for a malformed list with more or fewer arrays than the Glyph counts above.
