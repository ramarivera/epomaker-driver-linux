"""Loopback-only control API and packaged UI. See docs/control-interface.md."""

import base64
import io
import json
import mimetypes
import secrets
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from pathlib import Path
from urllib.parse import unquote, urlsplit

from . import actions, codec, macros, media, snapshot, system_info
from .device import Keyboard
from .discovery import discover
from .errors import DeviceUnavailable, DriverError, ProtocolError, UnsupportedDevice
from .models import glyph_matrix
from .transport import Transport

MAX_BODY = 20 * 1024 * 1024


class Controller:
    def __init__(self, backup_dir, *, discovery=discover, transport_factory=Transport.open):
        self.backup_dir = Path(backup_dir)
        self.discovery, self.transport_factory = discovery, transport_factory
        self.keyboard = None
        self.identity = None
        self.lock = threading.RLock()

    def close(self):
        with self.lock:
            if self.keyboard is not None:
                self.keyboard.transport.close()
                self.keyboard = None
                self.identity = None

    def call(self, operation, data):
        with self.lock:
            return self._call(operation, data)

    def _call(self, operation, data):
        if operation == "devices":
            return [device.public_dict() for device in self.discovery() if device.command_transport]
        if operation == "catalog":
            root = files("epomaker_driver").joinpath("data")
            return {
                "layout": json.loads(root.joinpath("glyph-key-layout.json").read_text()),
                "matrices": [
                    list(glyph_matrix(name))
                    for name in ("defaultMatrix", "defaultFnMatrix", "defaultFnMacMatrix")
                ],
                "keys": actions.KEYS,
                "modifiers": actions.MODIFIERS,
                "media": actions.MEDIA,
                "mouse": actions.MOUSE,
                "macro_modes": actions.MACRO_MODES,
                "light_modes": codec.LIGHT_MODES,
                "side_modes": codec.SIDE_MODES,
            }
        if operation == "validate_macro":
            value = data["value"]
            macros.encode(value["repeat"], value["events"])
            return value
        if operation == "connect":
            info = next(
                (d for d in self.discovery() if d.path == data.get("path") and d.command_transport),
                None,
            )
            if info is None:
                raise DeviceUnavailable("selected command device is no longer available")
            transport = self.transport_factory(info)
            try:
                keyboard = Keyboard(transport)
                keyboard._supported()
                identity = keyboard.identify()
                if identity["device_id"] != 3059:
                    raise UnsupportedDevice(
                        "The graphical interface currently supports Glyph; use the CLI for RT85/RT75 and RY6602 core"
                    )
            except Exception:
                transport.close()
                raise
            self.close()
            self.keyboard, self.identity = keyboard, identity
            return identity
        if operation == "disconnect":
            self.close()
            return {"ok": True}
        if operation == "connection":
            return self.identity
        keyboard = self.keyboard
        if keyboard is None:
            raise DeviceUnavailable("connect a keyboard first")
        if operation == "read":
            section = data.get("section")
            if section == "keymap":
                raw = keyboard.read_matrix(
                    data.get("profile", 0), fn=data.get("fn", False), os_mode=data.get("os_mode", 0)
                )
                return {
                    "raw": list(raw),
                    "slots": [actions.decode(raw[i : i + 4]) for i in range(0, 512, 4)],
                }
            if section == "lighting":
                return {"main": keyboard.get_light(), "side": keyboard.get_light(side=True)}
            if section == "picture":
                return {"colors": keyboard.read_picture(data.get("index", 0)).hex()}
            if section == "macro":
                raw = keyboard.read_macro(data.get("slot", 0))
                try:
                    decoded = macros.decode(raw)
                    return {"data": raw.hex(), "decoded": decoded}
                except ProtocolError as error:
                    return {"data": raw.hex(), "decode_error": str(error)}
            if section == "settings":
                return {
                    **keyboard.status(),
                    "options": keyboard.get_options(),
                    "auto_os": keyboard.get_auto_os(),
                }
            if section == "backup":
                return snapshot.capture(keyboard)
            raise ValueError("unknown read section")
        if operation != "write":
            raise ValueError("unknown operation")
        kind = data.get("kind")
        if kind == "key":
            keyboard.set_key(
                data["slot"],
                bytes.fromhex(data["action"]),
                profile=data.get("profile", 0),
                fn=data.get("fn", False),
                os_mode=data.get("os_mode", 0),
            )
        elif kind == "lighting":
            return keyboard.set_light(
                data["mode"],
                side=data.get("side", False),
                rgb=data["rgb"],
                brightness=data["brightness"],
                speed=data["speed"],
                option=data.get("option", 0),
                rainbow=data.get("rainbow", False),
            )
        elif kind == "picture":
            keyboard.write_picture(bytes.fromhex(data["colors"]), data["index"])
        elif kind == "macro":
            value = data["value"]
            keyboard.write_macro(data["slot"], macros.encode(value["repeat"], value["events"]))
        elif kind in ("screen", "animation"):
            content = base64.b64decode(data["content"], validate=True)
            source = io.BytesIO(content)
            if kind == "screen":
                bank = codec.bounded(data.get("bank", 0), 4, "still bank")
                keyboard.upload_screen(
                    media.screen_image(source, fit=True), (0, 0, 428, 142), frame=bank
                )
            else:
                frames, delay = media.screen_animation(
                    source, fit=True, delay_ms=data.get("delay_ms")
                )
                keyboard.upload_animation(frames, delay)
        elif kind == "clock":
            keyboard.sync_clock()
        elif kind == "display_language_toggle":
            keyboard.toggle_display_language()
        elif kind == "system_info":
            value = system_info.Collector().collect()
            keyboard.sync_system_info(value)
            return value
        elif kind == "profile":
            keyboard.set_profile(data["profile"])
        elif kind == "debounce":
            keyboard.set_debounce(data["milliseconds"])
        elif kind == "sleep":
            keyboard.set_sleep(data["bt"], data["dongle"], data["deep_bt"], data["deep_dongle"])
        elif kind == "options":
            return keyboard.set_options(system=data.get("system"), wasd_swap=data.get("wasd_swap"))
        elif kind == "auto_os":
            keyboard.set_auto_os(data["enabled"])
        elif kind == "restore":
            return snapshot.restore(
                keyboard, data["value"], self.backup_dir / f"recovery-{uuid.uuid4().hex}.json"
            )
        else:
            raise ValueError("unknown write kind")
        return {"ok": True}


class ControlServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, controller, *, port=0, web_root=None, token=None):
        self.controller = controller
        self.token = token or secrets.token_urlsafe(32)
        self.web_root = Path(web_root or files("epomaker_driver").joinpath("web")).resolve()
        super().__init__(("127.0.0.1", port), Handler)

    def server_close(self):
        self.controller.close()
        super().server_close()


class Handler(BaseHTTPRequestHandler):
    def setup(self):
        super().setup()
        self.connection.settimeout(15)

    def log_message(self, *_):
        pass  # No tokens, image content or profile data in request logs.

    def _reply(self, code, body, content_type="application/json"):
        raw = body if isinstance(body, bytes) else json.dumps(body, allow_nan=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' blob: data:; style-src 'self' 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'",
        )
        self.end_headers()
        self.wfile.write(raw)

    def _guard(self, api):
        port = self.server.server_port
        hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
        if self.headers.get("Host") not in hosts:
            self._reply(403, {"error": "invalid Host"})
            return False
        origin = self.headers.get("Origin")
        if origin is not None and origin not in {f"http://{host}" for host in hosts}:
            self._reply(403, {"error": "cross-origin request denied"})
            return False
        if api and not secrets.compare_digest(
            self.headers.get("X-Epomaker-Token", "").encode(), self.server.token.encode()
        ):
            self._reply(
                403, {"error": "session token required; open the URL printed by epomaker serve"}
            )
            return False
        return True

    def do_GET(self):
        path = urlsplit(self.path).path
        api = path.startswith("/api/")
        if not self._guard(api):
            return
        if api:
            if path not in ("/api/devices", "/api/catalog", "/api/connection"):
                self._reply(404, {"error": "unknown endpoint"})
                return
            self._call(path[5:], {})
            return
        target = (self.server.web_root / (unquote(path).lstrip("/") or "index.html")).resolve()
        if not target.is_relative_to(self.server.web_root) or not target.is_file():
            self._reply(404, {"error": "UI asset missing; run npm ci && npm run build in ui/"})
            return
        self._reply(
            200,
            target.read_bytes(),
            mimetypes.guess_type(target.name)[0] or "application/octet-stream",
        )

    def do_POST(self):
        if not self._guard(True):
            return
        path = urlsplit(self.path).path
        if path not in (
            "/api/connect",
            "/api/disconnect",
            "/api/read",
            "/api/write",
            "/api/validate_macro",
        ):
            self._reply(404, {"error": "unknown endpoint"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= MAX_BODY or self.headers.get("Transfer-Encoding"):
                self._reply(413, {"error": "request body outside supported size"})
                return
            if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                self._reply(415, {"error": "JSON body required"})
                return
            value = json.loads(self.rfile.read(length))
            if not isinstance(value, dict):
                raise ValueError("JSON body must be an object")
        except (ValueError, OSError):
            self._reply(400, {"error": "invalid JSON request"})
            return
        self._call(path[5:], value)

    def _call(self, operation, value):
        try:
            result = self.server.controller.call(operation, value)
        except (DriverError, ValueError, TypeError, KeyError, OSError) as error:
            self._reply(400, {"error": str(error), "type": type(error).__name__})
            return
        self._reply(200, result)
