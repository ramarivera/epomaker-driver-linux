import base64
import io

import pytest
from PIL import Image

from epomaker_driver import media
from epomaker_driver.display_import import inspect_import, transform_import


def image_bytes(size=(2, 1), fmt="PNG", frames=None, durations=None):
    frames = frames or [Image.new("RGBA", size, (255, 0, 0, 255))]
    out = io.BytesIO()
    frames[0].save(
        out, format=fmt, save_all=len(frames) > 1, append_images=frames[1:], duration=durations or 1
    )
    return out.getvalue()


def test_inspect_reports_fit_center_and_preview():
    result = inspect_import(image_bytes((2, 1)))
    assert result["source_width"] == 2 and result["source_height"] == 1
    assert result["fit_width"] == 284 and result["fit_height"] == 142
    assert result["initial_x"] == 72 and result["initial_y"] == 0
    assert result["frame_count"] == 1 and result["replace_all"] is False
    assert Image.open(io.BytesIO(base64.b64decode(result["preview_png"]))).size == (428, 142)


def test_transform_multiframe_preserves_count_and_delay_zero_falls_back():
    content = image_bytes(
        (2, 1),
        "GIF",
        [Image.new("RGB", (2, 1), "red"), Image.new("RGB", (2, 1), "blue")],
        [0, 0],
    )
    result = transform_import(content, scale=100)
    assert result["kind"] == "animation" and result["frame_count"] == 2
    assert result["delay_ms"] == 60 and result["selected_index"] == 0
    assert result["replace_all"] is True


def test_transform_outside_view_is_black_and_invalid_geometry_rejected():
    result = transform_import(image_bytes((1, 1)), scale=300, x=10_000.0, y=-10_000.0)
    preview = Image.open(io.BytesIO(base64.b64decode(result["preview_png"])))
    assert preview.getbbox() is None
    for kwargs in ({"scale": 30}, {"scale": True}, {"x": float("nan"), "y": 0}, {"x": 1}):
        with pytest.raises(ValueError):
            transform_import(image_bytes(), **kwargs)


def test_transform_rejects_unsupported_format_and_source_pixels():
    with pytest.raises(ValueError, match="format"):
        inspect_import(image_bytes(fmt="BMP"))
    with pytest.raises(ValueError, match="16 million"):
        inspect_import(image_bytes((4001, 4001)))


@pytest.mark.parametrize("fmt,replace", [("PNG", False), ("GIF", True)])
def test_import_replace_all_for_still_png_and_gif(fmt, replace):
    result = inspect_import(image_bytes(fmt=fmt))
    assert result["replace_all"] is replace


def test_gif_frame_order_and_delay_rounding():
    content = image_bytes(
        fmt="GIF",
        frames=[Image.new("RGB", (2, 1), "red"), Image.new("RGB", (2, 1), "blue")],
        durations=[250, 260],
    )
    result = transform_import(content)
    assert result["frame_count"] == 2 and result["delay_ms"] == 253
    with Image.open(io.BytesIO(base64.b64decode(result["content"]))) as image:
        image.seek(0)
        assert image.convert("RGB").getpixel((214, 71)) == (255, 0, 0)
        image.seek(1)
        assert image.convert("RGB").getpixel((214, 71)) == (0, 0, 255)


@pytest.mark.parametrize(
    "value", [None, "1", [], {}, True, False, float("nan"), float("inf"), 10**1000]
)
def test_transform_rejects_invalid_coordinates(value):
    with pytest.raises(ValueError):
        transform_import(image_bytes(), x=value, y=0)


@pytest.mark.parametrize("scale", [19, 30, 301, True])
def test_transform_rejects_invalid_scale(scale):
    with pytest.raises(ValueError):
        transform_import(image_bytes(), scale=scale)


@pytest.mark.parametrize("scale", [20, 300])
def test_transform_accepts_scale_bounds(scale):
    assert transform_import(image_bytes(), scale=scale)["width"] == 428


