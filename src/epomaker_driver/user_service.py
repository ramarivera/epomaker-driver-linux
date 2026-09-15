"""Install and control the owned EPOMAKER systemd user service."""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

from .errors import DriverError

UNIT = "epomaker-driver-linux.service"
MARKER = "# Managed by epomaker-driver-linux"


class ServiceError(DriverError):
    """User service operation failed; no system-wide service is modified."""


def _path(value: Path, field: str) -> Path:
    result = Path(value)
    if not result.is_absolute() or any(char in str(result) for char in "\0\n\r"):
        raise ValueError(f"{field} must be an absolute path without newline or NUL")
    return result


def _exec(value: Path) -> str:
    text = str(_path(value, "python_executable"))
    if any(ord(char) < 32 or ord(char) == 127 or char in "\"'\\" for char in text):
        raise ValueError("systemd executable path cannot contain quotes, backslashes or controls")
    # systemd does not expand environment variables in the executable (first argument).
    escaped = text.replace("%", "%%")
    return f'"{escaped}"'


def _unit(value: Path) -> str:
    return "\n".join(
        (
            "[Unit]",
            "Description=EPOMAKER Linux driver",
            "",
            "[Service]",
            MARKER,
            f"ExecStart={_exec(value)} -m epomaker_driver.cli serve --port 0 --control-socket %t/epomaker-driver-linux/control.sock",
            "RuntimeDirectory=epomaker-driver-linux",
            "RuntimeDirectoryMode=0700",
            "KillSignal=SIGINT",
            "SuccessExitStatus=130",
            "TimeoutStopSec=15",
            "StandardOutput=null",
            "StandardError=journal",
            "",
            "[Install]",
            "WantedBy=default.target",
            "",
        )
    )


def _unit_path(config_home: Path) -> Path:
    return _path(config_home, "config_home") / "systemd" / "user" / UNIT


def _owned(path: Path) -> bool:
    if path.is_symlink() or not path.is_file():
        return False
    try:
        return MARKER in path.read_text(encoding="utf-8").splitlines()
    except UnicodeError:
        return False


def _systemctl(action: str) -> subprocess.CompletedProcess:
    command = ["systemctl", "--user", action]
    if action == "status":
        command = ["systemctl", "--user", "show", "--property=LoadState,ActiveState,SubState"]
    if action != "daemon-reload":
        command.append(UNIT)
    try:
        return subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise ServiceError(
            f"systemd user {action} failed; check your user session: {error}"
        ) from error


def install(config_home: Path, python_executable: Path) -> dict:
    home = _path(config_home, "config_home")
    executable = _path(python_executable, "python_executable")
    if not executable.is_file() or not os.access(executable, os.X_OK):
        raise ValueError("python_executable must be an existing executable file")
    path = _unit_path(home)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() or path.is_symlink():
        if not _owned(path):
            raise ValueError(f"refusing to replace unrelated unit: {path}")
    fd, temporary = tempfile.mkstemp(prefix=f".{UNIT}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as output:
            output.write(_unit(executable))
            output.flush()
            os.fsync(output.fileno())
        os.chmod(temporary, 0o644)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    try:
        _systemctl("daemon-reload")
    except ServiceError as error:
        raise ServiceError(
            f"unit saved at {path}, but daemon-reload failed; retry after restoring your user session"
        ) from error
    return {"installed": True, "path": str(path)}


def uninstall(config_home: Path) -> dict:
    path = _unit_path(_path(config_home, "config_home"))
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise ValueError(f"refusing to remove non-regular unit: {path}")
    if not path.exists():
        return {"removed": False, "path": str(path)}
    if not _owned(path):
        raise ValueError(f"refusing to remove unrelated unit: {path}")
    _systemctl("stop")
    path.unlink()
    _systemctl("daemon-reload")
    return {"removed": True, "path": str(path)}


def control(action: str) -> dict:
    if action not in ("start", "stop", "status"):
        raise ValueError("action must be start, stop, or status")
    result = _systemctl(action)
    if action != "status":
        return {"action": action, "unit": UNIT, "ok": True}
    values = {}
    for line in result.stdout.splitlines():
        key, separator, value = line.partition("=")
        if separator:
            values[key] = value
    return {"action": action, "unit": UNIT, "ok": True, **values}
