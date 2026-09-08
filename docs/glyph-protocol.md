# Epomaker Glyph protocol reference

**Confidence:** byte layouts below are recovered from the shipped JS implementation. Hardware behavior is unverified unless explicitly labeled as observed. All byte offsets are zero-based, in the **command payload**, excluding the HID report ID and Bluetooth routing marker.

Private analysis references (vendor code is not redistributed): `623d2d52.js`, `Glyph subclass`, `YC3123 subclass`, and `main transport`, class `q3` around line 104835.

## Identification and capability data

| Property | Recovered value |
|---|---|
| Internal device ID | `3059` / `0x0BF3` |
| Internal model | `yc3123_hf_kf107_3m_oled_1k_rgb_kb_soc_v100` |
| Catalog USB identity | VID `0x3151`, PID `0x5002` |
| USB command collection | usage page `0xFFFF`, usage `2`, interface `2`; default feature report `0`, 64 payload bytes |
| Bluetooth identity | VID `0x3151`, PID `0x5004` |
| Bluetooth command collection | usage page `0xFF55`, usage `0x0202`, report `6`; 65 payload bytes, input + output |
| Observed on this host | `Epomaker Glyph 5.0`, Bluetooth `3151:5004`; matching vendor report in sysfs |
| Key/profile layers | `3` in model metadata; Fn system layers `{win:1, mac:1}` |
| Matrix storage | 512 bytes = 128 four-byte slots, with unused entries and duplicate key identities |
| Knob identities | Volume Down, Play/Pause, Volume Up |
| Screen | 428×142, mode `16`, layer labels `1`–`5`; memorySize `6` means 6 MiB in the drawing-board calculation |
| Magnetic switches | Model explicitly sets `noMagneticSwitch: true`; do not expose Hall/RT controls merely because the base class has them |
| Main lighting | 22 catalog choices, usually brightness/speed 0–4; mode-specific options |
| Side lighting | Six choices; brightness up to 4, speed up to 3 |
| Sleep timers | Bluetooth/2.4 GHz sleep 0–64,800 seconds; deep sleep 10–64,800 seconds in UI metadata |

The catalog ID has not been queried from physical hardware in this project. Name/descriptor agreement is strong supporting evidence, but identify the actual board with `0x8F` before enabling writes. A dongle's PID was **not** inferred from adjacent USB/Bluetooth values.

## Transport framing and checksums

Commands shorter than nine bytes are zero-extended to nine bytes, then padded to the report's payload length. Most USB commands use 64 payload bytes. The checksum modes called `Bit7` and `Bit8` are **checksum byte positions**, not bit flags:

```text
Bit7: payload[7] = 255 - (sum(payload[0:7]) & 255)
Bit8: payload[8] = 255 - (sum(payload[0:8]) & 255)
None: do not insert a checksum
```

Bytes after the checksum are not covered. It is a one's-complement additive header checksum, not a CRC and not a sum-to-zero checksum. The covered header including checksum sums to `0xFF` modulo 256.

USB host API buffer for report 0:

```text
00 | command payload, 64 bytes
```

Bluetooth host API output buffer:

```text
06 | 55 | command payload, 64 bytes
```

The Bluetooth descriptor's 65-byte payload is `55 + 64 command bytes`; adding report ID 6 makes a 66-byte host API buffer. Do not send USB feature ioctls to this Bluetooth collection: its observed descriptor has input/output reports, not feature reports.

Bluetooth input decoding in the app removes report ID, then dispatches on the next byte:

| Marker | Meaning |
|---|---|
| `55` | Command response; following bytes are the response payload |
| `77` | Online/battery indication; next byte is battery |
| `88` | Offline indication |
| `66` | Vendor event/notification stream |

An output payload beginning `77`, padded to 65 bytes and prefixed by report ID 6, asks for status. This is separate from command framing. The app uses default Bluetooth send/read delays of 100/200 ms; USB defaults to 10/10 ms. Individual methods override these delays. The Bluetooth common-request path retries missing replies up to three additional times. Its response buffer takes the most recent response, so serialize operations and avoid simultaneous polling during transfers.

