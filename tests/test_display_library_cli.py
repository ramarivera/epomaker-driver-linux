"""Display asset storage survives server restarts independently of device backups."""

from pathlib import Path

from epomaker_driver import cli, server


def test_display_assets_default_directory(tmp_path):
    args = cli.parser().parse_args(["serve", "--backup-dir", str(tmp_path)])
    assert args.assets_dir == Path.home() / ".local/share/epomaker-driver-linux/display-assets"


def test_explicit_display_assets_directory(tmp_path, monkeypatch):
    import base64
    import io

    from PIL import Image

    output = io.BytesIO()
    Image.new("RGB", (2, 2), "red").save(output, format="PNG")
    seen = []

    def serve(instance):
        seen.append(
            instance.controller.call(
                "display_asset_save",
                {
                    "name": "Saved display",
                    "kind": "screen",
                    "delay_ms": None,
                    "content": base64.b64encode(output.getvalue()).decode(),
                },
            )
        )

    monkeypatch.setattr(server.ControlServer, "serve_forever", serve)
    assets = tmp_path / "assets"
    backups = tmp_path / "backups"
    assert (
        cli.main(
            ["serve", "--port", "0", "--assets-dir", str(assets), "--backup-dir", str(backups)]
        )
        == 0
    )
    assert (assets / f"{seen[0]['id']}.json").is_file()
    assert not backups.exists()
    restarted = server.Controller(backups, assets_dir=assets)
    loaded = restarted.call("display_asset_get", {"id": seen[0]["id"]})
    assert {key: loaded[key] for key in seen[0]} == seen[0]
    assert base64.b64decode(loaded["content"]) == output.getvalue()
