#!/usr/bin/env python3
"""Apply the assistant's configuration to both evaluation UIs, from files in this directory.

Single sources:
- system-prompt.txt — the system prompt ({{DATE}} becomes each UI's date variable);
- infra/homelab-home/openapi.json — the status tool (GET https://hub.tail6d0ed4.ts.net/status.json).

LibreChat: a "Homelab assistant" agent (the prompt as its instructions, model `assistant` on the Homelab
gateway, all Grafana MCP tools, and the hub status as an OpenAPI action); librechat.yaml gets the actions
allowlist for the hub and a default model spec that opens on that agent (rewritten between the markers
below), and the container is restarted when that block changed.
Open WebUI: the `assistant` model's system prompt and its default tools (the Grafana MCP server and the
hub status OpenAPI server), both tool servers registered.

Both are driven through their APIs as the operator's account (~/assistant-ui-eval-accounts.env).
Run on the X3 from this directory: ./apply-ui-config.py. Idempotent.
"""
import json
import os
import subprocess
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
PROMPT = open(os.path.join(HERE, "system-prompt.txt")).read().strip()
SPECS_DIR = os.path.join(HERE, "..", "..", "homelab-home")
SPEC_TEXT = open(os.path.join(SPECS_DIR, "openapi.json")).read()
SPEC = json.loads(SPEC_TEXT)
GT_SPEC_TEXT = open(os.path.join(SPECS_DIR, "glitchtip-openapi.json")).read()
GT_SPEC = json.loads(GT_SPEC_TEXT)
GT = "glitchtip.tail6d0ed4.ts.net"
GT_ADDR = "100.121.204.22"           # GlitchTip's tailnet address (SSRF guard)
# the read-only GlitchTip token (GlitchTip token "assistant chat read-only": event/project/org read)
ENV = dict(l.strip().split("=", 1) for l in open(os.path.join(HERE, ".env")) if "=" in l and not l.startswith("#"))
GT_TOKEN = ENV["ASSISTANT_GLITCHTIP_TOKEN"]


def functions_of(spec):
    """Function definitions (name, description, JSON-schema parameters) from an OpenAPI spec."""
    out = []
    for path, ops in spec["paths"].items():
        for method, op in ops.items():
            props = {p["name"]: {**p.get("schema", {}), "description": p.get("description", "")} for p in op.get("parameters", [])}
            req = [p["name"] for p in op.get("parameters", []) if p.get("required")]
            out.append({"type": "function", "function": {"name": op["operationId"], "description": op["summary"],
                        "parameters": {"type": "object", "properties": props, **({"required": req} if req else {})}}})
    return out


# the actions each agent gets: (domain, spec text, spec, auth metadata)
ACTIONS = [
    ("hub.tail6d0ed4.ts.net", SPEC_TEXT, SPEC, {"auth": {"type": "none"}}),
    (GT, GT_SPEC_TEXT, GT_SPEC, {"auth": {"type": "service_http", "authorization_type": "bearer"}, "api_key": GT_TOKEN}),
]
HUB = "hub.tail6d0ed4.ts.net"
HUB_ADDR = "100.120.76.68"          # the hub's tailnet address: LibreChat's SSRF guard checks the resolved IP
MARK = "\n# The same system prompt as Open WebUI's"
LIBRECHAT, OPENWEBUI = "http://127.0.0.1:3080", "http://127.0.0.1:3081"
AGENT_NAME = "Homelab assistant"
ACC = dict(line.strip().split("=", 1) for line in open(os.path.expanduser("~/assistant-ui-eval-accounts.env")) if "=" in line)


# LibreChat refuses API calls without a browser User-Agent ("Illegal request") and logs each as a
# violation (no ban here: BAN_VIOLATIONS is unset), so this admin script presents one.
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0 Safari/537.36 apply-ui-config"


def call(base, method, path, token=None, body=None):
    req = urllib.request.Request(base + path, method=method,
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json", "User-Agent": UA,
                                          **({"Authorization": "Bearer " + token} if token else {})})
    with urllib.request.urlopen(req, timeout=60) as r:
        raw = r.read()
        return json.loads(raw) if raw else {}


