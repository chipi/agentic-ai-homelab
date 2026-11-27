#!/usr/bin/env python3
"""Turn `docker system df --format '{{json .}}'` into per-engine disk metrics.

Run hourly on each box for each engine it has (x3-host.sh: the X3's dev engine; mini-metrics: the mini's
production engine and, when it runs, its dev engine; dgx-scrape: the DGX's engine over its existing SSH),
for the Hub's "Docker disk" tables (operator, 2026-11-27). Reads the JSON lines on stdin, writes Prometheus
lines on stdout:

    docker_engine_bytes{box,engine,type}              size; type = images | containers | volumes | build_cache
    docker_engine_reclaimable_bytes{box,engine,type}  what docker counts as removable
    docker_engine_count{box,engine,type}              how many (images, containers, volumes, cache entries)
    docker_engine_measured_timestamp{box,engine}      when

Docker prints sizes rounded (3 or 4 digits, decimal units), so the bytes are that precise.

    docker system df --format '{{json .}}' | engine-df.py <box> <engine>
"""
import json
import re
import sys
import time

TYPES = {"Images": "images", "Containers": "containers", "Local Volumes": "volumes", "Build Cache": "build_cache"}
UNITS = {"B": 1, "kB": 1e3, "KB": 1e3, "MB": 1e6, "GB": 1e9, "TB": 1e12}


def size(s):
    m = re.match(r"\s*([\d.]+)\s*([kKMGT]?B)", s or "")
    return int(float(m.group(1)) * UNITS[m.group(2)]) if m else 0


def main(box, engine):
    out = []
    lab = 'box="%s",engine="%s"' % (box, engine)
    for line in sys.stdin:
        try:
            r = json.loads(line)
        except ValueError:
            continue
        t = TYPES.get(r.get("Type"))
        if not t:
            continue
        out.append('docker_engine_bytes{%s,type="%s"} %d' % (lab, t, size(r.get("Size"))))
        out.append('docker_engine_reclaimable_bytes{%s,type="%s"} %d' % (lab, t, size(r.get("Reclaimable"))))
        out.append('docker_engine_count{%s,type="%s"} %s' % (lab, t, int(r.get("TotalCount") or 0)))
    if out:
        out.append("docker_engine_measured_timestamp{%s} %d" % (lab, time.time()))
        print("\n".join(out))


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit("usage: docker system df --format '{{json .}}' | engine-df.py <box> <engine>")
    main(sys.argv[1], sys.argv[2])
