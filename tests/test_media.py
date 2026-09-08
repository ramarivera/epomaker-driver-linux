import pytest
from PIL import Image

from epomaker_driver.media import screen_image


def test_screen_color_order_and_alpha(tmp_path):
    path = tmp_path / "image.png"
    image = Image.new("RGBA", (428, 142), (0, 0, 0, 0))
    image.putpixel((0, 0), (255, 0, 0, 255))
    image.putpixel((0, 1), (0, 255, 0, 255))
    image.putpixel((1, 0), (0, 0, 255, 255))
    image.save(path)
    data = screen_image(path)
    assert len(data) == 121552
    assert data[:6] == bytes.fromhex("f80007e00000")
    assert data[284:286] == bytes.fromhex("001f")


def test_size_fit_and_animation(tmp_path):
    path = tmp_path / "small.png"
    Image.new("RGB", (10, 10), "red").save(path)
    with pytest.raises(ValueError, match="428x142"):
        screen_image(path)
    data = screen_image(path, fit=True)
    assert data[:284] == bytes(284)
    assert data[214 * 284 : 214 * 284 + 2] == bytes.fromhex("f800")
    gif = tmp_path / "animated.gif"
    Image.new("RGB", (2, 2), "red").save(
        gif, save_all=True, append_images=[Image.new("RGB", (2, 2), "blue")]
    )
    with pytest.raises(ValueError, match="animated"):
        screen_image(gif)


def test_large_source_rejected_before_decode(tmp_path):
    path = tmp_path / "large.png"
    Image.new("1", (4001, 4000)).save(path)
    with pytest.raises(ValueError, match="16 million"):
        screen_image(path)


def test_animation_conversion_and_timing(tmp_path):
    from epomaker_driver.media import MAX_ANIMATION_FRAMES, screen_animation

    assert MAX_ANIMATION_FRAMES == 46
    path = tmp_path / "animation.gif"
    Image.new("RGB", (428, 142), "red").save(
        path,
        save_all=True,
        append_images=[Image.new("RGB", (428, 142), "blue")],
        duration=[10, 500],
        disposal=2,
    )
    frames, delay = screen_animation(path)
    assert delay == 133  # clamp 500 to 255, then round 132.5 upward
    assert frames == [bytes.fromhex("f800") * (428 * 142), bytes.fromhex("001f") * (428 * 142)]
    assert screen_animation(path, delay_ms=50)[1] == 50
    with pytest.raises(ValueError, match="frame delay"):
        screen_animation(path, delay_ms=256)


def test_animation_limits(tmp_path):
    from epomaker_driver.media import screen_animation

    path = tmp_path / "frames.gif"
    images = [Image.new("RGB", (2, 2), (i, i * 2, i * 3)) for i in range(47)]
    images[0].save(path, save_all=True, append_images=images[1:], duration=50, optimize=False)
    with pytest.raises(ValueError, match="2..46"):
        screen_animation(path)
    path = tmp_path / "still.png"
    images[0].save(path)
    with pytest.raises(ValueError, match="2..46"):
        screen_animation(path)
