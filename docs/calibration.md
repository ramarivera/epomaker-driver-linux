# USB magnetic calibration

The CLI provides a timed calibration session for migrated H60, HE68 Lite and
HE60 Lite models and the [additional wired RY5088 models](ry5088-wired.md):
internal IDs 3662, 3664, 2762, 2883, 3727, 3759, 2465, 2586, 2870 and 3691. A
wireless-capable keyboard must be connected through its supported USB command
interface. Calibration is a device mutation; the implementation has only been
validated with source inspection and simulated firmware, not physical keyboards.

Run `epomaker --device /dev/hidrawN calibrate --seconds 30`. The CLI tells you
when to release all keys for the two-second baseline, then when to press every
key fully during the timed phase. `--seconds` controls that second phase, accepts
1–300 seconds and defaults to 30. Ctrl-C ends the session and attempts cleanup.
The time limit is a Linux CLI bound, not a recovered firmware restriction.

The JSON result includes `completed`, `samples`, `duration` and `last` telemetry.
`completed: true` means the timed session and stop command finished successfully;
it does not prove that each physical key reached its calibrated position. There
is no recovered firmware completion acknowledgement or per-key success flag in
this interface. The vendor UI uses a visual raw-value threshold and remembers
which keys crossed it; the CLI does not turn that heuristic into a success claim.

`epomaker --device /dev/hidrawN read-calibration` reads the raw telemetry once
without starting or stopping calibration. Its meaning outside an active session
still needs hardware comparison.

## Protocol and sequencing

Baseline archives are identified by [source-releases.json](source-releases.json).
The private modern bases are macOS `623d2d52.js` and Windows `17dc9c62.js`.
Their calibration methods use the same commands and ordering:

1. Send `1c 01` to start released-position measurement.
2. Wait two seconds, in addition to the ordinary command-settling delay.
3. Send `1c 00` to stop released-position measurement.
4. Send `1e 01` to start maximum-travel calibration.
5. Poll telemetry for the chosen duration.
6. Send `1e 00` to stop maximum-travel calibration.

Commands use 64-byte packets and checksum byte 7. The CLI does not send
key-selection masks, magnetic parameter writes, switch-type writes or factory
reset commands. Calibration telemetry covers the full 128-slot matrix.

A telemetry sample sends four `e5 fe 01 PAGE` requests for pages 0–3, using the
vendor's 1 ms send/read delays. Each response is exactly 64 raw bytes: there is
no echoed opcode or header. The concatenated 256 bytes encode 128 little-endian
uint16 values, returned as `values` with the original bytes in `raw`. They are
not converted to millimeters. The vendor's displayed flux values are initialized
to zero in this path; the CLI does not invent flux measurements from them.

Linux polls with a 100 ms interval after each sample and retains only the last
sample plus a count. The backend holds the transport transaction lock throughout
the session, including cleanup, so another operation on that transport cannot
interleave settings commands. Standalone four-page reads also hold the lock.

## Cancellation and errors

After an attempted start, any exception or Ctrl-C independently attempts both
`1c 00` and `1e 00`. Failure of the first cleanup command does not prevent the
second attempt. The original error is retained; failed cleanup is reported
explicitly with its cause. A failed send is treated as potentially delivered.
If the progress callback fails before any start attempt, no cleanup commands are
sent. Normal completion sends only the vendor's maximum-travel stop command.

Cleanup cannot guarantee device recovery after disconnection, forced process
termination or a rejected stop command. Calibration data is not backed up or
rolled back by this command. The completion result is returned only after the
normal stop command succeeds.

## Evidence and tests

Private prettified macOS base references: command IDs at 82–84; bulk read and
uint16 decoding at 951–976; calibration helpers and orchestration at 1547–1603.
The corresponding Windows base has equivalent methods. The vendor UI's start
and stop dispatch is at macOS main 115125 onward / Windows main 114037 onward.
The UI's visual threshold logic is at macOS main 122973–122991. This is separate
from switch selection and ordinary actuation settings.

Tests cover exact command order and checksum shape, baseline delay, raw reads
whose first byte is not an opcode, all ten model IDs through CLI dispatch,
USB/model gates, invalid duration, cancellation, partial starts, failed stops,
malformed pages, lock scope and independent cleanup failures. Firmware behavior,
physical calibration results, reconnect recovery and GUI integration remain
unverified or unfinished; see [migration status](parity.md).
