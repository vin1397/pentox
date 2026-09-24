"""Watcher heuristics: hint matching and the /proc polling fallback."""

import os

from pentox import watch


def test_looks_like_game_hints():
    assert watch.looks_like_game({"class": "steam_app_123", "title": ""})
    assert watch.looks_like_game({"class": "wine", "title": "Cyberpunk"})
    assert watch.looks_like_game({"class": "vkcube", "title": ""})


def test_looks_like_game_fullscreen_heuristic():
    assert watch.looks_like_game({"class": "unknown-game", "title": "x",
                                  "fullscreen": True})
    # Steam Big Picture must not be detected as a game
    assert not watch.looks_like_game({"class": "steam", "title": "",
                                      "fullscreen": True})
    assert not watch.looks_like_game({"class": "foot", "title": "vim",
                                      "fullscreen": False})


def test_poll_game_process_ignores_self_and_shell():
    # this test process is python and matches NEVER_GAME — must not be found
    hit = watch.poll_game_process()
    if hit is not None:
        _pid, name = hit
        assert not any(n in name for n in watch.NEVER_GAME)


def test_poll_game_process_returns_rss_sorted():
    hit = watch.poll_game_process()
    if hit is not None:
        pid, name = hit
        assert isinstance(pid, int) and pid > 0
        assert watch._rss_pages(pid) >= 300_000


def test_game_hints_content():
    assert "steam_app_" in watch.GAME_HINTS
    assert "vkcube" in watch.GAME_HINTS


def test_write_chip_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(watch, "state_dir", lambda: tmp_path)
    watch.write_chip("on", "vkcube", "top right corner", pid=4242)
    st = (tmp_path / "chip.state").read_text()
    assert "state=on" in st and "game=vkcube" in st and "pid=4242" in st
