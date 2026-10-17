#!/usr/bin/env python3
"""mint-credential: mint a scoped credential, store it, prove it, and say where it lives.

Runs ON the Mac mini (via host-run). Never prints a secret value.

    mint.py litellm   --alias proj-x-dev --models "NVFP4/Qwen3-30B-A3B-Instruct-2507-FP4" --budget 1 \
                      --out ~/x-litellm-dev.env [--duration 30d] [--langfuse-keys ~/x-langfuse-dev.env]
    mint.py glitchtip --label "x sourcemaps" --scopes project:releases,org:read --out ~/glitchtip/x.env
    mint.py revoke-litellm   --alias proj-x-dev            # delete a key by alias (for tests / rotation)
    mint.py revoke-glitchtip --label "x sourcemaps"        # delete a token by label

The value is written ONCE, straight into --out (mode 600, created exclusively: an existing file is
never overwritten). Then the credential is used for real:
  - LiteLLM: one call to the first allowed model, and one call to a model outside the list, which
    must be refused (403);
  - GlitchTip: one authenticated read.
It ends with the credentials-table row to add to docs/recipes/agent-access.md. LiteLLM and
GlitchTip show a value only once, so a credential that isn't in that table is effectively lost
(the 2026-10-13 proj-podcast-dev key was).
"""
import argparse, json, os, subprocess, sys, urllib.error, urllib.request

LL = "http://127.0.0.1:4001"
GT = "http://127.0.0.1:8090"
results = []


def check(ok, what):
    results.append(ok)
    print(f"  [{'PASS' if ok else 'FAIL'}] {what}")
    return ok


def envfile(path):
    d = {}
    for line in open(os.path.expanduser(path)):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            d[k] = v.strip().strip('"').strip("'")
    return d


def http(url, body=None, headers=None, method=None, timeout=120):
    data = json.dumps(body).encode() if body is not None else None
    h = {"Content-Type": "application/json", **(headers or {})}
    req = urllib.request.Request(url, data=data, headers=h, method=method)
    try:
        r = urllib.request.urlopen(req, timeout=timeout)
        return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b"{}")
        except ValueError:
            return e.code, {}


def write_secret_file(path, lines):
    path = os.path.expanduser(path)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)   # never overwrite
    with os.fdopen(fd, "w") as f:
        f.write("\n".join(lines) + "\n")
    return path


def master():
    return {"Authorization": "Bearer " + envfile("~/agentic-ai-homelab/infra/litellm/.env")["LITELLM_MASTER_KEY"]}


def litellm_key_by_alias(alias):
    code, r = http(f"{LL}/key/list?key_alias={alias}&return_full_object=true", headers=master())
    return [k for k in (r.get("keys") or []) if isinstance(k, dict)]


def cmd_litellm(a):
    if os.path.exists(os.path.expanduser(a.out)):
        sys.exit(f"refusing: {a.out} exists. Pick another path, or move the old file after checking it.")
    existing = litellm_key_by_alias(a.alias)
    if existing:
        k = existing[0]
        sys.exit(f"refusing: alias {a.alias!r} exists (key {k.get('key_name')}, spend {k.get('spend')}). "
                 f"If nobody holds its value, revoke it first: mint.py revoke-litellm --alias {a.alias}")
    models = [m.strip() for m in a.models.split(",") if m.strip()]
    md = {"owner": a.owner}
    if a.langfuse_keys:
        lf = envfile(a.langfuse_keys)
        host = envfile("~/agentic-ai-homelab/infra/litellm/.env").get("LANGFUSE_HOST")
        md["logging"] = [{"callback_name": "langfuse", "callback_type": "success_and_failure",
                          "callback_vars": {"langfuse_public_key": lf["LANGFUSE_PUBLIC_KEY"],
                                            "langfuse_secret_key": lf["LANGFUSE_SECRET_KEY"],
                                            "langfuse_host": host}}]
    body = {"key_alias": a.alias, "models": models, "max_budget": a.budget, "metadata": md}
    if a.duration:
        body["duration"] = a.duration
    code, r = http(f"{LL}/key/generate", body, headers=master(), method="POST")
    if code != 200 or "key" not in r:
        sys.exit(f"mint failed: HTTP {code} {str(r.get('error', r))[:200]}")
    path = write_secret_file(a.out, [f"# LiteLLM virtual key {a.alias}: models {models}, budget ${a.budget}"
                                     + (f", expires {a.duration}" if a.duration else ""),
                                     f"LITELLM_API_KEY={r['key']}",
                                     f"LITELLM_API_BASE={a.base}"])
    check(True, f"minted {a.alias} (token id {str(r.get('token', ''))[:10]}), stored in {path} (600)")
    key = envfile(path)["LITELLM_API_KEY"]
    auth = {"Authorization": "Bearer " + key}
    code, rr = http(f"{LL}/v1/chat/completions", {"model": models[0], "max_tokens": 4,
                    "messages": [{"role": "user", "content": "Reply with the word ok."}]}, headers=auth, method="POST")
    check(code == 200, f"allowed model {models[0]} answers (HTTP {code})")
    _, all_models = http(f"{LL}/v1/models", headers=master())
    other = next((m["id"] for m in all_models.get("data", []) if m["id"] not in models), None)
    if other:
        code, _ = http(f"{LL}/v1/chat/completions", {"model": other, "max_tokens": 1,
                       "messages": [{"role": "user", "content": "x"}]}, headers=auth, method="POST")
        check(code in (401, 403), f"model outside the key ({other}) is refused (HTTP {code})")
    print("\nAdd this row to the credentials table in docs/recipes/agent-access.md:")
    print(f"| LiteLLM `{a.alias}` | `set -a; . {a.out}; set +a` | `LITELLM_API_KEY` (models {', '.join(models)}; "
          f"${a.budget} cap{'; expires ' + a.duration if a.duration else ''}{'; traces to Langfuse' if a.langfuse_keys else ''}) "
          f"+ `LITELLM_API_BASE={a.base}` |")


