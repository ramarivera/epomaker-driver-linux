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


def test_rt85_conversion_geometry_and_animation(tmp_path):
    from epomaker_driver.media import screen_animation

    path = tmp_path / "rt85.png"
    image = Image.new("RGBA", (320, 172), (0, 0, 0, 0))
    image.putpixel((0, 1), (255, 0, 0, 255))
    image.putpixel((1, 0), (0, 255, 0, 255))
    image.save(path)
    pixels = screen_image(path, model_id=2895)
    assert len(pixels) == 110080
    assert pixels[:4] == bytes.fromhex("0000f800")
    assert pixels[344:346] == bytes.fromhex("07e0")
    with pytest.raises(ValueError, match="428x142"):
        screen_image(path)
    gif = tmp_path / "rt85.gif"
    Image.new("RGB", (2, 2), "red").save(
        gif, save_all=True, append_images=[Image.new("RGB", (2, 2), "blue")], duration=80
    )
    frames, delay = screen_animation(gif, fit=True, model_id=2895)
    assert len(frames) == 2 and delay == 80
    assert all(len(frame) == 110080 for frame in frames)
    assert frames[0][:344] == bytes(344)  # letterbox side columns
    assert frames[0][160 * 344 : 160 * 344 + 2] == bytes.fromhex("f800")


@pytest.mark.parametrize("model_id,width", [(3858, 33), (3673, 7), (3674, 7)])
def test_rgb24_media(model_id, width, tmp_path):
    from epomaker_driver.media import screen_animation

    image = Image.new("RGBA", (width, 7), (0, 0, 0, 0))
    image.putpixel((0, 1), (255, 0, 0, 255))
    image.putpixel((1, 0), (0, 255, 0, 255))
    path = tmp_path / "rgb24.png"
    image.save(path)
    pixels = screen_image(path, model_id=model_id)
    assert len(pixels) == width * 7 * 3
    assert pixels[:6] == bytes.fromhex("000000ff0000")
    assert pixels[21:24] == bytes.fromhex("00ff00")
    gif = tmp_path / "rgb24.gif"
    Image.new("RGB", (2, 2), "red").save(
        gif, save_all=True, append_images=[Image.new("RGB", (2, 2), "blue")], duration=80
    )
    frames, delay = screen_animation(gif, fit=True, model_id=model_id)
    assert len(frames) == 2 and delay == 80 and len(frames[0]) == width * 7 * 3


def test_rgb24_small_allocation_limit(tmp_path):
    from epomaker_driver.media import screen_animation

    frames = [Image.new("RGB", (7, 7), (i, 0, 0)) for i in range(17)]
    path = tmp_path / "overflow.gif"
    frames[0].save(path, save_all=True, append_images=frames[1:], optimize=False, duration=80)
    with pytest.raises(ValueError, match="2..16"):
        screen_animation(path, model_id=3674)
