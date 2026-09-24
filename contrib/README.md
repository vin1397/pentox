# contrib/

Optional integration snippets that are **not** installed by `install.sh`.

## quickshell/ — Status bar widget

`PentoxChip.qml` is a small widget for [quickshell](https://quickshell.outfoxxed.me)
that mirrors the built-in layer-shell chip: it reads
`~/.local/state/pentox/chip.state` and shows a lavender pill while a game
session is active, with the game name and live FPS.

Drop it into your quickshell config:

```qml
import "quickshell"

PentoxChip { }
```

## systemd/ — On-demand watcher units

`pentox-watch.path` starts the watcher the first time a frame ring appears in
`/tmp` — useful together with the Vulkan implicit layer, which creates rings
even for games launched without `pentox run`. Copy both units to
`~/.config/systemd/user/` and enable the `.path` unit instead of the service:

```sh
cp contrib/systemd/* ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now pentox-watch.path
```