### Identification

Send `8F`, with checksum at position 7. Full USB API prefix is:

```text
00 8F 00 00 00 00 00 00 70 00 ...zero padding to 65 bytes total
```

Bluetooth begins `06 55 8F 00 00 00 00 00 00 70 ...`, 66 bytes total.

Expected unwrapped response:

- `[0] == 0x8F`.
- `[1:5]` internal ID, unsigned little-endian 32-bit. Glyph would be `F3 0B 00 00`.
- `[7:9]` USB firmware version in this family, little-endian 16-bit.
- `[9] == 1` is the YC3123 boot-state check.
- `[11] == 1` reports light-sync support; the app gates its light-sync probe to USB.

Do not apply this response layout to every family's firmware-version command; the older base uses a different read.

## Principal command map for the Glyph family

| SET | GET | Function | Payload / result notes |
|---|---|---|---|
| `01` | — | Factory reset | Long settle; destructive to configuration |
| `03` | `83` | Report rate | Index at `[2]`; base maps 0..6 to 8000,4000,2000,1000,500,250,125 Hz; actual Glyph capability must constrain this |
| `04` | `84` | Current profile | Profile at `[1]` |
| `06` | `86` | Debounce | Value at `[1]` |
| `07` | `87` | Main RGB effect | SET checksum at `[8]`; GET request checksum at `[7]` |
| `08` | `88` | Side RGB effect | SET checksum at `[8]`; different effect IDs/speed handling |
| `09` | `89` | Keyboard options | Multiple packed flags; port exact `setKBOption/getKBOption` |
| `0A` | `8A` | Key matrix | Single-slot or paged full matrix |
| `0B` | `8B` | Macro data | 256-byte logical macro area; write chunks 56 bytes |
| `0C` | `8C` | User RGB picture | RGB triples keyed by matrix slot; family sender uses 378-byte logical picture |
| `10` | `90` | Fn mapping | Adds OS and Fn-layer selectors |
| `11` | `91` | Sleep timers | Four little-endian u16 values at `[8:16]` |
| `17` | `97` | Automatic OS selection | Boolean at `[1]` |
| `22` | — | Screen system information | Statistics at `[8:22]` |
| `25` | `A5` | RGB565 screen transfer | `A5` prepares/authorizes an upload; it is **not a harmless read** |
| `27` | — | Screen language | Boolean selector `[1]`; naming/locale mapping requires UI confirmation |
| `28` | — | Screen clock | Date/time begins at `[8]` |
| `29` | `A9` | RGB888 screen variant | Shared code; Glyph metadata selects RGB565 |
| `50` | `D0` | SKU | Shared base; expose only where the model supports it |
| — | `80` | RF firmware version | u16 at `[1:3]` |
| — | `8F` | Identity/USB version | See above |
| — | `AD` / `AE` | OLED / MLED version | u16 at `[1:3]` |
| `AC` | — | Erase screen flash | Expected reply prefix `AC AA AA 55 55`; destructive |

The wider private analysis also indexes magnetic-axis, mouse and other family commands. Presence in the base class is not proof of Glyph support.

## Key maps and Fn layers

Four-byte actions include:

```text
00 modifiers primary-key secondary-key   keyboard/combo
00 00 00 00                            disabled
09 mode macro-slot 00                   macro binding; modes 0=count,1=toggle,2=while-held
03 00 consumer-low consumer-high        examples include media/volume functions
```

Other action types are preserved in the matrices. `configToMatrix` / `changeArrToConfig` in the main bundle are the authoritative broader conversion table. Preserve unknown four-byte values when editing an existing profile.

**Read a normal matrix:** command `8A`, profile `[1]`, `FF` at `[2]`, page `[3]` from 0 to 7, optional mode `[4]`, checksum `[7]`. Concatenate eight 64-byte response payloads. Those pages are treated as raw matrix bytes, not replies with an opcode header.

