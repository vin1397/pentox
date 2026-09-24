"""Metrics engine — pure sysfs/procfs probing, no external libraries.

Portable by design: AMD (amdgpu), NVIDIA (nvidia + optional NVML ctypes),
Intel (i915/xe best-effort), any CPU via /proc/stat + hwmon, RAM via
/proc/meminfo. Every probe returns None on unsupported systems and the
overlay simply hides that line, so the same code runs on any Linux laptop
or desktop.
"""

from __future__ import annotations

import ctypes
import ctypes.util
import glob
import os
import pathlib
import re
import time

from .util import hwmon_find, read_float, read_int, read_first

SYS = pathlib.Path("/sys")
PROC = pathlib.Path("/proc")


class GpuInfo:
    def __init__(self, pci: str | None, card: str | None, hwmon: str | None,
                 vendor: str, name: str, kind: str):
        self.pci = pci or ""
        self.card = card or ""
        self.hwmon = hwmon
        self.vendor = vendor
        self.name = name
        self.kind = kind          # "amdgpu" | "nvidia" | "intel" | "unknown"

    @property
    def label(self) -> str:
        return self.name or self.vendor.upper() + " GPU"


def _hwmon_for_card(card_path: pathlib.Path) -> str | None:
    try:
        hm = sorted((card_path / "device" / "hwmon").glob("hwmon*"))
        return str(hm[0]) if hm else None
    except OSError:
        return None


def _gpu_name(pci_dev: pathlib.Path, kind: str) -> str:
    # amdgpu exposes product_name on modern kernels; others fall back to PCI ids
    for cand in ("product_name", "product"):
        try:
            v = (pci_dev / cand).read_text().strip()
            if v:
                return v
        except OSError:
            pass
    if kind == "nvidia":
        info = pathlib.Path("/proc/driver/nvidia/gpus")
        try:
            for d in info.iterdir():
                try:
                    txt = (d / "information").read_text()
                    m = re.search(r"Model:\s*(.+)", txt)
                    if m:
                        return m.group(1).strip()
                except OSError:
                    continue
        except OSError:
            pass
    vendor_ids = {"0x1002": "AMD", "0x10de": "NVIDIA", "0x8086": "Intel"}
    try:
        ven = (pci_dev / "vendor").read_text().strip().lower()
        return vendor_ids.get(ven, "GPU")
    except OSError:
        return "GPU"


def detect_gpu(preferred_pci: str = "auto") -> GpuInfo:
    """Pick the primary discrete/APU GPU, preferring amdgpu > nvidia > intel."""
    candidates: list[GpuInfo] = []
    for card in sorted(glob.glob("/sys/class/drm/card[0-9]*")):
        cp = pathlib.Path(card)
        dev = cp / "device"
        try:
            ven = (dev / "vendor").read_text().strip().lower()
        except OSError:
            continue
        kind = {"0x1002": "amdgpu", "0x10de": "nvidia", "0x8086": "intel"}.get(ven, "unknown")
        if kind == "unknown":
            continue
        pci = dev.name
        candidates.append(GpuInfo(pci, cp.name, _hwmon_for_card(cp), kind.split("0")[0],
                                  _gpu_name(dev, kind), kind))
    order = {"amdgpu": 0, "nvidia": 1, "intel": 2}
    candidates.sort(key=lambda g: (order.get(g.kind, 9), g.pci))
    if preferred_pci and preferred_pci != "auto":
        for g in candidates:
            if g.pci == preferred_pci:
                return g
    if candidates:
        return candidates[0]
    return GpuInfo(None, None, None, "unknown", "GPU", "unknown")


def _hwmon_temp(hm: str | None, labels=("edge", "junction", "gpu", None)) -> dict:
    out = {}
    if not hm:
        return out
    for idx in range(1, 6):
        lab_p = pathlib.Path(hm) / f"temp{idx}_label"
        in_p = pathlib.Path(hm) / f"temp{idx}_input"
        label = None
        try:
            label = lab_p.read_text().strip().lower()
        except OSError:
            pass
        v = read_float(in_p)
        if v is None:
            continue
        v = v / 1000.0
        if label and ("junction" in label or "hotspot" in label):
            out["junction"] = v
        elif label and ("edge" in label or label == "gpu" or "composite" in label):
            out.setdefault("edge", v)
        else:
            out.setdefault("other", v)
    if "edge" not in out and "other" in out:
        out["edge"] = out.pop("other")
    return out


def gpu_sample(g: GpuInfo) -> dict:
    s = {"busy": None, "mem_used_kib": None, "mem_total_kib": None,
         "temp": None, "junction": None, "fan_rpm": None, "power_w": None,
         "core_mhz": None, "mem_mhz": None}
    if g.kind == "amdgpu":
        base = SYS / "class" / "drm" / g.card / "device"
        s["busy"] = read_int(base / "gpu_busy_percent")
        s["mem_used_kib"] = read_int(base / "mem_info_vram_used")
        s["mem_total_kib"] = read_int(base / "mem_info_vram_total")
        temps = _hwmon_temp(g.hwmon)
        s["temp"] = temps.get("edge")
        s["junction"] = temps.get("junction")
        if g.hwmon:
            s["fan_rpm"] = read_float(os.path.join(g.hwmon, "fan1_input"))
            s["power_w"] = read_first([os.path.join(g.hwmon, "power1_average"),
                                       os.path.join(g.hwmon, "power1_input")])
            s["core_mhz"] = read_first([os.path.join(g.hwmon, "freq1_input")])
            s["mem_mhz"] = read_first([os.path.join(g.hwmon, "freq2_input")])
            if s["core_mhz"]:
                s["core_mhz"] /= 1_000_000.0
            if s["mem_mhz"]:
                s["mem_mhz"] /= 1_000_000.0
            if s["power_w"]:
                s["power_w"] /= 1_000_000.0
    elif g.kind == "nvidia":
        nv = _nvidia()
        if nv:
            s.update(nv.sample())
    else:  # intel / unknown — best effort
        base = SYS / "class" / "drm" / g.card
        for cand in ("gt/gt0/rps_cur_freq_mhz", "gt/gt0/cur_freq_mhz"):
            s["core_mhz"] = read_int(base / cand)
            if s["core_mhz"]:
                break
    return s


