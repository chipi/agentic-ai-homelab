# LibreChat slim deploy

> **Status: v0.1 placeholder.** Real templated compose lands in v0.2 per
> `docs/wip/NEXT_STEPS.md`. The session that produced the source compose
> is recorded in `docs/history/0001-genesis.md` Phase 5.

## What goes here (target state)

Templated slim 3-container deploy of LibreChat for mobile-friendly chat
with the local vLLM + cloud LLM providers:

- `librechat-api` — Node app, port 3080
- `librechat-mongodb` — chat history, user data
- `librechat-meilisearch` — chat search

Skips:
- `nginx` client (tailnet handles transport encryption)
- `vectordb` + `rag_api` (deferred — add only when you actually want RAG)

## Pre-wired vLLM endpoint

The `librechat.yaml` declares the local vLLM coder model as a custom
OpenAI-compatible endpoint. `host.docker.internal` lets the api container
reach the vLLM service running on the same host but in a different
compose project.

## Mobile access flow

1. Start the LibreChat stack on the homelab host.
2. Open the Tailscale ACL on port 3080.
3. From phone (Tailscale connected): visit `http://<host>:3080`.
4. Register the first user (any email/password — mongo just stores it).
5. Lock down registration:
   ```
   sed -i 's|ALLOW_REGISTRATION=true|ALLOW_REGISTRATION=false|' .env
   docker compose restart api
   ```
6. Pick "vLLM Coder-Next (DGX)" endpoint in the chat UI.

## Reference source

The actual working compose lives on the operator's DGX at
`~/docker-compose/librechat/`. Until templated and committed here, that
is the canonical reference.

## Open in v0.1

- [ ] `docker-compose.yml` — templated slim deploy.
- [ ] `librechat.yaml.example` — vLLM custom endpoint + placeholders for
      Claude/OpenAI/Gemini cloud endpoints.
- [ ] `.env.example` — with auto-secret-generation hint
      (`openssl rand -hex 32` for `CREDS_KEY`, etc.).
- [ ] `README.md` — RAG add-on path, MCP add-on path, lockdown checklist.
