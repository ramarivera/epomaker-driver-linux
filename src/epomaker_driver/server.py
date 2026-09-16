"""Loopback-only control API and packaged UI. See docs/control-interface.md."""

import base64
import copy
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

from . import (
    actions,
    codec,
    display_edit,
    firmware,
    firmware_service,
    firmware_versions,
    macros,
    media,
    profiles,
    snapshot,
    system_info,
    vendor_apply,
    vendor_import,
)
from .audio_capture import AudioCaptureError, PipeWireCapture
from .audio_devices import list_audio_outputs
from .audio_preview import AudioPreview
from .audio_spectrum import DEFAULT_SETTINGS, SETTINGS_LIMITS
from .config_library import ConfigLibrary
from .device import Keyboard
from .discovery import discover
from .display_library import DisplayLibrary
from .errors import DeviceUnavailable, DriverError, ProtocolError, UnsupportedDevice
from .live_light_session import LiveLightSession
from .macro_library import MacroLibrary
from .models import glyph_matrix
from .system_info_refresh import SystemInfoRefresh
from .transport import Transport

MAX_BODY = 20 * 1024 * 1024
MAX_FIRMWARE_INSPECT_BODY = 4 * ((firmware.MAX_SIZE + 2) // 3) + 4096


class Controller:
    def __init__(
        self,
        backup_dir,
        *,
        library_dir=None,
        assets_dir=None,
        discovery=discover,
        transport_factory=Transport.open,
        collector_factory=system_info.Collector,
        audio_capture_factory=PipeWireCapture,
        audio_discovery=list_audio_outputs,
    ):
        self.backup_dir = Path(backup_dir)
        self.library = MacroLibrary(library_dir or self.backup_dir / "macro-library")
        self.config_library = ConfigLibrary(self.backup_dir / "key-configurations")
        self.display_library = DisplayLibrary(assets_dir or self.backup_dir / "display-assets")
        self.discovery, self.transport_factory = discovery, transport_factory
        self.keyboard = None
        self.identity = None
        self.connection_info = None
        self.lock = threading.RLock()
        self.system_info_refresh = SystemInfoRefresh(self, collector_factory)
        self.live_light = LiveLightSession()
        self.audio_preview = AudioPreview(audio_capture_factory)
        self.audio_discovery = audio_discovery
        self.vendor_preview = None

    def close(self):
        with self.lock:
            self.vendor_preview = None
            self.audio_preview.stop()
            self.live_light.cancel()
            self.system_info_refresh.stop()
            keyboard, self.keyboard = self.keyboard, None
            self.identity = self.connection_info = None
            if keyboard is not None:
                keyboard.transport.close()

    def call(self, operation, data):
        # Metadata may block on the remote service; keep it outside the controller lock.
        if operation in ("firmware_metadata", "firmware_inspect"):
            return self._firmware_call(operation, data)
        with self.lock:
            try:
                return self._call(operation, data)
            except DeviceUnavailable:
                # A failed replacement connection must not discard a still-open device.
                if operation != "connect":
                    self.close()
                raise

    @staticmethod
    def _firmware_call(operation, data):
        if not isinstance(data, dict):
            raise ValueError("request must be an object")
        if operation == "firmware_metadata":
            return firmware_service.fetch_metadata()
        content = data.get("content")
        if not isinstance(content, str) or not content:
            raise ValueError("firmware content must be a base64 string")
        encoded_limit = 4 * ((firmware.MAX_SIZE + 2) // 3)
        if len(content) > encoded_limit:
            raise ValueError("firmware content exceeds size limit")
        try:
            raw = base64.b64decode(content, validate=True)
        except (ValueError, TypeError) as error:
            raise ValueError("firmware content must be valid base64") from error
        if len(raw) > firmware.MAX_SIZE:
            raise ValueError("firmware content exceeds size limit")
        version = data.get("version")
        if not isinstance(version, str) or not version.strip() or len(version) > 256:
            raise ValueError("firmware version must be nonempty and at most 256 characters")
        result = firmware.inspect_container(raw, version=version)
        if "current_versions" in data:
            current = data["current_versions"]
            result["comparison"] = firmware_versions.analyze(version, current, result["components"])
        return result

    def _call(self, operation, data):
        if operation == "audio_outputs":
            return self.audio_discovery()
        if operation == "audio_config":
            return {
                "defaults": DEFAULT_SETTINGS,
                "limits": {
                    key: dict(zip(("min", "max", "step"), bounds, strict=True))
                    for key, bounds in SETTINGS_LIMITS.items()
                },
            }
        if operation == "audio_preview_start":
            settings = data.get("settings", {})
            if not isinstance(settings, dict) or set(settings) - set(DEFAULT_SETTINGS):
                raise ValueError("unsupported audio settings")
            target = data.get("target", "auto")
            if not isinstance(target, str) or (
                target != "auto"
                and target not in {output["id"] for output in self.audio_discovery()}
            ):
                raise ValueError("select an available audio output")
            return self.audio_preview.start(target, **settings)
        if operation in ("audio_preview_sample", "audio_preview_stop"):
            session = data.get("session")
            if not isinstance(session, str) or not session:
                raise ValueError("audio preview session is required")
            if operation == "audio_preview_sample":
                return self.audio_preview.sample(session)
            return self.audio_preview.stop(session)
        if operation == "system_info_refresh":
            return self.system_info_refresh.status()
        if operation == "system_info_refresh_start":
            keyboard = self.keyboard
            if keyboard is None or self.identity is None or self.identity.get("device_id") != 3059:
                raise DeviceUnavailable("connect a Glyph keyboard first")
            return self.system_info_refresh.start(
                keyboard,
                data.get("interval"),
                data.get("disk", "/"),
                data.get("interface"),
            )
        if operation == "system_info_refresh_stop":
            return self.system_info_refresh.stop()
        if operation == "devices":
            return [device.public_dict() for device in self.discovery() if device.command_transport]
        if operation == "catalog":
            root = files("epomaker_driver").joinpath("data")
            lighting_capabilities = json.loads(
                root.joinpath("glyph-lighting-capabilities.json").read_text()
            )
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
                # Keep the functional Glyph metadata alongside the legacy flat
                # mode maps. The UI uses this to avoid exposing controls that a
                # particular effect does not implement.
                "lighting_capabilities": lighting_capabilities,
            }
        if operation == "validate_macro":
            value = data["value"]
            macros.encode(value["repeat"], value["events"])
            return value
        if operation == "config_library":
            return {"entries": self.config_library.list()}
        if operation == "config_library_save":
            return self.config_library.save(
                data.get("name"),
                data.get("matrix"),
                data.get("layer"),
                data.get("id"),
                data.get("revision"),
            )
        if operation == "config_library_delete":
            return self.config_library.delete(data.get("id"), data.get("revision"))
        if operation == "macro_library":
            return {"entries": self.library.list()}
        if operation == "macro_library_save":
            return self.library.save(
                data.get("name"),
                data.get("value"),
                data.get("mode"),
                data.get("id"),
                data.get("revision"),
            )
        if operation == "macro_library_delete":
            return self.library.delete(data.get("id"), data.get("revision"))
        if operation == "backup_validate":
            return snapshot.describe(data.get("value"))
        if operation == "display_library":
            return {"entries": self.display_library.list()}
        if operation == "display_asset_save":
            return self.display_library.save(
                data.get("name"), data.get("kind"), data.get("delay_ms"), data.get("content")
            )
        if operation == "display_asset_get":
            return self.display_library.get(data.get("id"))
        if operation == "display_asset_export":
            return self.display_library.export(data.get("id"))
        if operation == "display_asset_import":
            return self.display_library.import_asset(data.get("value"))
        if operation == "display_asset_delete":
            return self.display_library.delete(data.get("id"))
        if operation in ("display_prepare", "display_edit"):
            encoded = data.get("content")
            if not isinstance(encoded, str) or not encoded:
                raise ValueError("display content must be a base64 string")
            if len(encoded) > MAX_BODY:
                raise ValueError("display content exceeds request size limit")
            content = base64.b64decode(encoded, validate=True)
            if operation == "display_edit":
                return display_edit.edit_display(
                    content,
                    kind=data.get("kind"),
                    delay_ms=data.get("delay_ms"),
                    operation=data.get("operation"),
                    index=data.get("index"),
                )
            return media.prepare_display(
                content,
                kind=data.get("kind"),
                delay_ms=data.get("delay_ms"),
            )
        if operation == "connect":
            self.live_light.cancel()
            self.system_info_refresh.stop()
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
                # The transport kind comes from the opened command collection;
                # expose it so the UI can gate Glyph animation controls.
                identity["transport"] = getattr(transport, "kind", None)
                identity["path"] = info.path
                identity["session"] = uuid.uuid4().hex
                identity["telemetry"] = None
                if identity["device_id"] != 3059:
                    raise UnsupportedDevice(
                        "The graphical interface currently supports Glyph; use the CLI for RT85/RT75 and RY6602 core"
                    )
            except Exception:
                transport.close()
                raise
            self.close()
            self.keyboard, self.identity = keyboard, identity
            self.connection_info = info
            return identity
        if operation == "disconnect":
            self.system_info_refresh.stop()
            self.close()
            return {"ok": True}
        if operation == "connection":
            # Poll metadata and queued notifications without sending HID commands.
            # Compare the full command collection, since hidraw paths can be reused.
            if self.connection_info is not None and self.connection_info not in self.discovery():
                self.close()
            identity = copy.deepcopy(self.identity)
            if identity is not None:
                telemetry = getattr(self.keyboard.transport, "telemetry", None)
                identity["telemetry"] = telemetry() if telemetry is not None else None
            return identity
        keyboard = self.keyboard
        if keyboard is None:
            raise DeviceUnavailable("connect a keyboard first")
        if operation == "vendor_import_preview":
            self.vendor_preview = None
            content = data.get("content")
            if not isinstance(content, str) or not content:
                raise ValueError("vendor configuration content must be base64 text")
            if len(content) > 4 * ((profiles.MAX_PROFILE_BYTES + 2) // 3):
                raise ValueError("vendor configuration exceeds size limit")
            record = profiles.decode(base64.b64decode(content, validate=True))
            if keyboard.identify().get("device_id") != 3059:
                raise UnsupportedDevice("vendor configuration import supports Glyph only")
            planned = vendor_import.plan(
                record,
                snapshot.capture(keyboard),
                data.get("target", "Main"),
                data.get("profile", 0),
            )
            token = secrets.token_urlsafe(24)
            self.vendor_preview = (token, record, planned)
            return {"token": token, "plan": copy.deepcopy(planned)}
        if operation == "live_light_start":
            return self.live_light.start(keyboard)
        if operation == "live_light_frame":
            return self.live_light.frame(data.get("session"), data.get("colors"))
        if operation == "live_light_stop":
            return self.live_light.stop(data.get("session"))
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
            if section == "firmware_versions":
                return keyboard.read_firmware_versions()
            if section == "backup":
                return snapshot.capture(keyboard)
            raise ValueError("unknown read section")
        if operation != "write":
            raise ValueError("unknown operation")
        kind = data.get("kind")
        if self.live_light.session is not None:
            if kind in ("factory_reset", "restore"):
                self.live_light.cancel()
            else:
                self.live_light.stop(self.live_light.session)
        if kind == "vendor_import":
            pending = self.vendor_preview
            if pending is None or data.get("token") != pending[0]:
                raise ValueError("preview the vendor configuration before importing")
            self.vendor_preview = None
            _, record, planned = pending
            return vendor_apply.apply(
                keyboard,
                record,
                self.backup_dir / f"recovery-{uuid.uuid4().hex}.json",
                target=planned["target"],
                profile=planned["profile"],
                expected_plan=planned,
            )
        if kind == "factory_reset":
            self.system_info_refresh.stop()
            backup = self.backup_dir / f"recovery-{uuid.uuid4().hex}.json"
            try:
                # Re-identify immediately before the destructive operation; a
                # cached identity can outlive a device replacement.
                identity = keyboard.identify()
                if identity.get("device_id") != 3059:
                    raise UnsupportedDevice("graphical factory reset currently supports Glyph only")
                result = snapshot.factory_reset(keyboard, backup)
            finally:
                # The reset invalidates the cache after sending the command, but
                # backup capture can fail first. Either way reconnect is required.
                self.close()
            return {
                **result,
                "connection": {
                    "state": "disconnected",
                    "reconnect_required": True,
                    "factory_defaults_verified": False,
                },
            }
        if kind == "key":
            keyboard.set_key(
                data["slot"],
                bytes.fromhex(data["action"]),
                profile=data.get("profile", 0),
                fn=data.get("fn", False),
                os_mode=data.get("os_mode", 0),
            )
        elif kind == "config":
            entry = self.config_library.get(data.get("id"), data.get("revision"))
            profile = codec.bounded(data.get("profile", 0), 2, "profile")
            if keyboard.identify().get("device_id") != 3059:
                raise UnsupportedDevice("saved key configurations support Glyph only")
            matrix = bytes.fromhex(entry["matrix"])
            if entry["layer"] == "Main":
                keyboard.write_matrix(matrix, profile)
            else:
                if profile != 0:
                    raise ValueError("Fn configurations require profile 0")
                keyboard.write_fn_matrix(matrix, os_mode=int(entry["layer"] == "Fn Mac"))
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
            self.system_info_refresh.stop()
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
            if path not in (
                "/api/devices",
                "/api/catalog",
                "/api/connection",
                "/api/config_library",
                "/api/macro_library",
                "/api/display_library",
                "/api/system_info_refresh",
                "/api/audio_outputs",
                "/api/audio_config",
                "/api/firmware_metadata",
            ):
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
            "/api/config_library_save",
            "/api/config_library_delete",
            "/api/macro_library_save",
            "/api/macro_library_delete",
            "/api/display_prepare",
            "/api/display_edit",
            "/api/display_asset_save",
            "/api/display_asset_get",
            "/api/display_asset_export",
            "/api/display_asset_import",
            "/api/display_asset_delete",
            "/api/system_info_refresh_start",
            "/api/system_info_refresh_stop",
            "/api/live_light_start",
            "/api/live_light_frame",
            "/api/live_light_stop",
            "/api/backup_validate",
            "/api/vendor_import_preview",
            "/api/audio_preview_start",
            "/api/audio_preview_sample",
            "/api/audio_preview_stop",
            "/api/firmware_inspect",
        ):
            self._reply(404, {"error": "unknown endpoint"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            body_limit = MAX_FIRMWARE_INSPECT_BODY if path == "/api/firmware_inspect" else MAX_BODY
            if not 0 < length <= body_limit or self.headers.get("Transfer-Encoding"):
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
        except (DriverError, AudioCaptureError, ValueError, TypeError, KeyError, OSError) as error:
            self._reply(400, {"error": str(error), "type": type(error).__name__})
            return
        self._reply(200, result)