# ---------------------------------------------------------------- NVIDIA ---

_nvml = None


def _nvidia():
    """Lazy ctypes NVML loader — no pip dependency, lib comes with the driver."""
    global _nvml
    if _nvml is False:
        return None
    if _nvml is None:
        lib = ctypes.util.find_library("nvidia-ml") or "libnvidia-ml.so.1"
        try:
            _nvml = ctypes.CDLL(lib)
            if _nvml.nvmlInit_v2() != 0:
                _nvml = False
                return None
        except OSError:
            _nvml = False
            return None
    return _nvml


# ------------------------------------------------------------------- CPU ---

class CpuSampler:
    def __init__(self):
        self._prev = None
        self.name = "CPU"
        try:
            for line in (PROC / "cpuinfo").read_text().splitlines():
                if line.lower().startswith("model name"):
                    self.name = line.split(":", 1)[1].strip()
                    break
        except OSError:
            pass
        self.temp_hwmon = hwmon_find("k10temp") or hwmon_find("coretemp") \
            or hwmon_find("cpu_thermal") or hwmon_find("zenpower") \
            or hwmon_find("acpitz", None)
        # first sensor with temp1_input
        if self.temp_hwmon and not read_float(os.path.join(self.temp_hwmon, "temp1_input")):
            alt = hwmon_find("it86") or hwmon_find("nct")
            if alt:
                self.temp_hwmon = alt
        self.rapl = None
        for rz in sorted(glob.glob("/sys/class/powercap/*rapl*/name")):
            try:
                nm = pathlib.Path(rz).read_text().strip().lower()
            except OSError:
                continue
            if nm.startswith("core") or "package" in nm or nm.startswith("psys"):
                self.rapl = pathlib.Path(rz).parent / "energy_uj"
                break

    def busy_percent(self) -> float | None:
        try:
            line = (PROC / "stat").read_text().splitlines()[0]
        except (OSError, IndexError):
            return None
        vals = [int(x) for x in line.split()[1:]]
        idle = vals[3] + (vals[4] if len(vals) > 4 else 0)
        total = sum(vals[:8]) if len(vals) >= 8 else sum(vals)
        if self._prev is None:
            self._prev = (idle, total)
            return None
        pi, pt = self._prev
        dt, di = total - pt, idle - pi
        self._prev = (idle, total)
        if dt <= 0:
            return None
        return max(0.0, min(100.0, 100.0 * (1.0 - di / dt)))

    def temp_c(self) -> float | None:
        if not self.temp_hwmon:
            return None
        v = read_float(os.path.join(self.temp_hwmon, "temp1_input"))
        return v / 1000.0 if v is not None else None

    def clock_mhz(self) -> float | None:
        # average current frequency across cores
        vals = []
        try:
            for line in (PROC / "cpuinfo").read_text().splitlines():
                if line.lower().startswith("cpu mhz"):
                    vals.append(float(line.split(":", 1)[1]))
                    if len(vals) >= 32:
                        break
        except (OSError, ValueError):
            pass
        if vals:
            return sum(vals) / len(vals)
        # cpufreq fallback
        f = read_first(sorted(glob.glob(
            "/sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq")))
        return f / 1000.0 if f else None

    def power_w(self) -> float | None:
        if not self.rapl:
            return None
        e = read_float(self.rapl)
        if e is None:
            return None
        now = time.monotonic()
        if getattr(self, "_pe", None) is None:
            self._pe, self._pt = e, now
            return None
        de = e - self._pe
        dt = now - self._pt
        self._pe, self._pt = e, now
        if de < 0 or dt <= 0:      # counter wrap / resume
            return None
        return de / dt / 1e6


# ------------------------------------------------------------------ MEM ---

def mem_sample() -> dict:
    out = {}
    try:
        txt = (PROC / "meminfo").read_text()
    except OSError:
        return out
    want = {"MemTotal": "total_kib", "MemAvailable": "avail_kib"}
    for line in txt.splitlines():
        parts = line.split(":", 1)
        if parts[0] in want:
            out[want[parts[0]]] = int(parts[1].strip().split()[0])
    if "total_kib" in out and "avail_kib" in out:
        out["used_kib"] = out["total_kib"] - out["avail_kib"]
        out["pct"] = 100.0 * out["used_kib"] / out["total_kib"]
    return out


def swap_sample() -> dict:
    total = used = None
    try:
        for line in (PROC / "meminfo").read_text().splitlines():
            if line.startswith("SwapTotal"):
                total = int(line.split()[1])
            elif line.startswith("SwapFree"):
                used = total - int(line.split()[1])
        if total:                      # zero swap = present but disabled
            return {"total_kib": total, "used_kib": max(0, used or 0),
                    "pct": 100.0 * max(0, used or 0) / total}
    except (OSError, ValueError, IndexError):
        pass
    return {}
