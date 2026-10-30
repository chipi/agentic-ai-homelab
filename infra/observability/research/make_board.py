"""Generate Homelab/research-bench.json (run from the repo root: python3 infra/observability/research/make_board.py).
One board, a host selector over the three
machines that run local models (dgx-llm-1, x3, macbook)."""
import json

VM = {"type": "prometheus", "uid": "victoriametrics"}
VL = {"type": "victoriametrics-logs-datasource", "uid": "victorialogs"}
H = 'instance=~"$host"'
panels, y = [], 0


def ts(title, exprs, unit, w=12, x=0, h=8, desc=""):
    global y
    p = {"type": "timeseries", "title": title, "description": desc, "datasource": VM,
         "targets": [{"refId": chr(65 + i), "datasource": VM, "expr": e, "legendFormat": l} for i, (e, l) in enumerate(exprs)],
         "fieldConfig": {"defaults": {"unit": unit, "custom": {"drawStyle": "line", "fillOpacity": 10, "lineWidth": 1}}, "overrides": []},
         "gridPos": {"h": h, "w": w, "x": x, "y": y}}
    panels.append(p)
    return p


def lts(title, q, unit, w=12, x=0, h=8, desc=""):
    p = {"type": "timeseries", "title": title, "description": desc, "datasource": VL,
         "targets": [{"refId": "A", "datasource": VL, "expr": q, "queryType": "statsRange"}],
         "fieldConfig": {"defaults": {"unit": unit, "custom": {"drawStyle": "points", "pointSize": 4, "fillOpacity": 0}}, "overrides": []},
         "gridPos": {"h": h, "w": w, "x": x, "y": y}}
    panels.append(p)
    return p


def row(title):
    global y
    panels.append({"type": "row", "title": title, "collapsed": False, "gridPos": {"h": 1, "w": 24, "x": 0, "y": y}, "panels": []})
    y += 1


OL = f'job:"ollama" instance:~"$host"'
row("Model speed (from each host's Ollama log)")
lts("Generation speed (tokens/s)", f'{OL} "print_timing" | extract_regexp "tg = +(?P<tg>[0-9.]+) t/s" | stats by (instance) avg(tg) tg', "none", 12, 0,
    desc="llama.cpp's per-request generation rate, averaged per host per interval. MacBook runs use speculative decoding (draft acceptance in its log).")
lts("Prompt processing (tokens/s)", f'{OL} "prompt eval time" | extract_regexp "(?P<pp>[0-9.]+) tokens per second" | stats by (instance) avg(pp) pp', "none", 12, 12)
y += 8
lts("Model loads (llama-server starts)", f'{OL} "starting llama-server" | stats by (instance) count() loads', "none", 8, 0,
    desc="Each start is a model (re)load; the DGX loads gpt-oss:120b etc. from the shared blob store.")
lts("Ollama errors / OOM / offload lines", f'{OL} ("level=ERROR" OR "out of memory" OR "offload" OR "failed") | stats by (instance) count() lines', "none", 8, 8)
lts("Ollama log volume", f'{OL} | stats by (instance) count() lines', "none", 8, 16)
y += 8
row("Machine")
ts("GPU busy %", [(f'DCGM_FI_DEV_GPU_UTIL{{{H}}}', "{{instance}} (NVIDIA)"), (f'node_drm_gpu_busy_percent{{{H}}}', "{{instance}} (AMD)")], "percent", 12, 0,
   desc="DGX: dcgm. X3: the kernel's amdgpu busy counter (drm collector). MacBook: not available without root.")
ts("Memory available", [(f'node_memory_MemAvailable_bytes{{{H}}}', "{{instance}}"),
                        (f'(node_memory_free_bytes{{{H}}} + node_memory_inactive_bytes{{{H}}})', "{{instance}} (macOS free+inactive)")], "bytes", 12, 12,
   desc="Unified memory on all three: the model's weights and KV cache come out of this.")
y += 8
ts("Memory pressure (PSI, share of time stalled)", [(f'rate(node_pressure_memory_waiting_seconds_total{{{H}}}[2m])', "{{instance}} waiting"),
                                                    (f'rate(node_pressure_memory_stalled_seconds_total{{{H}}}[2m])', "{{instance}} stalled")], "percentunit", 8, 0,
   desc="Linux only. Rising pressure while a model serves means it no longer fits.")
ts("CPU busy", [(f'1 - avg by (instance) (rate(node_cpu_seconds_total{{{H}, mode="idle"}}[2m]))', "{{instance}}")], "percentunit", 8, 8,
   desc="High CPU with low GPU during a run = layers offloaded to the CPU.")
ts("GPU power (W) and temperature (C)", [(f'DCGM_FI_DEV_POWER_USAGE{{{H}}}', "{{instance}} W"), (f'DCGM_FI_DEV_GPU_TEMP{{{H}}}', "{{instance}} C")], "none", 8, 16)
y += 8
ts("Loaded model and its memory (DGX sidecar)", [(f'ollama_model_ram_mb{{{H}}} * 1024 * 1024', "{{instance}} {{model}}")], "bytes", 12, 0,
   desc="From the ollama-metrics sidecar (DGX only; X3 and MacBook have no Docker). Model names per load are in the log panel below.")
ts("Swap used", [(f'node_memory_SwapTotal_bytes{{{H}}} - node_memory_SwapFree_bytes{{{H}}}', "{{instance}}"),
                 (f'node_memory_swap_used_bytes{{{H}}}', "{{instance}} (macOS)")], "bytes", 12, 12)
y += 8
row("Ollama log")
panels.append({"type": "logs", "title": "Ollama log (loads, memory, errors; per-request timing lines excluded)", "datasource": VL,
               "targets": [{"refId": "A", "datasource": VL, "expr": f'{OL} -"print_timing" -"slot " -"[GIN]"', "queryType": "instant"}],
               "options": {"showTime": True, "wrapLogMessage": True, "sortOrder": "Descending"},
               "gridPos": {"h": 12, "w": 24, "x": 0, "y": y}})

board = {
    "uid": "research-bench", "title": "Research bench — local models (DGX, X3, MacBook)",
    "description": "What a local-model run needs next to its results: per-host model speed from the Ollama log, GPU, memory and pressure. Hosts: dgx-llm-1, x3, macbook.",
    "tags": ["research", "ollama", "dgx", "workstation"], "schemaVersion": 39, "editable": True,
    "time": {"from": "now-6h", "to": "now"}, "refresh": "1m",
    "annotations": {"list": [{"name": "Research runs", "enable": True, "iconColor": "purple",
                              "datasource": {"type": "grafana", "uid": "-- Grafana --"},
                              "target": {"type": "dashboard", "limit": 200, "matchAny": False, "tags": []},
                              "builtIn": 1, "hide": False}]},
    "templating": {"list": [{"name": "host", "label": "Host", "type": "custom", "query": "dgx-llm-1,x3,macbook",
                             "multi": True, "includeAll": True, "allValue": "dgx-llm-1|x3|macbook",
                             "current": {"selected": True, "text": ["All"], "value": ["$__all"]}}]},
    "panels": panels,
}
out = "/work/agentic-ai-homelab/infra/observability/backend/grafana/dashboards/Homelab/research-bench.json"
json.dump(board, open(out, "w"), indent=2)
print("wrote", out, "panels:", len(panels))
