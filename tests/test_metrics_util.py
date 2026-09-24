"""Metrics and util helpers: read_* fallbacks, hwmon lookup, meminfo."""

import pathlib

from pentox import metrics
from pentox.util import hex_to_rgb, human_gib, proc_alive, read_first


def test_mem_sample_shape():
    m = metrics.mem_sample()
    assert "total_kib" in m and "used_kib" in m and "pct" in m
    assert 0.0 <= m["pct"] <= 100.0


def test_swap_sample_shape():
    s = metrics.swap_sample()
    # either empty (no swap) or a consistent total/used pair
    if s:
        assert s["total_kib"] > 0
        assert 0 <= s["used_kib"] <= s["total_kib"]
        assert 0.0 <= s["pct"] <= 100.0


def test_detect_gpu_returns_object():
    g = metrics.detect_gpu()
    assert hasattr(g, "kind") and hasattr(g, "label")
    assert g.kind in ("amdgpu", "nvidia", "intel", "unknown")


def test_gpu_sample_never_raises():
    s = metrics.gpu_sample(metrics.detect_gpu())
    assert isinstance(s, dict)


def test_hex_to_rgb():
    assert hex_to_rgb("FF0000") == (1.0, 0.0, 0.0)
    assert hex_to_rgb("#00ff00") == (0.0, 1.0, 0.0)
    assert hex_to_rgb(" 0B0812 ") == (11 / 255, 8 / 255, 18 / 255)


def test_human_gib():
    assert human_gib(2 * 1024 * 1024) == "2.0 GiB"
    assert human_gib(1048576, 4 * 1048576) == "1.0 / 4.0 GiB"


def test_read_first_prefers_first_readable(tmp_path: pathlib.Path):
    missing = tmp_path / "nope"
    present = tmp_path / "yes"
    present.write_text("42\n")
    assert read_first([missing, present]) == 42
    assert read_first([missing, missing]) is None


def test_proc_alive_self():
    import os
    assert proc_alive(os.getpid()) is True
    assert proc_alive(999999) is False
