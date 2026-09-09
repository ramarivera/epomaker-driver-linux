"""Library location must survive server restarts and be independent of backups."""

from pathlib import Path

from epomaker_driver import cli, server


def test_library_default_independent_of_backup_dir(tmp_path):
    args = cli.parser().parse_args(["serve", "--backup-dir", str(tmp_path)])
    assert args.library_dir == Path.home() / ".local/share/epomaker-driver-linux/macros"


def test_serve_passes_explicit_library_directory(tmp_path, monkeypatch):
    seen = []

    def serve(instance):
        entry = instance.controller.call(
            "macro_library_save",
            {"name": "Example", "mode": "held", "value": {"repeat": 1, "events": []}},
        )
        seen.append(entry)

    monkeypatch.setattr(server.ControlServer, "serve_forever", serve)
    library = tmp_path / "library"
    backups = tmp_path / "backups"
    assert (
        cli.main(
            ["serve", "--port", "0", "--library-dir", str(library), "--backup-dir", str(backups)]
        )
        == 0
    )
    assert (library / f"{seen[0]['id']}.json").is_file()
    assert not backups.exists()
    restarted = server.Controller(backups, library_dir=library)
    assert restarted.call("macro_library", {}) == {"entries": seen}