def wait_up(url):
    for _ in range(40):
        try:
            if urllib.request.urlopen(url, timeout=5).status == 200:
                return
        except OSError:
            pass
        time.sleep(3)
    raise SystemExit(f"{url} did not come back within 2 minutes")


# ---------- LibreChat ----------

def librechat_yaml(agent_id):
    """Rewrite the generated block at the end of librechat.yaml; True when it changed."""
    spec = (f"      preset:\n        endpoint: \"agents\"\n        agent_id: \"{agent_id}\"\n" if agent_id else
            "      preset:\n        endpoint: \"Homelab gateway\"\n        model: \"assistant\"\n        modelLabel: \"Homelab\"\n"
            "        promptPrefix: |\n" + "\n".join("          " + l for l in PROMPT.replace("{{DATE}}", "{{current_datetime}}").splitlines()) + "\n")
    block = f"""{MARK} (system-prompt.txt) and tools; generated by apply-ui-config.py,
# do not edit by hand. Actions may call the hub and GlitchTip only. The default spec opens on the "{AGENT_NAME}" agent
# (prompt, model `assistant`, Grafana tools, hub status action), not on "My Agents".
actions:
  allowedDomains: ["{HUB}", "{GT}"]
  allowedAddresses: ["{HUB}:443", "{HUB_ADDR}:443", "{GT}:443", "{GT_ADDR}:443"]

modelSpecs:
  prioritize: true
  list:
    - name: homelab-assistant
      label: "{AGENT_NAME}"
      description: "assistant on the X3 (OpenRouter as failover), Grafana tools, hub status"
      default: true
      mcpServers: ["grafana"]
{spec}"""
    path = os.path.join(HERE, "librechat.yaml")
    s = open(path).read()
    i = s.find(MARK)
    new = (s[:i] if i >= 0 else s).rstrip("\n") + "\n" + block
    if new == s:
        return False
    open(path, "w").write(new)
    return True


def restart_librechat():
    subprocess.run(["docker", "restart", "assistant-eval-librechat"], check=True, stdout=subprocess.DEVNULL)
    wait_up(LIBRECHAT + "/api/config")


def librechat():
    def token():
        return call(LIBRECHAT, "POST", "/api/auth/login", body={"email": ACC["ASSISTANT_EVAL_USER"], "password": ACC["ASSISTANT_EVAL_PASSWORD"]})["token"]
    tok = token()
    agents = call(LIBRECHAT, "GET", "/api/agents?limit=100", tok).get("data", [])
    agent = next((a for a in agents if a.get("name") == AGENT_NAME), None)
    # the actions allowlist must be live before the action is added; keep the current spec target
    if librechat_yaml(agent["id"] if agent else None):
        restart_librechat()
        tok = token()
    body = {"name": AGENT_NAME, "description": "The homelab assistant: Grafana tools, the hub's status, GlitchTip errors",
            "instructions": PROMPT.replace("{{DATE}}", "{{current_datetime}}"),
            "provider": "Homelab gateway", "model": "assistant", "tools": ["sys__all__sys_mcp_grafana"]}
    if agent:
        keep = [t for t in agent.get("tools") or [] if "_action_" in t]   # the action's own tool entry
        body["tools"] = body["tools"] + keep
        agent = call(LIBRECHAT, "PATCH", f"/api/agents/{agent['id']}", tok, body)
    else:
        agent = call(LIBRECHAT, "POST", "/api/agents", tok, body)
    have = call(LIBRECHAT, "GET", "/api/agents/actions", tok) or []
    for domain, text, spec, meta in ACTIONS:
        existing = [a for a in have if a.get("agent_id") == agent["id"] and (a.get("metadata") or {}).get("domain") == domain]
        act = {"functions": functions_of(spec), "metadata": {"domain": domain, "raw_spec": text, **meta}}
        if existing:
            act["action_id"] = existing[0]["action_id"]
        call(LIBRECHAT, "POST", f"/api/agents/actions/{agent['id']}", tok, act)
    if librechat_yaml(agent["id"]):
        restart_librechat()
        tok = token()
    # the container must see the file as it is on disk: an editor or `sed -i` replaces the file, and the
    # single-file bind mount keeps the old one until a restart
    seen = subprocess.run(["docker", "exec", "assistant-eval-librechat", "cat", "/app/librechat.yaml"], capture_output=True, text=True).stdout
    if seen != open(os.path.join(HERE, "librechat.yaml")).read():
        restart_librechat()
        tok = token()
        print("LibreChat: restarted (the container saw an older librechat.yaml)")
    got = call(LIBRECHAT, "GET", f"/api/agents/{agent['id']}", tok)
    print(f"LibreChat: agent {got['id']} ({got.get('model')} on {got.get('provider')}), tools {got.get('tools')}, "
          f"instructions match system-prompt.txt: {got.get('instructions') == body['instructions']}; default spec opens on it")


