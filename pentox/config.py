"""Configuration: ~/.config/pentox/pentox.conf

Format is deliberately tiny: `key = value` lines, `#` comments, every key
optional. Unknown keys are ignored (forward compatible). All defaults live
here so a missing file still produces a fully working overlay.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from . import theme
from .util import config_file, hex_to_rgb


@dataclass
class PentoxConfig:
    # window
    position: str = "top-right"       # top-right|top-left|bottom-right|bottom-left
    width: int = theme.DEFAULT_WIDTH
    margin_x: int = theme.DEFAULT_MARGIN_X
    margin_y: int = theme.DEFAULT_MARGIN_Y
    radius: int = theme.DEFAULT_RADIUS
    bg: str = theme.COLORS["bg"]
    bg_alpha: float = theme.COLORS["bg_alpha"]
    border: str = theme.COLORS["border"]
    border_alpha: float = theme.COLORS["border_alpha"]

    # text
    font: str = theme.DEFAULT_FONT
    font_size: float = theme.DEFAULT_FONT_SIZE
    text: str = theme.COLORS["text"]
    muted: str = theme.COLORS["muted"]
    accent: str = theme.COLORS["accent"]
    graph: str = theme.COLORS["graph"]
    graph_fill: str = theme.COLORS["graph_fill"]

    # behavior
    update_ms: int = 120
    graph_seconds: float = 9.0
    hide_on_esc: bool = True
    chip_enabled: bool = True
    notify_enabled: bool = True
    watch_interval_s: float = 1.0

    # metrics
    gpu_pci: str = "auto"             # e.g. "0000:05:00.0" to pin a card
    show_junction: bool = True
    show_fan: bool = True

    def rgba(self, key: str, alpha_override: float | None = None):
        r, g, b = hex_to_rgb(getattr(self, key))
        a = alpha_override if alpha_override is not None else 1.0
        return (r, g, b, a)

    def load_path(self, path) -> "PentoxConfig":
        try:
            text = open(path, encoding="utf-8", errors="replace").read()
        except OSError:
            return self
        for raw in text.splitlines():
            line = raw.split("#", 1)[0].strip()
            if not line or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k, v = k.strip().lower(), v.strip().strip('"').strip("'")
            if not v:
                continue
            if hasattr(self, k):
                cur = getattr(self, k)
                try:
                    if isinstance(cur, bool):
                        setattr(self, k, v.lower() in ("1", "true", "yes", "on"))
                    elif isinstance(cur, int):
                        setattr(self, k, int(float(v)))
                    elif isinstance(cur, float):
                        setattr(self, k, float(v))
                    else:
                        setattr(self, k, v)
                except ValueError:
                    pass
        return self


def load() -> PentoxConfig:
    cfg = PentoxConfig()
    p = config_file()
    if p.exists():
        cfg.load_path(p)
    # env overrides (used by `pentox run` internally)
    if os.environ.get("PENTOX_POSITION"):
        cfg.position = os.environ["PENTOX_POSITION"]
    return cfg
