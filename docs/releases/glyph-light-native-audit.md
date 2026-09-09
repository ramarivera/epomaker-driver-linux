# Glyph3059 light native helper audit

Static audit of the Windows 3.2.22 extracted helpers. No vendor executable was run.

## Provenance and platform coverage

The Windows files are Rust PE32+ x86-64 GUI executables:

| helper | SHA-256 | size | imports relevant to behavior |
|---|---|---:|---|
| `iot_manager/rhythm_service.exe` | `d40cde8e34216d77f2d07379a74edc5db0cdf2a2601c6316cc3ddad288ac9706` | 4.5 MiB | `ws2_32.dll` sockets, no screen/DXGI imports |
| `iot_manager/screen_capture_service.exe` | `0838804a8bb24670d3765081119d6e4e5a726175eaeb6d2126fdd6a240a35a4d` | 3.7 MiB | `ws2_32.dll`, `d3d11.dll`, `dxgi.dll` |

The Mac app's `Contents/Resources/app/iot_manager` contains `iot_manager_rs` and `common_hid_rs`, but no equivalent rhythm or screen-capture helper. The release manifest identifies these artifacts as the 3.2.22 Windows and Mac packages (`docs/source-releases.json`).

## Confirmed IPC contract

The renderer bundle `dist/js/57cfa1b3.js` is the strongest contract evidence. Both helpers serve gRPC-Web over loopback HTTP/1.1:

### Rhythm analysis (`rhythm_service.exe`)

- Renderer connects to `http://127.0.0.1:3839` (bundle offset 23454).
- Service strings at PE offsets `0x3604c8` and `0x3664c0` identify “Rhythm Analysis Service with gRPC-Web” and `rhythm_analysis.RhythmAnalysisService`; method path strings begin at `0x369338`.
- Methods: unary `ListAudioDevices`, unary `GetConfiguration`, unary `Configure`, and server-streaming `StreamData`.
- The temporary extracted descriptor `/tmp/epomaker-analysis/proto-win/rhythm_analysis.proto` (reconstructed from bundled protobuf descriptors; not checked into this repository) gives configuration fields: audio device id, `num_bands`, `fft_size`, gain, tilt/contrast/release factors, dB min/max, and `attack_frames`. Stream responses contain repeated float `spectrum_data`.
- Renderer starts the helper by launching `iot_manager/rhythm_service.exe`, then starts `StreamData`; it stops the stream after a 3-second no-data timeout. This timeout and port are renderer behavior, not proof of native frame cadence.

Native strings at `0x352610` include the configuration field names. Strings at `0x3a6dc0` include FFT/rustfft diagnostics; strings at `0x369518` identify generated Rust protobuf source `src\\proto_gen\\rhythm_analysis.rs`, and `0x3664c0` identifies the service name. These establish implementation family and API, but do not establish a specific FFT window, sample rate, band mapping, or stream frequency.

### Screen capture (`screen_capture_service.exe`)

- Renderer connects to `http://127.0.0.1:3840` (bundle offset 32647).
- Methods: unary `ListScreens`, server-streaming `StreamScreenThumbnails`.
- Request fields are `screen_id`, crop `x/y/width/height`, and `thumbnail_width/thumbnail_height`; response is raw `pixels` bytes. The temporary extracted descriptor `/tmp/epomaker-analysis/proto-win/screen.proto` (reconstructed from bundled protobuf descriptors; not checked into this repository) records these fields.
- Renderer launches `iot_manager/screen_capture_service.exe`, lists displays, then requests the selected crop at `thumbnail_width=21`, `thumbnail_height=6` and redraws its canvas every 30 ms. It converts each returned RGBA quadruplet to RGB by alpha premultiplication (`round(channel * alpha/255)`) before drawing. The 21×6 layout and 30 ms redraw are renderer choices; native capture cadence is not proven by these strings.
- Native imports `d3d11.dll` and `dxgi.dll`, while strings at `0x297590`, `0x2976a0`, `0x29c580`, and `0x29c730` identify the capture/grpc service, screen id logging, initialization, port fallback, and gRPC-Web listener. Strings at `0x29e798` expose the request field names. This supports a DirectX/DXGI desktop capture implementation, but static imports alone do not prove which API path is used at runtime.

## Actionable limits

The helpers do not expose a command-line contract in the inspected strings; the observable contract is loopback gRPC-Web on ports 3839/3840. No reliable native evidence establishes audio sample rate, FFT cadence, spectrum normalization, screen pixel format beyond the renderer's four-byte RGBA expectation, or whether the service chooses a different port when occupied. Implementations should follow the protobuf/renderer contract and treat cadence and DSP details as unknown until tested against a live service.
