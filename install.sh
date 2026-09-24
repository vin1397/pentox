#!/bin/sh
# Pentox user installer — no root required.
#   ./install.sh             install to ~/.local + enable watcher service
#   ./install.sh --no-service  install without the background watcher
#   ./install.sh --uninstall   remove everything
set -e
PREFIX="${HOME}/.local"
SRC="$(cd "$(dirname "$0")" && pwd)"

if [ "$1" = "--uninstall" ]; then
  systemctl --user disable --now pentox-watch.service 2>/dev/null || true
  rm -f "$HOME/.config/systemd/user/pentox-watch.service"
  rm -f "$PREFIX/bin/pentox"
  rm -rf "$PREFIX/lib/pentox"
  rm -f "$HOME/.local/share/vulkan/implicit_layer.d/Pentox_layer.json"
  rm -f "$HOME/.local/share/applications/io.github.pentox.desktop"
  rm -f "$HOME/.local/share/icons/hicolor/scalable/apps/pentox.svg"
  rm -f "$HOME/.cache/pentox-gui.css"
  update-desktop-database "$HOME/.local/share/applications" 2>/dev/null || true
  gtk-update-icon-cache -f -t "$HOME/.local/share/icons/hicolor" 2>/dev/null || true
  systemctl --user daemon-reload 2>/dev/null || true
  echo "Pentox removed."
  exit 0
fi

echo "==> building capture shims"
make -C "$SRC" >/dev/null

echo "==> installing python package -> $PREFIX/lib/pentox"
rm -rf "$PREFIX/lib/pentox"
mkdir -p "$PREFIX/lib/pentox" "$PREFIX/bin"
cp -r "$SRC/pentox" "$PREFIX/lib/pentox/pentox"
mkdir -p "$PREFIX/lib/pentox/src"
cp "$SRC"/src/*.so "$PREFIX/lib/pentox/src/"
cp "$SRC/src/Pentox_layer.json" "$PREFIX/lib/pentox/src/"
find "$PREFIX/lib/pentox" -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true

echo "==> installing launcher -> $PREFIX/bin/pentox"
install -m 0755 "$SRC/bin/pentox" "$PREFIX/bin/pentox"

echo "==> installing desktop entry + icon (application search: 'pentox')"
APPS="$HOME/.local/share/applications"
ICONDIR="$HOME/.local/share/icons/hicolor/scalable/apps"
mkdir -p "$APPS" "$ICONDIR"
install -m 0644 "$SRC/data/io.github.pentox.desktop" "$APPS/io.github.pentox.desktop"
install -m 0644 "$SRC/data/icons/hicolor/scalable/apps/pentox.svg" "$ICONDIR/pentox.svg"
update-desktop-database "$APPS" 2>/dev/null || true
gtk-update-icon-cache -f -t "$HOME/.local/share/icons/hicolor" 2>/dev/null || true

echo "==> registering Vulkan implicit layer (auto-capture for every Vulkan app)"
VLDIR="$HOME/.local/share/vulkan/implicit_layer.d"
mkdir -p "$VLDIR"
python3 - "$PREFIX/lib/pentox/src/libpentoxvk.so" "$VLDIR/Pentox_layer.json" <<'PYEOF'
import json, sys
lib, out = sys.argv[1], sys.argv[2]
manifest = {
    "file_format_version": "1.2.0",
    "layer": {
        "name": "VK_LAYER_PENTOX_capture",
        "type": "GLOBAL",
        "library_path": lib,
        "api_version": "1.3.0",
        "implementation_version": "1",
        "description": "Pentox frame-capture layer (self-written)",
        "disable_environment": {"PENTOX_VK_DISABLE": "1"},
    },
}
open(out, "w").write(json.dumps(manifest, indent=2) + "\n")
PYEOF

if [ "$1" != "--no-service" ]; then
  echo "==> installing watcher service (game auto-detect, notification, taskbar chip)"
  if command -v systemctl >/dev/null 2>&1 && \
     systemctl --user is-system-running 2>/dev/null | grep -qE '^(running|degraded)$'; then
    mkdir -p "$HOME/.config/systemd/user"
    install -m 0644 "$SRC/pentox-watch.service" "$HOME/.config/systemd/user/pentox-watch.service"
    systemctl --user daemon-reload
    systemctl --user enable --now pentox-watch.service
  else
    echo "    systemd user session not usable — skipping service."
    echo "    The watcher will still start on demand from the Pentox app."
  fi
fi

case ":$PATH:" in
  *":$PREFIX/bin:"*) ;;
  *) echo "NOTE: add $PREFIX/bin to PATH (fish: fish_add_path ~/.local/bin)" ;;
esac

echo "==> done. Try:  pentox gui     pentox doctor     pentox run -- vkcube"
