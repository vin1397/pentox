"""Config: parsing, type coercion, and comment-preserving saves."""

import pathlib

from pentox.config import PentoxConfig


def test_load_path_types_and_comments(tmp_path: pathlib.Path):
    p = tmp_path / "pentox.conf"
    p.write_text(
        "# comment line\n"
        "position = bottom-left\n"
        "width = 420          # trailing comment\n"
        "bg_alpha = 0.5\n"
        "notify_enabled = false\n"
        "unknown_future_key = hello\n",
        encoding="utf-8",
    )
    cfg = PentoxConfig().load_path(p)
    assert cfg.position == "bottom-left"
    assert cfg.width == 420
    assert cfg.bg_alpha == 0.5
    assert cfg.notify_enabled is False
    assert cfg.hide_on_esc is True          # untouched default


def test_save_path_preserves_comments_and_unknown_keys(tmp_path: pathlib.Path):
    p = tmp_path / "pentox.conf"
    p.write_text(
        "# my tuning\n"
        "position = top-left\n"
        "width = 500\n"
        "custom_thing = keep me\n",
        encoding="utf-8",
    )
    cfg = PentoxConfig()
    cfg.save_path(p, {"position": "bottom-right", "notify_enabled": False})
    lines = p.read_text().splitlines()
    assert "# my tuning" in lines
    assert "position = bottom-right" in lines
    assert "custom_thing = keep me" in lines
    assert "notify_enabled = false" in lines
    assert "width = 500" in lines


def test_save_path_drops_duplicates(tmp_path: pathlib.Path):
    p = tmp_path / "pentox.conf"
    p.write_text("position = top-left\nposition = top-right\n",
                 encoding="utf-8")
    PentoxConfig().save_path(p, {"position": "bottom-left"})
    positions = [ln for ln in p.read_text().splitlines()
                 if ln.startswith("position")]
    assert positions == ["position = bottom-left"]


def test_bool_parsing_variants():
    for raw, expected in [("1", True), ("true", True), ("YES", True),
                          ("on", True), ("0", False), ("no", False),
                          ("off", False)]:
        p = pathlib.Path("/dev/null")     # never read; we set attrs directly
        cfg = PentoxConfig()
        # emulate the parser path by writing a temp file
        import tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".conf",
                                         delete=False) as f:
            f.write(f"notify_enabled = {raw}\n")
            tmp = f.name
        cfg = PentoxConfig().load_path(tmp)
        assert cfg.notify_enabled is expected, raw
        pathlib.Path(tmp).unlink()
