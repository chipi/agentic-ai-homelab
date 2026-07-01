---
name: homelab-endpoint
description: Resolve a homelab service name to its real endpoint URL and how to call it — DGX host, vLLM coder-next/autoresearch slots, Ollama, observability labels. Use when an agent or client needs to point at a homelab service, when writing config that consumes one, or when asked "what's the URL for X". Read-only.
---

# homelab-endpoint

Resolve a homelab service to a concrete endpoint + how to consume it. Read-only.
Source of truth for the namespace and the `${VAR}` substitution convention:
`docs/recipes/consuming-homelab-services.md`.

## The namespace (canonical values)

Host: `DGX_TAILNET_HOST = dgx-llm-1.tail6d0ed4.ts.net` (use anywhere on the
tailnet) · `DGX_LAN_IP = 192.168.0.59` (same-LAN only).

| Service | Base URL | model / notes |
|---|---|---|
| coder-next vLLM | `http://${DGX_TAILNET_HOST}:9000/v1` | model `coder-next`, bearer `buddy-is-the-king`; needs gpu-mode **code** |
| autoresearch vLLM | `http://${DGX_TAILNET_HOST}:8003/v1` | model `autoresearch`, bearer `buddy-is-the-king`; needs gpu-mode **research** |
| Ollama | `http://${DGX_TAILNET_HOST}:11434` | metrics exporter on `:9778` |
| Observability (PromQL labels) | — | `instance="homelab-1"`, `cluster="homelab"` |

## Resolve

- Default to `DGX_TAILNET_HOST` (works anywhere on the tailnet); use `DGX_LAN_IP`
  only when the consumer is on the same LAN.
- The two vLLM slots are **mutually exclusive** on the GPU — a slot is only live
  when its gpu-mode is active. Check with the `gpu-mode` skill before assuming
  `:9000` or `:8003` answers.

## Report

Print the full base URL + `model` name + auth header (`Authorization: Bearer …`),
and note the gpu-mode dependency for the vLLM slots.
