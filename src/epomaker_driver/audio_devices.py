"""Discover PipeWire audio output nodes without exposing node metadata."""

from __future__ import annotations

import json
import subprocess

from .audio_capture import AudioCaptureError

_MAX_OUTPUT_BYTES = 8 * 1024 * 1024
_MAX_SERIAL = 2**63 - 1


def _serial(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return str(value) if 0 < value <= _MAX_SERIAL else None
    if isinstance(value, str) and value.isascii() and len(value) <= 19 and value.isdecimal():
        number = int(value)
        return str(number) if 0 < number <= _MAX_SERIAL else None
    return None


def list_audio_outputs(*, runner=subprocess.run):
    """Return stable ``id``/``name`` records for PipeWire playback sinks."""
    argv = ["pw-dump"]
    try:
        result = runner(
            argv,
            shell=False,
            capture_output=True,
            timeout=5,
            check=False,
        )
    except FileNotFoundError as error:
        raise AudioCaptureError("pw-dump is not installed; install PipeWire tools") from error
    except subprocess.TimeoutExpired as error:
        raise AudioCaptureError("timed out waiting for pw-dump") from error
    if result.returncode != 0:
        raise AudioCaptureError(f"pw-dump exited with status {result.returncode}")
    output = result.stdout
    if isinstance(output, str):
        output_size = len(output.encode())
    else:
        output_size = len(output or b"")
    if output_size > _MAX_OUTPUT_BYTES:
        raise AudioCaptureError("pw-dump output is too large")
    try:
        records = json.loads(output)
    except (TypeError, ValueError, json.JSONDecodeError) as error:
        raise AudioCaptureError("pw-dump returned invalid JSON") from error
    if not isinstance(records, list):
        raise AudioCaptureError("pw-dump JSON root must be an array")

    outputs = []
    for record in records:
        if not isinstance(record, dict):
            raise AudioCaptureError("pw-dump JSON entries must be objects")
        if record.get("type") != "PipeWire:Interface:Node":
            continue
        info = record.get("info")
        if not isinstance(info, dict):
            continue
        props = info.get("props")
        if not isinstance(props, dict) or props.get("media.class") != "Audio/Sink":
            continue
        serial = _serial(props.get("object.serial", record.get("object.serial")))
        if serial is None:
            continue
        label = serial
        for source in (props, info):
            candidate = next(
                (
                    source.get(key)
                    for key in (
                        "node.description",
                        "node.nick",
                        "node.name",
                        "description",
                        "nick",
                        "name",
                    )
                    if isinstance(source.get(key), str) and source[key]
                ),
                None,
            )
            if candidate is not None:
                label = candidate
                break
        outputs.append({"id": serial, "name": label})

    unique = {}
    for output in outputs:
        unique.setdefault(output["id"], output)
    return sorted(unique.values(), key=lambda output: (output["name"].casefold(), output["id"]))
