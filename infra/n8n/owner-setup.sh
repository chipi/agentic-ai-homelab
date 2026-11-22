#!/bin/bash
# Create n8n's owner account once, on the mini, after the first `docker compose up -d`.
# Writes the login to ~/n8n/owner.env (mode 600) unless it exists, then calls n8n's own setup endpoint
# from inside the container (nothing is published on the host). Prints no secret. Idempotent: an
# owner that already exists is reported, not replaced.
set -euo pipefail
umask 077
F="$HOME/n8n/owner.env"
mkdir -p "$HOME/n8n"; chmod 700 "$HOME/n8n"
if [ ! -f "$F" ]; then
  printf 'N8N_OWNER_EMAIL=operator@homelab.local\nN8N_OWNER_PASSWORD=%sAa1\n' "$(openssl rand -hex 20)" > "$F"
  echo "wrote $F"
fi
chmod 600 "$F"
set -a; . "$F"; set +a
docker exec -i -e N8N_OWNER_EMAIL -e N8N_OWNER_PASSWORD n8n node - <<'JS'
const body = {email: process.env.N8N_OWNER_EMAIL, firstName: "Homelab", lastName: "Operator",
              password: process.env.N8N_OWNER_PASSWORD};
const base = "http://127.0.0.1:5678";
(async () => {
  const r = await fetch(base + "/rest/owner/setup", {method: "POST", headers: {"content-type": "application/json"},
                                                     body: JSON.stringify(body)});
  const t = await r.text();
  if (r.ok) { console.log("owner created:", body.email); return; }
  if (/already|setup/i.test(t) && r.status === 400) { console.log("owner already set up (HTTP 400)"); return; }
  console.log("owner setup FAILED: HTTP " + r.status + " " + t.slice(0, 200)); process.exit(1);
})();
JS
# prove the login works (a wrong password would be 401)
docker exec -i -e N8N_OWNER_EMAIL -e N8N_OWNER_PASSWORD n8n node - <<'JS'
(async () => {
  const r = await fetch("http://127.0.0.1:5678/rest/login", {method: "POST", headers: {"content-type": "application/json"},
    body: JSON.stringify({emailOrLdapLoginId: process.env.N8N_OWNER_EMAIL, password: process.env.N8N_OWNER_PASSWORD})});
  console.log("owner login: HTTP " + r.status); process.exit(r.ok ? 0 : 1);
})();
JS
