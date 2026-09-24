"""Frame-ring reader against synthetic rings written exactly like the C shims."""

import mmap
import os
import struct
import time

import pytest

from pentox import fpsreader as fr


def write_ring(path, stamps_ns, api=fr.API_VULKAN, pid=os.getpid()):
    size = fr.HEADER_SIZE + fr.CAPACITY * fr.ENTRY_SIZE
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    os.ftruncate(fd, size)
    mm = mmap.mmap(fd, size)
    mm[0:8] = struct.pack("<Q", fr.MAGIC)
    mm[8:12] = struct.pack("<I", fr.ENTRY_SIZE)
    mm[12:16] = struct.pack("<I", fr.CAPACITY)
    mm[16:24] = struct.pack("<Q", len(stamps_ns))
    for i, t in enumerate(stamps_ns):
        off = fr.HEADER_SIZE + i * fr.ENTRY_SIZE
        mm[off:off + 16] = struct.pack("<QII", t, pid, api)
    mm.flush()
    mm.close()
    os.close(fd)
    return path


def recent(n=300, step_ms=16.6):
    now = time.monotonic_ns()
    step = int(step_ms * 1e6)
    return [now - (n - i) * step for i in range(n)]


def test_sample_fps_and_api(tmp_path):
    p = write_ring(tmp_path / "pentox-run-123.ring", recent())
    r = fr.Ring(p)
    assert r.open()
    fps, frames, api, pid = r.sample(window_s=1.0)
    assert 40 < fps < 80
    assert api == fr.API_VULKAN
    assert pid == os.getpid()


def test_sample_rejects_bad_magic(tmp_path):
    p = write_ring(tmp_path / "pentox-run-124.ring", recent())
    data = bytearray(p.read_bytes())
    data[0:8] = b"XXXXXXXX"
    p.write_bytes(bytes(data))
    r = fr.Ring(p)
    assert not r.open()


def test_sample_empty_ring(tmp_path):
    p = write_ring(tmp_path / "pentox-run-125.ring", [])
    r = fr.Ring(p)
    assert r.open()
    fps, frames, api, pid = r.sample(window_s=1.0)
    assert fps == 0.0 and frames == []


def test_frametimes_are_inter_frame_gaps(tmp_path):
    # exactly 60 Hz -> every gap must be ~16.6 ms
    p = write_ring(tmp_path / "pentox-run-126.ring", recent(120))
    r = fr.Ring(p)
    ft, api, _pid = r.frametimes_ms(limit=240)
    assert 60 <= len(ft) <= 240
    assert all(abs(x - 16.6) < 0.5 for x in ft)


def test_frametimes_window_order(tmp_path):
    stamps = recent(200, step_ms=10.0)
    p = write_ring(tmp_path / "pentox-run-127.ring", stamps)
    r = fr.Ring(p)
    ft, _api, _pid = r.frametimes_ms(limit=50)
    assert len(ft) == 50                      # limit respected
    assert all(abs(x - 10.0) < 0.5 for x in ft)


def test_discover_rings_skips_dead_pids(tmp_path, monkeypatch):
    monkeypatch.setattr(fr, "RING_PREFIX", "pentox-test-")
    dead = write_ring(tmp_path / "pentox-test-999999.ring", recent(5))
    assert fr.discover_rings() == []          # pid 999999 does not exist
    live = write_ring(f"/tmp/pentox-test-{os.getpid()}.ring", recent(5))
    found = [str(p) for p, _ in fr.discover_rings()]
    assert str(live) in found
    assert str(dead) not in found
    for f in (dead, live):
        os.unlink(f)
