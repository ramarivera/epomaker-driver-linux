"""Convert local still images into keyboard display pixels before touching hardware."""

import base64
import io

from PIL import Image, ImageOps

from .codec import rgb24_column_major, rgb565_column_major
from .models import display_spec

# Compatibility constant for the default Glyph conversion. See docs/display.md.
MAX_ANIMATION_FRAMES = display_spec(3059)["max_frames"]


def _pixels(source, fit, spec):
    width, height = spec["width"], spec["height"]
    if source.width * source.height > 16_000_000:
        raise ValueError("source image exceeds 16 million pixels")
    image = ImageOps.exif_transpose(source).convert("RGBA")
    if fit:
        image = ImageOps.pad(image, (width, height), color=(0, 0, 0, 255))
    if image.size != (width, height):
        raise ValueError(f"image must be {width}x{height} pixels; use --fit to scale and letterbox")
    background = Image.new("RGBA", image.size, (0, 0, 0, 255))
    background.alpha_composite(image)
    rgb = background.convert("RGB").tobytes()
    rows = [
        [
            int.from_bytes(rgb[(y * width + x) * 3 : (y * width + x) * 3 + 3], "big")
            for x in range(width)
        ]
        for y in range(height)
    ]
    return rgb24_column_major(rows) if spec["pixel_bytes"] == 3 else rgb565_column_major(rows)


def screen_image(path, *, fit=False, model_id=3059):
    spec = display_spec(model_id)
    with Image.open(path) as source:
        if getattr(source, "n_frames", 1) != 1:
            raise ValueError("animated images require the animation command")
        return _pixels(source, fit, spec)


def screen_animation(path, *, fit=False, delay_ms=None, model_id=3059):
    from .codec import bounded

    spec = display_spec(model_id)
    maximum = spec["max_frames"]
    if delay_ms is not None:
        bounded(delay_ms, 255, "frame delay")
    with Image.open(path) as source:
        count = getattr(source, "n_frames", 1)
        if not 2 <= count <= maximum:
            raise ValueError(f"animation must contain 2..{maximum} frames")
        frames, delays = [], []
        for index in range(count):
            # Pillow composes GIF disposal/transparency while seeking sequentially.
            source.seek(index)
            frames.append(_pixels(source, fit, spec))
            delays.append(min(255, max(0, int(source.info.get("duration", 0)))))
        # Match positive Math.round rather than Python's half-to-even rounding.
        actual_delay = (2 * sum(delays) + count) // (2 * count) if delay_ms is None else delay_ms
        return frames, actual_delay


def _preview_png(frame, spec):
    """Reconstruct a PNG from the exact column-major wire pixels."""
    width, height = spec["width"], spec["height"]
    image = Image.new("RGB", (width, height))
    pixels = image.load()
    step = spec["pixel_bytes"]
    for x in range(width):
        for y in range(height):
            offset = (x * height + y) * step
            if step == 2:
                value = int.from_bytes(frame[offset : offset + 2], "big")
                r = (value >> 11) & 31
                g = (value >> 5) & 63
                b = value & 31
                pixels[x, y] = ((r * 255 + 15) // 31, (g * 255 + 31) // 63, (b * 255 + 15) // 31)
            else:
                pixels[x, y] = tuple(frame[offset : offset + 3])
    output = io.BytesIO()
    image.save(output, format="PNG")
    return base64.b64encode(output.getvalue()).decode("ascii")


def prepare_display(content, *, kind, delay_ms=None, model_id=3059):
    """Prepare an offline display preview using the same conversion as uploads."""
    if kind not in ("screen", "animation"):
        raise ValueError("display kind must be screen or animation")
    if not isinstance(content, (bytes, bytearray)) or not content:
        raise ValueError("display content must be nonempty bytes")
    spec = display_spec(model_id)
    source = io.BytesIO(content)
    if kind == "screen":
        frames = [screen_image(source, fit=True, model_id=model_id)]
        actual_delay = None
    else:
        frames, actual_delay = screen_animation(
            source, fit=True, delay_ms=delay_ms, model_id=model_id
        )
    return {
        "width": spec["width"],
        "height": spec["height"],
        "frame_count": len(frames),
        "delay_ms": actual_delay,
        "pixel_bytes": sum(len(frame) for frame in frames),
        "preview_png": _preview_png(frames[0], spec),
    }
