# G84 HE Pro, internal model 4071

`G84HE  PRO` is catalogued as `ry5088_0005_fq_x122_a_us_3m_8k_8k`, VID/PID
3151:5030. Its partial Linux backend uses the USB command interface, with four
profiles and four normal magnetic submodes per profile, Windows/Mac Fn banks,
macros, magnetic actuation/modes/snap, switch selection, main lighting, five
custom RGB pictures, OS controls, calibration and schema-7 backup/restore.
Physical hardware behavior remains unverified. Side lighting and debounce are
not advertised in this model's catalog and remain unavailable.

The supplied Mac loader maps `6f31d22e.js` → `7519543c.js` → modern base
`623d2d52.js`; Windows maps `d915b681.js` → `e83663f3.js` → `17dc9c62.js`.
The child modules declare only three 512-byte matrices, with no method overrides.
Their bytes match between the two installers:

| Matrix | SHA-256 |
| --- | --- |
| Normal | `20c83b83c2882d81c0974e608e16dc3a436d9895ac7c6a85228a7985c35bf262` |
| Windows Fn | `0b9f2f66c68584faad7a72fd6368cb0cc2fc8c67e33bc1a1c1763be5d83283fb` |
| Mac Fn | `6187392234efbdf8c241ef8c775281491f7e9e5de39286c09b6cab31e6b21509` |

The catalog supports `海木比目鱼轴` (wire code 133/0x85), `磁玉` (1),
`磁玉pro` (2), `磁玉gaming` (3), `天王` (4) and `万磁王` (5).
The shared base encodes the global switch enum directly in field 252.
There is no model-specific alias mapping. Global code 0 (`高特`) is not on
this model's supported list. New enum entries do not widen older models' gates.

Catalog travel is 0.1–3.3 mm, step 0.005 mm, default 2 mm. Bottom dead zone is
0–1 mm, step 0.005 mm, default 0.3 mm. On effective firmware below 0300, the shared UI max-4 precedence applies before catalog maxima; newer firmware uses these catalog bounds. Ordinary edits reject precision finer than the active firmware can represent.
RF version takes precedence over USB version for this wireless-capable model.
No rapid-trigger bounds override is specified, so the shared firmware-dependent
limits apply. See [magnetic commands](magnetic-protocol.md).

Normal Bluetooth and dongle sleep timers are 60–3600 seconds; deep Bluetooth
is 600–3600 seconds. Writes validate against catalog data and preserve the hidden
fourth timer. [Recovery](he-recovery.md) preserves raw configuration, including
values outside ordinary edit limits, with exact model/firmware checks.

Evidence: both main bundles' model block at lines 57723–57762; global enum at
Mac main line 9833; model modules above and their shared magnetic base.
Independent simulated tests cover CLI dispatch, switch packets, unsupported
feature rejection, matrix hashes, limits, calibration and complete recovery.
This establishes software behavior, not measured feature parity on hardware.
