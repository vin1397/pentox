"""Pentox overlay — self-drawn GTK3 + gtk-layer-shell Wayland HUD (Cairo).

Everything on screen is rendered here: glass panel, sections, bars,
frametime graph. No HUD engine is embedded.
"""

from __future__ import annotations

import collections
import os
import pathlib
import signal
import sys

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("GtkLayerShell", "0.1")
from gi.repository import Gtk, GLib, Gdk, GtkLayerShell  # noqa: E402

from . import fpsreader, metrics
from .config import load as load_cfg
from .theme import (BAR_HEIGHT, BAR_WIDTH_FRAC, INNER_PAD, ROW_PAD,
                    SECTION_PAD, SECTION_SCALE, HERO_SCALE)
from .util import hex_to_rgb, human_gib

POS_MAP = {
    "top-right":    (GtkLayerShell.Edge.TOP, GtkLayerShell.Edge.RIGHT),
    "top-left":     (GtkLayerShell.Edge.TOP, GtkLayerShell.Edge.LEFT),
    "bottom-right": (GtkLayerShell.Edge.BOTTOM, GtkLayerShell.Edge.RIGHT),
    "bottom-left":  (GtkLayerShell.Edge.BOTTOM, GtkLayerShell.Edge.LEFT),
}


class Hud(Gtk.Window):
    def __init__(self, cfg, target_pid: int | None, game: str = ""):
        super().__init__(type=Gtk.WindowType.TOPLEVEL)
        self.cfg = cfg
        self.target_pid = target_pid
        self.game = game
        self.ring = None
        self.ring_api = 0
        self.hidden = False
        self.gpu = metrics.detect_gpu(cfg.gpu_pci)
        self.cpu = metrics.CpuSampler()
        self.cpu_load = None
        self.cpu_power = None
        self.fps_hist = collections.deque(maxlen=240)
        self._toggle_acc = 0.0

        self.set_app_paintable(True)
        self.set_decorated(False)
        self.set_resizable(False)
        self.set_skip_taskbar_hint(False)     # appears as a taskbar entry
        self.set_skip_pager_hint(True)
        self.set_wmclass("pentox-overlay", "Pentox Overlay")
        self.set_default_size(cfg.width, 10)

        screen = self.get_screen()
        visual = screen.get_rgba_visual()
        if visual:
            self.set_visual(visual)

        self.connect("draw", self.on_draw)
        self.connect("destroy", Gtk.main_quit)
        self.connect("key-press-event", self.on_key)

        self._setup_layer_shell()
        try:
            GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGUSR1, self.toggle)
        except AttributeError:
            pass
        GLib.timeout_add(cfg.update_ms, self.tick)

    # ------------------------------------------------------------ shell ---

    def _setup_layer_shell(self):
        try:
            ls = GtkLayerShell
            ls.init_for_window(self)
            ls.set_namespace(self, "pentox")
            ls.set_layer(self, ls.Layer.OVERLAY)
            e1, e2 = POS_MAP.get(self.cfg.position, POS_MAP["top-right"])
            ls.set_anchor(self, e1, True)
            ls.set_anchor(self, e2, True)
            m = ls.Edge.LEFT if "right" in self.cfg.position else ls.Edge.RIGHT
            ls.set_margin(self, m, self.cfg.margin_x)
            m2 = ls.Edge.TOP if "top" in self.cfg.position else ls.Edge.BOTTOM
            ls.set_margin(self, m2, self.cfg.margin_y)
            self.layer_shell = True
        except Exception:
            self.layer_shell = False   # X11 fallback: plain always-on-top window
            self.set_keep_above(True)
            self.set_position(Gtk.WindowPosition.NONE)

    # ------------------------------------------------------------ data ----

    def _open_ring(self):
        pid = self.target_pid or int(os.environ.get("PENTOX_PID", "0") or 0)
        if pid:
            p = pathlib.Path(f"/tmp/pentox-run-{pid}.ring")
            if p.exists():
                r = fpsreader.Ring(p)
                if r.open():
                    self.ring = r
                else:
                    self._diag(f"ring open failed: {p}")
                return
            self._diag(f"ring missing: {p}")
        # fall back: newest live ring
        for p, _meta in fpsreader.discover_rings():
            r = fpsreader.Ring(p)
            if r.open():
                self.ring = r
                return

    def _diag(self, msg: str):
        if not getattr(self, "_diag_once", False):
            self._diag_once = True
            print(f"pentox-overlay: {msg}", file=sys.stderr, flush=True)

    def tick(self):
        try:
            # self-heal: exit when the game we were spawned for is gone
            if self.target_pid and not os.environ.get("PENTOX_STAY"):
                from .util import proc_alive
                if not proc_alive(self.target_pid):
                    print("pentox-overlay: game exited, closing",
                          file=sys.stderr, flush=True)
                    Gtk.main_quit()
                    return False
            if self.ring is None:
                self._open_ring()
            if self.ring:
                fps, frames, api, _pid = self.ring.sample(window_s=1.0)
                self.ring_api = api
                self.fps_hist.append(fps)
                if os.environ.get("PENTOX_DEBUG"):
                    self._dbg_acc = getattr(self, "_dbg_acc", 0) + 1
                    if self._dbg_acc % 8 == 0:
                        print(f"pentox-overlay: ring={self.ring.path} fps={fps:.1f} "
                              f"api={api} hist={len(self.fps_hist)}",
                              file=sys.stderr, flush=True)
            cl = self.cpu.busy_percent()
            if cl is not None:
                self.cpu_load = cl
            pw = self.cpu.power_w()
            if pw is not None:
                self.cpu_power = pw
        except Exception:
            pass                    # never let a probe error kill the HUD timer
        if self.hidden:
            self.hide()
        else:
            self.show_all()
            self.queue_draw()   # show_all alone does NOT repaint a mapped window
        return True

    def toggle(self):
        self.hidden = not self.hidden
        return True

    # ------------------------------------------------------------ paint ---

    def _rounded(self, cr, x, y, w, h, r):
        cr.new_sub_path()
        cr.arc(x + w - r, y + r, r, -90 * 3.14159 / 180, 0)
        cr.arc(x + w - r, y + h - r, r, 0, 90 * 3.14159 / 180)
        cr.arc(x + r, y + h - r, r, 90 * 3.14159 / 180, 180 * 3.14159 / 180)
        cr.arc(x + r, y + r, r, 180 * 3.14159 / 180, 270 * 3.14159 / 180)
        cr.close_path()

    def on_draw(self, _w, cr):
        cfg = self.cfg
        W = cfg.width
        H = self.get_allocated_height()

        # panel
        r, g, b, _ = cfg.rgba("bg")
        cr.set_source_rgba(r, g, b, cfg.bg_alpha)
        self._rounded(cr, 0, 0, W, H, cfg.radius)
        cr.fill()
        br, bg_, bb, _ = cfg.rgba("border")
        cr.set_source_rgba(br, bg_, bb, cfg.border_alpha)
        cr.set_line_width(1.0)
        self._rounded(cr, 0.5, 0.5, W - 1, H - 1, cfg.radius)
        cr.stroke()

        x0 = INNER_PAD
        y = INNER_PAD
        y = self._header(cr, x0, y, W - 2 * INNER_PAD)
        y += SECTION_PAD
        y = self._fps_section(cr, x0, y, W - 2 * INNER_PAD)
        y += SECTION_PAD
        y = self._gpu_section(cr, x0, y, W - 2 * INNER_PAD)
        y += SECTION_PAD
        y = self._cpu_section(cr, x0, y, W - 2 * INNER_PAD)
        y += SECTION_PAD
        y = self._mem_section(cr, x0, y, W - 2 * INNER_PAD)
        y += SECTION_PAD
        y = self._footer(cr, x0, y, W - 2 * INNER_PAD)
        y += INNER_PAD - ROW_PAD

        want = max(int(y), 120)
        if abs(want - H) > 6:
            self.resize(cfg.width, want)
        return False

    # ---- text helpers -----------------------------------------------------

    def _text(self, cr, x, y, s, size, color, alpha=1.0, bold=False):
        cr.set_source_rgba(*hex_to_rgb(color), alpha)
        cr.select_font_face(self.cfg.font,
                            cairo.FONT_SLANT_NORMAL,
                            cairo.FONT_WEIGHT_BOLD if bold else cairo.FONT_SLANT_NORMAL)
        cr.set_font_size(size)
        cr.move_to(x, y)
        cr.show_text(s)
        return cr.text_extents(s)[4]   # x_advance

    def _measure(self, cr, s, size, bold=False):
        cr.select_font_face(self.cfg.font, cairo.FONT_SLANT_NORMAL,
                            cairo.FONT_WEIGHT_BOLD if bold else cairo.FONT_SLANT_NORMAL)
        cr.set_font_size(size)
        return cr.text_extents(s)[4]

    # ---- sections ----------------------------------------------------------

    def _header(self, cr, x, y, w):
        s = SECTION_SCALE * self.cfg.font_size
        self._text(cr, x, y + s, "Pentox", s, self.cfg.accent, bold=True)
        if self.game:
            name = self.game if len(self.game) <= 34 else self.game[:31] + "…"
            nsize = self.cfg.font_size * 0.85
            nw = self._measure(cr, name, nsize)
            self._text(cr, x + w - nw, y + s, name, nsize, self.cfg.muted)
        return y + s + ROW_PAD

    def _fps_section(self, cr, x, y, w):
        base = self.cfg.font_size
        hero = base * HERO_SCALE
        fps = self.fps_hist[-1] if self.fps_hist else 0.0
        self._text(cr, x, y + hero, f"{fps:.0f}", hero, self.cfg.text, bold=True)
        lab = "FPS"
        self._text(cr, x + self._measure(cr, f"{fps:.0f}", hero, True) + 10,
                   y + hero, lab, base * 1.2, self.cfg.muted)

        # percentiles right column
        pct = self._percentiles()
        px = x + w - self._measure(cr, "0.1%  00", base)
        yy = y + base * 1.4
        for lab, val in pct:
            self._text(cr, px, yy, lab, base * 0.9, self.cfg.muted)
            self._text(cr, px + self._measure(cr, "0.1% ", base * 0.9), yy,
                       f"{val:.0f}", base * 1.05, self.cfg.text, bold=True)
            yy += base * 1.5

        # frametime graph
        gy = y + hero + base * 1.6
        gh = base * 3.2
        cur = self._frametime_ms()
        self._text(cr, x, gy - 2, "frametime", base * 0.85, self.cfg.muted)
        cur_s = f"{cur:.1f} ms" if cur else "—"
        cw = self._measure(cr, cur_s, base * 0.9)
        self._text(cr, x + w - cw, gy - 2, cur_s, base * 0.9, self.cfg.accent)
        self._graph(cr, x, gy + 4, w, gh)
        return gy + 4 + gh

    def _percentiles(self):
        fps_list = list(self.fps_hist)[-120:]
        if len(fps_list) < 20:
            return []
        s = sorted(fps_list)
        avg = sum(s) / len(s)
        p1 = s[max(0, int(len(s) * 0.01))]
        p01 = s[max(0, int(len(s) * 0.001))]
        return [("avg", avg), ("1%", p1), ("0.1%", p01)]

    def _frametime_ms(self):
        ft, _api, _pid = self.ring.frametimes_ms(limit=2) if self.ring else ([], 0, 0)
        if not ft:
            return None
        return ft[-1]

    def _ft_series_ms(self):
        ft, _api, _pid = self.ring.frametimes_ms(limit=240) if self.ring else ([], 0, 0)
        return ft

    def _graph(self, cr, x, y, w, h):
        series = self._ft_series_ms()
        # track
        tr = hex_to_rgb(self.cfg.muted)
        cr.set_source_rgba(tr[0], tr[1], tr[2], 0.14)
        self._rounded(cr, x, y, w, h, 3)
        cr.fill()
        if len(series) < 2:
            return
        lo, hi = min(series), max(series)
        span = max(1.0, hi - lo)
        gr = hex_to_rgb(self.cfg.graph)
        gf = hex_to_rgb(self.cfg.graph_fill)
        pts = []
        n = len(series)
        for i, v in enumerate(series):
            px = x + w * i / (n - 1)
            py = y + h - h * ((v - lo) / span)
            pts.append((px, py))
        cr.set_source_rgba(gf[0], gf[1], gf[2], 0.30)
        cr.move_to(x, y + h)
        for px, py in pts:
            cr.line_to(px, py)
        cr.line_to(x + w, y + h)
        cr.close_path()
        cr.fill()
        cr.set_source_rgba(gr[0], gr[1], gr[2], 0.95)
        cr.set_line_width(1.2)
        cr.move_to(*pts[0])
        for px, py in pts[1:]:
            cr.line_to(px, py)
        cr.stroke()

    def _bar(self, cr, x, y, w, frac):
        frac = max(0.0, min(1.0, frac))
        tr = hex_to_rgb(self.cfg.muted)
        cr.set_source_rgba(tr[0], tr[1], tr[2], 0.16)
        self._rounded(cr, x, y, w, BAR_HEIGHT, BAR_HEIGHT / 2)
        cr.fill()
        ac = hex_to_rgb(self.cfg.accent)
        if frac > 0.01:
            cr.set_source_rgba(ac[0], ac[1], ac[2], 0.92)
            self._rounded(cr, x, y, max(BAR_HEIGHT, w * frac), BAR_HEIGHT, BAR_HEIGHT / 2)
            cr.fill()

    def _two_col(self, cr, x, y, w, label, value, size):
        self._text(cr, x, y, label, size * 0.92, self.cfg.muted)
        vw = self._measure(cr, value, size * 0.95)
        self._text(cr, x + w / 2, y, value, size * 0.95, self.cfg.text)
        return y + size * 1.55

    def _gpu_section(self, cr, x, y, w):
        base = self.cfg.font_size
        s = self.gpu_sample_cache
        head = base * SECTION_SCALE
        self._text(cr, x, y + head, "GPU", head, self.cfg.text, bold=True)
        nm = self.gpu.label
        if len(nm) > 30:
            nm = nm[:27] + "…"
        self._text(cr, x, y + head + base * 1.5, nm, base * 0.9, self.cfg.muted)
        # right column: load + temp
        load_s = f"{s['busy']:.0f}%" if s["busy"] is not None else "—"
        lw = self._measure(cr, load_s, head, True)
        self._text(cr, x + w / 2, y + head, load_s, head, self.cfg.accent, bold=True)
        if s["temp"] is not None:
            tcol = self.cfg.text
            if s["temp"] >= 85:
                tcol = self.cfg.hot
            elif s["temp"] >= 75:
                tcol = self.cfg.warn
            ts = f"{s['temp']:.0f}°C"
            tw = self._measure(cr, ts, head, True)
            self._text(cr, x + w - tw, y + head, ts, head, tcol, bold=True)
        yy = y + head + base * 2.1
        col2 = x + w / 2 + 8
        # bars row (load + vram)
        bw = w * BAR_WIDTH_FRAC / 2 - 8
        if s["busy"] is not None:
            self._bar(cr, x, yy, bw, s["busy"] / 100.0)
        if s["mem_used_kib"] and s["mem_total_kib"]:
            self._bar(cr, col2, yy, bw, s["mem_used_kib"] / s["mem_total_kib"])
            vs = f"{s['mem_used_kib'] / 1048576:.1f} / {s['mem_total_kib'] / 1048576:.1f} GiB"
            self._text(cr, col2, yy + base * 1.7, "VRAM", base * 0.85, self.cfg.muted)
            vw = self._measure(cr, vs, base * 0.9)
            self._text(cr, x + w - vw, yy + base * 1.7, vs, base * 0.9, self.cfg.text)
        yy += BAR_HEIGHT + base * 2.0
        # two-column details
        L = [("core", f"{s['core_mhz']:.0f} MHz" if s["core_mhz"] else None),
             ("power", f"{s['power_w']:.1f} W" if s["power_w"] else None),
             ("fan", f"{s['fan_rpm']:.0f} RPM" if s["fan_rpm"] is not None else None)]
        R = [("mem clock", f"{s['mem_mhz']:.0f} MHz" if s["mem_mhz"] else None),
             ("junction", f"{s['junction']:.0f}°C" if (s["junction"] and self.cfg.show_junction) else None),
             (None, None)]
        for (lk, lv), (rk, rv) in zip(L, R):
            if lv:
                self._text(cr, x, yy, lk, base * 0.85, self.cfg.muted)
                self._text(cr, x + w / 4, yy, lv, base * 0.95, self.cfg.text)
            if rk and rv:
                self._text(cr, col2, yy, rk, base * 0.85, self.cfg.muted)
                self._text(cr, col2 + w / 4, yy, rv, base * 0.95, self.cfg.text)
            yy += base * 1.5
        return yy

    def _cpu_section(self, cr, x, y, w):
        base = self.cfg.font_size
        head = base * SECTION_SCALE
        s = base
        self._text(cr, x, y + head, "CPU", head, self.cfg.text, bold=True)
        load = self.cpu_load
        load_s = f"{load:.0f}%" if load is not None else "—"
        self._text(cr, x + w / 2, y + head, load_s, head, self.cfg.accent, bold=True)
        t = self.cpu.temp_c()
        if t is not None:
            tcol = self.cfg.text
            if t >= 90:
                tcol = self.cfg.hot
            elif t >= 80:
                tcol = self.cfg.warn
            ts = f"{t:.0f}°C"
            tw = self._measure(cr, ts, head, True)
            self._text(cr, x + w - tw, y + head, ts, head, tcol, bold=True)
        yy = y + head + base * 2.1
        bw = w * BAR_WIDTH_FRAC / 2 - 8
        if load is not None:
            self._bar(cr, x, yy, bw, load / 100.0)
        yy += BAR_HEIGHT + base * 1.0
        clk = self.cpu.clock_mhz()
        if clk:
            self._text(cr, x, yy, "clock", base * 0.85, self.cfg.muted)
            cs = f"{clk:.0f} MHz"
            self._text(cr, x + w / 4, yy, cs, base * 0.95, self.cfg.text)
        if self.cpu_power:
            self._text(cr, x + w / 2 + 8, yy, "power", base * 0.85, self.cfg.muted)
            ps = f"{self.cpu_power:.1f} W"
            self._text(cr, x + w / 2 + 8 + w / 4, yy, ps, base * 0.95, self.cfg.text)
        yy += base * 1.5
        return yy

    def _mem_section(self, cr, x, y, w):
        base = self.cfg.font_size
        m = metrics.mem_sample()
        if not m:
            return y
        yy = y
        lab = "RAM"
        used = human_gib(m["used_kib"], m["total_kib"])
        self._text(cr, x, yy + base, lab, base * 1.1, self.cfg.text, bold=True)
        uw = self._measure(cr, used, base * 0.95)
        self._text(cr, x + w / 2, yy + base, used, base * 0.95, self.cfg.text)
        pct_s = f"{m['pct']:.0f}%"
        pw = self._measure(cr, pct_s, base * 0.9)
        self._text(cr, x + w - pw, yy + base, pct_s, base * 0.9, self.cfg.muted)
        yy += base * 1.4
        self._bar(cr, x, yy, w * BAR_WIDTH_FRAC, m["pct"] / 100.0)
        yy += BAR_HEIGHT + base * 1.2
        return yy

    def _footer(self, cr, x, y, w):
        base = self.cfg.font_size
        api = fpsreader.API_NAME.get(self.ring_api, "")
        s = api or "standby"
        self._text(cr, x, y + base, s, base * 0.9, self.cfg.muted)
        return y + base * 1.6

    # ------------------------------------------------------------ keys ----

    def on_key(self, _w, ev):
        if self.cfg.hide_on_esc and ev.keyval == Gdk.KEY_Escape:
            self.toggle()
            return True
        return False

    def run(self):
        self.show_all()
        if not self.layer_shell:
            pass
        Gtk.main()


def main_overlay():
    cfg = load_cfg()
    pid = None
    if "--pid" in sys.argv:
        pid = int(sys.argv[sys.argv.index("--pid") + 1])
    game = os.environ.get("PENTOX_GAME", "")
    Hud(cfg, pid, game).run()


# cairo is imported lazily here so doctor can run without the overlay deps
import cairo  # noqa: E402

gpu_sample_cache = {}


def _patch_gpu_cache(hud):
    hud.gpu_sample_cache = metrics.gpu_sample(hud.gpu)


_orig_init = Hud.__init__


def _init_with_cache(self, cfg, target_pid, game=""):
    _orig_init(self, cfg, target_pid, game)
    self.gpu_sample_cache = metrics.gpu_sample(self.gpu)
    GLib.timeout_add(max(200, cfg.update_ms), self._refresh_gpu)


def _refresh_gpu(self):
    self.gpu_sample_cache = metrics.gpu_sample(self.gpu)
    return True


Hud.__init__ = _init_with_cache
Hud._refresh_gpu = _refresh_gpu
