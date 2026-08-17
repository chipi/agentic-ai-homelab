#!/usr/bin/env python3
"""Turn `docker stats --no-stream` output into per-container cpu/mem metrics.

Why not cAdvisor: on colima (cgroup v2 + cgroupfs driver + cgroupns) cAdvisor only
sees the system/systemd cgroups, NOT the docker container scopes — so it yields no
per-container data on the mini. `docker stats` sees every container AND carries the
friendly name. Shared by mini-metrics (local) and dgx-scrape (DGX over SSH).

Input (one container per line, tab-separated), produced by:
    docker stats --no-stream --format '{{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}'

Emits:
    container_cpu_percent{box,name}   <0-100*ncpu>
    container_memory_bytes{box,name}  <bytes>
"""
import re
import sys

box = sys.argv[1] if len(sys.argv) > 1 else "unknown"
UNIT = {"B": 1, "KiB": 1024, "MiB": 1024**2, "GiB": 1024**3, "TiB": 1024**4,
        "KB": 1000, "MB": 1000**2, "GB": 1000**3, "TB": 1000**4, "kB": 1000}


def esc(v):
    return str(v).replace("\\", "\\\\").replace('"', '\\"')


def to_bytes(s):
    m = re.match(r"([\d.]+)\s*([KMGT]?i?B)$", s.strip())
    if not m:
        return None
    return float(m.group(1)) * UNIT.get(m.group(2), 1)


for line in sys.stdin:
    parts = line.rstrip("\n").split("\t")
    if len(parts) < 3:
        continue
    name = parts[0].lstrip("/")
    try:
        cpu = float(parts[1].rstrip("%"))
    except ValueError:
        continue
    print('container_cpu_percent{box="%s",name="%s"} %s' % (esc(box), esc(name), cpu))
    used = parts[2].split("/")[0]  # "202.2MiB / 19.53GiB" -> "202.2MiB"
    b = to_bytes(used)
    if b is not None:
        print('container_memory_bytes{box="%s",name="%s"} %d' % (esc(box), esc(name), int(b)))
