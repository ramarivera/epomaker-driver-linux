import io
import zipfile
import zlib

import pytest

from epomaker_driver import firmware


def raw_image(size=65537):
    value = bytes(range(256)) * (size // 256) + bytes(range(size % 256))
    return value


def zipped(members):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        for name, value in members.items():
            archive.writestr(name, value)
    return output.getvalue()


def test_raw_deflate_main_structure():
    image = raw_image()
    result = firmware.inspect_container(zlib.compress(image)[2:-4], version="1")
    assert result["components"]["main"]["length"] == len(image)
    assert result["components"]["main"]["payload_length"] == 1
    assert result["components"]["main"]["chunks"] == 1
    assert result["structural_only"] is True
    assert result["write_ready"] is False


def test_zip_routes_components_and_chunk_rules():
    main = raw_image(65537)
    flash = b"x" * 113
    result = firmware.inspect_container(
        zipped(
            {
                "firmwareFile.bin": main,
                "firmwareFlashFile.bin": flash,
                "firmwareMledFile.bin": b"mled",
            }
        ),
        version="usb_1",
    )
    assert result["components"]["main"]["chunks"] == 1
    assert result["components"]["flash"]["chunks"] == 3
    assert "chunks" not in result["components"]["mled"]


@pytest.mark.parametrize("data", [b"", b"bad", zlib.compress(b"valid") + b"tail"])
def test_rejects_malformed_raw(data):
    with pytest.raises(ValueError):
        firmware.inspect_container(data, version="1")


def test_rejects_bad_archives_and_members():
    with pytest.raises(ValueError, match="nonempty"):
        firmware.inspect_container(zipped({"firmwareFile.bin": b""}), version="usb_1")
    with pytest.raises(ValueError, match="unsupported"):
        firmware.inspect_container(
            zipped({"firmwareFile.bin": raw_image(), "other.bin": b"x"}), version="usb_1"
        )


def test_rejects_short_calculated_components_and_limits(monkeypatch):
    with pytest.raises(ValueError, match="65536"):
        firmware.inspect_container(zlib.compress(b"short")[2:-4], version="1")
    monkeypatch.setattr(firmware, "MAX_SIZE", 2)
    with pytest.raises(ValueError, match="size"):
        firmware.inspect_container(b"123", version="1")


@pytest.mark.parametrize("version", ["", "_v1_", "___"])
def test_single_or_no_token_uses_raw(version):
    result = firmware.inspect_container(zlib.compress(raw_image(), wbits=-15), version=version)
    assert set(result["components"]) == {"main"}


@pytest.mark.parametrize("version", [None, 1, "v\0", "v\n", "v\r"])
def test_invalid_version(version):
    with pytest.raises(ValueError):
        firmware.inspect_container(b"", version=version)


def test_truncation_trailing_and_raw_expansion(monkeypatch):
    packed = zlib.compress(raw_image(), wbits=-15)
    for value in (packed[:-1], packed + b"tail", packed + packed):
        with pytest.raises(ValueError, match="DEFLATE"):
            firmware.inspect_container(value, version="1")
    monkeypatch.setattr(firmware, "MAX_EXPANDED_SIZE", 16)
    with pytest.raises(ValueError, match="DEFLATE"):
        firmware.inspect_container(packed, version="1")


def test_empty_raw():
    with pytest.raises(ValueError, match="nonempty"):
        firmware.inspect_container(zlib.compress(b"", wbits=-15), version="1")


def test_all_roles_and_checksum():
    import hashlib

    image = bytes(65536) + bytes([255]) * 65
    members = {name: b"component" for name in firmware.MEMBERS}
    members.update({"firmwareFile.bin": image, "firmwareOledFile.bin": image})
    result = firmware.inspect_container(zipped(members), version="main__oled")
    for role in ("main", "oled"):
        info = result["components"][role]
        assert info["checksum"] == 16575
        assert info["chunks"] == 2
        assert info["payload_length"] == 65
        assert info["sha256"] == hashlib.sha256(image).hexdigest()
    for role in ("rf", "mled", "nordic"):
        assert set(result["components"][role]) == {"length", "sha256"}
    assert result["authenticity_verified"] is False
    assert result["model_applicability"] == "unverified"


def test_bad_zip_crc_and_duplicate():
    with pytest.raises(ValueError, match="ZIP"):
        firmware.inspect_container(b"garbage", version="a_b")
    packed = bytearray(zipped({"firmwareFile.bin": raw_image()}))
    packed[30 + len("firmwareFile.bin") + 10] ^= 1
    with pytest.raises(ValueError, match="ZIP"):
        firmware.inspect_container(bytes(packed), version="a_b")
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("firmwareFile.bin", raw_image())
        with pytest.warns(UserWarning, match="Duplicate"):
            archive.writestr("firmwareFile.bin", raw_image())
    with pytest.raises(ValueError, match="duplicate"):
        firmware.inspect_container(output.getvalue(), version="a_b")


def test_zip_expansion_count_and_optional_empty(monkeypatch):
    packed = zipped({"firmwareFile.bin": raw_image(), "firmwareRFFile.bin": b"rf"})
    monkeypatch.setattr(firmware, "MAX_ZIP_ENTRIES", 1)
    with pytest.raises(ValueError, match="entries"):
        firmware.inspect_container(packed, version="a_b")
    monkeypatch.setattr(firmware, "MAX_ZIP_ENTRIES", 32)
    monkeypatch.setattr(firmware, "MAX_EXPANDED_SIZE", 65538)
    with pytest.raises(ValueError, match="size"):
        firmware.inspect_container(packed, version="a_b")
    with pytest.raises(ValueError, match="nonempty"):
        firmware.inspect_container(
            zipped({"firmwareFile.bin": raw_image(), "firmwareRFFile.bin": b""}), version="a_b"
        )


def test_unsupported_compression_and_encryption():
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_BZIP2) as archive:
        archive.writestr("firmwareFile.bin", raw_image())
    with pytest.raises(ValueError, match="compression"):
        firmware.inspect_container(output.getvalue(), version="a_b")
    packed = bytearray(zipped({"firmwareFile.bin": raw_image()}))
    central = packed.index(b"PK\x01\x02")
    packed[central + 8] |= 1
    with pytest.raises(ValueError, match="unsupported"):
        firmware.inspect_container(bytes(packed), version="a_b")


def test_deflated_zip_and_uint32_checksum_wrap():
    payload = b"\xff" * 16843010
    image = bytes(65536) + payload
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("firmwareFile.bin", image)
    result = firmware.inspect_container(output.getvalue(), version="usb_rf")
    assert result["components"]["main"]["checksum"] == 254
    assert result["components"]["main"]["chunks"] == 263173
