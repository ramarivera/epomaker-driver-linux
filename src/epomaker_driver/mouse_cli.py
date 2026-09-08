"""CH585 command-line dispatch, separate from keyboard action encodings."""

from . import mouse_codec


def parsers(commands):
    setting = commands.add_parser("mouse-setting", help="read or set one mouse setting")
    setting.add_argument("setting", choices=tuple(mouse_codec.SETTINGS))
    setting.add_argument(
        "value", nargs="?", type=int, help="integer value; boolean controls use 0/1"
    )
    commands.add_parser(
        "get-mouse-settings", help="read mouse sensor, sleep and report-rate settings"
    )
    commands.add_parser("mouse-rate", help="set the USB mouse report rate").add_argument(
        "rate", type=int
    )
    for name in ("mouse-matrix", "get-mouse-dpi"):
        commands.add_parser(name).add_argument("--profile", type=int, default=0)
    key = commands.add_parser(
        "mouse-key", help="write a raw four-byte mouse action to the active profile"
    )
    key.add_argument("slot", type=int)
    key.add_argument("action", help="eight hexadecimal digits in the mouse action format")
    key.add_argument("--profile", type=int)
    dpi = commands.add_parser("mouse-dpi", help="edit one DPI level or select the current level")
    dpi.add_argument("--profile", type=int, default=0)
    for name in ("current", "slot", "x", "y"):
        dpi.add_argument("--" + name, type=int)
    dpi.add_argument("--rgb", type=lambda value: int(value, 16), help="six-digit RGB color")


def run(mouse, args):
    if args.command == "identify":
        return mouse.identify()
    if args.command == "status":
        return mouse.status()
    if args.command == "profile":
        return mouse.set_profile(args.index)
    if args.command == "mouse-matrix":
        matrix = mouse.read_matrix(args.profile)
        return {
            "profile": args.profile,
            "slots": [matrix[i : i + 4].hex() for i in range(0, 64, 4)],
        }
    if args.command == "mouse-key":
        return mouse.set_key(args.slot, bytes.fromhex(args.action), profile=args.profile)
    if args.command == "get-mouse-dpi":
        return mouse.get_dpi(args.profile)
    if args.command == "mouse-dpi":
        return mouse.set_dpi(
            args.profile, current=args.current, slot=args.slot, x=args.x, y=args.y, rgb=args.rgb
        )
    if args.command == "mouse-rate":
        return mouse.set_rate(args.rate)
    if args.command == "get-mouse-settings":
        return mouse.settings()
    if args.command == "mouse-setting":
        if args.value is None:
            return {"setting": args.setting, "value": mouse.get_setting(args.setting)}
        value = args.value
        if args.setting in ("line_repair", "wave_repair"):
            if value not in (0, 1):
                raise ValueError("mouse boolean settings require 0 or 1")
            value = bool(value)
        return mouse.set_setting(args.setting, value)
    raise ValueError("unsupported mouse command")
