import json

import pytest
from PIL import Image

from epomaker_driver import cli
from epomaker_driver.device import Keyboard
from epomaker_driver.discovery import DeviceInfo
from epomaker_driver.errors import UnsupportedDevice
from epomaker_driver.models import default_matrix, display_spec, model_by_id
from epomaker_driver.snapshot import capture, factory_reset, restore
from epomaker_driver.transport import Transport


@pytest.fixture
def rt100pro(firmware):
    firmware.model_id = 3152
    firmware.matrices = [bytearray(default_matrix(3152)) for _ in range(3)]
    firmware.fn = [
        bytearray(default_matrix(3152, name)) for name in ("defaultFnMatrix", "defaultFnMacMatrix")
    ]

    class USB:
        response = b""
        prepares = []

        def set_feature(self, data):
            assert len(data) == 65 and data[0] == 0
            command = data[1:]
            if command[0] >= 128:
                if command[0] in (0xA5, 0xA9):
                    self.prepares.append(command)
                self.response = firmware.exchange(command)
            else:
                firmware.send(command)

        def get_feature(self, report_id, length):
            assert report_id == 0 and length == 64
            return self.response

        def close(self):
            firmware.close()

    return Keyboard(Transport(USB(), "usb", sleep=lambda _: None))


def test_rt100_pro_catalog_and_display_limits():
    model = model_by_id(3152)
    assert model["layer"] == 3
    assert model["fnSysLayer"] == {"win": 1, "mac": 1}
    assert model["other"]["screen"]["size"] == {"w": 240, "h": 240}
    assert display_spec(3152) == {
        "width": 240,
        "height": 240,
        "banks": 5,
        "max_frames": 56,
        "pixel_bytes": 2,
    }


def test_rt100_pro_installer_matrices_are_complete():
    assert len(default_matrix(3152)) == 512
    assert len(default_matrix(3152, "defaultFnMatrix")) == 512
    assert len(default_matrix(3152, "defaultFnMacMatrix")) == 512
    assert default_matrix(3152, "defaultFnMACMatrix") != default_matrix(3152, "defaultFnMacMatrix")


def test_rt100_pro_core_configuration_and_lighting_gate(rt100pro, firmware):
    original = rt100pro.read_matrix(0)
    rt100pro.set_key(9, [0, 0, 5, 0], profile=2)
    rt100pro.set_profile(2)
    assert rt100pro.read_matrix(2)[36:40] == bytes([0, 0, 5, 0])
    rt100pro.write_fn_matrix(original, 0)
    rt100pro.write_macro(7, bytes([7]) * 256)
    rt100pro.set_debounce(10)
    rt100pro.set_sleep(60, 3600, 60, 3600)
    rt100pro.set_options(system="mac", wasd_swap=True)
    rt100pro.set_auto_os(True)
    assert rt100pro.status()["profiles"] == 3
    assert rt100pro.status()["options"]["system"] == "mac"
    sent = len(firmware.sent)
    with pytest.raises(UnsupportedDevice):
        rt100pro.set_light("off")
    with pytest.raises(UnsupportedDevice):
        rt100pro.set_light("solid", side=True)
    assert len(firmware.sent) == sent


@pytest.mark.parametrize("os_mode", [0, 1])
def test_rt100_pro_fn_selectors_are_isolated(rt100pro, firmware, os_mode):
    other = bytes(firmware.fn[1 - os_mode])
    matrix = rt100pro.read_matrix(fn=True, os_mode=os_mode)
    rt100pro.set_key(9, [0, 0, 6, 0], fn=True, os_mode=os_mode)
    assert rt100pro.read_matrix(fn=True, os_mode=os_mode)[36:40] == bytes([0, 0, 6, 0])
    assert bytes(firmware.fn[1 - os_mode]) == other
    assert rt100pro.read_matrix(fn=True, os_mode=1 - os_mode) == other
    rt100pro.write_fn_matrix(matrix, os_mode)


def test_rt100_pro_sleep_boundaries_reject_before_writes(rt100pro, firmware):
    rt100pro.set_sleep(0, 64800, 10, 64800)
    before = len(firmware.sent)
    with pytest.raises(ValueError):
        rt100pro.set_sleep(0, 64800, 9, 64800)
    assert len(firmware.sent) == before


