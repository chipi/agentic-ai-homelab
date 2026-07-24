"""signal-fleet MVP config — endpoints + creds from env, homelab defaults.

Stdlib-only. The fleet runs on the mini (`homelab`), where every source is on
localhost/tailnet. Endpoints default to the `homelab` tailnet name; creds come
from env (source the stack .envs before running — see run.sh). No secrets in code.
"""
import os


def env(key, default=None, required=False):
    v = os.environ.get(key, default)
    if required and not v:
        raise SystemExit(f"[config] missing required env: {key}")
    return v


HOST = env("SF_HOST", "homelab")

# the fleet's OWN identity as a telemetry PRODUCER — kept separate from the
# monitored projects (dgx / orrery / podcast use dev|staging|prod). The fleet is
# its own application in its own environment so its traces/errors/metrics never
# mix with the systems it watches.
SF_ENV = env("SF_ENV", "operations")           # not dev/staging/prod
SF_SERVICE = env("SF_SERVICE", "triage-fleet")  # the application name

# correlation-read backends (no auth on the tailnet)
VM_URL = env("SF_VM_URL", f"http://{HOST}:8428")           # VictoriaMetrics (PromQL)
VL_URL = env("SF_VL_URL", f"http://{HOST}:9428")           # VictoriaLogs (LogsQL)
VT_URL = env("SF_VT_URL", f"http://{HOST}:10428")          # VictoriaTraces (Jaeger)

# trigger sources
GRAFANA_URL = env("SF_GRAFANA_URL", f"http://{HOST}:3000")
GRAFANA_USER = env("GRAFANA_ADMIN_USER", "admin")
GRAFANA_PW = env("GRAFANA_ADMIN_PASSWORD")                 # from observability .env
GLITCHTIP_URL = env("SF_GLITCHTIP_URL", f"http://{HOST}:8090")
GLITCHTIP_TOKEN = env("GLITCHTIP_TOKEN")                   # signal-fleet token

# triager (OpenRouter — reuse the bug-fleet key)
OPENROUTER_KEY = env("OPENROUTER_API_KEY")
OPENROUTER_URL = env("SF_OPENROUTER_URL", "https://openrouter.ai/api/v1/chat/completions")
TRIAGE_MODEL = env("SF_TRIAGE_MODEL", "deepseek/deepseek-v4-flash")
TRIAGE_PROMPT_VER = "mvp-1"

# state
LEDGER = env("SF_LEDGER", os.path.expanduser("~/signal-fleet/results/dispositions.tsv"))
