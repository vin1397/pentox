<div align="center">

# ▲ Pentox

**A from-scratch Linux gaming overlay.**

> 🚧 **Pentox is currently under active development.**  
> Features, APIs, architecture, and compatibility may change frequently.  
> It is not yet considered production-ready.

No MangoHud, no GOverlay, no embedded HUD engines — the overlay, metrics
engine, frame-capture shims, watcher and integrations are all written here.

**Dark glass · Lavender accents · JetBrains Mono · end4-pC inspired**

</div>

---

## 🚧 Development Status

Pentox is an **early-stage project under active development**.

The core architecture is being built from scratch, including the overlay,
metrics engine, frame-capture layers, game watcher and desktop integrations.

Things may currently be:

- 🛠️ Incomplete
- 🐛 Experimental
- 🔄 Subject to breaking changes
- 🎮 Limited to certain games or APIs
- 🖥️ Dependent on compositor/GPU configuration

**Do not consider the current build production-ready.**

Testing, feedback, bug reports and contributions are welcome.

---

## Why

Existing HUDs are often tightly coupled to their rendering engines.

MangoHud provides a powerful gaming overlay, while GOverlay provides a GUI
for configuring it. Pentox takes a different approach: the overlay,
metrics engine, frame-capture layers and integrations are built directly
into the project.

Pentox aims to be a small, hackable Python + C project that:

- **Captures frames itself** — a hand-written Vulkan layer using
  `vkQueuePresentKHR` and a hand-written `LD_PRELOAD` shim using
  `eglSwapBuffers` / `glXSwapBuffers`
- **Renders the HUD itself** — GTK3 + gtk-layer-shell + Cairo
- **Works across environments** — Wayland with X11 fallback
- **Supports multiple GPU vendors** — AMD, NVIDIA and Intel
- **Requires no driver modifications**
- **Requires no compositor configuration edits**
- **Runs in user space**
- **Can be removed without leaving system modifications behind**

---

## Features

### 🎮 Gaming Overlay

- FPS
- Frame timing
- GPU statistics
- CPU statistics
- RAM / VRAM usage
- Temperature monitoring
- GPU clocks
- CPU clocks
- GPU power information
- Game detection
- Game session state

### 🖥️ Desktop Integration

- Wayland layer-shell support
- X11 fallback
- Hyprland integration
- Game watcher
- Taskbar/status chip
- Desktop notifications
- Global overlay toggle

### 🎨 UI

- Dark glass aesthetic
- Lavender accent palette
- JetBrains Mono
- end4-pC-inspired styling
- Cairo-rendered interface
- Configurable geometry and appearance

---

## Install

> ⚠️ Installation and compatibility are currently experimental.

```sh
git clone https://github.com/vin1397/pentox.git
cd pentox
./install.sh
```

The installer installs Pentox into the user's local environment and registers
the user-level watcher.

### Requirements

- Python ≥ 3.9
- Python Cairo
- PyGObject
- GTK3
- gtk-layer-shell *(optional; X11 fallback available)*
- GCC
- Vulkan headers
- Make
- `notify-send`

Fish users:

```text
./install.sh
```

works as-is because the installer uses POSIX `sh`.

---

## Usage

### System self-test

```sh
pentox doctor
```

Runs diagnostics for:

- GPU metrics
- CPU metrics
- Layer-shell support
- Frame capture
- Runtime environment

### Launch an application with Pentox

```sh
pentox run -- vkcube
```

Or:

```sh
pentox run -- <application>
```

### Steam

```text
pentox run -- %command%
```

### Start the watcher

```sh
pentox watch
```

The watcher is normally started automatically by the installer.

### Toggle the overlay

```sh
pentox toggle
```

### Print status

```sh
pentox chip --print
```

This can be used by status bars and other scripts.

---

## Ambient Vulkan Capture

Pentox currently registers a Vulkan **implicit layer**.

This allows Vulkan applications to be frame-captured automatically without
requiring a wrapper command.

For example, Vulkan games launched normally can be detected by the watcher.

To disable Pentox Vulkan capture for an application:

```sh
PENTOX_VK_DISABLE=1
```

---

## OpenGL Capture

OpenGL applications can be captured through the `LD_PRELOAD` shim.

Launch an OpenGL application with:

```sh
pentox run -- <application>
```

Pentox currently hooks:

```text
eglSwapBuffers
glXSwapBuffers
```

---

## Steam

Vulkan titles can currently be captured through the Vulkan implicit layer.

For per-game control, use:

```text
pentox run -- %command%
```

> ⚠️ Steam and game compatibility are still being tested.

Different games, engines, graphics APIs, Proton versions and drivers may
behave differently while Pentox is under development.

---

## How It Works

```text
                    ┌─────────────────┐
                    │      Game       │
                    └────────┬────────┘
                             │
                   ┌─────────┴─────────┐
                   │                   │
              Vulkan Layer        OpenGL Shim
                   │                   │
                   └─────────┬─────────┘
                             │
                             ▼
                  /tmp/pentox-run-<pid>.ring
                             │
                             ▼
                       fpsreader
                             │
                             ▼
                    ┌────────────────┐
                    │     Overlay    │
                    │ GTK3 + Cairo   │
                    └───────┬────────┘
                            │
                            ▼
                     Layer-shell HUD
```

