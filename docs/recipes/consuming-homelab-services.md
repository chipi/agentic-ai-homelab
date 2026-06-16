# Consuming homelab services — the `${VAR}` substitution convention

**Date:** 2026-06-16
**Status:** v0.1 — design call adopted, first consumer pending
**Reach:** any downstream project (podcast_scraper, future agents) that
points config at homelab-served services (autoresearch vLLM, coder-next
vLLM, Ollama, observability, …)

When a downstream project's config references a homelab service it should
use **docker-compose-style `${VAR}` substitution** for the homelab-side
parts (host, port). The **consumer expands** at config-load time using
its own small expander. This file is the contract: the syntax, the
variable namespace homelab exports, and a reference expander.

Settles chipi/agentic-ai-homelab#4.

---

## TL;DR

| Side | Responsibility |
|---|---|
| **Homelab (this repo)** | Defines the **syntax** (compose-style `${VAR}` / `${VAR:-default}`) and the **variable namespace** of homelab-side facts (host, ports, model IDs). |
| **Consumer (podcast_scraper, etc.)** | Expands `${VAR}` before parsing its own config. Errors loudly on unset required vars. ~15 lines of consumer-side code. |

No shared library, no compose-time JSON file, no service-discovery layer.
Plain text substitution that mirrors what docker-compose already does at
homelab-side compose-up time, applied at consumer-side config-load time.

---

## Why this is the choice

