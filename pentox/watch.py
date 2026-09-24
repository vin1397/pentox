"""Game watcher — detects game windows (Hyprland IPC) and renders the overlay.

Design:
- Talks directly to $XDG_RUNTIME_DIR/hypr/$HIS/.socket.sock / .socket2.sock
  (no external IPC library).
- Falls back to a polling mode on other compositors/X11: watches /proc for
  any process whose comm matches the process-whitelist in config.
- For every detected game it spawns `pentox overlay --for <pid>`, which
  reads that process's own frame ring and displays the HUD.
- Fires a whereabouts notification on start ("Pentox: overlay top-right in
  <game>") and drops a taskbar chip state file that end4-pC/any bar can
  display; `pentox chip` renders it for simple bars.
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import signal
import socket
import subprocess
import sys
import time

from . import APP_NAME, RUNTIME_DIR, STATE_DIR_NAME
from .util import log_error, proc_alive, proc_name, state_dir

GAME_HINTS = (
    "wine", "gamescope", "steam_app_", "vkcube", "supertuxkart", "openarena",
    "xonotic", "0ad", "minetest", "lutris", "heroic", "bottles", "dxvk",
)

# Processes that are never games, even when they hit other heuristics.
NEVER_GAME = (
    "pentox", "watch", "overlay", "chip", "python", "sh", "bash", "zsh",
    "fish", "systemd", "plasmashell", "kwin", "hyprland", "mutter", "gnome-",
    "weston", "labwc", "waybar", "sway", "dunst", "mako", "kanshi", "grim",
    "steam", "steamwebhelper", "code", "firefox", "chromium", "chrome",
    "kitty", "alacritty", "foot", "konsole", "gnome-terminal",
)


def hypr_paths():
    his = os.environ.get("HYPRLAND_INSTANCE_SIGNATURE")
    xrd = os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
    if not his or not pathlib.Path(f"{xrd}/hypr/{his}").exists():
        return None, None
    base = pathlib.Path(xrd) / "hypr" / his
    return str(base / ".socket.sock"), str(base / ".socket2.sock")


def hypr_clients() -> list[dict]:
    req, _ = hypr_paths()
    if not req:
        return []
    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(2.0)
        s.connect(req)
        s.send(b"j/clients")
        buf = b""
        while True:
            chunk = s.recv(65536)
            if not chunk:
                break
            buf += chunk
        s.close()
        return json.loads(buf.decode() or "[]")
    except (OSError, json.JSONDecodeError):
        return []


def looks_like_game(client: dict) -> bool:
    cls = (client.get("class") or "").lower()
    title = (client.get("title") or "").lower()
    for h in GAME_HINTS:
        if h in cls or h in title:
            return True
    # heuristic: fullscreen windows are usually games
    return bool(client.get("fullscreen")) and "steam" not in cls


def find_pid_for_client(client: dict) -> int:
    return int(client.get("pid") or 0)


def poll_game_process() -> tuple[int, str] | None:
    """Fallback detection for non-Hyprland sessions: scan /proc for a
    game-like process (hint names, or any fullscreen-ish GPU consumer).
    Returns (pid, name) or None. Kept cheap — one pass per watch interval."""
    hits = []
    for p in pathlib.Path("/proc").iterdir():
        if not p.name.isdigit():
            continue
        pid = int(p.name)
        name = proc_name(pid).lower()
        if not name or any(n in name for n in NEVER_GAME):
            continue
        hinted = any(h in name for h in GAME_HINTS)
        if not hinted:
            # likely-3D heuristic: sizeable private memory (apps mapping big
            # GPU buffers) — cheap filter so we don't flag every daemon
            try:
                st = (p / "statm").read_text().split()
                rss_pages = int(st[1])
            except (OSError, ValueError, IndexError):
                continue
            if rss_pages < 300_000:        # ~1.2 GiB at 4 KiB pages
                continue
        hits.append((pid, name))
    if not hits:
        return None
    # prefer the hungriest candidate
    return max(hits, key=lambda h: _rss_pages(h[0]))


def _rss_pages(pid: int) -> int:
    try:
        return int(pathlib.Path(f"/proc/{pid}/statm").read_text().split()[1])
    except (OSError, ValueError, IndexError):
        return 0


def write_chip(state: str, name: str = "", where: str = "", pid: int = 0):
    try:
        f = state_dir() / "chip.state"
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(
            f"state={state}\ngame={name}\nwhere={where}\npid={pid}\nts={int(time.time())}\n")
    except OSError:
        pass


def notify(summary: str, body: str, enabled: bool = True):
    if not enabled:
        return
    try:
        subprocess.Popen(["notify-send", "-a", APP_NAME, summary, body],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        pass


def announce_start(cfg, pid: int, name: str, where: str):
    write_chip("on", name, where, pid)
    notify(f"{APP_NAME} — game started",
           f"{name}\nOverlay: {where}  ·  'pentox toggle' hides", cfg.notify_enabled)


def announce_end(cfg):
    write_chip("off")


class Watcher:
    def __init__(self, cfg, spawn_overlay=True):
        self.cfg = cfg
        self.spawn_overlay = spawn_overlay
        self.proc = None                 # Popen of the overlay
        self.current = None              # (pid, name)
        self._stop = False
        self.chip_file = state_dir() / "chip.state"

    # ---------------------------------------------------------------- util

    def _write_chip(self, state: str, name: str = "", where: str = ""):
        write_chip(state, name, where, self.current[0] if self.current else 0)

    def _notify(self, summary: str, body: str):
        notify(summary, body, self.cfg.notify_enabled)

    def _ring_for(self, pid: int) -> str:
        return f"{RUNTIME_DIR}/pentox-run-{pid}.ring"

    # ---------------------------------------------------------------- loop

    def stop(self, *a):
        self._stop = True

    def _teardown(self):
        if self.proc:
            try:
                self.proc.terminate()
            except OSError:
                pass
            self.proc = None
        write_chip("off")

    def run_forever(self):
        signal.signal(signal.SIGINT, self.stop)
        signal.signal(signal.SIGTERM, self.stop)
        self._hypr = hypr_paths()[0] is not None
        # seed history so first event doesn't trip detection
        known = {c.get("address") for c in hypr_clients() if looks_like_game(c)}
        self._poll_pid = None               # fallback-mode tracked game
        while not self._stop:
            if self._hypr:
                started, stopped = self._scan(known)
                known = started if started is not None else known
                # pid-based fallback: the layer-shell surface is invisible to us
                # if the watcher was restarted, so also check the game process
                if self.current and not proc_alive(self.current[0]):
                    self._on_game_end()
            else:
                self._poll_scan()
            time.sleep(self.cfg.watch_interval_s)
        self._teardown()

    def _poll_scan(self):
        """Non-Hyprland fallback: /proc-based game detection."""
        hit = poll_game_process()
        if hit and self.current is None:
            pid, name = hit
            self._on_game_start({"pid": pid, "class": name,
                                 "title": name, "initial_title": name})
        elif self.current and (hit is None or not proc_alive(self.current[0])):
            self._on_game_end()

    def _scan(self, known):
        clients = [c for c in hypr_clients() if looks_like_game(c)]
        new = {c.get("address") for c in clients}
        started = new - known
        for c in clients:
            if c.get("address") in started:
                self._on_game_start(c)
        if not clients and self.current:
            self._on_game_end()
        return new or None, None

    def _overlay_running(self) -> bool:
        """True if an overlay started by `pentox run` is up (pid marker file).
        The watcher must NOT stack a second HUD on top in that case."""
        try:
            txt = (pathlib.Path(RUNTIME_DIR) / "pentox-overlay.pid").read_text().strip()
            return bool(txt) and proc_alive(int(txt))
        except (OSError, ValueError):
            return False

    def _on_game_start(self, client):
        pid = find_pid_for_client(client)
        name = (client.get("initial_title") or client.get("title")
                or client.get("class") or "game").strip()
        if self.proc:
            try:
                self.proc.terminate()
            except OSError:
                pass
            self.proc = None
        self.current = (pid, name)
        if self._overlay_running():
            self.external = True     # `pentox run` owns HUD + chip + notification
            return
        self.external = False
        pos = self.cfg.position.replace("-", " ")
        if self.spawn_overlay:
            env = dict(os.environ, PENTOX_PID=str(pid), PENTOX_GAME=name)
            try:
                self._ovlog = open("/tmp/pentox-overlay.err", "w")
                self.proc = subprocess.Popen(
                    [sys.executable, "-m", "pentox", "overlay", "--pid", str(pid)],
                    env=env, stdout=self._ovlog, stderr=self._ovlog)
            except OSError as e:
                log_error(f"watcher: overlay spawn failed for pid {pid}", errno=True)
        where = f"{pos} corner"
        self._write_chip("on", name, where)
        self._notify(f"{APP_NAME} — game detected",
                     f"{name}\nOverlay: {where} — 'pentox toggle' hides it")

    def _on_game_end(self):
        if self.proc:
            try:
                self.proc.terminate()
            except OSError:
                pass
            self.proc = None
        if getattr(self, "external", False):
            self.current = None      # `pentox run` cleans up its own HUD + chip
            return
        self._write_chip("off")
        self.current = None