def test_transform_exif_orientation_and_exact_asymmetric_placement():
    image = Image.new("RGB", (428, 142), "black")
    image.putpixel((0, 0), (255, 0, 0))
    output = io.BytesIO()
    image.save(output, format="PNG")
    result = transform_import(output.getvalue(), scale=100, x=3, y=4)
    assert result["frame_count"] == 1
    preview = Image.open(io.BytesIO(base64.b64decode(result["preview_png"])))
    assert preview.getpixel((3, 4)) == (255, 0, 0) and preview.getpixel((0, 0)) == (0, 0, 0)

    jpeg = Image.new("RGB", (2, 3), "red")
    exif = Image.Exif()
    exif[0x0112] = 6
    encoded = io.BytesIO()
    jpeg.save(encoded, format="JPEG", exif=exif)
    oriented = inspect_import(encoded.getvalue())
    assert (oriented["source_width"], oriented["source_height"]) == (3, 2)
    assert oriented["fit_width"] == 213


def test_fractional_position_changes_checkerboard_result_and_alpha_is_black_composited():
    image = Image.new("RGBA", (2, 2), (0, 0, 0, 0))
    image.putpixel((0, 0), (255, 0, 0, 128))
    output = io.BytesIO()
    image.save(output, format="PNG")
    zero = transform_import(output.getvalue(), scale=100, x=0, y=0)
    half = transform_import(output.getvalue(), scale=100, x=0.5, y=0)
    assert zero["preview_png"] != half["preview_png"]
    uniform = image_bytes(frames=[Image.new("RGBA", (2, 2), (255, 0, 0, 128))])
    composite = transform_import(uniform, x=0, y=0)
    preview = Image.open(io.BytesIO(base64.b64decode(composite["preview_png"])))
    assert preview.getpixel((50, 50)) == (132, 0, 0)
    assert preview.getpixel((200, 50)) == (0, 0, 0)


def test_asymmetric_zero_offset_matches_media_wire_conversion():
    image = Image.new("RGB", (428, 142), "black")
    image.putpixel((0, 0), (255, 0, 0))
    image.putpixel((100, 30), (145, 78, 230))
    image.putpixel((427, 141), (0, 0, 255))
    output = io.BytesIO()
    image.save(output, format="PNG")
    result = transform_import(output.getvalue(), scale=100, x=0, y=0)
    assert media.screen_image(
        io.BytesIO(base64.b64decode(result["content"])), fit=False
    ) == media.screen_image(io.BytesIO(output.getvalue()), fit=False)


def test_frame_limit_rejects_47_gif_frames():
    frames = [Image.new("RGB", (2, 1), (index, 0, 0)) for index in range(47)]
    output = io.BytesIO()
    frames[0].save(output, format="GIF", save_all=True, append_images=frames[1:], duration=1)
    with pytest.raises(ValueError, match="1..46"):
        inspect_import(output.getvalue())


@pytest.mark.parametrize(
    "content",
    [b"", None, "text", b"not an image", b"x" * (14 * 1024 * 1024 + 1)],
    ids=["empty", "none", "text", "invalid", "oversized"],
)
def test_import_content_validation(content):
    with pytest.raises(ValueError):
        inspect_import(content)


def test_frame_limit_accepts_46_and_fully_offscreen_duplicate_frames_are_retained():
    frames = [Image.new("RGB", (2, 1), (i, 0, 0)) for i in range(46)]
    assert inspect_import(image_bytes(fmt="GIF", frames=frames))["frame_count"] == 46
    content = image_bytes(
        fmt="GIF",
        frames=[Image.new("RGB", (2, 1), "red"), Image.new("RGB", (2, 1), "blue")],
        durations=[0, 0],
    )
    for x in (1e308, -1e308):
        result = transform_import(content, scale=300, x=x, y=0)
        wire, delay = media.screen_animation(
            io.BytesIO(base64.b64decode(result["content"])), delay_ms=result["delay_ms"]
        )
        assert wire == [bytes(121552), bytes(121552)]
        assert result["frame_count"] == 2 and delay == 60


def test_inspect_ceil_fit_preview_matches_initial_transform():
    content = image_bytes((1000, 101))
    metadata = inspect_import(content)
    assert (metadata["fit_width"], metadata["fit_height"], metadata["initial_y"]) == (428, 44, 49)
    result = transform_import(content, x=metadata["initial_x"], y=metadata["initial_y"])
    assert metadata["preview_png"] == result["preview_png"]


def test_extreme_png_dimensions_are_rejected_before_pixel_decode():
    import struct
    import zlib

    raw = bytearray(image_bytes())
    raw[16:24] = struct.pack(">II", 1_000_000, 1_000_000)
    raw[29:33] = struct.pack(">I", zlib.crc32(raw[12:29]))
    with pytest.raises(ValueError, match="invalid image"):
        inspect_import(bytes(raw))
