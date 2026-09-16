"""Offline Glyph image placement; see docs/releases/glyph-display-import-audit.md."""

from __future__ import annotations

import base64
import io
import math

from PIL import Image, ImageOps

from . import media

MAX_CONTENT_BYTES = 14 * 1024 * 1024
MAX_SOURCE_PIXELS = 16_000_000
MAX_FRAMES = 46
MAX_SCALE = 300
_FORMATS = {"PNG", "JPEG", "GIF", "WEBP"}


def _open(content):
    if not isinstance(content, bytes) or not content:
        raise ValueError("image content must be nonempty bytes")
    if len(content) > MAX_CONTENT_BYTES:
        raise ValueError("image content exceeds the 14 MiB limit")
    try:
        source = Image.open(io.BytesIO(content))
    except (OSError, SyntaxError, Image.DecompressionBombError) as error:
        raise ValueError("unsupported or invalid image") from error
    if source.format not in _FORMATS:
        source.close()
        raise ValueError("image format must be PNG, JPEG, GIF, or WEBP")
    if source.width * source.height > MAX_SOURCE_PIXELS:
        source.close()
        raise ValueError("source image exceeds 16 million pixels")
    return source


def _fit_size(width, height):
    if width / height > 428 / 142:
        return 428, max(1, math.ceil(428 * height / width))
    return max(1, math.ceil(142 * width / height)), 142


def _round_positive(value):
    return math.floor(value + 0.5)


def _delay(source):
    return min(255, max(0, int(source.info.get("duration", 0))))


def _frame_count(source):
    count = getattr(source, "n_frames", 1)
    if not 1 <= count <= MAX_FRAMES:
        raise ValueError("image must contain 1..46 frames")
    return count


def inspect_import(content: bytes):
    source = _open(content)
    try:
        count = _frame_count(source)
        source.seek(0)
        oriented = ImageOps.exif_transpose(source).convert("RGBA")
        fit_width, fit_height = _fit_size(oriented.width, oriented.height)
        initial_x = _round_positive((428 - fit_width) / 2)
        initial_y = _round_positive((142 - fit_height) / 2)
        canvas = _render(oriented, fit_width, fit_height, initial_x, initial_y)
        # Validate later decoded frames sequentially before the browser opens the source.
        for index in range(1, count):
            source.seek(index)
            source.load()
        wire = media.screen_image(io.BytesIO(_png(canvas)), fit=False)
        spec = media.display_spec(3059)
        preview_png = media._preview_png(wire, spec)
        return {
            "source_width": oriented.width,
            "source_height": oriented.height,
            "fit_width": fit_width,
            "fit_height": fit_height,
            "initial_x": _round_positive((428 - fit_width) / 2),
            "initial_y": _round_positive((142 - fit_height) / 2),
            "frame_count": count,
            "replace_all": source.format == "GIF" or count > 1,
            "preview_png": preview_png,
        }
    finally:
        source.close()


def _png(image):
    output = io.BytesIO()
    image.convert("RGB").save(output, format="PNG")
    return output.getvalue()


def _validate_transform(scale, x, y):
    if type(scale) is not int or scale < 20 or scale > MAX_SCALE or scale % 20:
        raise ValueError("scale must be an integer from 20 to 300 in steps of 20")
    if (x is None) != (y is None):
        raise ValueError("x and y must both be provided or both omitted")
    if x is not None:
        if type(x) not in (int, float) or type(y) not in (int, float):
            raise ValueError("x and y must be finite numbers")
        try:
            x, y = float(x), float(y)
        except OverflowError as error:
            raise ValueError("x and y must be finite numbers") from error
        if not math.isfinite(x) or not math.isfinite(y):
            raise ValueError("x and y must be finite numbers")
    return scale, x, y


def _render(frame, width, height, x, y):
    canvas = Image.new("RGBA", (428, 142), (0, 0, 0, 255))
    if x >= 428 or y >= 142 or x + width <= 0 or y + height <= 0:
        return canvas
    # Transform the original once into a bounded output, preserving fractional placement.
    # Pillow's bicubic kernel is independent of the vendor browser's rendering kernel.
    sx, sy = frame.width / width, frame.height / height
    placed = frame.convert("RGBA").transform(
        (428, 142),
        Image.Transform.AFFINE,
        (sx, 0, -x * sx, 0, sy, -y * sy),
        resample=Image.Resampling.BICUBIC,
        fillcolor=(0, 0, 0, 0),
    )
    canvas.alpha_composite(placed)
    return canvas


def transform_import(content: bytes, *, scale=100, x=None, y=None):
    scale, x, y = _validate_transform(scale, x, y)
    source = _open(content)
    try:
        count = _frame_count(source)
        source.seek(0)
        oriented = ImageOps.exif_transpose(source)
        fit_width, fit_height = _fit_size(oriented.width, oriented.height)
        scaled_width = fit_width * scale / 100
        scaled_height = fit_height * scale / 100
        pos_x = (
            (
                _round_positive((428 - scaled_width) / 2)
                if scale == 100
                else (428 - scaled_width) / 2
            )
            if x is None
            else x
        )
        pos_y = (
            (
                _round_positive((142 - scaled_height) / 2)
                if scale == 100
                else (142 - scaled_height) / 2
            )
            if y is None
            else y
        )
        transformed, delays = [], []
        for index in range(count):
            source.seek(index)
            frame = ImageOps.exif_transpose(source).convert("RGBA")
            canvas = _render(frame, scaled_width, scaled_height, pos_x, pos_y).convert("RGB")
            transformed.append(canvas)
            delays.append(_delay(source))
        output = io.BytesIO()
        if len(transformed) == 1:
            transformed[0].save(output, format="PNG")
            kind, delay = "screen", None
        else:
            effective = (2 * sum(delays) + len(delays)) // (2 * len(delays))
            delay = effective or 60
            transformed[0].save(
                output,
                format="TIFF",
                save_all=True,
                append_images=transformed[1:],
                compression="raw",
                duration=delay,
            )
            kind = "animation"
        raw = output.getvalue()
        result = media.prepare_display(raw, kind=kind, delay_ms=delay)
        result.update(
            {
                "content": base64.b64encode(raw).decode("ascii"),
                "kind": kind,
                "selected_index": 0,
                "replace_all": source.format == "GIF" or count > 1,
            }
        )
        return result
    finally:
        source.close()
