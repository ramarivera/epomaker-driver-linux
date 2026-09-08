"""Convert local still images into Glyph display pixels before touching hardware."""

from PIL import Image, ImageOps

from .codec import rgb565_column_major

# Vendor display allocation: 6 MiB, one 4 KiB header and five still-image slots.
# Each 428x142 RGB565 frame occupies 30 flash blocks. See docs/display.md.
MAX_ANIMATION_FRAMES = ((6 * 1024 * 1024 - 4096) // ((428 * 142 * 2 // 4096 + 1) * 4096)) - 5


def _pixels(source, fit):
    if source.width * source.height > 16_000_000:
        raise ValueError("source image exceeds 16 million pixels")
    image = ImageOps.exif_transpose(source).convert("RGBA")
    if fit:
        image = ImageOps.pad(image, (428, 142), color=(0, 0, 0, 255))
    if image.size != (428, 142):
        raise ValueError("image must be 428x142 pixels; use --fit to scale and letterbox")
    background = Image.new("RGBA", image.size, (0, 0, 0, 255))
    background.alpha_composite(image)
    rgb = background.convert("RGB").tobytes()
    rows = [
        [int.from_bytes(rgb[(y * 428 + x) * 3 : (y * 428 + x) * 3 + 3], "big") for x in range(428)]
        for y in range(142)
    ]
    return rgb565_column_major(rows)


def screen_image(path, *, fit=False):
    with Image.open(path) as source:
        if getattr(source, "n_frames", 1) != 1:
            raise ValueError("animated images require the animation command")
        return _pixels(source, fit)


def screen_animation(path, *, fit=False, delay_ms=None):
    from .codec import bounded

    if delay_ms is not None:
        bounded(delay_ms, 255, "frame delay")
    with Image.open(path) as source:
        count = getattr(source, "n_frames", 1)
        if not 2 <= count <= MAX_ANIMATION_FRAMES:
            raise ValueError(f"animation must contain 2..{MAX_ANIMATION_FRAMES} frames")
        frames, delays = [], []
        for index in range(count):
            # Pillow composes GIF disposal/transparency while seeking sequentially.
            source.seek(index)
            frames.append(_pixels(source, fit))
            delays.append(min(255, max(0, int(source.info.get("duration", 0)))))
        # Match positive Math.round rather than Python's half-to-even rounding.
        actual_delay = (2 * sum(delays) + count) // (2 * count) if delay_ms is None else delay_ms
        return frames, actual_delay
