"""Offline display-frame editing built on media.prepare_display conversion.

Frame semantics and upload limits are documented in ``docs/display.md``.
"""

import base64
import io

from PIL import Image

from . import media

MAX_CONTENT_BYTES = 14 * 1024 * 1024
_OPERATIONS = {"add", "copy_previous", "delete", "clear", "clear_all", "replace"}
MAX_REPLACEMENT_BYTES = 1 * 1024 * 1024


def _index(value, count):
    if type(value) is not int:
        raise ValueError("index must be an integer")
    if not 0 <= value < count:
        raise ValueError("index is outside the frame range")
    return value


def _images(prepared):
    return [
        Image.open(io.BytesIO(base64.b64decode(raw))).convert("RGB")
        for raw in prepared["preview_frames"]
    ]


def _replacement_image(replacement):
    if not isinstance(replacement, bytes) or not replacement:
        raise ValueError("replacement must be nonempty PNG bytes")
    if len(replacement) > MAX_REPLACEMENT_BYTES:
        raise ValueError("replacement exceeds the 1 MiB limit")
    try:
        with Image.open(io.BytesIO(replacement)) as source:
            if source.format != "PNG":
                raise ValueError("replacement must be a PNG image")
            if getattr(source, "n_frames", 1) != 1:
                raise ValueError("replacement must contain exactly one frame")
            if source.size != (428, 142):
                raise ValueError("replacement must be exactly 428x142 pixels")
            source.verify()
        frame = media.screen_image(io.BytesIO(replacement), fit=False, model_id=3059)
        preview = media._preview_png(frame, media.display_spec(3059))
        return Image.open(io.BytesIO(base64.b64decode(preview))).convert("RGB")
    except ValueError:
        raise
    except (OSError, SyntaxError) as error:
        raise ValueError("replacement must be a valid PNG image") from error


def edit_display(content: bytes, *, kind, delay_ms=None, operation, index, replacement=None):
    """Apply one reversible frame operation without touching a device."""
    if not isinstance(operation, str) or operation not in _OPERATIONS:
        raise ValueError("unknown display edit operation")
    if operation == "replace" and replacement is None:
        raise ValueError("replacement is required for replace")
    if operation != "replace" and replacement is not None:
        raise ValueError("replacement is only valid for replace")
    if type(index) is not int:
        raise ValueError("index must be an integer")
    if not isinstance(content, bytes) or len(content) > MAX_CONTENT_BYTES:
        raise ValueError("display content exceeds the 14 MiB limit")
    if kind == "screen" and delay_ms is not None:
        raise ValueError("still images do not accept a frame delay")
    prepared = media.prepare_display(content, kind=kind, delay_ms=delay_ms)
    frames = _images(prepared)
    selected = _index(index, len(frames))
    if operation == "add":
        if len(frames) >= media.MAX_ANIMATION_FRAMES:
            raise ValueError(f"animation must contain at most {media.MAX_ANIMATION_FRAMES} frames")
        frames.insert(selected + 1, Image.new("RGB", frames[0].size, "black"))
        selected += 1
    elif operation == "copy_previous":
        if selected == 0:
            raise ValueError("copy_previous requires a frame after the first")
        frames[selected] = frames[selected - 1].copy()
    elif operation == "delete":
        if len(frames) == 1:
            raise ValueError("cannot delete the last frame")
        frames.pop(selected)
        selected = min(selected, len(frames) - 1)
    elif operation == "clear":
        frames[selected] = Image.new("RGB", frames[0].size, "black")
    elif operation == "replace":
        frames[selected] = _replacement_image(replacement)
    else:
        frames = [Image.new("RGB", frames[0].size, "black")]
        selected = 0

    output = io.BytesIO()
    if len(frames) == 1:
        frames[0].save(output, format="PNG")
        output_kind, output_delay = "screen", None
    else:
        frame_delay = prepared["delay_ms"] if prepared["delay_ms"] is not None else 80
        frames[0].save(
            output,
            format="TIFF",
            save_all=True,
            append_images=frames[1:],
            compression="raw",
            duration=frame_delay,
        )
        output_kind, output_delay = "animation", frame_delay
    result = media.prepare_display(output.getvalue(), kind=output_kind, delay_ms=output_delay)
    result.update(
        {
            "content": base64.b64encode(output.getvalue()).decode("ascii"),
            "kind": output_kind,
            "selected_index": selected,
        }
    )
    return result