The alternatives considered (in chipi/agentic-ai-homelab#4):

| Alternative | Why not |
|---|---|
| **Shared Python library** | Forces a Python dep on every consumer; ceremony around release/versioning that ~15 lines of code doesn't justify. |
| **Compose-time `connection-info.json`** | Solves a service-discovery problem we don't have yet. Tailnet hostnames + ports are stable; the JSON would mostly sit on disk. |
| **Hardcode + grep** | What we had before this convention. Bites at FQDN rotation time, and contradicts the "run-from-repo, no drift" rule from the root [`AGENTS.md`](https://github.com/chipi/agentic-ai-homelab/blob/main/AGENTS.md). |
| **`envsubst` in a shell wrapper** | Works when the consumer can be wrapped in a pipe (`envsubst < x.yaml > resolved.yaml`). Doesn't help when the consumer's tooling reads YAML through its own loader (the actual reported case). |

Hat-tip to `envsubst` — useful complement when applicable, but not the
primary path.

---

## The syntax (docker-compose subset)

Consumers implement these and only these:

| Form | Behaviour |
|---|---|
| `${VAR}` | Required. If `VAR` is unset → consumer **MUST raise** at config-load. Never silently substitute empty string. |
| `${VAR:-default}` | Optional with literal default value. If unset → use the default. The default is plain text (cannot reference other vars). |
| `${VAR:?message}` | *Optional to implement.* Required with custom error. Equivalent to `${VAR}` + a custom message. Skip if you don't need it; just emit a clear error message for `${VAR}`. |

**Out of scope** (intentionally):
- Nested expansion (`${OUTER:-${INNER}}` is NOT supported)
- Command substitution (`$(...)`)
- Defaults that reference other vars
- Anything POSIX-shell that isn't on the list above

Keep it boring on purpose. If a consumer reaches for fancier substitution
it should either (a) use a real templating engine (Jinja, Mako) on top, or
(b) precompute the value in shell before invoking the consumer.

---

## The variable namespace homelab exports

These are the **stable names** consumers can depend on existing. Adding,
renaming, or removing a name is a homelab-side doc change that must
appear in commit history under `infra/` AND be announced (issue or
README update).

### DGX networking

| Variable | Canonical value | What it is |
|---|---|---|
| `DGX_TAILNET_HOST` | `dgx-llm-1.tail6d0ed4.ts.net` | Tailnet FQDN of the GB10 DGX host. Stable; only changes if the tailnet is rotated. |
| `DGX_LAN_IP` | `192.168.0.59` | DGX local IP. Use only when both consumer and DGX are on the same LAN. |

### vLLM autoresearch slot (`infra/vllm/autoresearch/`)

| Variable | Canonical value | What it is |
|---|---|---|
| `AUTORESEARCH_VLLM_PORT` | `8003` | Port the autoresearch vLLM listens on (also `GPU_MODE_RESEARCH_PORT` for the GPU-mode swap script). |
| `AUTORESEARCH_VLLM_MODEL` | `autoresearch` | `served-model-name` clients pass in OpenAI `model` field. NOT the HF repo id. |
| `AUTORESEARCH_VLLM_API_KEY` | `buddy-is-the-king` (or override in `.env`) | Bearer token. Consumers should treat as a secret even though the canonical value is well-known in this homelab. |

### vLLM coder-next slot (`infra/vllm/coder-next/`)

| Variable | Canonical value | What it is |
|---|---|---|
| `CODER_NEXT_VLLM_PORT` | `9000` | Port. Also `GPU_MODE_CODER_PORT`. |
| `CODER_NEXT_VLLM_MODEL` | `coder-next` | `served-model-name`. |
| `CODER_NEXT_VLLM_API_KEY` | `buddy-is-the-king` (default) | Bearer token. |

### Ollama (`infra/observability/` sidecar serves a Level-1 view)

| Variable | Canonical value | What it is |
|---|---|---|
| `OLLAMA_PORT` | `11434` | Standard Ollama API port. |
| `OLLAMA_METRICS_PORT` | `9778` | NorskHelsenett exporter sidecar; if a consumer wants the Level-2 transparent-proxy path. |

### Observability

| Variable | Canonical value | What it is |
|---|---|---|
| `GRAFANA_INSTANCE_LABEL` | `homelab-1` | The `instance` label every metric carries. Use in PromQL filters from other repos. |
| `GRAFANA_CLUSTER_LABEL` | `homelab` | The `cluster` label. |

---

## Reference expander — Python

Copy verbatim or adapt. ~15 lines, no dependencies beyond stdlib.

```python
import os
import re


_VAR_RE = re.compile(r"\$\{([^}]+)\}")


def expand_env(s: str) -> str:
    """Docker-compose-style ${VAR} and ${VAR:-default} expansion.

    Used by consumers of homelab services (autoresearch vLLM, coder-next
    vLLM, etc.) to resolve homelab-side facts before YAML/JSON parse.
    See: docs/recipes/consuming-homelab-services.md in
    chipi/agentic-ai-homelab for the convention.
    """

    def repl(match: re.Match[str]) -> str:
        token = match.group(1)
        if ":-" in token:
            name, default = token.split(":-", 1)
            return os.environ.get(name, default)
        if token not in os.environ:
            raise KeyError(
                f"required env var ${{{token}}} not set "
                f"(homelab convention; see consuming-homelab-services recipe)"
            )
        return os.environ[token]

    return _VAR_RE.sub(repl, s)
```

Call before `yaml.safe_load` / `json.loads` / whatever:

```python
with open(config_path) as f:
    raw = f.read()
expanded = expand_env(raw)
config = yaml.safe_load(expanded)
```

If the consumer reads many configs, wrap it once at the loader boundary
and the rest of the codebase is untouched.

### Reference expander — shell (no defaults)

When the consumer can be wrapped in a pipe (any tool that accepts a
pre-rendered config on stdin or path), `envsubst` from `gettext` does
the `${VAR}` form:

```bash
envsubst < config.yaml.template > config.yaml
```

**Caveat:** `envsubst` doesn't implement `${VAR:-default}` — it
substitutes empty string when the var is unset. For the default form
either pre-export the var with the desired value before calling
`envsubst`, or use the Python expander above.

To restrict which vars `envsubst` expands (avoid eating literal `$amounts`
in YAML):

```bash
envsubst '${DGX_TAILNET_HOST} ${AUTORESEARCH_VLLM_PORT}' < x.yaml.template > x.yaml
```

---

## Usage example — podcast_scraper eval config

Before (broken — un-expanded literal hits OpenAI client):

```yaml
backend:
  type: openai
  base_url: "http://${DGX_TAILNET_HOST}:${AUTORESEARCH_VLLM_PORT}/v1"
  api_key_env: AUTORESEARCH_VLLM_API_KEY
  model: ${AUTORESEARCH_VLLM_MODEL}
```

Consumer-side loader (one ~20-line change, e.g. in
`src/podcast_scraper/evaluation/experiment_config.py`):

```python
from podcast_scraper.evaluation.env_expand import expand_env  # noqa
# ...
def load_experiment_config(path: str) -> dict:
    with open(path) as f:
        raw = f.read()
    return yaml.safe_load(expand_env(raw))
```

Operator's shell (or systemd unit, or `.env` sourced beforehand) exports:

```bash
export DGX_TAILNET_HOST=dgx-llm-1.tail6d0ed4.ts.net
export AUTORESEARCH_VLLM_PORT=8003
export AUTORESEARCH_VLLM_MODEL=autoresearch
export AUTORESEARCH_VLLM_API_KEY=buddy-is-the-king
```

(For the operator's existing setup these are typically already in
`~/.config/<project>/env` or a per-project `.env`.)

---

## What this is NOT

- **Not** a service-discovery mechanism. Address changes still require
  consumers to update their env. Acceptable at this scale (1 DGX,
  ~3 services, low churn). Re-evaluate when there are >5 services on
  >1 host.
- **Not** a shared library. Each consumer writes its own ~15-line
  expander. The contract is the **syntax** and the **variable namespace**,
  not the code.
- **Not** runtime service discovery (DNS-based or otherwise). The
  Tailscale magic-DNS name *is* the discovery layer for the host.
  Ports + model names are stable contracts published in this recipe.

---

## When to revisit this design

Promote to one of the rejected alternatives (compose-time JSON,
shared library) when ANY of the following is true:

- More than 5 distinct homelab services consumers point at
- Ports start moving routinely (currently fixed)
- More than 3 consumer projects exist (currently 1: podcast_scraper)
- A consumer wants capability-discovery (e.g. "what models does
  autoresearch serve right now") at runtime instead of by-convention

Until then this is the right level of indirection for the homelab's
size and churn rate.

---

## Cross-references

- The original ticket: chipi/agentic-ai-homelab#4
- The reported bug in podcast_scraper that triggered this:
  `src/podcast_scraper/evaluation/experiment_config.py:load_experiment_config`
  passing un-expanded `${VAR}` strings to the OpenAI client.
- The homelab compose files that use the same syntax:
  - [`infra/vllm/autoresearch/docker-compose.yml`](https://github.com/chipi/agentic-ai-homelab/blob/main/infra/vllm/autoresearch/docker-compose.yml)
  - [`infra/vllm/coder-next/docker-compose.yml`](https://github.com/chipi/agentic-ai-homelab/blob/main/infra/vllm/coder-next/docker-compose.yml)
- Related operator rule: every operational value via `${VAR:-default}`
  in compose (commit `30b2597`).
