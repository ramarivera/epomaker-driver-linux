"""CLI for discovery, configuration and portable backups. See README.md."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__, codec, media, profiles
from .device import Keyboard
from .discovery import discover
from .errors import DeviceUnavailable, DriverError
from .models import catalog
from .transport import Transport


def integer(value):
    return int(value, 0)


def parser():
    root = argparse.ArgumentParser(prog="epomaker")
    root.add_argument("--version", action="version", version=__version__)
    root.add_argument("--device", help="explicit /dev/hidrawN command collection")
    commands = root.add_subparsers(dest="command", required=True)
    commands.add_parser("discover", help="list HID metadata without opening devices")
    commands.add_parser("models", help="list catalog and implementation status")
    commands.add_parser("identify", help="query internal model ID and firmware")
    commands.add_parser("status")
    commands.add_parser("clock", help="synchronize the display clock")
    commands.add_parser("get-light").add_argument("--side", action="store_true")
    light = commands.add_parser("light")
    light.add_argument("mode", choices=codec.LIGHT_MODES)
    light.add_argument("--rgb", type=lambda v: int(v.removeprefix("#"), 16), default=0xFFFFFF)
    light.add_argument("--brightness", type=int, default=4)
    light.add_argument("--speed", type=int, default=0)
    light.add_argument("--option", type=int, default=0)
    light.add_argument("--rainbow", action="store_true")
    light.add_argument("--side", action="store_true")
    commands.add_parser("get-sleep")
    sleep = commands.add_parser("sleep")
    for name in ("bt", "dongle", "deep_bt", "deep_dongle"):
        sleep.add_argument(name, type=int)
    matrix = commands.add_parser("matrix")
    matrix.add_argument("--profile", type=int, default=0)
    matrix.add_argument("--fn", action="store_true")
    matrix.add_argument("--os-mode", type=int, default=0)
    key = commands.add_parser("key")
    key.add_argument("slot", type=int)
    key.add_argument("action", help="four bytes as hex, for example 00000500")
    key.add_argument("--profile", type=int, default=0)
    key.add_argument("--fn", action="store_true")
    key.add_argument("--os-mode", type=int, default=0)
    commands.add_parser("profile").add_argument("index", type=int)
    commands.add_parser("debounce").add_argument("milliseconds", type=int)
    commands.add_parser("get-macro").add_argument("slot", type=int)
    macro = commands.add_parser("macro", help="write a keyboard-event JSON macro with readback")
    macro.add_argument("slot", type=int)
    macro.add_argument("path", type=Path)
    screen = commands.add_parser("screen", help="upload a still image to the Glyph display")
    screen.add_argument("path", type=Path)
    screen.add_argument("--fit", action="store_true")
    backup = commands.add_parser("backup")
    backup.add_argument("path", type=Path)
    backup.add_argument("--overwrite", action="store_true")
    info = commands.add_parser("inspect-profile", help="decode a local JSON/raw-DEFLATE profile")
    info.add_argument("path", type=Path)
    return root


def select_device(path):
    if path is None:
        raise ValueError("choose --device from epomaker discover; no implicit device writes")
    device = next((d for d in discover() if d.path == path), None)
    if device is None or device.command_transport is None:
        raise DeviceUnavailable("selected path is not a supported command collection")
    return device


def execute(args):
    if args.command == "discover":
        return [d.public_dict() for d in discover()]
    if args.command == "models":
        return catalog()
    if args.command == "inspect-profile":
        with args.path.open("rb") as stream:
            return profiles.decode(stream.read(profiles.MAX_PROFILE_BYTES + 1))
    # Decode and validate entire local inputs before opening the device.
    prepared = None
    if args.command == "screen":
        prepared = media.screen_image(args.path, fit=args.fit)
    elif args.command == "macro":
        with args.path.open("rb") as stream:
            value = profiles.decode(stream.read(profiles.MAX_PROFILE_BYTES + 1))
        if not isinstance(value, dict) or set(value) != {"repeat", "events"}:
            raise ValueError("macro must contain exactly repeat and events")
        prepared = codec.macro_data(value["repeat"], value["events"])
    with Transport.open(select_device(args.device)) as transport:
        keyboard = Keyboard(transport)
        if args.command == "identify":
            return keyboard.identify()
        if args.command == "status":
            return keyboard.status()
        if args.command == "get-light":
            return keyboard.get_light(side=args.side)
        if args.command == "light":
            return keyboard.set_light(
                args.mode,
                rgb=args.rgb,
                brightness=args.brightness,
                speed=args.speed,
                option=args.option,
                rainbow=args.rainbow,
                side=args.side,
            )
        if args.command == "get-sleep":
            return keyboard.get_sleep()
        if args.command == "sleep":
            return keyboard.set_sleep(args.bt, args.dongle, args.deep_bt, args.deep_dongle)
        if args.command == "matrix":
            value = keyboard.read_matrix(args.profile, fn=args.fn, os_mode=args.os_mode)
            return {"slots": [list(value[i : i + 4]) for i in range(0, len(value), 4)]}
        if args.command == "key":
            return keyboard.set_key(
                args.slot,
                bytes.fromhex(args.action),
                profile=args.profile,
                fn=args.fn,
                os_mode=args.os_mode,
            )
        if args.command == "profile":
            keyboard.set_profile(args.index)
        elif args.command == "get-macro":
            return {"slot": args.slot, "data": keyboard.read_macro(args.slot).hex()}
        elif args.command == "macro":
            keyboard.write_macro(args.slot, prepared)
        elif args.command == "screen":
            keyboard.upload_screen(prepared, (0, 0, 428, 142))
        elif args.command == "debounce":
            keyboard.set_debounce(args.milliseconds)
        elif args.command == "clock":
            keyboard.sync_clock()
        elif args.command == "backup":
            identity = keyboard.identify()
            matrices = [keyboard.read_matrix(p).hex() for p in range(3)]
            fn = {
                name: keyboard.read_matrix(0, fn=True, os_mode=os_mode).hex()
                for name, os_mode in [("win", 0), ("mac", 1)]
            }
            snapshot = {
                "schema_version": 1,
                "identity": identity,
                "matrices": matrices,
                "fn": fn,
                "light": keyboard.get_light(),
                "side_light": keyboard.get_light(side=True),
                "sleep": keyboard.get_sleep(),
                "limitations": ["macro bodies and screen pixels are not included yet"],
            }
            profiles.save(args.path, snapshot, overwrite=args.overwrite)
            return {"saved": str(args.path), "limitations": snapshot["limitations"]}
        return {"ok": True}


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        result = execute(args)
    except (DriverError, OSError, ValueError) as error:
        print(json.dumps({"error": type(error).__name__, "message": str(error)}), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
