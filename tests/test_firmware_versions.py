import pytest

from epomaker_driver.firmware_versions import analyze

CURRENT = {name: 0x100 for name in ("usb", "rf", "oled", "flash", "mled", "nordic")}
IMAGES = {name: {"length": 1} for name in ("main", "rf", "oled", "flash", "mled", "nordic")}


def test_routes_tokens_and_uses_hex_digit_runs():
    result = analyze("usbv1.0.2_rfv2.0.0_mledv3", CURRENT, IMAGES)
    assert [item["component"] for item in result["candidates"]] == ["usb", "rf", "mled"]
    assert result["candidates"][0]["observed"] == 0x102
    assert result["candidates"][0]["candidate"] is True
    assert result["candidates"][2]["reason"] == "unsupported-dispatch"
    assert result["write_ready"] is False


def test_missing_and_unavailable_current_versions():
    current = {**CURRENT, "rf": None, "oled": 0}
    images = {"main": IMAGES["main"]}
    result = analyze("usbv100_rfv200_oledv200", current, images)
    assert [item["reason"] for item in result["candidates"]] == [
        "not-newer",
        "missing-image",
        "missing-image",
    ]


@pytest.mark.parametrize(
    "version", ["", "usbv", "usbv100_usbv101", "usbv100_rfv100_rfv101", "usbv100_bad1"]
)
def test_rejects_malformed_version_tokens(version):
    with pytest.raises(ValueError):
        analyze(version, CURRENT, IMAGES)


def test_rejects_bad_current_components_and_missing_main():
    with pytest.raises(ValueError):
        analyze("usbv100", {**CURRENT, "usb": True}, IMAGES)
    with pytest.raises(ValueError):
        analyze("usbv100", CURRENT, {})


@pytest.mark.parametrize("first", ["v1.0.2", "1.0.2", "usbv1.0.2"])
def test_first_token_has_no_required_prefix_and_missing_versions_are_unknown(first):
    result = analyze(first + "_rfv200", {"usb": 0x100}, IMAGES)
    assert result["candidates"][0]["candidate"] is True
    assert result["candidates"][1]["reason"] == "unknown-current"


@pytest.mark.parametrize("value", [None, 0])
def test_unavailable_is_not_an_update(value):
    item = analyze("v200", {"usb": value}, IMAGES)["candidates"][0]
    assert item["candidate"] is False
    assert item["reason"] == "unknown-current"


def test_all_dispatch_targets():
    result = analyze("v200_rfv200_oledv200_flashv200_mledv200_nordicv200", CURRENT, IMAGES)
    assert [c["candidate"] for c in result["candidates"]] == [True, True, True, True, False, False]
    assert [c["reason"] for c in result["candidates"]][-2:] == ["unsupported-dispatch"] * 2


@pytest.mark.parametrize(
    "version",
    [
        "___",
        "v100_rfv2oledv3",
        "usbvusbv1",
        "v99999",
        "v١٢",
        "v100_UNKNOWN2",
        "v" * 257,
        None,
    ],
)
def test_invalid_token_contract(version):
    with pytest.raises(ValueError):
        analyze(version, CURRENT, IMAGES)


@pytest.mark.parametrize("current", [[], {"bad": 1}, {"usb": -1}, {"rf": 65536}, {"oled": 1.2}])
def test_invalid_current_versions(current):
    with pytest.raises(ValueError):
        analyze("v100", current, IMAGES)


@pytest.mark.parametrize("images", [[], {"main": {}, "bad": {}}, {"main": {"length": 1}, 1: {}}])
def test_invalid_image_container(images):
    with pytest.raises(ValueError):
        analyze("v100", CURRENT, images)
