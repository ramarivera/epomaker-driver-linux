"""CLI for discovery, configuration and portable backups. See README.md."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from . import (
    __version__,
    actions,
    codec,
    he_recovery,
    he_snapshot,
    legacy_snapshot,
    macros,
    media,
    mouse_cli,
    profiles,
    snapshot,
    system_info,
)
from .device import Keyboard
from .discovery import discover
from .errors import DeviceUnavailable, DriverError, UnsupportedDevice
from .he import COMMANDS as HE_COMMANDS
from .he import HE_PRODUCTS, HEKeyboard
from .he_calibration import validate_duration
from .he_modes import validate_definition
from .he_switches import resolve_switch
from .legacy import COMMANDS as LEGACY_COMMANDS
from .legacy import LegacyKeyboard
from .models import catalog
from .mouse import COMMANDS as MOUSE_COMMANDS
from .mouse import PRODUCTS as MOUSE_PRODUCTS
from .mouse import Mouse
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
    commands.add_parser("actions", help="list supported semantic binding names")
    serve = commands.add_parser("serve", help="start the local control interface")
    serve.add_argument("--port", type=int, default=8932)
    serve.add_argument(
        "--backup-dir",
        type=Path,
        default=Path.home() / ".local/state/epomaker-driver-linux/backups",
    )
    commands.add_parser("identify", help="query internal model ID and firmware")
    commands.add_parser("status")
    mouse_cli.parsers(commands)
    commands.add_parser(
        "get-magnetic", help="read supported magnetic-keyboard parameters for the current profile"
    )
    commands.add_parser("read-calibration", help="read raw calibration telemetry over USB")
    calibration = commands.add_parser("calibrate", help="run a timed USB key calibration session")
    calibration.add_argument("--seconds", type=validate_duration, default=30)
    magnetic = commands.add_parser(
        "magnetic-key", help="update magnetic actuation/rapid-trigger settings"
    )
    magnetic.add_argument("slot", type=int)
    for name in ("travel", "lift", "deadzone", "top-deadzone", "rapid-press", "rapid-lift"):
        magnetic.add_argument("--" + name, type=float)
    magnetic.add_argument("--fire", action=argparse.BooleanOptionalAction, default=None)
    magnetic_mode = commands.add_parser(
        "magnetic-mode", help="install magnetic mode, actions and parameters from JSON"
    )
    magnetic_mode.add_argument("slot", type=int)
    magnetic_mode.add_argument("path", type=Path)
    switch = commands.add_parser("switch-type", help="select a switch type by name or decimal code")
    switch.add_argument("switch", type=resolve_switch)
    switch.add_argument("slots", type=int, nargs="+")
    snap = commands.add_parser("snap", help="pair two physical key slots")
    snap.add_argument("first", type=int)
    snap.add_argument("second", type=int)
    commands.add_parser("snap-clear", help="remove both sides of a snap pair").add_argument(
        "slot", type=int
    )
    commands.add_parser(
        "factory-reset", help="save recovery snapshot, then reset keyboard configuration"
    ).add_argument("--backup", type=Path, required=True)
    commands.add_parser("clock", help="synchronize the display clock")
    for name in ("host-info", "system-info"):
        info = commands.add_parser(
            name,
            help="collect Linux statistics"
            if name == "host-info"
            else "send statistics to the display",
        )
        info.add_argument("--disk", default="/")
        info.add_argument("--interface")
        if name == "system-info":
            info.add_argument("--count", type=int, default=1)
            info.add_argument("--interval", type=float, default=3.0)
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
    commands.add_parser("get-options")
    options = commands.add_parser("options")
    options.add_argument("--system", choices=("win", "mac"))
    options.add_argument("--wasd-swap", action=argparse.BooleanOptionalAction, default=None)
    commands.add_parser("get-auto-os")
    commands.add_parser("auto-os").add_argument("enabled", choices=("on", "off"))
    sleep = commands.add_parser("sleep")
    for name in ("bt", "dongle", "deep_bt", "deep_dongle"):
        sleep.add_argument(name, type=int, **({"nargs": "?"} if name == "deep_dongle" else {}))
    matrix = commands.add_parser("matrix")
    matrix.add_argument("--profile", type=int, default=0)
    matrix.add_argument("--fn", action="store_true")
    matrix.add_argument("--os-mode", type=int, default=0)
    matrix.add_argument("--submode", type=int, choices=range(4), default=0)
    matrix.add_argument("--decoded", action="store_true")
    for name in ("bind-key", "bind-media", "bind-mouse", "bind-macro", "disable-key"):
        binding = commands.add_parser(name)
        binding.add_argument("slot", type=int)
        binding.add_argument("--profile", type=int, default=0)
        binding.add_argument("--fn", action="store_true")
        binding.add_argument("--os-mode", type=int, default=0)
        binding.add_argument("--submode", type=int, choices=range(4), default=0)
        if name == "bind-key":
            binding.add_argument("key", choices=actions.KEYS)
            binding.add_argument("--second", choices=actions.KEYS, default=0)
            binding.add_argument(
                "--modifier", choices=actions.MODIFIERS, action="append", default=[]
            )
        elif name == "bind-media":
            binding.add_argument("name", choices=actions.MEDIA)
        elif name == "bind-mouse":
            binding.add_argument("name", choices=actions.MOUSE)
        elif name == "bind-macro":
            binding.add_argument("macro_slot", type=int)
            binding.add_argument("--mode", choices=actions.MACRO_MODES, default="count")
    key = commands.add_parser("key")
    key.add_argument("slot", type=int)
    key.add_argument("action", help="four bytes as hex, for example 00000500")
    key.add_argument("--profile", type=int, default=0)
    key.add_argument("--fn", action="store_true")
    key.add_argument("--os-mode", type=int, default=0)
    key.add_argument("--submode", type=int, choices=range(4), default=0)
    commands.add_parser("profile").add_argument("index", type=int)
    commands.add_parser("debounce").add_argument("milliseconds", type=int)
    get_macro = commands.add_parser("get-macro")
    get_macro.add_argument("slot", type=int)
    get_macro.add_argument("--decoded", action="store_true")
    macro = commands.add_parser("macro", help="write a keyboard/mouse JSON macro with readback")
    macro.add_argument("slot", type=int)
    macro.add_argument("path", type=Path)
    screen = commands.add_parser("screen", help="upload a still image to the Glyph display")
    screen.add_argument("path", type=Path)
    screen.add_argument("--fit", action="store_true")
    screen.add_argument("--bank", type=int, choices=range(1, 6), default=1)
    commands.add_parser("display-language-toggle", help="toggle the display language")
    animation = commands.add_parser("animation", help="upload composed animation frames")
    animation.add_argument("path", type=Path)
    animation.add_argument("--fit", action="store_true")
    animation.add_argument("--delay-ms", type=int)
    commands.add_parser("get-picture").add_argument("index", type=int)
    picture = commands.add_parser("picture", help="write model-sized RGB slot colors from JSON")
    picture.add_argument("index", type=int)
    picture.add_argument("path", type=Path)
    picture.add_argument("--activate", action="store_true")
    picture_key = commands.add_parser("picture-key", help="change one RGB slot, preserving others")
    picture_key.add_argument("index", type=int)
    picture_key.add_argument("slot", type=int)
    picture_key.add_argument("rgb", type=lambda v: int(v.removeprefix("#"), 16))
    backup = commands.add_parser("backup")
    backup.add_argument("path", type=Path)
    backup.add_argument("--overwrite", action="store_true")
    restore = commands.add_parser(
        "restore", help="restore a supported snapshot with a saved recovery copy"
    )
    restore.add_argument("path", type=Path)
    restore.add_argument(
        "--backup", type=Path, required=True, help="new file for current configuration"
    )
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
    if args.command == "serve":
        from .server import Controller, ControlServer

        codec.bounded(args.port, 65535, "port")
        with ControlServer(Controller(args.backup_dir), port=args.port) as server:
            print(f"http://127.0.0.1:{server.server_port}/#token={server.token}", flush=True)
            server.serve_forever()
        return {"stopped": True}
    if args.command == "discover":
        return [d.public_dict() for d in discover()]
    if args.command == "models":
        return catalog()
    if args.command == "actions":
        return {
            "keys": actions.KEYS,
            "modifiers": actions.MODIFIERS,
            "media": actions.MEDIA,
            "mouse": actions.MOUSE,
            "macro_modes": actions.MACRO_MODES,
        }
    if args.command == "host-info":
        return system_info.Collector(disk=args.disk, interface=args.interface).collect()
    if args.command == "inspect-profile":
        with args.path.open("rb") as stream:
            return profiles.decode(stream.read(profiles.MAX_PROFILE_BYTES + 1))
    # Validate local inputs before writes. Display conversion needs read-only model identity.
    prepared = None
    if args.command == "magnetic-key":
        prepared = {
            name: getattr(args, name)
            for name in (
                "travel",
                "lift",
                "deadzone",
                "top_deadzone",
                "rapid_press",
                "rapid_lift",
                "fire",
            )
            if getattr(args, name) is not None
        }
        if not prepared:
            raise ValueError("choose at least one magnetic setting")
    if args.command == "magnetic-mode":
        codec.bounded(args.slot, 127, "slot")
        with args.path.open("rb") as stream:
            prepared = profiles.decode(stream.read(profiles.MAX_PROFILE_BYTES + 1))
        validate_definition(prepared)
    if args.command == "system-info":
        if not 1 <= args.count <= 10000 or not 0.1 <= args.interval <= 3600:
            raise ValueError("count must be 1..10000 and interval 0.1..3600 seconds")
        prepared = system_info.Collector(disk=args.disk, interface=args.interface)
    if args.command == "macro":
        with args.path.open("rb") as stream:
            value = profiles.decode(stream.read(profiles.MAX_PROFILE_BYTES + 1))
        if not isinstance(value, dict) or set(value) != {"repeat", "events"}:
            raise ValueError("macro must contain exactly repeat and events")
        prepared = macros.encode(value["repeat"], value["events"])
    elif args.command == "restore":
        with args.path.open("rb") as stream:
            prepared = profiles.decode(stream.read(profiles.MAX_PROFILE_BYTES + 1))
        if isinstance(prepared, dict) and prepared.get("schema_version") == 7:
            he_snapshot.validate(prepared)
        elif isinstance(prepared, dict) and prepared.get("schema_version") == 6:
            legacy_snapshot.validate(prepared)
        else:
            snapshot.validate(prepared)
    elif args.command == "picture":
        with args.path.open("rb") as stream:
            value = profiles.decode(stream.read(profiles.MAX_PROFILE_BYTES + 1))
        colors = value.get("colors") if isinstance(value, dict) else None
        if (
            not isinstance(colors, list)
            or len(colors) not in (126, 128)
            or any(not isinstance(color, str) or len(color) != 6 for color in colors)
        ):
            raise ValueError("colors must contain exactly 126 or 128 six-digit RGB hex strings")
        prepared = b"".join(
            codec.bounded(int(color, 16), 0xFFFFFF, "rgb").to_bytes(3, "big") for color in colors
        )
    device = select_device(args.device)
    is_he = device.product_id in HE_PRODUCTS
    is_mouse = device.product_id in MOUSE_PRODUCTS
    if is_mouse and args.command not in MOUSE_COMMANDS:
        raise UnsupportedDevice("this command is not implemented for CH585 mice")
    if args.command in MOUSE_COMMANDS - {"identify", "status", "profile"} and not is_mouse:
        raise UnsupportedDevice("mouse commands require a supported CH585 mouse")
    if is_he and args.command not in HE_COMMANDS:
        raise UnsupportedDevice("This magnetic-keyboard command has not been migrated yet")
    if not is_he and (
        args.command
        in (
            "get-magnetic",
            "read-calibration",
            "calibrate",
            "magnetic-key",
            "magnetic-mode",
            "snap",
            "snap-clear",
            "switch-type",
        )
        or getattr(args, "submode", 0)
    ):
        raise UnsupportedDevice(
            "Magnetic controls and keymap submodes require a supported magnetic keyboard"
        )
    matrix_options = {"mode": getattr(args, "submode", 0)} if is_he else {}
    if (
        args.command == "restore"
        and isinstance(prepared, dict)
        and prepared.get("schema_version") == 6
        and device.product_id != 0x4015
    ):
        raise UnsupportedDevice("schema 6 snapshots require a YC3121 device")
    if args.command == "restore" and (prepared.get("schema_version") == 7) != is_he:
        raise UnsupportedDevice("schema 7 snapshots require a supported magnetic keyboard")
    with Transport.open(device) as transport:
        if is_mouse:
            return mouse_cli.run(Mouse(transport, product_id=device.product_id), args)
        if is_he:
            keyboard = HEKeyboard(transport, product_id=device.product_id)
        elif device.product_id == 0x4015:
            if args.command not in LEGACY_COMMANDS:
                raise UnsupportedDevice("This YC3121 command has not been migrated yet")
            keyboard = LegacyKeyboard(transport)
        else:
            keyboard = Keyboard(transport)
        if args.command.startswith("bind-") or args.command == "disable-key":
            if args.command == "bind-key":
                action = actions.keyboard(args.key, second=args.second, modifiers=args.modifier)
            elif args.command == "bind-media":
                action = actions.media(args.name)
            elif args.command == "bind-mouse":
                action = actions.mouse(args.name)
            elif args.command == "bind-macro":
                action = actions.macro(args.macro_slot, args.mode)
            else:
                action = bytes(4)
            keyboard.set_key(
                args.slot,
                action,
                profile=args.profile,
                fn=args.fn,
                os_mode=args.os_mode,
                **matrix_options,
            )
            return actions.decode(action)
        if args.command == "identify":
            return keyboard.identify()
        if args.command == "status":
            return keyboard.status()
        if args.command == "snap":
            return keyboard.set_snap(args.first, args.second)
        if args.command == "snap-clear":
            return keyboard.clear_snap(args.slot)
        if args.command == "magnetic-mode":
            return keyboard.set_magnetic_mode(args.slot, prepared)
        if args.command == "read-calibration":
            return keyboard.read_calibration()
        if args.command == "calibrate":

            def progress(event):
                if event["phase"] == "release":
                    print(
                        "Release all keys for the two-second baseline measurement.",
                        file=sys.stderr,
                        flush=True,
                    )
                elif event["phase"] == "press":
                    print(
                        f"Press every key fully during the next {args.seconds:g} seconds. Ctrl-C stops the session.",
                        file=sys.stderr,
                        flush=True,
                    )

            return keyboard.calibrate(args.seconds, on_progress=progress)
        if args.command == "switch-type":
            return keyboard.set_switch_type(args.slots, args.switch)
        if args.command == "get-magnetic":
            return keyboard.get_magnetic()
        if args.command == "magnetic-key":
            return keyboard.set_magnetic(args.slot, prepared)
        if args.command == "system-info":
            for index in range(args.count):
                if index:
                    time.sleep(args.interval)
                values = prepared.collect()
                keyboard.sync_system_info(values)
            return {"sent": args.count, "last_sample": values}
        if args.command == "get-picture":
            colors = keyboard.read_picture(args.index)
            return {"colors": [colors[i : i + 3].hex() for i in range(0, len(colors), 3)]}
        if args.command == "picture":
            keyboard.write_picture(prepared, args.index)
            if args.activate:
                keyboard.set_light("picture", option=args.index)
            return {"ok": True}
        if args.command == "picture-key":
            keyboard.set_picture_key(args.index, args.slot, args.rgb)
            return {"ok": True}
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
        if args.command == "get-options":
            return keyboard.get_options()
        if args.command == "options":
            return keyboard.set_options(system=args.system, wasd_swap=args.wasd_swap)
        if args.command == "get-auto-os":
            return keyboard.get_auto_os()
        if args.command == "auto-os":
            keyboard.set_auto_os(args.enabled == "on")
            return {"ok": True}
        if args.command == "restore":
            if is_he:
                return he_recovery.restore(keyboard, prepared, args.backup)
            if device.product_id == 0x4015:
                return legacy_snapshot.restore(keyboard, prepared, args.backup)
            return snapshot.restore(keyboard, prepared, args.backup)
        if args.command == "sleep":
            return keyboard.set_sleep(args.bt, args.dongle, args.deep_bt, args.deep_dongle)
        if args.command == "matrix":
            value = keyboard.read_matrix(
                args.profile, fn=args.fn, os_mode=args.os_mode, **matrix_options
            )
            if args.decoded:
                return {
                    "slots": [actions.decode(value[i : i + 4]) for i in range(0, len(value), 4)]
                }
            return {"slots": [list(value[i : i + 4]) for i in range(0, len(value), 4)]}
        if args.command == "key":
            return keyboard.set_key(
                args.slot,
                bytes.fromhex(args.action),
                profile=args.profile,
                fn=args.fn,
                os_mode=args.os_mode,
                **matrix_options,
            )
        if args.command == "profile":
            keyboard.set_profile(args.index)
        elif args.command == "get-macro":
            data = keyboard.read_macro(args.slot)
            return macros.decode(data) if args.decoded else {"slot": args.slot, "data": data.hex()}
        elif args.command == "macro":
            keyboard.write_macro(args.slot, prepared)
        elif args.command == "screen":
            model_id = keyboard.identify()["device_id"]
            spec = media.display_spec(model_id)
            prepared = media.screen_image(args.path, fit=args.fit, model_id=model_id)
            keyboard.upload_screen(
                prepared, (0, 0, spec["width"], spec["height"]), frame=args.bank - 1
            )
        elif args.command == "display-language-toggle":
            keyboard.toggle_display_language()
        elif args.command == "factory-reset":
            return snapshot.factory_reset(keyboard, args.backup)
        elif args.command == "animation":
            model_id = keyboard.identify()["device_id"]
            frames, delay = media.screen_animation(
                args.path, fit=args.fit, delay_ms=args.delay_ms, model_id=model_id
            )
            keyboard.upload_animation(frames, delay)
            return {"ok": True, "frames": len(frames), "frame_delay_ms": delay}
        elif args.command == "debounce":
            keyboard.set_debounce(args.milliseconds)
        elif args.command == "clock":
            keyboard.sync_clock()
        elif args.command == "backup":
            value = (
                he_snapshot.capture(keyboard)
                if is_he
                else legacy_snapshot.capture(keyboard)
                if device.product_id == 0x4015
                else snapshot.capture(keyboard)
            )
            profiles.save(args.path, value, overwrite=args.overwrite)
            return {"saved": str(args.path), "limitations": value["limitations"]}
        return {"ok": True}


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        result = execute(args)
    except KeyboardInterrupt:
        print(json.dumps({"interrupted": True}), file=sys.stderr)
        return 130
    except (DriverError, OSError, ValueError) as error:
        print(json.dumps({"error": type(error).__name__, "message": str(error)}), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
