"""Small shared helpers used across Pentox."""

from __future__ import annotations

import os
import pathlib
import time


def log_file() -> pathlib.Path:
    """Persistent user log (errors and watcher diagnostics)."""
    p = state_dir() / "pentox.log"
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    return p


def log_error(msg: str, errno: bool = False):
    """Best-effort error logging: stderr + $XDG_STATE_HOME/pentox/pentox.log."""
    import sys
    import traceback
    line = msg
    if errno:
        etype, evalue, _ = sys.exc_info()
        if etype is not None:
            line = f"{msg}: {etype.__name__}: {evalue}"
    print(line, file=sys.stderr, flush=True)
    try:
        with open(log_file(), "a", encoding="utf-8") as f:
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {line}\n")
            if errno:
                traceback.print_exc(file=f)
    except OSError:
        pass


def xdg_config_home() -> pathlib.Path:
    return pathlib.Path(os.environ.get("XDG_CONFIG_HOME", "~/.config")).expanduser()


def xdg_state_home() -> pathlib.Path:
    return pathlib.Path(os.environ.get("XDG_STATE_HOME", "~/.local/state")).expanduser()


def config_file() -> pathlib.Path:
    return xdg_config_home() / "pentox" / "pentox.conf"


def state_dir() -> pathlib.Path:
    return xdg_state_home() / "pentox"


def hex_to_rgb(s: str):
    s = s.strip().lstrip("#")
    return tuple(int(s[i:i + 2], 16) / 255.0 for i in (0, 2, 4))


def human_gib(used_kib: float, total_kib: float | None = None) -> str:
    u = used_kib / (1024.0 * 1024.0)
    if total_kib is None:
        return f"{u:.1f} GiB"
    t = total_kib / (1024.0 * 1024.0)
    return f"{u:.1f} / {t:.1f} GiB"


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def monotonic_ns() -> int:
    return time.monotonic_ns()


def proc_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False


def proc_name(pid: int) -> str:
    try:
        return (pathlib.Path(f"/proc/{pid}/comm").read_text().strip() or "?")
    except OSError:
        return "?"


def read_int(path: str | pathlib.Path) -> int | None:
    try:
        return int(pathlib.Path(path).read_text().strip(), 0)
    except (OSError, ValueError):
        return None


def read_float(path: str | pathlib.Path) -> float | None:
    try:
        return float(pathlib.Path(path).read_text().strip())
    except (OSError, ValueError):
        return None


def read_first(paths, cast=None):
    """Return first readable value from an iterable of candidate paths."""
    for p in paths:
        v = read_float(p) if cast is float else read_int(p)
        if v is not None:
            return v
        if cast is str:
            try:
                t = pathlib.Path(p).read_text().strip()
                if t:
                    return t
            except OSError:
                pass
    return None


def hwmon_find(name_substr: str, label_substr: str | None = None) -> str | None:
    """Find a hwmon dir whose 'name' (and optional temp label) matches.

    Returns the hwmon directory path, e.g. /sys/class/hwmon/hwmon4.
    """
    base = pathlib.Path("/sys/class/hwmon")
    try:
        dirs = sorted(base.iterdir())
    except OSError:
        return None
    for d in dirs:
        try:
            nm = (d / "name").read_text().strip().lower()
        except OSError:
            continue
        if name_substr.lower() not in nm:
            continue
        if label_substr is None:
            return str(d)
        for tl in sorted(d.glob("temp*_label")):
            try:
                if label_substr.lower() in tl.read_text().strip().lower():
                    return str(d)
            except OSError:
                pass
    return None
