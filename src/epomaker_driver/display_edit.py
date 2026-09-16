"""Offline display-frame editing built on media.prepare_display conversion.

Frame semantics and upload limits are documented in ``docs/display.md``.
"""

import base64
import io

from PIL import Image

from . import media

MAX_CONTENT_BYTES = 14 * 1024 * 1024
_OPERATIONS = {"add", "copy_previous", "delete", "clear", "clear_all"}


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


def edit_display(content: bytes, *, kind, delay_ms=None, operation, index):
    """Apply one reversible frame operation without touching a device."""
    if not isinstance(operation, str) or operation not in _OPERATIONS:
        raise ValueError("unknown display edit operation")
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
