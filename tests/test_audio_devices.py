import json
import subprocess

import pytest

from epomaker_driver.audio_capture import AudioCaptureError
from epomaker_driver.audio_devices import list_audio_outputs


class Result:
    def __init__(self, payload, returncode=0):
        self.stdout = json.dumps(payload).encode()
        self.returncode = returncode


def runner_for(payload, returncode=0):
    calls = []

    def runner(*args, **kwargs):
        calls.append((args, kwargs))
        return Result(payload, returncode)

    runner.calls = calls
    return runner


def test_discovers_only_audio_sinks_with_stable_labels_and_sorting():
    runner = runner_for(
        [
            {
                "type": "PipeWire:Interface:Node",
                "info": {"props": {"media.class": "Audio/Source", "object.serial": 1}},
            },
            {
                "type": "PipeWire:Interface:Node",
                "info": {
                    "props": {"media.class": "Audio/Sink", "object.serial": "12", "node.nick": "Z"}
                },
            },
            {
                "type": "PipeWire:Interface:Node",
                "info": {
                    "props": {
                        "media.class": "Audio/Sink",
                        "object.serial": 3,
                        "node.description": "A",
                    }
                },
            },
            {
                "type": "PipeWire:Interface:Node",
                "info": {
                    "props": {
                        "media.class": "Audio/Sink",
                        "object.serial": 12,
                        "node.description": "Duplicate",
                    }
                },
            },
        ]
    )
    assert list_audio_outputs(runner=runner) == [
        {"id": "3", "name": "A"},
        {"id": "12", "name": "Z"},
    ]
    assert runner.calls[0][0] == (["pw-dump"],)
    assert runner.calls[0][1] == {
        "shell": False,
        "capture_output": True,
        "timeout": 5,
        "check": False,
    }


def test_skips_invalid_sink_serials_and_falls_back_to_id():
    runner = runner_for(
        [
            {
                "type": "PipeWire:Interface:Node",
                "info": {"props": {"media.class": "Audio/Sink", "object.serial": -1}},
            },
            {
                "type": "PipeWire:Interface:Node",
                "info": {"props": {"media.class": "Audio/Sink", "object.serial": True}},
            },
            {
                "type": "PipeWire:Interface:Node",
                "info": {"props": {"media.class": "Audio/Sink", "object.serial": "20"}},
            },
        ]
    )
    assert list_audio_outputs(runner=runner) == [{"id": "20", "name": "20"}]


@pytest.mark.parametrize(
    "payload, message", [(None, "root"), ([1], "entries"), ("bad", "invalid JSON")]
)
def test_rejects_malformed_json_shapes(payload, message):
    if payload == "bad":

        class BadResult:
            stdout = b"{bad"
            returncode = 0

        def runner(*args, **kwargs):
            return BadResult()
    else:
        runner = runner_for(payload)
    with pytest.raises(AudioCaptureError, match=message):
        list_audio_outputs(runner=runner)


def test_reports_missing_timeout_and_nonzero():
    def missing(*args, **kwargs):
        raise FileNotFoundError

    with pytest.raises(AudioCaptureError, match="not installed"):
        list_audio_outputs(runner=missing)

    def timed_out(*args, **kwargs):
        raise subprocess.TimeoutExpired("pw-dump", 5)

    with pytest.raises(AudioCaptureError, match="timed out"):
        list_audio_outputs(runner=timed_out)
    with pytest.raises(AudioCaptureError, match="status 7"):
        list_audio_outputs(runner=runner_for([], returncode=7))


def test_rejects_oversized_output():
    class HugeResult:
        returncode = 0
        stdout = b"x" * (8 * 1024 * 1024 + 1)

    with pytest.raises(AudioCaptureError, match="too large"):
        list_audio_outputs(runner=lambda *args, **kwargs: HugeResult())


@pytest.mark.parametrize("serial", [0, "0", "²", "１２", "-1", 2**63, "9" * 20])
def test_non_target_serials_are_not_offered(serial):
    payload = [
        {
            "type": "PipeWire:Interface:Node",
            "info": {
                "props": {
                    "media.class": "Audio/Sink",
                    "object.serial": serial,
                }
            },
        }
    ]
    assert list_audio_outputs(runner=runner_for(payload)) == []


@pytest.mark.parametrize(
    "record",
    [
        {"type": "PipeWire:Interface:Device"},
        {"type": "PipeWire:Interface:Node", "info": None},
        {"type": "PipeWire:Interface:Node", "info": {"props": None}},
    ],
)
def test_ignores_nodes_without_playback_metadata(record):
    assert list_audio_outputs(runner=runner_for([record])) == []