**Write one key:** `0A`, profile `[1]`, physical slot `[2]`, commit flag `[5]` (default 1), optional mode `[6]`, checksum `[7]`, action `[8:12]`.

**Write whole matrix:** `0A`, profile `[1]`, `FF` at `[2]`, page `[3]`, actual data length `[4]`, final-page flag `[5]`, optional mode `[6]`, checksum `[7]`, up to 56 data bytes `[8:64]`. A 512-byte matrix takes ten pages; last carries eight meaningful bytes.

The hardware slot is **not** the HID keycode or UI key position. Resolve through `matrices.json`; duplicate usages are disambiguated by occurrence index. Default arrays contain hidden/unused positions, knob entries and duplicate Return/Backspace identities.

Fn reads use `90, os-selector, fn-layer, FF, page`; system selectors are Windows 0, Mac 1, iOS 2, Android 3 in the base helper. Fn single writes use `10, os-selector, fn-layer, slot` and action bytes `[8:12]`. The full Fn sender has a special tenth packet with length 0 and final flag 1 despite padding data; reproduce/test that method separately rather than assuming normal-matrix chunk semantics.

## Macros

Macro payload begins with a little-endian u16 repeat count, followed by event/delay pairs. The app allocates a 256-byte zero-filled buffer.

Keyboard event + short delay (1–127 ms):

```text
usage, delay | (0x80 if key-down else 0)
```

Long delay:

```text
usage, (0x80 if key-down else 0), delay-low, delay-high
```

Mouse button event IDs are `F0` left, `F1` right, `F2` middle, `F3` back, `F4` forward. Mouse motion uses `F9, delay-marker, dx, dy`, optionally followed by a u16 delay. `dx/dy` are signed 8-bit values on decoding.

The bundled motion encoder and decoder disagree for compact delay (`delay` encoded directly, decoder shifts it right by one). Zero-delay key events are also ambiguous because zero is the long-delay marker. Treat these as capture/test targets rather than silently copying questionable behavior.

Macro write header is `0B, slot, chunk-index, 56, final-flag, 0, 0, checksum`, followed by 56 bytes. The writer counts chunks containing nonzero bytes, then sends that many leading chunks, which assumes no empty hole. Validate length and chunk layout in a Linux implementation. Read requests use `8B, slot, page` for up to four 64-byte pages and may stop early on a zero-run heuristic.

A macro definition in local JSON is distinct from its device memory representation and from the four-byte action binding to the macro slot.

## Lighting

Main-light payload:

```text
[0] 07
[1] effect ID
[2] 4 - UI speed
[3] brightness
[4] option<<4 | color-mode
[5:8] R,G,B
[8] checksum of bytes 0..7
```

Normal fixed color uses low nibble 7; rainbow/dazzle uses 8. User pictures, music and screen-color modes have overrides. Pure white is substituted with **FA FF FA**, and converted back on read. Do not overwrite blue at `[7]` with a Bit7 checksum.

Main effect IDs are defined by `LightList`: off 0, solid 1, breathing 2, neon 3, wave 4, ripple 5, raindrop 6, snake 7, reactive 8, convergence 9, sine 10, kaleidoscope 11, line-wave 12, user picture 13, laser 14, circle-wave 15, dazzling 16, rain 17, meteor 18, reactive-off 19, music-3 20, screen-color 21, music-2 22, train 23, fireworks 24, user-color 25. **Glyph exposes a subset of 22**, listed in `lighting-capabilities.json`.

Side-light SET uses `08`, direct speed (not `4-speed`), and its own IDs: off 0, solid 1, breathing 2, neon 3, wave 4, snake 5, music 6. Glyph's catalog exposes the first six, not music.

User RGB pictures use one RGB triple per matrix slot. The common sender emits seven 56-byte chunks for 378 meaningful bytes; final data length 42. Query sends six pages of up to 64 bytes. Check meaningful slot limits before exposing edits to the final matrix positions.

