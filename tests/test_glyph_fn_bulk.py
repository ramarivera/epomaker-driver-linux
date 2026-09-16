"""Full Fn frame fixtures from docs/releases/glyph-full-writer-audit.md."""

import pytest

from epomaker_driver import codec
from epomaker_driver.device import Keyboard
from epomaker_driver.errors import ProtocolError


@pytest.mark.parametrize("os_mode", [0, 1])
def test_full_fn_wire_headers_tail_and_roundtrip(firmware, os_mode):
    # Nonzero final bytes catch treating the final header length of zero as no data.
    matrix = bytes(range(256)) * 2
    other = bytes(firmware.fn[1 - os_mode])
    keyboard = Keyboard(firmware)
    keyboard.write_fn_matrix(matrix, os_mode)
    frames = [frame for frame in firmware.sent if frame[0] == 0x10]
    assert len(frames) == 10
    for page, frame in enumerate(frames):
        header = bytes([0x10, os_mode, 0, 255, page, 0 if page == 9 else 56, int(page == 9)])
        expected = header + bytes([255 - (sum(header) & 255)])
        expected += matrix[page * 56 : (page + 1) * 56].ljust(56, b"\0")
        assert frame == expected
    assert frames[-1][8:16] == bytes(range(248, 256))
    assert frames[-1][16:] == bytes(48)
    assert keyboard.read_matrix(fn=True, os_mode=os_mode) == matrix
    assert bytes(firmware.fn[1 - os_mode]) == other


@pytest.mark.parametrize("size", [0, 511, 513])
def test_fn_bulk_rejects_bad_matrix_length(size):
    with pytest.raises(ValueError):
        list(codec.fn_matrix_chunks(bytes(size)))


@pytest.mark.parametrize("os_mode", [-1, 2, True, "0"])
def test_fn_bulk_rejects_invalid_os(os_mode):
    with pytest.raises(ValueError):
        list(codec.fn_matrix_chunks(bytes(512), os_mode=os_mode))


def test_fn_bulk_readback_corruption_is_reported(firmware):
    send = firmware.send

    def corrupt_final(frame, **options):
        send(frame, **options)
        if frame[0] == 0x10 and frame[3] == 255 and frame[4] == 9:
            firmware.fn[0][511] ^= 1

    firmware.send = corrupt_final
    with pytest.raises(ProtocolError, match="Fn matrix readback"):
        Keyboard(firmware).write_fn_matrix(bytes(range(256)) * 2)


def test_fn_bulk_stops_after_transport_failure(firmware):
    send = firmware.send
    attempted = []

    def fail_middle(frame, **options):
        attempted.append(frame)
        if frame[0] == 0x10 and frame[4] == 4:
            raise OSError("disconnected during upload")
        send(frame, **options)

    firmware.send = fail_middle
    with pytest.raises(OSError, match="disconnected"):
        Keyboard(firmware).write_fn_matrix(bytes(range(256)) * 2)
    assert [frame[4] for frame in attempted] == list(range(5))
    # This asserts no retries or later commit, not physical flash atomicity.


def test_other_models_keep_existing_changed_slot_path(firmware):
    firmware.model_id = 2895
    matrix = bytearray(firmware.fn[0])
    matrix[36:40] = bytes([0, 0, 5, 0])
    Keyboard(firmware).write_fn_matrix(matrix)
    frames = [frame for frame in firmware.sent if frame[0] == 0x10]
    assert len(frames) == 1 and frames[0][3] == 9
    assert frames[0][8:12] == bytes([0, 0, 5, 0])


@pytest.mark.parametrize("layer", [-1, 1, True])
def test_fn_bulk_rejects_unavailable_layer(layer):
    with pytest.raises(ValueError):
        list(codec.fn_matrix_chunks(bytes(512), layer=layer))
