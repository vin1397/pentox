"""Pentox GUI — a small GTK3 control panel.

Opened by the desktop entry (`pentox gui`). Shows session status with live
FPS, controls the watcher, toggles the HUD and edits the few options that
matter — writing back to ~/.config/pentox/pentox.conf while preserving
comments and unknown keys.

Styled with the same end4-pC dark-glass palette as the overlay (see theme.py).
"""

from __future__ import annotations

import os
import pathlib
import subprocess
import sys

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib, Gdk  # noqa: E402

from . import APP_NAME, __version__, fpsreader
from .chip import read_chip_state
from .config import load as load_cfg
from .theme import COLORS
from .util import log_error, state_dir

SERVICE = "pentox-watch.service"

POSITIONS = ["top-right", "top-left", "bottom-right", "bottom-left"]

CSS = b"""
window.pentox { background: rgba(11, 8, 18, 0.97); }
.pentox label { color: #EDE8FF; }
.pentox .title { color: #B9A3FF; font-weight: bold; }
.pentox .muted { color: #9C8CD4; }
.pentox .status { color: #EDE8FF; font-size: 13px; }
.pentox .ok { color: #A6E3A1; }
.pentox .warn { color: #F9E2AF; }
.pentox button { background: rgba(185, 163, 255, 0.10); color: #EDE8FF;
                 border: 1px solid rgba(185, 163, 255, 0.28);
                 border-radius: 10px; padding: 7px 14px; }
.pentox button:hover { background: rgba(185, 163, 255, 0.20); }
.pentox button:active { background: rgba(185, 163, 255, 0.30); }
.pentox combobox button { padding: 4px 10px; }
.pentox switch { color: #EDE8FF; }
.pentox frame > border { border-color: rgba(185, 163, 255, 0.18);
                         border-radius: 12px; background: rgba(185,163,255,0.05); }
.pentox textview { background: rgba(11, 8, 18, 0.6); color: #EDE8FF;
                   font-family: "JetBrainsMono Nerd Font"; font-size: 10px; }
"""


def _systemctl_active() -> str:
    """'active' | 'inactive' | ... for the user watcher unit (or '' if none)."""
    try:
        r = subprocess.run(["systemctl", "--user", "is-active", SERVICE],
                           capture_output=True, text=True, timeout=3)
        return r.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return ""


def _unit_installed() -> bool:
    return pathlib.Path.home().joinpath(
        ".config/systemd/user", SERVICE).exists()


