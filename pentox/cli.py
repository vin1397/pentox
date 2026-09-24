"""Pentox command line interface.

  pentox run -- CMD       launch CMD with Pentox frame capture + overlay
  pentox watch            ambient watcher: HUD on any detected game window
  pentox overlay          render the HUD for a pid (used internally/by hand)
  pentox chip             taskbar tab pill (Wayland layer-shell)
  pentox chip --print     one-line status for simple bars/scripts
  pentox doctor           environment self-test
"""

from __future__ import annotations

import argparse
import os
import pathlib
import shutil
import signal
import subprocess
import sys
import time

from . import APP_NAME, __version__
from .config import load as load_cfg
from .util import config_file


def _lib_dir() -> pathlib.Path:
    # shims sit next to the package: <root>/src in dev, <prefix>/lib/pentox/src installed
    return pathlib.Path(__file__).resolve().parent.parent / "src"


def _env_for_capture(pid: int, ring: str, meta: str) -> dict:
    env = dict(os.environ)
    libdir = _lib_dir()
    # GL capture: LD_PRELOAD our self-written shim
    shim = libdir / "libpentoxgl.so"
    if shim.exists():
        env["LD_PRELOAD"] = (str(shim) + " " + env.get("LD_PRELOAD", "")).strip()
    # Vulkan capture: our own layer via standard Vulkan loader discovery
    if (libdir / "libpentoxvk.so").exists() or (libdir / "Pentox_layer.json").exists():
        env["VK_LAYER_PATH"] = str(libdir) + os.pathsep + env.get("VK_LAYER_PATH", "")
        env["VK_INSTANCE_LAYERS"] = ("VK_LAYER_PENTOX_capture" + os.pathsep +
                                     env.get("VK_INSTANCE_LAYERS", "")).strip()
    env["PENTOX_RING"] = ring
    env["PENTOX_META"] = meta
    env["PENTOX_PID"] = str(pid)
    return env


def cmd_run(args):
    cfg = load_cfg()
    cmd = list(args.cmd)
    while cmd and cmd[0] == "--":   # argparse REMAINDER keeps the separator
        cmd.pop(0)
    if not cmd:
        print("usage: pentox run -- COMMAND [ARGS...]")
        return 2
    ring = f"/tmp/pentox-run-{os.getpid()}.ring"
    meta = ring + ".meta"
    pathlib.Path(meta).write_text(f"pid={os.getpid()}\nstarted={time.time()}\n")
    env = _env_for_capture(os.getpid(), ring, meta)

    # spawn overlay alongside the game
    overlay_proc = None
    where = cfg.position.replace("-", " ") + " corner"
    marker = pathlib.Path("/tmp/pentox-overlay.pid")
    try:
        overlay_proc = subprocess.Popen(
            [sys.executable, "-m", "pentox", "overlay", "--pid", str(os.getpid())],
            env=dict(os.environ, PENTOX_PID=str(os.getpid()), PENTOX_GAME=cmd[0]))
        marker.write_text(str(os.getpid()))   # tells the watcher to defer
    except OSError as e:
        print(f"warning: overlay not started ({e})")
    from .watch import announce_start
    announce_start(cfg, os.getpid(), cmd[0], where)

    import signal as _sig

    def _on_term(signum, _frame):
        raise SystemExit(128 + signum)

    _sig.signal(_sig.SIGTERM, _on_term)

    game = subprocess.Popen(cmd, env=env)
    try:
        rc = game.wait()
    except (KeyboardInterrupt, SystemExit) as e:
        game.terminate()
        try:
            game.wait(timeout=3)
        except subprocess.TimeoutExpired:
            game.kill()
        rc = getattr(e, "code", 130) or 130
    finally:
        from .watch import announce_end
        announce_end(cfg)
        try:
            marker.unlink()
        except OSError:
            pass
        if overlay_proc:
            overlay_proc.terminate()
    return rc


def cmd_watch(args):
    from .watch import Watcher
    cfg = load_cfg()
    w = Watcher(cfg)
    print(f"{APP_NAME}: watching for games (Hyprland IPC or process poll)…")
    w.run_forever()
    return 0


def cmd_overlay(args):
    from .overlay import main_overlay
    main_overlay()
    return 0


