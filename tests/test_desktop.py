import shutil
import subprocess

import pytest

from epomaker_driver.desktop import FILENAME, MARKER, install, status, uninstall


def executable(tmp_path):
    path = tmp_path / 'py "x$`%\\bin'
    path.write_text("python")
    path.chmod(0o755)
    return path


def test_install_update_status_and_uninstall_are_scoped(tmp_path):
    home = tmp_path / "xdg"
    python = executable(tmp_path)
    result = install(home, python)
    path = home / "applications" / FILENAME
    assert result == {"installed": True, "path": str(path)}
    assert status(home) == {"installed": True, "path": str(path)}
    content = path.read_text()
    assert MARKER in content
    assert "Terminal=true" in content
    assert "Categories=Settings;HardwareSettings;" in content
    assert "--open-browser --port 0" in content
    assert install(home, python) == result
    assert uninstall(home)["removed"] is True
    assert uninstall(home)["removed"] is False
    assert status(home)["installed"] is False


@pytest.mark.parametrize("value", ["relative", "bad\npath", "bad\rpath", "bad\0path"])
def test_rejects_invalid_paths(tmp_path, value):
    with pytest.raises(ValueError):
        install(tmp_path / "xdg", tmp_path / value)


def test_refuses_unrelated_and_symlink_launcher(tmp_path):
    home = tmp_path / "xdg"
    path = home / "applications" / FILENAME
    path.parent.mkdir(parents=True)
    path.write_text("[Desktop Entry]\nName=someone else\n")
    with pytest.raises(ValueError):
        install(home, executable(tmp_path))
    path.unlink()
    target = tmp_path / "target"
    target.write_text("owned target")
    path.symlink_to(target)
    with pytest.raises(ValueError):
        uninstall(home)
    assert target.read_text() == "owned target"


@pytest.mark.parametrize("background", [False, True])
def test_desktop_file_validator_when_available(tmp_path, background):
    validator = shutil.which("desktop-file-validate")
    if not validator:
        pytest.skip("desktop-file-validate unavailable")
    path = tmp_path / "xdg" / "applications" / FILENAME
    install(path.parents[1], executable(tmp_path), background=background)
    subprocess.run([validator, str(path)], check=True)


def test_update_preserves_venv_symlink_path(tmp_path):
    original = executable(tmp_path)
    environment = tmp_path / "venv/bin"
    environment.mkdir(parents=True)
    python = environment / "python"
    python.symlink_to(original)
    home = tmp_path / "xdg"
    install(home, original)
    install(home, python)
    entry = (home / "applications" / FILENAME).read_text()
    assert f'Exec="{python}" -m epomaker_driver.cli' in entry
    assert str(original) not in entry


def test_background_mode_switches_owned_entry(tmp_path):
    home = tmp_path / "xdg"
    python = executable(tmp_path)
    path = home / "applications" / FILENAME
    install(home, python)
    assert "Terminal=true" in path.read_text()
    install(home, python, background=True)
    content = path.read_text()
    assert "Terminal=false" in content
    assert "service-launch" in content
    assert "serve --open-browser" not in content
    install(home, python, background=False)
    assert "Terminal=true" in path.read_text()


def test_background_requires_strict_boolean_before_writes(tmp_path):
    home = tmp_path / "xdg"
    with pytest.raises(ValueError):
        install(home, executable(tmp_path), background=1)
    assert not (home / "applications" / FILENAME).exists()


def test_equals_in_executable_is_rejected(tmp_path):
    python = tmp_path / "py=thon"
    python.write_text("python")
    python.chmod(0o755)
    with pytest.raises(ValueError, match="cannot contain"):
        install(tmp_path / "xdg", python)


def test_relative_executable_and_nonexecutable_are_rejected(tmp_path):
    with pytest.raises(ValueError, match="absolute"):
        install(tmp_path, "python")
    python = tmp_path / "python"
    python.write_text("not executable")
    with pytest.raises(ValueError, match="executable"):
        install(tmp_path, python)


def test_uninstall_preserves_unrelated_regular_file(tmp_path):
    path = tmp_path / "applications" / FILENAME
    path.parent.mkdir()
    path.write_text("keep")
    with pytest.raises(ValueError, match="unrelated"):
        uninstall(tmp_path)
    assert path.read_text() == "keep"


def test_invalid_utf8_is_unowned_and_read_errors_propagate(tmp_path, monkeypatch):
    from pathlib import Path

    path = tmp_path / "applications" / FILENAME
    path.parent.mkdir()
    path.write_bytes(b"\xff")
    assert status(tmp_path)["installed"] is False

    def fail(*args, **kwargs):
        raise PermissionError("unreadable launcher")

    monkeypatch.setattr(Path, "read_text", fail)
    with pytest.raises(PermissionError, match="unreadable"):
        status(tmp_path)
