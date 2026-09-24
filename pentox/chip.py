"""Taskbar chip (tab) — a tiny layer-shell pill anchored top-center.

Shown while a game session is active. Reads the chip state file written by
the watcher and live FPS from the game's ring. Works on any Wayland
compositor with layer-shell, without touching the user's bar config; simple
bars can instead display `pentox chip --print`.
"""

from __future__ import annotations

import os
import signal
import time

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib, Gdk  # noqa: E402

# layer-shell is optional — the Chip class falls back to a plain window
try:
    gi.require_version("GtkLayerShell", "0.1")
    from gi.repository import GtkLayerShell  # noqa: E402,F401
except (ValueError, ImportError):
    GtkLayerShell = None

from . import APP_NAME, fpsreader
from .config import load as load_cfg
from .theme import COLORS
from .util import hex_to_rgb, state_dir


def read_chip_state() -> dict:
    d = {}
    try:
        for line in (state_dir() / "chip.state").read_text().splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                d[k.strip()] = v.strip()
    except OSError:
        pass
    return d


def live_fps_for(pid: int) -> float:
    if not pid:
        return 0.0
    try:
        from . import fpsreader as fr
        ring = fr.Ring(f"/tmp/pentox-run-{pid}.ring")
        if ring.open():
            fps, _f, _a, _p = ring.sample(window_s=1.0)
            ring.close()
            return fps
    except Exception:
        pass
    return 0.0


class Chip(Gtk.Window):
    def __init__(self, cfg):
        super().__init__(type=Gtk.WindowType.TOPLEVEL)
        self.cfg = cfg
        self.set_decorated(False)
        self.set_resizable(False)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_app_paintable(True)
        screen = self.get_screen()
        vis = screen.get_rgba_visual()
        if vis:
            self.set_visual(vis)
        self.connect("draw", self.on_draw)
        self.connect("destroy", Gtk.main_quit)
        try:
            ls = GtkLayerShell
            ls.init_for_window(self)
            ls.set_namespace(self, "pentox-chip")
            ls.set_layer(self, ls.Layer.TOP)
            ls.set_anchor(self, ls.Edge.TOP, True)
            ls.set_margin(self, ls.Edge.TOP, 4)
        except Exception:
            self.set_keep_above(True)
        GLib.timeout_add(500, self.tick)

    def tick(self):
        st = read_chip_state()
        on = st.get("state") == "on"
        self.resize(self._wanted_width(st), 28)
        if on:
            self.show_all()
        else:
            self.hide()
        return True

    def _wanted_width(self, st) -> int:
        base = 150
        name = (st.get("game") or "")[:24]
        if name:
            base += 6 * len(name)
        return base

    def on_draw(self, _w, cr):
        st = read_chip_state()
        on = st.get("state") == "on"
        W = self.get_allocated_width()
        H = self.get_allocated_height()
        r, g, b, _ = hex_to_rgb(COLORS["bg"])
        cr.set_source_rgba(r, g, b, 0.86)
        cr.new_sub_path()
        rr = H / 2
        cr.arc(W - rr, rr, rr, -1.5707963267948966, 1.5707963267948966)
        cr.arc(rr, rr, rr, 1.5707963267948966, 4.71238898038469)
        cr.close_path()
        cr.fill()
        br, bg_, bb, _ = hex_to_rgb(COLORS["border"])
        cr.set_source_rgba(br, bg_, bb, 0.25)
        cr.set_line_width(1.0)
        cr.stroke()

        cr.select_font_face(self.cfg.font, 0, 1)
        cr.set_font_size(10.5)
        if on:
            game = (st.get("game") or "game")[:24]
            where = st.get("where") or ""
            pid = 0
            try:
                pid = int(st.get("pid", "0") or 0)
            except ValueError:
                pid = 0
            fps = live_fps_for(pid)
            s = f"▲ {game}  ·  {fps:.0f} fps  ·  {where}"
        else:
            s = f"▲ {APP_NAME} idle"
        cr.set_source_rgba(*hex_to_rgb(COLORS["accent"]), 0.95)
        cr.move_to(14, H / 2 + 4)
        cr.show_text(s)
        return False


def main_chip():
    GLib.set_prgname("pentox-chip")      # Wayland app_id for window rules
    cfg = load_cfg()
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    Chip(cfg).run()


# pkg resource not needed; direct run
if __name__ == "__main__":
    main_chip()
