"""Private, memory-only browser activation URL; see docs/background-service.md."""

import os
import re
import socket
import stat
import threading
from pathlib import Path


def _directory(path):
    path = Path(path)
    if not path.is_absolute():
        raise ValueError("control socket path must be absolute")
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = path.parent.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise ValueError("control socket directory must be owned by this user with mode 0700")
    return path


def _url(value):
    match = re.fullmatch(r"http://127\.0\.0\.1:([0-9]{1,5})/#token=[A-Za-z0-9_-]{16,128}", value)
    if not match or not 1 <= int(match[1]) <= 65535:
        raise ValueError("control socket returned an invalid local session URL")
    return value


class ControlSocket:
    """Publish the live URL to this user without writing a token to disk or logs."""

    def __init__(self, path, url):
        self.path = _directory(path)
        self.url = _url(url)
        self.stop = threading.Event()
        self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            # Existing paths are never replaced; systemd removes its runtime directory on stop.
            self.socket.bind(str(self.path))
            self.inode = self.path.lstat().st_ino
            os.chmod(self.path, 0o600)
            self.socket.listen(4)
            self.socket.settimeout(0.1)
        except BaseException:
            self.socket.close()
            if hasattr(self, "inode") and self.path.lstat().st_ino == self.inode:
                self.path.unlink()
            raise
        self.thread = threading.Thread(target=self._serve, daemon=True)

    def _serve(self):
        while not self.stop.is_set():
            try:
                client, _ = self.socket.accept()
            except TimeoutError:
                continue
            with client:
                client.settimeout(1)
                try:
                    client.sendall(self.url.encode("ascii"))
                except OSError:
                    # A browser opener may disappear before receiving the short response.
                    continue

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *args):
        self.stop.set()
        self.thread.join()
        self.socket.close()
        try:
            if self.path.lstat().st_ino == self.inode:
                self.path.unlink()
        except FileNotFoundError:
            pass


def read_url(path):
    """Read a running instance's URL after checking the socket owner and permissions."""
    path = Path(path)
    if not path.is_absolute():
        raise ValueError("control socket path must be absolute")
    for item, kind in ((path.parent, stat.S_ISDIR), (path, stat.S_ISSOCK)):
        info = item.lstat()
        if not kind(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise ValueError("control socket and directory must be private and owned by this user")
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(2)
        client.connect(str(path))
        result = bytearray()
        while len(result) <= 1024:
            part = client.recv(1025 - len(result))
            if not part:
                break
            result.extend(part)
    return _url(result.decode("ascii"))
