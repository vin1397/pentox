<div align="center">

# ▲ Pentox

**A from-scratch Linux gaming overlay.** No MangoHud, no GOverlay, no embedded
HUD engines — the overlay, metrics engine, frame-capture shims, watcher and
integrations are all written here.

Dark glass · lavender accents · JetBrains Mono · end4-pC inspired

</div>

---

## Why

Existing HUDs are monolithic: MangoHud injects a full ImGui overlay, GOverlay
is a GUI for it, and neither is scriptable or portable across compositors.
Pentox is a small, hackable Python + C project that:

- **captures frames itself** — a hand-written Vulkan layer (`vkQueuePresentKHR`
  hook) and a hand-written `LD_PRELOAD` shim (`eglSwapBuffers` / `glXSwapBuffers`)
- **renders the HUD itself** — GTK3 + gtk-layer-shell + Cairo, nothing else
- **works everywhere** — Wayland (layer-shell) with X11 fallback, any GPU
  vendor via plain sysfs (`amdgpu` / `nvidia`+NVML / `i915`), any CPU
- **plays nice** — no drivers touched, no compositor config edits, user-space
  only, uninstall with one command

## Install

```sh
git clone https://github.com/vin1397/pentox.git
cd pentox
./install.sh            # → ~/.local + systemd user watcher
```

Requirements (all packaged on every distro):
`python` ≥ 3.9, `python-cairo`, `python-gobject`, `gtk3`,
`gtk-layer-shell` (optional, X11 fallback otherwise),
`gcc`, `vulkan-headers`, `make`, and a notification daemon
(`notify-send`) for the whereabouts toasts.

Fish users: `./install.sh` works as-is (POSIX sh inside).

## Use

```sh
pentox doctor           # self-test: GPU/CPU metrics, layer-shell, capture
pentox run -- vkcube    # launch any game with capture + overlay
pentox run -- %command% # Steam launch options (optional)
pentox watch            # ambient watcher (auto-started by install.sh)
pentox chip --print     # one-line status for simple bars/scripts
pentox toggle           # hide/show the overlay
```

**Ambient by default (Vulkan):** install.sh registers a Vulkan *implicit
layer*, so every Vulkan application is frame-captured automatically — no
wrappers, no launch options, Steam included. Opt an app out with
`PENTOX_VK_DISABLE=1`. OpenGL apps are captured via the `LD_PRELOAD` shim
when launched through `pentox run`.

- The watcher notices game windows (Hyprland IPC first, process poll as
  fallback), spawns the overlay, shows a **whereabouts notification**
  ("top-right corner") and a **taskbar chip** while the session is live.
- `pentox toggle` hides/shows the overlay.
- Config: `~/.config/pentox/pentox.conf` — see `pentox.conf.example`.
  Every key is optional; unknown keys are ignored.

### Steam

Nothing to configure: Vulkan titles (the vast majority — DXVK/vkd3d ship
Vulkan) are captured by the implicit layer and shown by the watcher.
Prefer per-game control? Use `pentox run -- %command%` instead and set
`PENTOX_VK_DISABLE=1` globally.

## Architecture

```
pentox/
├── pentox/            Python package
│   ├── cli.py         run / watch / overlay / chip / toggle / doctor
│   ├── overlay.py     GTK3 + gtk-layer-shell HUD, drawn with Cairo
│   ├── chip.py        taskbar pill (layer-shell) + --print for bars
│   ├── watch.py       game watcher (Hyprland IPC + process fallback)
│   ├── metrics.py     sysfs/procfs metrics: AMD/NVIDIA/Intel, any CPU
│   ├── fpsreader.py   reader for the shared frame ring in /tmp
│   ├── config.py      tiny key=value config with safe defaults
│   └── theme.py       end4-pC glass palette + geometry
├── src/               hand-written C capture shims
│   ├── ring.h         shared ring buffer (shm, 64 B header + entries)
│   ├── pentox_gl.c    LD_PRELOAD shim: eglSwapBuffers / glXSwapBuffers
│   ├── pentox_vk.c    Vulkan layer: vkQueuePresentKHR hook
│   └── Pentox_layer.json
├── bin/pentox         launcher
├── install.sh         user-space installer (no root)
└── pentox-watch.service
```

Data flow: `game + shim → /tmp/pentox-run-<pid>.ring → fpsreader →
overlay render → layer-shell surface`, while `watch.py` orchestrates,
notifies and writes the chip state.

## Compatibility

| Component | Requirement |
|---|---|
| Compositor | any Wayland with wlr-layer-shell (Hyprland, sway, wlroots, KDE ≥ 5.27…) or X11 |
| GPU | AMD (amdgpu sysfs), NVIDIA (nvidia + NVML optional), Intel (i915/xe best-effort) |
| CPU | any Linux; temps via k10temp/coretemp/zenpower/acpitz, power via RAPL |
| API | Vulkan + OpenGL/ES games |

## License

MIT — see `LICENSE`.
