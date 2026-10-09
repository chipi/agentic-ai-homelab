# ADR-0009 — An on-demand dev Docker engine on the mini, separate from production

**Status:** Accepted (2026-10-09)
**Date:** 2026-10-09

## Context

The Mac mini runs production in one colima VM (`_dockerhost`, qemu, 20 GiB):
observability, delivery, LiteLLM, Langfuse, GlitchTip. Until 2026-10-09 its docker
socket was `0666` and `/etc/zshenv` exported `DOCKER_HOST` to it for every account,
so other agents' development work (image builds, e2e stacks) ran in the production
VM. An e2e container publishing a port there preceded two of the three host↔VM
forward breaks (2026-09-03, 2026-10-08; the 10-08 one took the host side of
production down for 7 h —
[runbook](../recipes/colima-lima-forwarding-recovery.md)). On 10-09 the production
socket became `root:admin 0660` and the global `DOCKER_HOST` was removed, which left
development with no shared engine.

The operator's medium-term plan is to move development off the mini. Until then,
development on the mini is an exception that must stay possible, and must not cost
production memory.

Facts the decision rests on (measured 2026-10-09):

- The mini has 32 GiB and 12 threads. Container working memory in the production VM
  over 30 days: p50 4.8, p95 7.1, max 8.6 GiB (including the dev work that ran
  there). macOS swap over 30 days: p50 4.0, p95 10.2, max 14.7 GiB. Memory, not
  CPU, is the constraint.
- On the mini, agent sessions run under the `claude` account only. Sessions under the
  operator account run on the laptop and reach the mini over SSH, for production
  work.
- vz + virtiofs runs on this Intel mini (the `claude` account's own colima, since
  2026-10-08). virtiofs keeps `/Users` mounts off lima's SSH master.

## Decision

1. **A second, shared engine for development, off by default.** colima under its own
   service account `_dockerdev` (vz, virtiofs, 4 CPU / 6 GiB / 60 GiB disk). It costs
   no memory while stopped.
2. **Any local account starts and stops it** with `devengine start|stop|status`. A
   sudoers rule lets the `staff` group run exactly one fixed script as `_dockerdev`;
   no other command is allowed. `start` refuses when the host is already short of
   memory, and creates the caller's docker context `dev`.
3. **Socket** `/var/run/docker-dev.sock`, `root:staff 0660`, relayed by socat like
   production's. Production stays `/var/run/docker.sock`, `root:admin 0660`.
4. **It stops itself.** A launchd job checks every 15 min; after 30 min with no
   running container it prunes week-old leftovers (containers, images, build cache;
   never volumes) and stops the VM.
5. **Production is unchanged.** The operator account keeps the default socket, so
   every production tool, deploy and collector works as before.
6. **The contract for agents** lives in one recipe,
   [dev Docker engine](../recipes/dev-docker-engine.md): use the `dev` context, cap
   container memory, one image build at a time, label and tear down, treat the
   engine as disposable, stop it when done.

## Consequences

**Positive**

- Development can't wedge the production forward or take its memory: separate VM,
  separate lima SSH master, separate socket.
- Zero memory cost while idle; 6 GiB only while someone uses it.
- When development leaves the mini, only the `dev` context changes (for example
  `docker context create dev --docker host=ssh://<new host>`); the agents' contract
  stays the same.

**Negative**

- A cold start takes about a minute.
- Dev users share one engine: one heavy build slows the others. The contract limits
  that; nothing enforces it.
- While dev runs, the mini holds 26 GiB of VMs on 32 GiB. `start` checks free memory
  first, but a long build alongside other host load can still push macOS into swap.
- A new sudoers rule. It is scoped to one script and one target account, and the
  script accepts only `start`, `stop`, `status` and `idle-check`.

**Neutral**

- The `claude` account's private colima (2 CPU / 2 GiB) becomes redundant; retiring
  it is that account's call.
- Shrinking the production VM (20 GiB, peak use ~9 GiB) would relieve host swap. It
  is a separate decision, not a precondition for this one.

## Alternatives considered

- **One colima per agent or account.** Each VM reserves its memory; several do not
  fit beside a 20 GiB production VM. Rejected.
- **An always-on shared dev engine, paid for by shrinking production to ~12 GiB.**
  Workable (VMs would total less than today), but it costs memory all the time for
  occasional use, and the shrink needs a planned VM recreation. Kept as an option if
  dev use becomes daily.
- **Dev back in the production VM, with rules.** That is the setup that preceded
  two breaks. Rejected.
- **Make `dev` the operator account's default context.** It would have meant
  re-pointing about 15 production scripts and every deploy at the production socket,
  to guard against agents that don't run on the mini. Rejected.
