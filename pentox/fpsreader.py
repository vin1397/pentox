"""Frame-timestamp ring reader.

The ring is produced by Pentox's own shims (src/ring.h) in a POSIX shared
memory file (/tmp/pentox-run-<pid>.ring). Layout (little endian):

  header 64 B : magic u64, entry_size u32, capacity u32, write_index u64, pad
  entries     : capacity * 16 B of { t_ns u64, pid u32, api u32 }

Writers advance write_index with atomics; each write lands at
(index++) % capacity. Readers take a snapshot and scan backwards.
"""

from __future__ import annotations

import ctypes
import os
import pathlib
import time

from . import META_SUFFIX, RING_PREFIX
from .util import proc_alive

MAGIC = 0x50454E5458583031  # "PENTXX01"
ENTRY_SIZE = 16
CAPACITY = 4096
HEADER_SIZE = 64

API_VULKAN = 1
API_OPENGL = 2
API_NAME = {API_VULKAN: "Vulkan", API_OPENGL: "OpenGL"}


class Entry(ctypes.LittleEndianStructure):
    _fields_ = [("t_ns", ctypes.c_uint64), ("pid", ctypes.c_uint32), ("api", ctypes.c_uint32)]


class Ring:
    def __init__(self, path: str | pathlib.Path):
        self.path = pathlib.Path(path)
        self._mmap = None
        self._hdr = None
        self._entries_off = HEADER_SIZE

    def open(self) -> bool:
        try:
            fd = os.open(self.path, os.O_RDONLY)
        except OSError:
            return False
        try:
            import mmap
            self._mmap = mmap.mmap(fd, HEADER_SIZE + CAPACITY * ENTRY_SIZE, prot=mmap.PROT_READ)
        except (OSError, ValueError):
            os.close(fd)
            return False
        finally:
            os.close(fd)
        magic, entsz, cap = self._read_header()
        if magic != MAGIC or entsz != ENTRY_SIZE or cap != CAPACITY:
            self.close()
            return False
        return True

    def _read_header(self):
        h = self._mmap[0:HEADER_SIZE]
        magic = int.from_bytes(h[0:8], "little")
        entsz = int.from_bytes(h[8:12], "little")
        cap = int.from_bytes(h[12:16], "little")
        return magic, entsz, cap

    def close(self):
        if self._mmap:
            self._mmap.close()
            self._mmap = None

    def sample(self, window_s: float = 1.0):
        """Return (fps, frame_times_ns_desc_list, api, last_pid)."""
        if not self._mmap:
            return 0.0, [], 0, 0
        widx = int.from_bytes(self._mmap[16:24], "little")
        now = time.monotonic_ns()
        cutoff = now - int(window_s * 1e9)
        frames, apis, pids = [], set(), set()
        n = CAPACITY
        start = max(0, widx - n)
        for i in range(widx - 1, start - 1, -1):
            off = self._entries_off + (i % CAPACITY) * ENTRY_SIZE
            e = Entry.from_buffer_copy(self._mmap[off:off + ENTRY_SIZE])
            t_ns, pid, api = e.t_ns, e.pid, e.api
            if t_ns == 0 or t_ns < cutoff:
                break  # older frames; ring is chronological
            frames.append(t_ns)
            if api:
                apis.add(api)
            if pid:
                pids.add(pid)
        fps = (len(frames) / window_s) if window_s > 0 else 0.0
        api = apis.pop() if len(apis) == 1 else (apis.pop() if apis else 0)
        pid = max(pids) if pids else 0
        return fps, frames, api, pid

    def frametimes_ms(self, limit: int = 240):
        fps, frames, api, pid = self.sample(window_s=60.0)
        frames = sorted(frames)               # chronological
        times = [frames[i] / 1e6 for i in range(len(frames))]
        diffs = [times[i + 1] - times[i] for i in range(1, len(times) - 1)]
        return diffs[-limit:], api, pid


def discover_rings(prefix: str = None):
    """All live ring files created by Pentox shims."""
    prefix = prefix or RING_PREFIX
    out = []
    for p in pathlib.Path("/tmp").glob(f"{prefix}*.ring"):
        try:
            pid = int(p.stem[len(prefix):])
        except ValueError:
            continue
        if not proc_alive(pid):
            continue            # stale ring from a dead process
        meta = p.with_suffix(p.suffix + META_SUFFIX)
        out.append((p, meta))
    return sorted(out, key=lambda x: x[0].stat().st_mtime if x[0].exists() else 0)


def read_meta(meta_path) -> dict:
    d = {}
    try:
        for line in pathlib.Path(meta_path).read_text().splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                d[k.strip()] = v.strip()
    except OSError:
        pass
    return d
