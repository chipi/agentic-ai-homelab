# DGX systemd drop-ins

Paths here mirror the real install paths on `dgx-llm-1` (`spark-2c14`) exactly, so
there is no guessing about where a file belongs.

| Repo path | Install path |
|---|---|
| `ollama.service.d/override.conf` | `/etc/systemd/system/ollama.service.d/override.conf` |

Install:

```bash
sudo install -m 0644 -D ollama.service.d/override.conf \
  /etc/systemd/system/ollama.service.d/override.conf
sudo systemctl daemon-reload
sudo systemctl restart ollama
```

Verify from ollama's own startup log rather than from the file — the file being
correct does not prove systemd loaded it:

```bash
journalctl -u ollama -b 0 --no-pager -o cat --since -1min \
  | grep -oE 'OLLAMA_CONTEXT_LENGTH:[0-9]+|OLLAMA_MAX_LOADED_MODELS:[0-9]+|OLLAMA_GPU_OVERHEAD:[0-9]+'
```

## Why `ollama.service.d/override.conf` exists

`dgx-llm-1` is GB10 with a **130.7 GB unified LPDDR5X pool** — there is no separate
VRAM. Every GPU consumer (vLLM, ollama, moss, pyannote, faster-whisper) allocates
from the same system memory, and none of them knows about the others' reservations.

ollama's scheduler reads the pool's *free* figure and concludes it owns all of it:

```
msg="system memory" total="121.7 GiB" free="80.6 GiB"
msg="gpu memory"    available="80.0 GiB" free="80.5 GiB" overhead="0 B"
```

That 80 GB was reported while vLLM was holding ~30 GB. With the stock defaults
(`OLLAMA_CONTEXT_LENGTH=0` → model default 262144, `OLLAMA_GPU_OVERHEAD=0`,
`OLLAMA_MAX_LOADED_MODELS=0`), a single research request loaded an 8B Q4_K_M model
— about 5 GB of weights — as **22–30 GB**, because the KV cache was sized for a
128K–256K context. `MemFree` collapsed to ~1 GB and the host wedged, twice, on
2026-09-15 and 2026-09-16. Each wedge needed a physical power-button press.

The `-c 262144` on every model load is the whole problem; **`OLLAMA_CONTEXT_LENGTH`
is the load-bearing setting here.** The other two are belt-and-braces:
`GPU_OVERHEAD` stops the scheduler treating vLLM's memory as its own (a too-large
model now degrades to CPU offload instead of taking the host down), and
`MAX_LOADED_MODELS=1` stops models stacking.

Measured effect on `llama3.1:8b`:

| | before | after |
|---|---|---|
| context | 131072 | 32768 |
| `size_vram` | 22.79 GB | **9.21 GB** |
| MemFree at the trough | 0.98 GB | ~50 GB |

### If research needs more than 32K context

Raise it **deliberately and by measurement**, not back to the model default. 262144
is what caused the outages. Note that the fatal band starts around 62 GB of total
GPU allocation while the pre-fix idle-with-ollama baseline was ~52 GB — there is not
much headroom, which is why the `dgx-memfree-crit` alert (MemFree < 8 GB) exists as
the backstop.

Full incident analysis: chipi/agentic-ai-homelab#63.
