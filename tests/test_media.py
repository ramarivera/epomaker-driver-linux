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