def test_rt100_pro_display_capacity_and_rgb565_transfer(rt100pro, monkeypatch):
    transfers = []
    monkeypatch.setattr(
        rt100pro, "_transfer_screen", lambda p, c, progress: transfers.append((p, c))
    )
    frame = bytes(240 * 240 * 2)
    rt100pro.upload_animation([frame] * 56, 100)
    prepare, chunks = transfers[0]
    assert prepare[2:4] == bytes([56, 100])
    assert len(chunks) == 56 * 2058
    with pytest.raises(ValueError, match="2..56"):
        rt100pro.upload_animation([frame] * 57, 100)


def test_rt100_pro_snapshot_roundtrip_and_wrong_model_rejection(rt100pro, firmware, tmp_path):
    source = capture(rt100pro)
    rt100pro.set_key(9, [9, 0, 7, 0], profile=2)
    rt100pro.write_macro(7, bytes([7]) * 256)
    rt100pro.write_picture(bytes([7]) * 378, 4)
    rt100pro.set_profile(2)
    recovery = tmp_path / "before.json"
    result = restore(rt100pro, source, recovery)
    assert result["restored"] and recovery.exists()
    after = capture(rt100pro)
    assert after["matrices"] == source["matrices"]
    assert after["fn"] == source["fn"]
    assert after["macros"] == source["macros"]
    assert after["pictures"] == source["pictures"]
    assert after["profile"] == source["profile"]
    assert after["light"] == source["light"]
    assert after["options"] == source["options"]

    firmware.model_id = 3223
    before = tmp_path / "wrong-before.json"
    with pytest.raises(ValueError, match="does not match"):
        restore(rt100pro, source, before)
    assert not before.exists()


def test_rt100_pro_factory_reset_saves_all_macros_first(rt100pro, firmware, tmp_path, monkeypatch):
    path = tmp_path / "reset.json"
    original_send = firmware.send

    def check_backup_before_reset(command):
        if command[0] == 1:
            assert path.exists()
            assert path.stat().st_mode & 0o777 == 0o600
            assert len(json.loads(path.read_text())["macros"]) == 256
        original_send(command)

    monkeypatch.setattr(firmware, "send", check_backup_before_reset)
    factory_reset(rt100pro, path)
    assert path.exists()
    assert len(json.loads(path.read_text())["macros"]) == 256
    reset_indices = [i for i, command in enumerate(firmware.sent) if command[0] == 1]
    assert reset_indices == [len(firmware.sent) - 1]


def test_rt100_pro_cli_png_and_gif_use_usb_rgb565(monkeypatch, firmware, tmp_path):
    firmware.model_id = 3152

    class USB:
        response = b""
        prepares = []

        def set_feature(self, data):
            assert len(data) == 65 and data[0] == 0
            command = data[1:]
            if command[0] >= 128:
                if command[0] in (0xA5, 0xA9):
                    self.prepares.append(command)
                self.response = firmware.exchange(command)
            else:
                firmware.send(command)

        def get_feature(self, report_id, length):
            assert report_id == 0 and length == 64
            return self.response

        def close(self):
            firmware.close()

    descriptor = bytes.fromhex("06ffff0902a10175089540b102c0")
    info = DeviceInfo("/dev/hidraw3152", "RT100 PRO", 3, 0x3151, 0x5002, descriptor, "usb", 0)
    monkeypatch.setattr(cli, "discover", lambda: [info])
    usb = USB()
    monkeypatch.setattr(
        cli.Transport, "open", lambda _: Transport(usb, "usb", sleep=lambda _: None)
    )
    prefix = ["--device", info.path]
    png = tmp_path / "one.png"
    Image.new("RGB", (240, 240), (255, 0, 0)).save(png)
    assert cli.main([*prefix, "screen", str(png), "--bank", "1"]) == 0
    assert len(usb.prepares) == 1
    chunks = [command for command in firmware.sent if command[0] == 0x25]
    assert b"".join(command[8 : 8 + command[6]] for command in chunks) == b"\xf8\x00" * (240 * 240)

    firmware.sent.clear()
    gif = tmp_path / "two.gif"
    first = Image.new("RGB", (240, 240), (255, 0, 0))
    second = Image.new("RGB", (240, 240), (0, 0, 255))
    first.save(gif, save_all=True, append_images=[second], duration=100, loop=0)
    assert cli.main([*prefix, "animation", str(gif)]) == 0
    prepares = usb.prepares[1:]
    chunks = [command for command in firmware.sent if command[0] == 0x25]
    assert len(prepares) == 1 and prepares[0][2:4] == bytes([2, 100])
    for frame, pixel in enumerate((b"\xf8\x00", b"\x00\x1f")):
        payload = b"".join(command[8 : 8 + command[6]] for command in chunks if command[1] == frame)
        assert payload == pixel * (240 * 240)
