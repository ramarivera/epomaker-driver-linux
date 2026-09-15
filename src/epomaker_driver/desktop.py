"""Install and remove the EPOMAKER Linux desktop launcher."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

FILENAME = "org.epomaker.DriverLinux.desktop"
MARKER = "X-EPOMAKER-DriverLinux-Managed=1"


def _path(value: Path, field: str) -> Path:
    result = Path(value)
    if not result.is_absolute():
        raise ValueError(f"{field} must be an absolute path")
    text = str(result)
    if "\0" in text or "\n" in text or "\r" in text:
        raise ValueError(f"{field} must not contain newline or NUL")
    return result


def _launcher(data_home: Path) -> Path:
    return _path(data_home, "data_home") / "applications" / FILENAME


def _exec_arg(value: Path) -> str:
    text = str(_path(value, "python_executable"))
    if "=" in text:
        raise ValueError("python_executable cannot contain '='")
    escaped = (
        text.replace("%", "%%")
        .replace("\\", "\\\\\\\\")
        .replace('"', '\\\\"')
        .replace("`", "\\\\`")
        .replace("$", "\\\\$")
    )
    return f'"{escaped}"'


def _content(python_executable: Path, *, background: bool = False) -> str:
    executable = _exec_arg(python_executable)
    command = (
        f"{executable} -m epomaker_driver.cli service-launch"
        if background
        else f"{executable} -m epomaker_driver.cli serve --open-browser --port 0"
    )
    return "\n".join(
        (
            "[Desktop Entry]",
            "Version=1.0",
            MARKER,
            "Name=EPOMAKER Linux driver",
            "Type=Application",
            f"Terminal={'false' if background else 'true'}",
            "Icon=input-keyboard",
            "Categories=Settings;HardwareSettings;",
            f"Exec={command}",
            "",
        )
    )


def _owned(path: Path) -> bool:
    if not path.is_file() or path.is_symlink():
        return False
    try:
        return MARKER in path.read_text(encoding="utf-8").splitlines()
    except UnicodeError:
        return False


def install(data_home: Path, python_executable: Path, *, background: bool = False) -> dict:
    """Atomically install or update the marker-owned desktop entry."""
    home = _path(data_home, "data_home")
    executable = _path(python_executable, "python_executable")
    if type(background) is not bool:
        raise ValueError("background must be a boolean")
    if not executable.is_file() or not os.access(executable, os.X_OK):
        raise ValueError("python_executable must be an existing executable file")
    path = _launcher(home)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() or path.is_symlink():
        if not _owned(path):
            raise ValueError(f"refusing to replace unrelated launcher: {path}")
    content = _content(executable, background=background)
    fd, temporary = tempfile.mkstemp(prefix=f".{FILENAME}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as output:
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        os.chmod(temporary, 0o644)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return {"installed": True, "path": str(path)}


def uninstall(data_home: Path) -> dict:
    """Remove only the marker-owned launcher, treating absence as a no-op."""
    path = _launcher(_path(data_home, "data_home"))
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise ValueError(f"refusing to remove non-regular launcher: {path}")
    if path.exists():
        if not _owned(path):
            raise ValueError(f"refusing to remove unrelated launcher: {path}")
        path.unlink()
        return {"removed": True, "path": str(path)}
    return {"removed": False, "path": str(path)}


def status(data_home: Path) -> dict:
    """Report whether the marker-owned launcher is installed."""
    path = _launcher(_path(data_home, "data_home"))
    return {"installed": _owned(path), "path": str(path)}
