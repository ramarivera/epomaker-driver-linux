"""Bounded, structural inspection of vendor firmware containers."""

from __future__ import annotations

import hashlib
import io
import re
import zipfile
import zlib

MAX_SIZE = 32 * 1024 * 1024
MAX_EXPANDED_SIZE = 32 * 1024 * 1024
MAX_ZIP_ENTRIES = 32
MEMBERS = {
    "firmwareFile.bin": "main",
    "firmwareRFFile.bin": "rf",
    "firmwareOledFile.bin": "oled",
    "firmwareMledFile.bin": "mled",
    "firmwareNordicFile.bin": "nordic",
    "firmwareFlashFile.bin": "flash",
}


def _image_info(data: bytes, *, prefix: bool, chunk_size: int) -> dict:
    result = {"length": len(data), "sha256": hashlib.sha256(data).hexdigest()}
    if prefix:
        if len(data) <= 65536:
            raise ValueError("component must be longer than its 65536-byte prefix")
        payload = data[65536:]
        result.update(
            prefix_length=65536,
            payload_length=len(payload),
            chunks=(len(payload) + chunk_size - 1) // chunk_size,
            checksum=sum(payload) % (2**32),
        )
    else:
        result["chunks"] = (len(data) + chunk_size - 1) // chunk_size
    return result


def _load_raw(data: bytes) -> bytes:
    try:
        inflater = zlib.decompressobj(-15)
        output = inflater.decompress(data, MAX_EXPANDED_SIZE + 1)
    except zlib.error as error:
        raise ValueError("malformed or oversized raw DEFLATE firmware") from error
    if (
        len(output) > MAX_EXPANDED_SIZE
        or not inflater.eof
        or inflater.unused_data
        or inflater.unconsumed_tail
    ):
        raise ValueError("malformed or oversized raw DEFLATE firmware")
    return output


def _load_zip(data: bytes) -> dict[str, bytes]:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            infos = archive.infolist()
            if len(infos) > MAX_ZIP_ENTRIES:
                raise ValueError("firmware archive has too many entries")
            result: dict[str, bytes] = {}
            for info in infos:
                if info.filename in result:
                    raise ValueError(f"duplicate firmware member: {info.filename}")
                if info.filename not in MEMBERS or info.is_dir() or info.flag_bits & 1:
                    raise ValueError(f"unsupported firmware member: {info.filename}")
                if info.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
                    raise ValueError(
                        f"unsupported compression for firmware member: {info.filename}"
                    )
                remaining = MAX_EXPANDED_SIZE - sum(map(len, result.values()))
                if info.file_size > remaining:
                    raise ValueError("expanded firmware exceeds size limit")
                with archive.open(info) as member:
                    value = member.read(remaining + 1)
                if len(value) != info.file_size:
                    raise ValueError("truncated firmware member")
                result[info.filename] = value
                if sum(len(value) for value in result.values()) > MAX_EXPANDED_SIZE:
                    raise ValueError("expanded firmware exceeds size limit")
    except (zipfile.BadZipFile, EOFError, RuntimeError, OSError, zlib.error) as error:
        raise ValueError("malformed firmware ZIP") from error
    if not result.get("firmwareFile.bin"):
        raise ValueError("firmware archive must contain nonempty firmwareFile.bin")
    return result


def inspect_container(data: bytes, *, version: str) -> dict:
    """Inspect a raw-deflate image or versioned vendor ZIP without extraction."""
    if not isinstance(data, bytes) or len(data) > MAX_SIZE:
        raise ValueError("firmware input exceeds size limit")
    if not isinstance(version, str) or "\0" in version or "\n" in version or "\r" in version:
        raise ValueError("version must be a safe string")
    components = {}
    if len(re.findall(r"[^_]+", version)) > 1:
        members = _load_zip(data)
        for filename, value in members.items():
            if not value:
                raise ValueError(f"firmware member must be nonempty: {filename}")
            role = MEMBERS[filename]
            if role in ("main", "oled"):
                components[role] = _image_info(value, prefix=True, chunk_size=64)
            elif role == "rf":
                components[role] = {
                    "length": len(value),
                    "sha256": hashlib.sha256(value).hexdigest(),
                }
            elif role == "flash":
                components[role] = _image_info(value, prefix=False, chunk_size=56)
            else:
                components[role] = {
                    "length": len(value),
                    "sha256": hashlib.sha256(value).hexdigest(),
                }
    else:
        image = _load_raw(data)
        if not image:
            raise ValueError("firmware image must be nonempty")
        components["main"] = _image_info(image, prefix=True, chunk_size=64)
    return {
        "version": version,
        "components": components,
        "structural_only": True,
        "write_ready": False,
        "model_applicability": "unverified",
        "authenticity_verified": False,
    }
