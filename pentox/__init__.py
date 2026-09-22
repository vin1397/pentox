"""Pentox — a from-scratch Linux gaming overlay.

No prebuilt HUD engines are used: the overlay, metrics engine, frame
sampler (self-written Vulkan layer + GL preload shim), watcher and
integrations are all implemented in this repository (see README.md).
"""

__version__ = "0.1.0"
APP_NAME = "Pentox"
APP_ID = "io.github.pentox"

RUNTIME_DIR = "/tmp"                      # rings + meta files live here
RING_PREFIX = "pentox-run-"               # /tmp/pentox-run-<pid>.ring
META_SUFFIX = ".meta"

STATE_DIR_NAME = "pentox"                 # under $XDG_STATE_HOME
CONFIG_DIR_NAME = "pentox"                # under $XDG_CONFIG_HOME
CONFIG_FILE_NAME = "pentox.conf"