The watcher operates alongside the capture system:

```text
watch.py
   │
   ├── Game detection
   ├── Process monitoring
   ├── Hyprland IPC
   ├── Overlay spawning
   ├── Notifications
   └── Taskbar chip
```

---

## Architecture

```text
pentox/
├── pentox/
│   ├── cli.py
│   ├── overlay.py
│   ├── chip.py
│   ├── watch.py
│   ├── metrics.py
│   ├── fpsreader.py
│   ├── config.py
│   └── theme.py
│
├── src/
│   ├── ring.h
│   ├── pentox_gl.c
│   ├── pentox_vk.c
│   └── Pentox_layer.json
│
├── bin/
│   └── pentox
│
├── install.sh
└── pentox-watch.service
```

### Components

| Component | Purpose |
|---|---|
| `cli.py` | Command-line interface |
| `overlay.py` | GTK3 + Cairo HUD |
| `chip.py` | Taskbar/status chip |
| `watch.py` | Game/session detection |
| `metrics.py` | GPU/CPU system metrics |
| `fpsreader.py` | Frame-ring reader |
| `config.py` | Configuration handling |
| `theme.py` | UI theme and geometry |
| `pentox_vk.c` | Vulkan capture layer |
| `pentox_gl.c` | OpenGL capture shim |
| `ring.h` | Shared frame-ring structure |

---

## Configuration

Pentox uses:

```text
~/.config/pentox/pentox.conf
```

An example configuration is provided as:

```text
pentox.conf.example
```

Configuration uses a simple `key=value` format.

All configuration keys are optional.

Unknown keys are ignored.

> ⚠️ Configuration options may change while the project is under development.

---

## Compatibility

| Component | Current Target |
|---|---|
| Wayland | ✅ |
| X11 | ✅ |
| Hyprland | ✅ |
| wlroots | ✅ |
| GTK3 | ✅ |
| Vulkan | ✅ |
| OpenGL / OpenGL ES | ✅ |
| AMD | ✅ |
| NVIDIA | ✅ |
| Intel | ✅ |

### GPU

Pentox currently targets:

- AMD `amdgpu`
- NVIDIA
- Intel `i915` / `xe`

Metrics are collected through standard Linux interfaces such as:

```text
/sys
/proc
```

NVIDIA NVML support is optional.

### CPU

Pentox supports Linux CPUs through available kernel interfaces and sensors.

Potential sources include:

```text
k10temp
coretemp
zenpower
acpitz
RAPL
```

---

## Development Roadmap

Pentox is actively being developed.

### Capture

- [✅] Stabilize Vulkan capture
- [✅] Stabilize OpenGL capture
- [✅] Improve frame timing accuracy
- [✅] Improve multi-process handling
- [✅] Improve Proton compatibility

### Metrics

- [✅] More AMD metrics
- [✅] More NVIDIA metrics
- [✅] More Intel metrics
- [✅] Additional CPU telemetry
- [✅] Power monitoring improvements
- [✅] Better temperature detection

### UI

- [ ] More layout options
- [ ] Better customization
- [ ] Configurable widgets
- [ ] Theme editor
- [ ] More animation options
- [ ] Better scaling for different displays

### Integration

- [ ] Improved Steam integration
- [ ] More compositor support
- [✅] Better game detection
- [ ] More status-bar integrations
- [ ] Desktop settings integration

### Stability

- [ ] More hardware testing
- [✅] More compositor testing
- [✅] Performance optimization
- [ ] Error handling improvements
- [ ] Packaging
- [ ] Stable release

---

## Project Philosophy

Pentox is designed around a few simple principles:

### No External HUD Engine

The HUD is rendered by Pentox itself.

### No Driver Modifications

Pentox operates entirely in user space.

### No Compositor Configuration

The overlay should work without modifying compositor configuration.

### Hackable

The project is intentionally split between Python and C so individual
components can be inspected, modified and replaced easily.

### Portable

Where possible, Pentox relies on standard Linux interfaces rather than
vendor-specific APIs.

---

## Contributing

Pentox is still experimental and actively evolving.

Contributions are welcome.

You can help with:

- 🐛 Bug reports
- 🎮 Game compatibility testing
- 🖥️ Compositor testing
- 📊 Metrics support
- 🎨 UI improvements
- ⚙️ Performance optimization
- 🔧 Code contributions
- 📖 Documentation

Before submitting a large change, opening an issue to discuss the approach
is recommended.

---

## Known Limitations

Pentox is **not production-ready**.

Current limitations may include:

- Some games may not be detected correctly.
- Some Vulkan applications may not expose expected information.
- OpenGL capture may vary between applications.
- GPU metrics depend on available kernel/vendor interfaces.
- Compositor behavior can vary.
- Proton compatibility is still being tested.
- Configuration and CLI interfaces may change.
- Performance and memory usage are still being optimized.

---

## Uninstall

Pentox is designed to be removable without modifying system drivers.

Use the uninstall functionality provided by the project:

```sh
./install.sh --uninstall
```

> Check the current installer options before running this command, as the
> uninstall interface may change during development.

---

## License

MIT License

See [`LICENSE`](LICENSE) for the full license text.

---

<div align="center">

**▲ Pentox**

*Built from scratch for Linux gaming.*

🚧 **Under active development**

</div>