def gt_superuser(method, path, body=""):
    script = r'''
set -a; . ~/agentic-ai-homelab/infra/glitchtip/.env; set +a
GT=http://127.0.0.1:8090; CJ=$(mktemp)
curl -s -c $CJ -b $CJ -o /dev/null $GT/_allauth/browser/v1/config; CSRF=$(awk '$6=="csrftoken"{print $7}' $CJ)
curl -s -c $CJ -b $CJ -o /dev/null -H 'Content-Type: application/json' -H "X-CSRFToken: $CSRF" -H "Referer: $GT/" \
  -d "{\"email\":\"$DJANGO_SUPERUSER_EMAIL\",\"password\":\"$DJANGO_SUPERUSER_PASSWORD\"}" $GT/_allauth/browser/v1/auth/login
CSRF=$(awk '$6=="csrftoken"{print $7}' $CJ)
curl -s -c $CJ -b $CJ -w "\n%{http_code}" -X "$1" -H "X-CSRFToken: $CSRF" -H "Referer: $GT/" \
  -H 'Content-Type: application/json' ${3:+-d "$3"} "$GT$2"
rm -f $CJ
'''
    out = subprocess.run(["bash", "-c", script, "gt", method, path, body], capture_output=True, text=True, timeout=60)
    text, _, code = out.stdout.rpartition("\n")
    return code.strip(), text


def gt_tokens():
    code, text = gt_superuser("GET", "/api/0/api-tokens/")
    return json.loads(text) if code == "200" else []


def cmd_glitchtip(a):
    if os.path.exists(os.path.expanduser(a.out)):
        sys.exit(f"refusing: {a.out} exists.")
    if any(t.get("label") == a.label for t in gt_tokens()):
        sys.exit(f"refusing: a GlitchTip token labelled {a.label!r} exists. Revoke it first if unused.")
    scopes = [s.strip() for s in a.scopes.split(",") if s.strip()]
    code, text = gt_superuser("POST", "/api/0/api-tokens/", json.dumps({"label": a.label, "scopes": scopes}))
    r = json.loads(text) if code in ("200", "201") else {}
    if not r.get("token"):
        sys.exit(f"mint failed: HTTP {code}")
    path = write_secret_file(a.out, [f"# GlitchTip API token '{a.label}': scopes {scopes}",
                                     f"{a.var}={r['token']}"])
    check(True, f"minted token id {r.get('id')} '{a.label}', stored in {path} (600)")
    tok = envfile(path)[a.var]
    # Prove the token with an endpoint its scopes actually grant (org:read alone can't list projects).
    probe = ("/api/0/organizations/homelab/chunk-upload/" if "project:releases" in scopes
             else "/api/0/organizations/homelab/projects/" if "project:read" in scopes
             else "/api/0/organizations/homelab/" if "org:read" in scopes else None)
    if probe:
        code, _ = http(GT + probe, headers={"Authorization": "Bearer " + tok})
        check(code == 200, f"token authenticates ({probe} HTTP {code})")
    else:
        print("  [SKIP] no read endpoint known for these scopes; verify by hand")
    print("\nAdd this row to the credentials table in docs/recipes/agent-access.md:")
    print(f"| GlitchTip `{a.label}` | `set -a; . {a.out}; set +a` | `{a.var}` ({', '.join(scopes)}, org-wide) |")


def cmd_revoke_litellm(a):
    keys = litellm_key_by_alias(a.alias)
    if not keys:
        sys.exit(f"no key with alias {a.alias!r}")
    code, r = http(f"{LL}/key/delete", {"keys": [k["token"] for k in keys]}, headers=master(), method="POST")
    check(code == 200, f"deleted {len(keys)} key(s) aliased {a.alias} (HTTP {code})")
    check(not litellm_key_by_alias(a.alias), "alias no longer listed")


def cmd_revoke_glitchtip(a):
    toks = [t for t in gt_tokens() if t.get("label") == a.label]
    if not toks:
        sys.exit(f"no token labelled {a.label!r}")
    for t in toks:
        code, _ = gt_superuser("DELETE", f"/api/0/api-tokens/{t['id']}/")
        check(code in ("200", "204"), f"deleted token id {t['id']} (HTTP {code})")
    check(not any(t.get("label") == a.label for t in gt_tokens()), "label no longer listed")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    l = sub.add_parser("litellm")
    l.add_argument("--alias", required=True); l.add_argument("--models", required=True)
    l.add_argument("--budget", type=float, required=True); l.add_argument("--duration")
    l.add_argument("--out", required=True); l.add_argument("--langfuse-keys")
    l.add_argument("--base", default="http://homelab:4001/v1")
    l.add_argument("--owner", default="minted by mint-credential")
    g = sub.add_parser("glitchtip")
    g.add_argument("--label", required=True); g.add_argument("--scopes", required=True)
    g.add_argument("--out", required=True); g.add_argument("--var", default="GLITCHTIP_TOKEN")
    rl = sub.add_parser("revoke-litellm"); rl.add_argument("--alias", required=True)
    rg = sub.add_parser("revoke-glitchtip"); rg.add_argument("--label", required=True)
    a = ap.parse_args()
    {"litellm": cmd_litellm, "glitchtip": cmd_glitchtip,
     "revoke-litellm": cmd_revoke_litellm, "revoke-glitchtip": cmd_revoke_glitchtip}[a.cmd](a)
    ok = all(results) and results
    print("MINT: PASS" if ok else "MINT: FAIL")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
