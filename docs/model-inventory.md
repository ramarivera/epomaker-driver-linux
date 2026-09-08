# Model inventory

Baseline: EPOMAKER Driver v4 3.2.22, from the two installers recorded in
[source-releases.json](source-releases.json). [model-inventory.json](model-inventory.json)
cross-references all 46 catalog rows with the Linux backend gates and the
installer modules that load each model.

There are **32 partial backends, 14 catalog-only entries and zero models verified
on physical hardware**. The implemented subset comprises 27 keyboards and five mice;
16 magnetic IDs have implemented magnetic backends,
including HE108 ID 3365. Hardware verification remains outstanding. These counts are not a feature-parity percentage. A
weighted feature inventory, hardware comparisons and application-wide workflows
remain necessary for the greater-than-95% target in [migration status](parity.md).

## Reading the data

- `catalog_functional_descriptors` preserves functional catalog values. Each
  value has a `present` flag: omission is different from an explicit `false`.
  `layer` retains the vendor field name; it does not establish the same profile
  semantics for keyboards and mice. `other` includes model-specific options.
- `installer_loaders` records exact name-keyed finder and model module filenames
  separately for macOS and Windows. A matching import establishes a loading path,
  not complete support or packet compatibility.
- `backend_implemented_features` lists implemented, model-gated operations.
  `backend_limits` records important restrictions. Neither means hardware-tested.
- `protocol_family` on catalog-only rows is a name-prefix grouping, explicitly
  marked `family_evidence: name-prefix-only`. See the loader and source evidence below for additional source evidence; H60, the HE68 variants and [four additional wired models](ry5088-wired.md) and [four wireless-capable models over USB](ry5088-wireless.md) have been enabled.
- `remaining_domains` is a migration checklist, not an exhaustive or weighted
  denominator. Shared application features must also be counted.

| Implemented family | Internal IDs | Current scope |
| --- | --- | --- |
| CH585 mice | 3961, 3303, 3304, 3929, 3919 | USB profiles, named/raw bindings, macros, DPI/settings, backup/restore and reset; [protocol and limitations](ch585-protocol.md) |
| Older YC3121 | 1379, 1723 | RT100 and Dynatab75X-UK; physical Fn layer 0, with OS-specific Fn addressing unresolved |
| Modern YC3123 | 2895, 3059, 3152, 3223 | RT85, Glyph, RT100 PRO and RT75; model-specific display and configuration gates |
| RY5088 | 3662, 3664, 2762, 2883, 2465, 2586, 2870, 3691, 3692, 3703, 2761, 2959, 3746, 3365 | H60, HE68 Lite and HE108 variants; four profiles and firmware-dependent magnetic precision; timed USB calibration for enabled models; schema 7 recovery for enabled models; hardware verification outstanding |
| HE60 Lite | 3727, 3759 | Wired/wireless; two profiles, four normal submodes, actuation, modes and snap; timed USB calibration; schema 7 recovery; hardware verification outstanding |
| RY6602 | 3858, 3633, 3673, 3573, 3674 | Five models; three have display transfers, none has enabled clock/language/system-info commands |

The desktop interface currently supports Glyph. Other enabled models have CLI
support with different capabilities. RT85 has no enabled debounce or system-info
command; Dynatab75X-UK has no enabled display-language command. These distinctions
are retained rather than inferred from a shared superclass.

## Loader coverage and remaining migration work

Exact catalog-name lookup resolves 45 of 46 rows in both installers. IDs 2762
and 2883 share a catalog name and loader, so 45 rows correspond to 44 distinct
resolved names. The unresolved entry is **Epomaker M65, ID 2550**,
`ry5088_mmdkm60c_dm_8k_002`. Its catalog presence remains in scope; the missing
loader match is a source ambiguity, not a reason to discard it or a claim that
the physical keyboard is unsupported by the vendor.

The 22 RY5088-named rows include fourteen partial backends and eight catalog-only
entries. Direct inspection of the following model modules confirms that they import the same
modern base, `623d2d52.js` on macOS / `17dc9c62.js` on Windows, and declare
512-byte default normal, Fn and Fn-Mac matrices without child method overrides.

| Inspected model | Internal ID | VID:PID | macOS module | Windows module |
| --- | --- | --- | --- | --- |
| H60 | 3662 | 3151:5029 | 00bc96cb.js | 82c2850d.js |
| HE68 Llte (vendor spelling) | 2762, 2883 | 3151:5029 | 1a9b921e.js | 4e6e3981.js |
| HE108 | 3365 | 3151:5030 | 949a2f06.js | f6203dd7.js |
| HE60 | 3746 | 3151:5029 | fa455a99.js | bb2c7696.js |
| HE60 Wired | 3691 | 3151:5030 | 66d72914.js | 8b45ed1f.js |
| HE60 Wireless | 3692 | 3151:5030 | bf16d6e2.js | dcf3221c.js |

Their catalog declares four layers and one Fn layer per OS, compared with the
two-profile HE60 Lite implementation. The [H60 migration](ry5088-h60.md),
[HE68 Lite](ry5088-he68.md), [wired additions](ry5088-wired.md) and
[wireless-capable additions](ry5088-wireless.md) and [HE60 3746](ry5088-he60.md) and [HE108](ry5088-he108.md) implement those model-specific
limits. The eight remaining catalog-only RY5088 rows require further capability
validation before enablement.

The same direct base inheritance and absence of child method overrides hold for
all 21 resolved RY5088 rows. Each declared matrix is 512 bytes and matches its
Windows counterpart byte for byte; the JSON records these checks in
`installer_class_evidence`. IDs 2520, 2586 and 2761 declare only normal and Fn
matrices, so their Fn-Mac defaults require tracing the inherited value. The other
18 rows declare all three matrices. None of these 21 children uses the separate
`7bb580fe.js` precision-extension superclass found elsewhere in the installer.
This establishes shared command ancestry, while model-specific catalog options
still govern which operations and limits should be exposed.

Other catalog groups include seven mice, two dongles, one PAN1086 entry and
additional YC3121/YC3123 entries. Their functional metadata is preserved in the
JSON, but DPI, sensor, polling, receiver and magnetic behavior require separate
protocol work. Firmware management, reconnect/monitoring, online services and
broader GUI support remain gaps across the inventory.

## Provenance and maintenance

The JSON `sources` list identifies the public catalog and implementation files
used for the backend crosswalk. Loader filenames refer to private extracted
installer JavaScript; vendor code and assets are not redistributed here. Archive
hashes in [source-releases.json](source-releases.json) identify the baseline.
Update this inventory when model gates or features change. Maintain the distinction
between catalog declarations, implemented behavior and hardware verification.