Host-generated live colors have a `0F` path with 56-byte chunks. The app's `supportsLightSync()` explicitly requires USB and identity byte `[11] == 1`. Do not promise Bluetooth reactive lighting from the shared method's existence.

## Screen images and animation

Glyph uses 16-bit **RGB565 big-endian pixels**, traversed **column first** (`x` outer, `y` inner). It crops to left/top inclusive, right/bottom exclusive. For a 2×2 image `red green / blue white`, expected bytes are `F8 00 00 1F 07 E0 FF FF`.

The default whole-screen payload is `428 * 142 * 2 = 121,552` bytes, or 2,171 packets carrying at most 56 bytes each. UI converts PNG/GIF into pixel data; it does not send a PNG/GIF file directly. Later tracing established that the UI converts GIF delays to milliseconds, caps each at 255 and rounds their average before passing that one-byte value to the uploader. See [display timing and memory evidence](display.md); actual hardware playback remains unverified.

**Prepare transfer** (`getTFTLCDDataRGBImg`, despite the name):

| Offset | Data |
|---|---|
| 0 | `A5` for RGB565 |
| 1,2,3 | Current frame, total frame count, delay |
| 4,5 | Image data length bits 0–15, little-endian |
| 6 | Zero |
| 7 | Header checksum |
| 8,9,10,11 | Low bytes of left, top, right, bottom |
| 12,13,14,15 | High bytes of left, top, right, bottom |
| 16,17 | Image data length bits 16–31, little-endian |
| 18 | Extra parameter, default 0 |

App requests a response with 10 ms send / 100 ms read delay and retries up to ten more times if missing or byte `[1] == 0`; success requires `[1] == 1`.

**Send frame data:** `25, frame, total-frames, delay, chunk-low, chunk-high, actual-length, checksum`, then 56 bytes of padded pixel data. The JS uses 2 ms per send for desktop and 5 ms for web; these are requested delays, **not measured throughput guarantees**, especially on Bluetooth.

Clock sync (`28`) uses a **big-endian year** at `[8:10]`, then month/day/hour/minute/second `[10:15]`. Other integers are often little-endian, so avoid a single blanket endianness rule.

System-info sync (`22`) uses u16 little-endian available disk GiB `[8:10]`, total disk GiB `[10:12]`, used RAM GiB `[12:14]`, total RAM GiB `[14:16]`, one-byte CPU usage `[16]`, CPU temperature `[17]`, cumulative network upload GiB `[18:20]`, download GiB `[20:22]`. This path sends host statistics, not text rendered by the host.

## 2.4 GHz routing

The general dongle adapter `yM` serializes/selects the destination:

- `F6 0A` selects keyboard; `F6 05` selects mouse; `F6 0D` selects other/all branch.
- `F7` reads status; `[0]==1` means readable, `[1]/[2]` keyboard/mouse battery, `[3]/[4]==0` online, `[5]==1` send-ready, `[6]` identifies keyboard/mouse/both (1/2/3), `[8]==1` RF boot.
- Before command send, readiness may be polled five times at 100 ms intervals.
- Before command read, the same readiness polling is followed by `FC` read notification.
- `FE,length` is an available send-length notification helper.
- `F1` can read a dongle ID as u16 little-endian in a restricted VID/PID allowlist.

These routing messages do not all pass through the ordinary checksum encoder. Match the source call path. Their presence establishes a general dongle mechanism; the connected Glyph receiver identity and behavior remain untested.

## Firmware findings

The YC3123 boot subclass uses `BA C0` preparation with a u32 little-endian size at byte 8; `BA C2` verification includes u32 values at bytes 8 and 12, with `[2]==55` as success. Its USB upgrade path passes a 65,536-byte boundary into the shared upgrade code. OLED update helpers use `30/31/B0/B1`; flash-content update uses `32/B2`.

This is a useful map for future analysis, not a verified flashing procedure. Image boundaries, board IDs, checksums, reconnect behavior and recovery have not been validated with a firmware image/device. No firmware images were downloaded and the offline codec intentionally contains no erase, bootloader or update transport.
