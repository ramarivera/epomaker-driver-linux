# Glyph 3059 receiver applicability audit

Static audit of the EPOMAKER Driver v4 Windows bundle and its matching macOS
bundle. No vendor executable, network request, device access, or HID write was
performed. Offsets below are UTF-8 byte offsets, obtained by searching the
original bytes for the cited literal/declaration (not by copying a prettified
source listing).

## Sources

| Source | Bytes | SHA-256 |
| --- | --- | --- |
| Win `dist/js/index.feaf50e4.js` | 2,556,505 | `72fb76b3c19e013d81e450d5245bc62bb5a275fcf6623530a5a652b9c7182be5` |
| Win `dist/js/d915b681.js` | 207,464 | `881d3f587f1a6eab1986580775cd4232719cd86c44a889c94436e90b572bfa8d` |
| Win `dist/js/ff90dc0d.js` | 3,509 | `ecec1279c4d681c8c673e3efc8156bffe720a2b69587659be5a612e2a5d465be` |
| Mac `dist/js/index.5af2e057.js` | 2,565,198 | `06c91320e6e5b0249fa9f80f055aa5e19099aa5762402cf7098ef8752a832286` |
| Mac `dist/js/6f31d22e.js` | 205,405 | `4f6d1831b2b29a6d4a7d322970c6e5ae44a549793c6a10230446b3e30356467e` |
| Mac `dist/js/b774daff.js` | 3,509 | `088c4a668e7eceda8bb4df1923a755e038f2b754d431ffb75846dc8e4d8c6da2` |
| Mac `dist/js/7884fb1d.js` | 5,707 | `803aa231c16191f5624265c9789514790cc2d6b8f7358704139fbfd1fcbb54d0` |

## Catalog and transport filters

The Glyph catalog record is a keyboard model whose catalog PID is USB PID
0x5002, at Win offset `896116`: `id:3059,vid:12625,pid:20482,...name:"yc3123_hf_kf107_3m_oled_1k_rgb_kb_soc_v100"`.
Decimal values are VID/PID `0x3151:0x5002`. The record has `type:"keyboard"`
and no receiver PID, receiver model id, or `connect` restriction. The device
loader maps this name to `ff90dc0d.js` at `d915b681.js` offset `121983`; the
class extends the YC3123/Glyph USB helper. The matching Mac catalog record is
at byte offset `896116` and the loader/class mapping is present in the matching
`6f31d22e.js`/`b774daff.js` pair.

The BLE HID filter contains VID `12625`, PID `20484` (0x5004), usage `514`,
usage page `65365`, interface `-1`, at Win offset `1126441`. This is an
unlabelled generic entry in `BR`; it is not embedded in
the `id:3059` catalog record. This agrees with `docs/provenance.md` and
`glyph-v1-features.json` G01.2: Bluetooth PID 0x5004 is distinct from Glyph's
USB PID 0x5002. The current Linux `discovery.py` has the explicit Bluetooth
branch for 3151:5004 and the USB branch for 3151:5002, but no receiver branch.

The 2.4G dongle filter is a generic `n1` list beginning at Win offset
`1118976`; it includes VID 12625 PIDs 16401, 16404, 16407, 16417, 16423,
16429, 16440, 20486, 20487, 20488, and more, all HID usage 2/page 65535,
interface 2. The receiver allowlist used for status polling, `JP`, is at
offset `1703601` and includes VID 12625 PIDs 20487, 20512, 20543, 20544,
20555 (plus other vendors). There is no 3059-specific receiver entry in
either list. The matching Mac bundle has the same generic 20487 entry; its
minified declaration layout differs.

## Receiver-to-model routing

The complete model resolver declaration `Ys` begins at Win byte offset
`1701723`. It first looks up the runtime id in `Ug`, and only
then applies special cases for boot/known HID filters. The relevant body starts
`Ys=(e,t,i,r)=>{...Ug.find(d=>d.id===e)...`; it returns a model object with
`connect:t`, `filter:i`, and constructs `new W3(o)` for `type:"keyboard"`,
`new ZP(o)` for mouse, or `new $P(o)` for dongle. There is no Glyph-specific
receiver exclusion. Therefore a receiver could resolve to model 3059 if its
firmware reports runtime id 3059 and the catalog/company filters permit it;
this is a conditional consequence of the generic resolver, not evidence that
the shipped bundle pairs a Glyph receiver.

The 2.4G status path calls `___whoAmI("keyboard")`, then `Ys(i,"24g",...)`
and emits the keyboard model if the resolver returns one (Win offset
`1706677`, literal `Ys(i,"24g",this.DEVICE_FILTER,this.THID)`). If unresolved,
it destroys the receiver and emits `DEVICE_NOT_SUPPORTED` with the message
that the device id may not support the new driver. `___whoAmI` retries the
normal-id command three times (Win offset `1709994`). The dongle itself is
opened by the generic `findDongleDevice` dynamic chunk (`45329c1f.js`, Win;
Mac `7884fb1d.js`); that chunk maps only dongle model names to generic dongle
classes and contains no Glyph/3059 name.

After resolution, the generic device class accepts `connect:"24g"`: its
`sendMsg` path forwards keyboard/mouse commands through the paired dongle.
This supports a future Linux receiver implementation at the transport level,
but does not establish a Glyph receiver fixture, receiver PID, or byte
protocol. The catalog evidence required by G01.3 remains pending.

## UI gates and implementation scope

The `handleWriteGif` UI guard blocks keyboard GIF/screen writes for both
2.4G and Bluetooth at Win offset `1841766`; this is a feature gate, not a receiver-discovery
failure. Firmware upgrade is separately wired to USB and tells users to remove
the 2.4G receiver and connect a data cable (existing firmware audit evidence).

Actionable Linux conclusion: the existing Linux USB and Bluetooth discovery
branches are separately documented. To claim G01.3, add receiver discovery only after a real Glyph
dongle/device-id fixture identifies the dongle VID/PID, reported keyboard id,
and the receiver command framing. The vendor bundle proves a generic 2.4G
resolver and command forwarding path, while leaving the Glyph-specific pairing
and receiver protocol unverified.
