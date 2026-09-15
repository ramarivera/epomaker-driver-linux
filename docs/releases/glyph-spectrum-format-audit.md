# Glyph spectrum format audit

This is a bounded static audit of the 3.2.22 extracted vendor bundles. No
vendor executable was run, and no audio, network, HID, or hardware operation
was attempted. The question was whether the host's `numBands=32` default is
compatible with renderer slices reaching `36:41`.

## Inputs and provenance

The inspected files are under `/tmp/glyph-layout-audit.fIoAml`:

| artifact | size | SHA-256 |
| --- | ---: | --- |
| `win-app/resources/app/dist/js/57cfa1b3.js` | 130,747 bytes | `9b9e81be794a543617eec5a125c9efd55004c78d6a4c17ea30318c5aa9a6cd22` |
| `win-app/resources/app/iot_manager/rhythm_service.exe` | 4,692,544 bytes | `d40cde8e34216d77f2d07379a74edc5db0cdf2a2601c6316cc3ddad288ac9706` |
| `mac-payload/.../Resources/app/dist/js/13da2307.js` | 130,753 bytes | `e58f558ab99d02de0c74c7febed4e8624064106cd0dd55339b82c4f6ce583d31` |
| `mac-payload/.../Resources/app/iot_manager/iot_manager_rs` | 7,103,792 bytes | `dac6bb1b52da08a7b0b189dbc361fe9098c2b2f753d75ef1ec93edb489c0a04e` |

The Windows native file is a PE32+ x86-64 executable. The Mac native file is
an x86-64 Mach-O executable. The Mac bundle has no separate rhythm helper;
rhythm code is compiled into `iot_manager_rs`. The Windows bundle does have
the separate `rhythm_service.exe` helper.

## What the host proves

Both renderer chunks contain the same relevant behavior documented in
`glyph-rhythm-audit.md`:

* missing configuration is initialized with `numBands=32` and `fftSize=512`;
* the stream response contains repeated float `spectrum_data`;
* `drawTripleCircle` and `drawTriangle` use `data.slice(36, 41)`;
* the renderer does not assert an exact response length.

The `36:41` expression is therefore a real host-side access pattern, but it
does not by itself prove that the service emits 41 values.

## Native evidence for a 42-element working shape

The Mac binary retains Rust symbols and source paths. Relevant symbols include:

* `iot_manager_rs::features::music_rhythm::RhythmProcessor::new`, at
  `0x1000e9ad0`;
* `iot_manager_rs::features::music_rhythm::RhythmProcessor::process`, at
  `0x1000e9c00`.

In the constructor disassembly, three independent allocations call
`rust_alloc_zeroed` with `edi=0xa8` and `esi=0x4`. Since `0xa8 / 4 = 42`, each
allocation reserves storage for 42 four-byte floats. The constructor then
writes `0x2a` (42) into the corresponding vector length/capacity fields. This
is direct native evidence of three fixed 42-element working vectors; it is
stronger than an incidental string or a renderer slice.

The process disassembly provides a second boundary clue. At
`0x1000ea340` and `0x1000ea3ce` it compares the effective length against
`0x29` (41), loads 41 as the fallback maximum, and uses the smaller value.
Later, the loop at `0x1000ea620` terminates after comparing its index against
`0x2b` (43), consistent with a bounded loop around the 42-element working
shape. These instructions show native fixed-size processing/guarding around
41/42; they do not show a protobuf response serializer writing exactly 41 or
42 floats.

The same Mac binary retains the native source paths
`src/features/music_rhythm.rs`, `src/io_client/rhythm_client.rs`, and
`src/gen_proto/rhythm_analysis.rs`, plus the generated protobuf field name
`spectrum_data`. Static strings in the Windows helper likewise retain
`src\\audio\\capture.rs`, `src\\proto_gen\\rhythm_analysis.rs`,
`rustfft-6.4.0`, `cpal-0.16.0`, and the `StreamData` gRPC-Web method. They
confirm the helper and implementation family, but the stripped Windows PE
does not expose a useful named processor symbol.

## Conclusion

The native audit resolves the apparent contradiction only partially:

1. `numBands=32` is conclusively a host default sent in the initial
   configuration.
2. The Mac native implementation conclusively has 42-float persistent working
   vectors and processing boundaries at 41/42. This is evidence that the
   native path can have a 41-index spectrum shape, and it makes the host's
   `36:41` group plausible.
3. This audit has not traced those buffers into an actual
   `StreamDataResponse.spectrum_data` serializer, or established whether the
   native processor expands 32 configured bands to 41/42 before serialization.
   The wire field is repeated and length-delimited, so its schema alone cannot
   answer that question.

Accordingly, Linux should continue to treat native stream length/expansion as
unknown. A 32-band local DSP cannot claim parity for the `36:41` modes. The next static step is to trace the processor result through its caller and
response serializer. If static tracing remains inconclusive, a controlled
experiment would feed synthetic PCM into an isolated helper harness and inspect
the emitted `StreamDataResponse` lengths while varying `numBands`; injecting
response messages would not establish what the native producer emits. No such
harness or experiment has been run.
