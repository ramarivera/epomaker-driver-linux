import base64
import io

import pytest
from PIL import Image

from epomaker_driver.display_edit import edit_display
from epomaker_driver.media import screen_animation


def source():
    out = io.BytesIO()
    Image.new("RGB", (2, 2), "red").save(out, format="PNG")
    return out.getvalue()


def three_frames():
    frames = [Image.new("RGB", (428, 142), color) for color in ("red", "blue", "green")]
    out = io.BytesIO()
    frames[0].save(
        out,
        format="TIFF",
        save_all=True,
        append_images=frames[1:],
        compression="raw",
        duration=[0, 1, 255],
    )
    return out.getvalue()


def test_frame_transitions_and_black_add():
    result = edit_display(source(), kind="screen", delay_ms=None, operation="add", index=0)
    assert result["kind"] == "animation" and result["frame_count"] == 2
    assert result["selected_index"] == 1
    assert len(result["preview_frames"]) == 2
    black = Image.open(io.BytesIO(base64.b64decode(result["preview_frames"][1])))
    assert black.getpixel((214, 71)) == (0, 0, 0)


def test_copy_clear_delete_and_clear_all():
    added = edit_display(source(), kind="screen", delay_ms=None, operation="add", index=0)
    copied = edit_display(
        base64.b64decode(added["content"]),
        kind="animation",
        delay_ms=0,
        operation="copy_previous",
        index=1,
    )
    assert copied["preview_frames"][0] == copied["preview_frames"][1]
    cleared = edit_display(
        base64.b64decode(copied["content"]),
        kind="animation",
        delay_ms=255,
        operation="clear",
        index=0,
    )
    assert cleared["delay_ms"] == 255
    deleted = edit_display(
        base64.b64decode(cleared["content"]),
        kind="animation",
        delay_ms=0,
        operation="delete",
        index=1,
    )
    assert deleted["kind"] == "screen" and deleted["frame_count"] == 1
    all_clear = edit_display(
        base64.b64decode(added["content"]),
        kind="animation",
        delay_ms=0,
        operation="clear_all",
        index=1,
    )
    assert all_clear["frame_count"] == 1 and all_clear["kind"] == "screen"


def test_operations_preserve_wire_order_duplicates_and_delays():
    content = three_frames()
    expected, _ = screen_animation(io.BytesIO(content), fit=False, delay_ms=0)
    result = edit_display(content, kind="animation", delay_ms=0, operation="copy_previous", index=2)
    actual, delay = screen_animation(
        io.BytesIO(base64.b64decode(result["content"])), fit=False, delay_ms=0
    )
    assert delay == 0 and len(actual) == 3
    assert actual[0] == expected[0] and actual[1] == expected[1] and actual[2] == expected[1]
    assert result["preview_frames"][1] == result["preview_frames"][2]
    result = edit_display(content, kind="animation", delay_ms=255, operation="delete", index=1)
    assert result["delay_ms"] == 255 and result["frame_count"] == 2


@pytest.mark.parametrize(
    "operation,index",
    [
        ("copy_previous", 0),
        ("delete", 0),
        ("clear", True),
        ("clear", -1),
        ("clear", 3),
        ("clear", 1.0),
    ],
)
def test_invalid_edits(operation, index):
    with pytest.raises(ValueError):
        edit_display(source(), kind="screen", delay_ms=None, operation=operation, index=index)


@pytest.mark.parametrize("operation", [[], {}, "unknown"])
def test_invalid_operation_is_value_error(operation):
    with pytest.raises(ValueError):
        edit_display(source(), kind="screen", delay_ms=None, operation=operation, index=0)


def test_add_at_maximum_and_large_content_rejected():
    frames = [Image.new("RGB", (428, 142), (index, 0, 0)) for index in range(46)]
    output = io.BytesIO()
    frames[0].save(
        output,
        format="TIFF",
        save_all=True,
        append_images=frames[1:],
        compression="raw",
        duration=1,
    )
    content = output.getvalue()
    with pytest.raises(ValueError, match="at most"):
        edit_display(content, kind="animation", delay_ms=1, operation="add", index=0)
    with pytest.raises(ValueError, match="14 MiB"):
        edit_display(
            b"x" * (14 * 1024 * 1024 + 1), kind="screen", delay_ms=None, operation="clear", index=0
        )


def test_screen_delay_is_rejected():
    with pytest.raises(ValueError, match="still"):
        edit_display(source(), kind="screen", delay_ms=1, operation="clear", index=0)


@pytest.mark.parametrize(
    "operation,index,order,selected",
    [
        ("add", 0, [0, None, 1, 2], 1),
        ("add", 2, [0, 1, 2, None], 3),
        ("copy_previous", 1, [0, 0, 2], 1),
        ("delete", 0, [1, 2], 0),
        ("delete", 2, [0, 1], 1),
        ("clear", 1, [0, None, 2], 1),
        ("clear_all", 2, [None], 0),
    ],
)
def test_every_edit_preserves_exact_unmodified_pixels_and_selection(
    operation, index, order, selected
):
    from epomaker_driver.media import screen_image

    images = [Image.new("RGB", (428, 142), (31, 95, 172 + i)) for i in range(3)]
    for i, image in enumerate(images):
        image.putpixel((0, 0), (255, i * 80, 0))
        image.putpixel((427, 141), (i * 80, 0, 255))
        image.putpixel((15 + i, 95), (75, 183, 21))
    output = io.BytesIO()
    images[0].save(
        output, format="TIFF", save_all=True, append_images=images[1:], compression="raw"
    )
    original, _ = screen_animation(io.BytesIO(output.getvalue()), delay_ms=255)
    edited = edit_display(
        output.getvalue(), kind="animation", delay_ms=255, operation=operation, index=index
    )
    content = io.BytesIO(base64.b64decode(edited["content"]))
    if len(order) == 1:
        assert edited["kind"] == "screen" and edited["delay_ms"] is None
        actual = [screen_image(content)]
    else:
        assert edited["kind"] == "animation"
        actual, delay = screen_animation(content, delay_ms=edited["delay_ms"])
        assert delay == 255
    assert actual == [bytes(121552) if item is None else original[item] for item in order]
    assert edited["frame_count"] == len(order)
    assert edited["selected_index"] == selected