def cmd_chip(args):
    if args.print:
        from .chip import read_chip_state
        st = read_chip_state()
        if st.get("state") == "on":
            print(f"▲ {st.get('game','game')} · {st.get('where','')}")
        else:
            print(f"▲ {APP_NAME} idle")
        return 0
    if not load_cfg().chip_enabled:
        return 0
    from .chip import main_chip
    main_chip()
    return 0


def cmd_toggle(args):
    subprocess.run(["pkill", "-USR1", "-f", "pentox.overlay"])
    return 0


def cmd_gui(args):
    from .gui import main_gui
    main_gui()
    return 0


def cmd_doctor(args):
    ok = True

    def check(name, cond, extra=""):
        nonlocal ok
        mark = "✔" if cond else "✘"
        if not cond:
            ok = False
        print(f"  {mark} {name}{(' — ' + extra) if extra else ''}")

    print(f"{APP_NAME} {__version__} — environment check\n")
    check("python", sys.version_info >= (3, 9), sys.version.split()[0])

    try:
        import cairo  # noqa
        check("pycairo", True, cairo.version)
    except Exception as e:
        check("pycairo", False, str(e))

    try:
        import gi
        gi.require_version("Gtk", "3.0")
        from gi.repository import Gtk  # noqa
        check("GTK3 + PyGObject", True)
    except Exception as e:
        check("GTK3 + PyGObject", False, str(e))

    try:
        import gi
        gi.require_version("GtkLayerShell", "0.1")
        from gi.repository import GtkLayerShell  # noqa
        check("gtk-layer-shell (Wayland overlay)", True)
    except Exception:
        check("gtk-layer-shell (Wayland overlay)", False,
              "X11 fallback will be used")

    check("gcc", bool(shutil.which("cc") or shutil.which("gcc")))
    check("vulkan headers", pathlib.Path("/usr/include/vulkan/vulkan.h").exists())
    check("grim (screenshot test)", bool(shutil.which("grim")))

    try:
        from .metrics import detect_gpu, CpuSampler
        g = detect_gpu()
        check("GPU detect", g.kind != "unknown", f"{g.label} ({g.kind})")
        s = __import__("pentox.metrics", fromlist=["gpu_sample"]).gpu_sample(g)
        check("GPU metrics", any(v is not None for v in s.values()),
              ", ".join(f"{k}={v}" for k, v in s.items() if v is not None))
        c = CpuSampler()
        check("CPU temp", c.temp_c() is not None, f"{c.temp_c()}°C")
        check("CPU freq", c.clock_mhz() is not None, f"{c.clock_mhz()} MHz")
        check("CPU power (RAPL)", c.power_w() is not None)
    except Exception as e:
        check("metrics", False, str(e))

    m = __import__("pentox.metrics", fromlist=["mem_sample"]).mem_sample()
    check("meminfo", bool(m), f"{m.get('pct', 0):.0f}% used")

    cfg = load_cfg()
    check("config", config_file().exists() or True, str(config_file()))

    print("\n" + ("all good ✔" if ok else "problems found ✘ — see above"))
    return 0 if ok else 1


def build_parser():
    ap = argparse.ArgumentParser(prog="pentox", description=f"{APP_NAME} — Linux game overlay")
    ap.add_argument("--version", action="version", version=f"{APP_NAME} {__version__}")
    sub = ap.add_subparsers(dest="cmdname", required=True)

    p = sub.add_parser("run", help="run a game with Pentox capture + overlay")
    p.add_argument("cmd", nargs=argparse.REMAINDER)
    p.set_defaults(fn=cmd_run)

    p = sub.add_parser("watch", help="ambient watcher: HUD on any game window")
    p.set_defaults(fn=cmd_watch)

    p = sub.add_parser("overlay", help="render the overlay (internal)")
    p.add_argument("--pid", type=int)
    p.set_defaults(fn=cmd_overlay)

    p = sub.add_parser("chip", help="taskbar tab pill")
    p.add_argument("--print", action="store_true")
    p.set_defaults(fn=cmd_chip)

    p = sub.add_parser("toggle", help="toggle overlay visibility")
    p.set_defaults(fn=cmd_toggle)

    p = sub.add_parser("gui", help="open the Pentox control panel")
    p.set_defaults(fn=cmd_gui)

    p = sub.add_parser("doctor", help="self-test")
    p.set_defaults(fn=cmd_doctor)
    return ap


def main(argv=None):
    args = build_parser().parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
