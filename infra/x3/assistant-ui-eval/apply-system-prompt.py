#!/usr/bin/env python3
"""Apply system-prompt.txt (the single source of the assistant's system prompt) to both evaluation UIs.

- LibreChat: rewrites the `modelSpecs` block at the end of librechat.yaml ({{DATE}} -> {{current_date}}),
  then restarts its container (the file is mounted, so compose sees no change).
- Open WebUI: stores it as the `assistant` model's system prompt ({{DATE}} -> {{CURRENT_DATE}}) through
  the admin API, as the operator's account (~/assistant-ui-eval-accounts.env), with the Grafana tool
  server on by default.

Run on the X3 from this directory: ./apply-system-prompt.py. Edit only system-prompt.txt, then run this.
"""
import json
import os
import subprocess
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
PROMPT = open(os.path.join(HERE, "system-prompt.txt")).read().strip()
MARK = "\n# The same system prompt as Open WebUI's"
OPENWEBUI = "http://127.0.0.1:3081"


def librechat():
    body = "\n".join("          " + line for line in PROMPT.replace("{{DATE}}", "{{current_date}}").splitlines())
    block = f"""{MARK} (system-prompt.txt, applied by apply-system-prompt.py; only the date
# variable differs). The default spec: new chats open on it (not on "My Agents"), with the assistant
# model and the Grafana tools.
modelSpecs:
  prioritize: true
  list:
    - name: homelab-assistant
      label: "Homelab assistant"
      description: "assistant on the X3 (OpenRouter as failover), Grafana tools"
      default: true
      mcpServers: ["grafana"]
      preset:
        endpoint: "Homelab gateway"
        model: "assistant"
        modelLabel: "Homelab"
        promptPrefix: |
{body}
"""
    path = os.path.join(HERE, "librechat.yaml")
    s = open(path).read()
    i = s.find(MARK)
    if i >= 0:
        s = s[:i]
    open(path, "w").write(s.rstrip("\n") + "\n" + block)
    subprocess.run(["docker", "restart", "assistant-eval-librechat"], check=True, stdout=subprocess.DEVNULL)
    for _ in range(40):
        try:
            if urllib.request.urlopen("http://127.0.0.1:3080/api/config", timeout=5).status == 200:
                print("LibreChat: librechat.yaml rewritten, container restarted, up")
                return
        except OSError:
            pass
        time.sleep(3)
    raise SystemExit("LibreChat did not come back within 2 minutes")


def call(method, path, token=None, body=None):
    req = urllib.request.Request(OPENWEBUI + path, method=method,
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json",
                                          **({"Authorization": "Bearer " + token} if token else {})})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def openwebui():
    acc = dict(line.strip().split("=", 1) for line in open(os.path.expanduser("~/assistant-ui-eval-accounts.env")) if "=" in line)
    token = call("POST", "/api/v1/auths/signin", body={"email": acc["ASSISTANT_EVAL_USER"], "password": acc["ASSISTANT_EVAL_PASSWORD"]})["token"]
    model = {"id": "assistant", "base_model_id": None, "name": "assistant",
             "meta": {"description": "assistant on the X3 (OpenRouter as failover), Grafana tools", "toolIds": ["server:mcp:grafana"]},
             "params": {"system": PROMPT.replace("{{DATE}}", "{{CURRENT_DATE}}")}}
    try:
        call("POST", "/api/v1/models/model/update?id=assistant", token, model)
    except urllib.error.HTTPError:
        call("POST", "/api/v1/models/create", token, model)
    stored = (call("GET", "/api/v1/models/model?id=assistant", token).get("params") or {}).get("system") or ""
    if stored != model["params"]["system"]:
        raise SystemExit("Open WebUI: the stored system prompt differs from system-prompt.txt")
    print("Open WebUI: the assistant model's system prompt matches system-prompt.txt")


if __name__ == "__main__":
    librechat()
    openwebui()
