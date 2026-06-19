"""Tests for the subprocess-free platform-stats helpers in MyPlatform.

These cover the /proc and /sys readers that replace the previous shell pipelines
(`grep /proc/stat | awk ...` and `ip link | grep ... | awk ...`). The key
regression guard is test_helpers_spawn_no_subprocess: the old code spawned ~9
processes per platform-stats request (sh + grep + awk for CPU%, and sh + ip +
grep x3 + awk for the active adapter), measured at ~216 spawns/min on a Pi via
genmqtt's 2s monitor_json poll. The helpers must spawn none.

Run: pytest tests/test_platform_stats.py
"""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from genmonlib.myplatform import MyPlatform


def _make_iface(base, name, ifindex, flags, carrier):
    d = base / name
    d.mkdir(parents=True)
    (d / "ifindex").write_text(str(ifindex))
    (d / "flags").write_text(flags)
    (d / "carrier").write_text(carrier)


def test_read_cpu_utilization_matches_old_awk_formula(tmp_path):
    stat = tmp_path / "stat"
    # cpu  user nice system idle iowait ...
    stat.write_text("cpu  100 0 50 850 0 0 0\ncpu0 50 0 25 425 0 0 0\n")
    # (user+system)*100/(user+system+idle) = (100+50)*100/(100+50+850) = 15.0
    assert MyPlatform.ReadCPUUtilization(str(stat)) == 15.0


def test_get_active_adapter_picks_first_broadcast_with_carrier(tmp_path):
    base = tmp_path / "net"
    _make_iface(base, "lo", 1, "0x9", "1")       # loopback: no IFF_BROADCAST -> skip
    _make_iface(base, "eth0", 2, "0x1003", "0")  # broadcast but NO-CARRIER -> skip
    _make_iface(base, "eth1", 3, "0x1003", "1")  # broadcast + carrier -> picked
    assert MyPlatform.GetActiveNetworkAdapter(str(base)) == "eth1"


def test_get_active_adapter_respects_ifindex_order(tmp_path):
    base = tmp_path / "net"
    # Two valid candidates; lowest ifindex wins (matches `ip link` / `grep -m1`).
    _make_iface(base, "wlan0", 5, "0x1003", "1")
    _make_iface(base, "eth0", 2, "0x1003", "1")
    assert MyPlatform.GetActiveNetworkAdapter(str(base)) == "eth0"


def test_get_active_adapter_missing_dir_returns_empty(tmp_path):
    assert MyPlatform.GetActiveNetworkAdapter(str(tmp_path / "does-not-exist")) == ""


def test_helpers_spawn_no_subprocess(tmp_path, monkeypatch):
    """Perf guard: the helpers must read /proc and /sys directly and never spawn
    a subprocess (the previous os.popen pipelines spawned ~9 per call)."""
    def boom(*a, **k):
        pytest.fail("unexpected subprocess spawn: %r %r" % (a, k))

    monkeypatch.setattr(os, "popen", boom)
    monkeypatch.setattr("subprocess.Popen", boom)
    monkeypatch.setattr("subprocess.check_output", boom)
    monkeypatch.setattr("subprocess.run", boom)
    monkeypatch.setattr(os, "system", boom)

    stat = tmp_path / "stat"
    stat.write_text("cpu  100 0 50 850 0\n")
    base = tmp_path / "net"
    _make_iface(base, "eth0", 2, "0x1003", "1")

    assert MyPlatform.ReadCPUUtilization(str(stat)) == 15.0
    assert MyPlatform.GetActiveNetworkAdapter(str(base)) == "eth0"
