"""Convert local still images into keyboard display pixels before touching hardware."""

from PIL import Image, ImageOps

from .codec import rgb565_column_major
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
    return rgb565_column_major(rows)


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
