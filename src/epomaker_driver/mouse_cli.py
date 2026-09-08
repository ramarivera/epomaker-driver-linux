"""CH585 command-line dispatch, separate from keyboard action encodings."""

from . import actions, codec, macros, mouse_actions, mouse_codec, mouse_snapshot, profiles

SHARED_COMMANDS = frozenset(
    (
        "identify",
        "status",
        "profile",
        "get-macro",
        "macro",
        "bind-key",
        "bind-media",
        "bind-mouse",
        "bind-macro",
        "disable-key",
        "backup",
        "restore",
    )
)


def parsers(commands):
    binding = commands.add_parser("mouse-bind", help="bind a named mouse-specific action")
    binding.add_argument("slot", type=int)
    binding.add_argument("name", choices=tuple(mouse_actions.BINDINGS))
    binding.add_argument("--profile", type=int)
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


def run(mouse, args, prepared=None):
    if args.command == "backup":
        value = mouse_snapshot.capture(mouse)
        profiles.save(args.path, value, overwrite=args.overwrite)
        return {"saved": str(args.path), "limitations": value["limitations"]}
    if args.command == "restore":
        return mouse_snapshot.restore(mouse, prepared, args.backup)
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
            "bindings": [mouse_actions.decode(matrix[i : i + 4]) for i in range(0, 64, 4)],
        }
    if args.command == "mouse-bind":
        return mouse.set_key(args.slot, mouse_actions.mouse(args.name), profile=args.profile)
    if args.command.startswith("bind-") or args.command == "disable-key":
        if args.fn or args.os_mode != 0 or args.submode != 0:
            raise ValueError("mouse bindings have no Fn, OS or keyboard submode bank")
        if args.command == "bind-key":
            action = actions.keyboard(args.key, second=args.second, modifiers=args.modifier)
        elif args.command == "bind-media":
            action = actions.media(args.name)
        elif args.command == "bind-mouse":
            action = mouse_actions.mouse(args.name)
        elif args.command == "bind-macro":
            codec.bounded(args.macro_slot, 49, "mouse macro slot")
            action = actions.macro(args.macro_slot, args.mode)
        else:
            action = bytes(4)
        return mouse.set_key(args.slot, action, profile=args.profile)
    if args.command == "get-macro":
        data = mouse.read_macro(args.slot)
        return macros.decode(data) if args.decoded else {"slot": args.slot, "data": data.hex()}
    if args.command == "macro":
        return mouse.write_macro(args.slot, prepared)
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
