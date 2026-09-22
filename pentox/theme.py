"""Theme: geometry + end4-pC dark-glass palette (lavender on deep purple)."""

# Geometry
DEFAULT_WIDTH = 380
DEFAULT_MARGIN_X = 16
DEFAULT_MARGIN_Y = 16
DEFAULT_RADIUS = 16

# Palette — hex RRGGBB + float alpha, tuned to end-4/pC glass
COLORS = {
    "bg":            "0B0812",
    "bg_alpha":      0.78,
    "border":        "B9A3FF",
    "border_alpha":  0.16,
    "text":          "EDE8FF",
    "muted":         "9C8CD4",
    "accent":        "B9A3FF",   # primary lavender
    "accent_dim":    "6E5FB8",
    "ok":            "A6E3A1",
    "warn":          "F9E2AF",
    "hot":           "F38BA8",
    "graph":         "C7B8FF",
    "graph_fill":    "8A6FE8",
    "bar_track":     "2A2138",
}

DEFAULT_FONT = "JetBrainsMono Nerd Font"
DEFAULT_FONT_SIZE = 11.0        # cairo/Pango base size (pt)
HERO_SCALE = 3.1                # FPS hero number = base * this
SECTION_SCALE = 1.45            # GPU / CPU headers

BAR_HEIGHT = 7
BAR_WIDTH_FRAC = 0.92           # fraction of inner width
ROW_PAD = 6
SECTION_PAD = 14
INNER_PAD = 18