class Panel(Gtk.Window):
    def __init__(self):
        super().__init__(type=Gtk.WindowType.TOPLEVEL)
        self.cfg = load_cfg()
        self.watcher_proc: subprocess.Popen | None = None

        self.set_title(APP_NAME)
        self.set_wmclass("pentox-gui", "Pentox")
        self.set_default_size(430, 520)
        self.set_resizable(False)
        self.set_position(Gtk.WindowPosition.CENTER)
        self._set_logo()
        self.get_style_context().add_class("pentox")
        css = Gtk.CssProvider()
        css.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_screen(
            self.get_screen(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self.connect("destroy", self._quit)

        self._build()
        self._refresh_status()
        GLib.timeout_add(1000, self._refresh_status)

    # ------------------------------------------------------------ layout ---

    def _set_logo(self):
        """Window icon: packaged logo.png first, theme icon as fallback."""
        logo = pathlib.Path(__file__).resolve().parent.parent / "data" / "logo.png"
        if logo.exists():
            try:
                self.set_default_icon_file(str(logo))
                return
            except Exception:
                pass
        try:
            theme = Gtk.IconTheme.get_default()
            if theme.has_icon("pentox"):
                self.set_default_icon_name("pentox")
        except Exception:
            pass

    def _build(self):
        v = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10,
                    border_width=16)
        self.add(v)

        # header
        head = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        try:
            logo = pathlib.Path(__file__).resolve().parent.parent / "data" / "logo.png"
            if logo.exists():
                img = Gtk.Image.new_from_file(str(logo))
                img.set_pixel_size(34)
                head.pack_start(img, False, False, 0)
        except Exception:
            pass
        logo_lbl = Gtk.Label(xalign=0)
        logo_lbl.set_markup(f"<span size='17000' color='#B9A3FF'>▲ Pentox</span>")
        logo_lbl.get_style_context().add_class("title")
        ver = Gtk.Label(xalign=1, hexpand=True)
        ver.set_markup(f"<span color='#9C8CD4'>v{__version__}</span>")
        ver.get_style_context().add_class("muted")
        head.pack_start(logo_lbl, False, False, 0)
        head.pack_end(ver, False, False, 0)
        v.pack_start(head, False, False, 0)

        # status frame
        frame = Gtk.Frame()
        sbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4,
                       border_width=12)
        self.status_lbl = Gtk.Label(xalign=0)
        self.status_lbl.get_style_context().add_class("status")
        self.detail_lbl = Gtk.Label(xalign=0)
        self.detail_lbl.get_style_context().add_class("muted")
        sbox.pack_start(self.status_lbl, False, False, 0)
        sbox.pack_start(self.detail_lbl, False, False, 0)
        frame.add(sbox)
        v.pack_start(frame, False, False, 0)

        # watcher controls
        wrow = Gtk.Box(spacing=8)
        self.watch_btn = Gtk.Button(label="Start watcher")
        self.watch_btn.connect("clicked", self._on_watch_btn)
        self.overlay_btn = Gtk.Button(label="Toggle overlay")
        self.overlay_btn.set_tooltip_text("Send SIGUSR1 to a running overlay")
        self.overlay_btn.connect("clicked", self._on_toggle)
        self.run_btn = Gtk.Button(label="Test overlay…")
        self.run_btn.set_tooltip_text("Launch vkcube (or glxgears) under Pentox")
        self.run_btn.connect("clicked", self._on_test)
        for b in (self.watch_btn, self.overlay_btn, self.run_btn):
            wrow.pack_start(b, True, True, 0)
        v.pack_start(wrow, False, False, 0)

        # options
        frame = Gtk.Frame()
        ob = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8,
                     border_width=12)

        prow = Gtk.Box(spacing=8)
        prow.pack_start(Gtk.Label(label="Overlay position", xalign=0,
                                  hexpand=True), True, True, 0)
        self.pos_combo = Gtk.ComboBoxText()
        for p in POSITIONS:
            self.pos_combo.append_text(p)
        if self.cfg.position in POSITIONS:
            self.pos_combo.set_active(POSITIONS.index(self.cfg.position))
        self.pos_combo.connect("changed", lambda *_: self._save())
        prow.pack_end(self.pos_combo, False, False, 0)
        ob.pack_start(prow, False, False, 0)

        self.sw_notify = self._switch(ob, "Desktop notifications",
                                      self.cfg.notify_enabled)
        self.sw_chip = self._switch(ob, "Taskbar chip", self.cfg.chip_enabled)
        self.sw_esc = self._switch(ob, "Hide HUD with Esc", self.cfg.hide_on_esc)
        frame.add(ob)
        v.pack_start(frame, False, False, 0)

        # doctor
        self.doc_btn = Gtk.Button(label="Run self-test (doctor)")
        self.doc_btn.connect("clicked", self._on_doctor)
        v.pack_start(self.doc_btn, False, False, 0)

        scroll = Gtk.ScrolledWindow(vexpand=True)
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.doc_view = Gtk.TextView(wrap_mode=Gtk.WrapMode.WORD_CHAR,
                                     editable=False, cursor_visible=False,
                                     left_margin=8, right_margin=8,
                                     top_margin=6, bottom_margin=6)
        scroll.add(self.doc_view)
        v.pack_start(scroll, True, True, 0)

    def _switch(self, box, label, active) -> Gtk.Switch:
        row = Gtk.Box(spacing=8)
        lbl = Gtk.Label(label=label, xalign=0, hexpand=True)
        lbl.get_style_context().add_class("muted")
        sw = Gtk.Switch(active=active)
        sw.connect("notify::active", lambda *_: self._save())
        row.pack_start(lbl, True, True, 0)
        row.pack_end(sw, False, False, 0)
        box.pack_start(row, False, False, 0)
        return sw

    # ------------------------------------------------------------ status ---

    def _refresh_status(self):
        st = read_chip_state()
        on = st.get("state") == "on"
        unit = _systemctl_active()
        mine = self.watcher_proc and self.watcher_proc.poll() is None

        if on:
            name = st.get("game") or "game"
            where = st.get("where") or ""
            pid = 0
            try:
                pid = int(st.get("pid", "0") or 0)
            except ValueError:
                pid = 0
            fps = self._fps(pid)
            self.status_lbl.set_markup(
                f"<span color='#A6E3A1'>● In session</span> — {name}")
            self.detail_lbl.set_text(f"HUD {where} · {fps:.0f} fps"
                                     if fps else f"HUD {where} · standby")
        else:
            self.status_lbl.set_markup(
                "<span color='#9C8CD4'>○ Idle</span> — no game detected")
            self.detail_lbl.set_text("Pentox watches in the background and "
                                     "spawns the HUD when a game appears")

        if mine:
            self.watch_btn.set_label("Stop watcher")
            sub = "started from this panel"
        elif unit == "active":
            self.watch_btn.set_label("Stop watcher")
            sub = "systemd user service"
        elif unit == "activating":
            self.watch_btn.set_label("Restart watcher")
            sub = "service starting…"
        else:
            self.watch_btn.set_label("Start watcher")
            sub = ("user service available" if _unit_installed()
                   else "not installed")
        self.detail_lbl.set_text(f"{self.detail_lbl.get_text()}  ·  watcher: {sub}")
        return True

    @staticmethod
    def _fps(pid: int) -> float:
        if not pid:
            return 0.0
        try:
            ring = fpsreader.Ring(f"/tmp/pentox-run-{pid}.ring")
            if ring.open():
                fps, _f, _a, _p = ring.sample(window_s=1.0)
                ring.close()
                return fps
        except Exception:
            pass
        return 0.0

    # ----------------------------------------------------------- actions ---

    def _on_watch_btn(self, _b):
        unit = _systemctl_active()
        mine = self.watcher_proc and self.watcher_proc.poll() is None
        if mine:
            self.watcher_proc.terminate()
            self.watcher_proc = None
        elif unit == "active":
            subprocess.run(["systemctl", "--user", "stop", SERVICE])
        else:
            if _unit_installed():
                subprocess.run(["systemctl", "--user", "start", SERVICE])
            else:
                env = dict(os.environ)
                self.watcher_proc = subprocess.Popen(
                    [sys.executable, "-m", "pentox", "watch"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    start_new_session=True)
        self._refresh_status()

    def _on_toggle(self, _b):
        subprocess.run(["pkill", "-USR1", "-f", "pentox.overlay"])

    def _on_test(self, _b):
        import shutil
        exe = shutil.which("vkcube") or shutil.which("glxgears")
        if not exe:
            self._doctor_append("No vkcube or glxgears found to launch a test "
                                "overlay.\n")
            return
        subprocess.Popen([sys.executable, "-m", "pentox", "run", "--", exe],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def _on_doctor(self, _b):
        self.doc_btn.set_sensitive(False)
        buf = self.doc_view.get_buffer()
        buf.set_text("running pentox doctor…\n")
        GLib.timeout_add(10, self._doctor_run)

    def _doctor_run(self):
        try:
            r = subprocess.run([sys.executable, "-m", "pentox", "doctor"],
                               capture_output=True, text=True, timeout=60)
            out = (r.stdout or "") + (r.stderr or "")
        except (OSError, subprocess.TimeoutExpired) as e:
            out = f"doctor failed: {e}"
        self._doctor_append(out)
        self.doc_btn.set_sensitive(True)
        return False

    def _doctor_append(self, text: str):
        buf = self.doc_view.get_buffer()
        buf.set_text(buf.get_text(*buf.get_bounds(), include_hidden_chars=False)
                     + text)

    # ------------------------------------------------------------- save ---

    def _collect(self) -> dict:
        return {
            "position": POSITIONS[self.pos_combo.get_active()] if
                        self.pos_combo.get_active() >= 0 else "top-right",
            "notify_enabled": bool(self.sw_notify.get_active()),
            "chip_enabled": bool(self.sw_chip.get_active()),
            "hide_on_esc": bool(self.sw_esc.get_active()),
        }

    def _save(self):
        vals = self._collect()
        for k, v in vals.items():
            setattr(self.cfg, k, v)
        try:
            self.cfg.save(vals)
        except OSError:
            log_error("gui: config save failed", errno=True)

    def _quit(self, *_a):
        if self.watcher_proc and self.watcher_proc.poll() is None:
            self.watcher_proc.terminate()
        Gtk.main_quit()


def main_gui():
    # Wayland app_id: GTK3 derives it from prgname, not set_wmclass — set it
    # before any window exists so compositors see class "pentox-gui".
    GLib.set_prgname("pentox-gui")
    GLib.set_application_name(APP_NAME)
    try:
        import signal
        signal.signal(signal.SIGINT, signal.SIG_DFL)
    except Exception:
        pass
    Panel().show_all()
    Gtk.main()


if __name__ == "__main__":
    main_gui()