# ---------- Open WebUI ----------

GATEWAY = "https://litellm.tail6d0ed4.ts.net/v1"   # the TLS name; the mini's plain :4001 drops connections


def openwebui():
    tok = call(OPENWEBUI, "POST", "/api/v1/auths/signin", body={"email": ACC["ASSISTANT_EVAL_USER"], "password": ACC["ASSISTANT_EVAL_PASSWORD"]})["token"]
    # the connection URL lives in Open WebUI's database (the env only seeds a fresh install); keys unchanged
    oc = call(OPENWEBUI, "GET", "/openai/config", tok)
    if oc.get("OPENAI_API_BASE_URLS") != [GATEWAY]:
        call(OPENWEBUI, "POST", "/openai/config/update", tok, {"ENABLE_OPENAI_API": True, "OPENAI_API_BASE_URLS": [GATEWAY],
             "OPENAI_API_KEYS": oc.get("OPENAI_API_KEYS") or [], "OPENAI_API_CONFIGS": oc.get("OPENAI_API_CONFIGS") or {}})
    print(f"Open WebUI: gateway {call(OPENWEBUI, 'GET', '/openai/config', tok).get('OPENAI_API_BASE_URLS')}")
    servers = [
        {"url": "http://mcp-grafana:8000/mcp", "path": "", "type": "mcp", "auth_type": "none", "key": "",
         "config": {"enable": True},
         "info": {"id": "grafana", "name": "Grafana", "description": "Grafana, read-only: alerts, alert rules, dashboards, VictoriaMetrics (Prometheus) queries"}},
        {"url": f"https://{HUB}", "path": "openapi.json", "type": "openapi", "auth_type": "none", "key": "",
         "config": {"enable": True},
         "info": {"id": "hubstatus", "name": "Homelab status", "description": SPEC["info"]["description"]}},
        {"url": f"https://{GT}", "path": f"https://{HUB}/glitchtip-openapi.json", "type": "openapi", "auth_type": "bearer",
         "key": GT_TOKEN, "config": {"enable": True},
         "info": {"id": "glitchtip", "name": "Homelab errors (GlitchTip)", "description": GT_SPEC["info"]["description"]}},
    ]
    call(OPENWEBUI, "POST", "/api/v1/configs/tool_servers", tok, {"TOOL_SERVER_CONNECTIONS": servers})
    model = {"id": "assistant", "base_model_id": None, "name": "assistant",
             "meta": {"description": "assistant on the X3 (OpenRouter as failover), Grafana tools, hub status",
                      "toolIds": ["server:mcp:grafana", "server:hubstatus", "server:glitchtip"]},
             "params": {"system": PROMPT.replace("{{DATE}}", "{{CURRENT_DATETIME}}")}}
    try:
        call(OPENWEBUI, "POST", "/api/v1/models/model/update?id=assistant", tok, model)
    except urllib.error.HTTPError:
        call(OPENWEBUI, "POST", "/api/v1/models/create", tok, model)
    got = call(OPENWEBUI, "GET", "/api/v1/models/model?id=assistant", tok)
    if (got.get("params") or {}).get("system") != model["params"]["system"]:
        raise SystemExit("Open WebUI: the stored system prompt differs from system-prompt.txt")
    print(f"Open WebUI: system prompt matches system-prompt.txt; tools {(got.get('meta') or {}).get('toolIds')}; "
          f"tool servers {[s['info']['id'] for s in servers]}")


if __name__ == "__main__":
    librechat()
    openwebui()
