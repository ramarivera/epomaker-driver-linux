"""Convert local still images into Glyph display pixels before touching hardware."""

from PIL import Image, ImageOps

from .codec import rgb565_column_major


def screen_image(path, *, fit=False):
    with Image.open(path) as source:
        if getattr(source, "n_frames", 1) != 1:
            raise ValueError(
                "animated images need a frame-timing implementation; use a still image"
            )
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
            [
                int.from_bytes(rgb[(y * 428 + x) * 3 : (y * 428 + x) * 3 + 3], "big")
                for x in range(428)
            ]
            for y in range(142)
        ]
        return rgb565_column_major(rows)
