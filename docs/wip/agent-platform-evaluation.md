# Agent platform — problem, constraints, options (evaluation, 2026-11-08)

**Outcome (2026-11-08):**
- The operator chose the plain route: our own fleet platform,
  [flotilla](https://github.com/chipi/flotilla).
- It converges the triage fleet, the bugfix fleet and the daily brief, plus new SEO and ops fleets.
- Its design is [RFC-0001](https://chipi.github.io/flotilla/rfc/RFC-0001-fleet-platform/), accepted
  as [ADR-0001](https://chipi.github.io/flotilla/adr/ADR-0001-platform-foundations/).
- Hermes Agent and OpenClaw (§6) stay as inspiration.

**Status:** WIP evaluation for the operator, kept as the record of how that decision was reached.
**Input:** the operator's
*Local-First SEO Intelligence — Architecture Brief* (a proposal, treated here as one candidate
design, not the frame) and the operator's notes of 2026-11-08:
- Umami is the analytics source, and GA4 is out completely.
- Google's search data is needed.
- Model choice is ours: use the DGX's prod model, and keep one model running non-stop on the X3.

This note keeps three things apart:

1. the problem (what we want, ranked, with no technology);
2. the constraints and non-functional requirements this homelab already lives by;
3. the candidate solutions, judged against 1 and 2.

The facts in sections 2 and 3 were checked on 2026-11-08; how is given inline.

---

## 1. The problem

### 1.1 What we want

An always-on assistant layer that **watches things for the operator, investigates what it
finds, and brings back evidence-backed proposals**. Humans decide anything that changes production
or reaches the outside world.

The first and most important job is **reach**: growing the audience of the operator's sites. The
other jobs share the same platform.

### 1.2 Use-case catalogue

Ranked by the operator's priority. "Exists" marks what already runs today.

**A. Outside-in: the sites' reach** (priority 1)

| # | Use case | Question it answers | Trigger | Output |
|---|---|---|---|---|
| A1 | Search performance health | Are impressions, clicks or positions moving, per site, page and query? | daily | regressions with evidence |
| A2 | Indexing and coverage | Are pages indexed? Do sitemaps, hreflang and canonicals work? | weekly, and after a deploy | issues with the URLs |
| A3 | Search opportunities | Which pages have high impressions but a weak click-through, or rank just below page one? | weekly | ranked candidates |
| A4 | Technical crawl audit | Broken links, redirects, titles and meta, noindex, sitemap drift | weekly, and after a deploy | issues per URL |
| A5 | Content and refresh proposals | What should a page add or change, and which new page is worth writing? | weekly | drafts for review |
| A6 | Experiment tracking | Did an accepted change help? | monthly | before/after with caveats |
| A7 | Referral and community reach | Where do visitors come from (Umami referrers), and which links bring them? | weekly | trends, new sources |
| A8 | Availability and speed from outside | Is it up and fast for visitors and crawlers? | continuous | **Exists**: blackbox probes, Cloudflare edge poller, Hub Projects tab |

Orrery is the natural first site. Its sitemap was submitted to Search Console on 2026-08-28: 3,668
URLs in 14 locales. It already has a written plan with a monthly Search Console watch-list
(orrery `docs/wip/multilingual-seo-analysis.md`) that nobody runs today.

**B. Own infrastructure**

| # | Use case | Today |
|---|---|---|
| B1 | Alert and error triage | **Exists**: the triage fleet (Fleet 2), every 10 min, files proposals |
| B2 | Periodic reviews (the daily Postgres review, weekly fleet health, the o11y review after a deploy) | done by hand, through scheduled prompts in a Claude session |
| B3 | Investigation of a slowdown or an incident (traces, logs, metrics) | done by hand |
| B4 | Capacity and cost watch (mini memory, disk, spend per key) | partly in alerts and the Hub |

**C. Personal briefs**

| # | Use case | Today |
|---|---|---|
| C1 | The daily brief | **Exists**: the Hub briefing at 07:00. Code gathers the facts, an LLM writes two opening sentences, and it is pushed to the iPhone through Home Assistant. |
| C2 | Home (energy, appliances, alerts) | Home Assistant automations; the X3 model is a read-only Assist agent |
| C3 | A cross-domain weekly digest (sites, infra, home, spend) | none |

**D. Product insight** (Umami behaviour: funnels, feature use, beta users). Partly covered by
Grafana dashboards and the Hub Projects tab; no interpretation layer.

### 1.3 What is common to all of them

- data collection on a schedule;
- deterministic checks;
- an LLM step that investigates and writes;
- a reviewable output;
- a human decision;
- a measured outcome.

The platform question is how to build that loop once and reuse it.

---

## 2. Constraints and non-functional requirements (what we already live by)

| # | Requirement | Source |
|---|---|---|
| N1 | **Humans decide anything outward.** No auto-publish, no prod change, per-instance approval for destructive or shared-state actions. GitHub issues only with the operator's approval. | global AGENTS.md rules 1, 4, 35 |
| N2 | **Secrets never in git.** Credentials live in mode-600 files, every credential is recorded in the handbook's credentials table, and keys are minted with `mint-credential`. | AGENTS.md 29; `docs/recipes/agent-access.md` |
| N3 | **Tailnet only, implicit deny.** No new public ports, logins or ACL grants without approval. | chipi/infra `tailscale/policy.hujson`; AGENTS.md |
| N4 | **Every scheduled job is observable.** It pushes a `*_last_success_timestamp`, a stale alert watches it, logs go to VictoriaLogs, and LLM calls are traced (Langfuse through LiteLLM). | `rules.yaml` (hub-briefing-missing, poller-stale rules) |
| N5 | **Scheduling is launchd on the mini** (no cron), as `/Library/LaunchDaemons` plists. Long-running loops use KeepAlive. | `infra/homelab-home/README.md` |
| N6 | **Inference is local first; cloud is a per-key, budgeted, explicit choice.** Every LiteLLM alias fails loudly except one: `assistant` (the X3 model) falls back to OpenRouter, and the Hub briefing uses it. | `infra/litellm/config.yaml` |
| N7 | **Agent frameworks are not adopted by default.** ADR-0008 adopted LiteLLM, rejected CrewAI and AutoGen, and left LangGraph and Temporal out. Adopting one is an ADR. | `docs/adr/ADR-0008` |
| N8 | **Agents on the mini run as the `claude` account**, not as the operator. | ADR-0009 |
| N9 | **LLM decisions are gated.** Deterministic gates come after the LLM, and a fleet moves through shadow, then propose, then live stages with a daily budget and a STOP flag. | RFC-0004, `fleetd/README.md` |
| N10 | **Behaviour changes are replay-proven** before they ship. | `replay-proven-fix` skill |
| N11 | **Web content is untrusted input.** Prompt injection from crawled or competitor pages must not reach tools. | brief §4.7; RFC-0008 is read-only by construction |
| N12 | **The mini, planned at 64 GB.** Intel i7-8700B, 6 cores / 12 threads, macOS 15.7. Today it has 32 GB: 31 GB used and 1.3 GB unused, with load ~6 on 12 threads, 35 containers and swap p95 at 10.2 GiB. The +32 GB is bought and waiting to be fitted (operator, 2026-11-08; NEXT_STEPS), and **this plan assumes 64 GB**. Fitting it is a precondition for anything new on the mini. The prod colima VM is off-limits for dev work: trials use the dev engine (ADR-0009). | `sysctl`/`top` on 2026-11-08; ADR-0009 |
| N13 | **The DGX has one GPU shared by modes** (prod / ollama / code / research). Prod vLLM serves the nightly pipeline. DGX changes need the operator's go. | `gpu-mode` skill; infra/dgx AGENTS.md |
| N14 | **Retention:** VictoriaLogs keeps 30 days and VictoriaMetrics 6 months. Search Console keeps 16 months with no backfill of its BigQuery export, so collection must start early. | `infra/observability/backend/docker-compose.yml`; Google docs |
| N15 | **Docs and decisions in git:** an ADR or RFC for platform choices, WIP notes, and a strict mkdocs build. | docs/AGENTS.md |

---

## 3. What exists, and the facts the solution depends on

**Data sources:**
- **Umami** covers all the sites, including markodragoljevic.com and airandspacehistory.com.
- **Cloudflare:**
  - `cloudflare-edge` polls requests by class, host and source (browser, bot, assistant, monitor), plus 5xx;
  - Cloudflare's own Web Analytics runs on two sites.
- **Blackbox probes** check every public host every minute.
- **Not found** in either repo: Search Console, Bing Webmaster, sitemap checks or crawlers.
- **Search Console:**
  - Orrery is verified, and humancopilot.eu has a `google-site-verification` TXT record (humancopilot.eu ADR-0001). The other sites are not checked.
  - The Search Console API facts (Google's developer docs):
    - data arrives 2–3 days late, and partial fresh data is available with `dataState=all`;
    - 25,000 rows per request and at most 50,000 rows per day per search type;
    - anonymized queries are absent from rows;
    - access by OAuth with the `webmasters.readonly` scope;
    - URL Inspection is limited to 2,000 per day per site;
    - the Indexing API does not apply to normal pages.
- **Bing Webmaster** has an API with clicks, impressions and position, in weekly buckets, keyed by API key.

**Models:**
- **DGX prod:** `NVFP4/Qwen3-30B-A3B-Instruct-2507-FP4` in vLLM, 64k context.
  - **Tool calling is not enabled**: no `--enable-auto-tool-choice` and no `--tool-call-parser` (`docker inspect vllm-prod-vllm`, 2026-11-08).
  - Turning it on restarts the server the nightly depends on (N13).
- **X3 always-on** (`ollama-assistant.service`, tailnet `:11435`): `qwen3:30b-a3b-instruct-2507-q4_K_M`, 25.4 GB loaded, 64k context. Ollama does tool calling for it. The X3 is also the operator's workstation: 124 GB total, 27 GB available with dev work running. Larger models are installed for on-demand use: gpt-oss 120B, Qwen3.5 122B, Nemotron 3.5 Super 120B.
- So both "a model on the DGX and a model on the X3" are **the same model family**, Qwen3-30B-A3B, at two quantizations. That is good for consistency; there is no larger reasoner online by default.

**Runners:**
- `fleetd`: a Go LaunchDaemon with per-fleet interval, budget, stage and STOP flag.
- launchd jobs.
- The Hub (pages, briefing, Projects tab).
- LiteLLM, with virtual keys and budgets.

**Hermes Agent** (Nous Research; web research 2026-11-08, links in the session):
- MIT licence, Python and Node. Very active: v0.23.0 shipped 2026-11-05, with several releases a month.
- **Intel macOS is unsupported** ("no release or CI workflow builds or tests an Intel macOS bundle"). It supports Linux, Docker and Apple Silicon. pip, uv and brew installs are unsupported; it installs with a `curl | bash` script.
- **Local models:** it takes custom OpenAI-compatible endpoints (vLLM, Ollama, LiteLLM). vLLM needs the tool-call flags above, and Ollama needs a large context set server-side.
- **Fallback providers** exist only if configured.
- **Web search defaults to cloud services** (Exa, Parallel, Firecrawl, Keenable, rotating keyless) unless SearXNG or a self-hosted Firecrawl is set.
- **Tools:** shell, file write, browser, code exec, web, memory, cron, and sub-agents.
- **Execution backends:** local, Docker, SSH, Modal and others.
- **Approvals:**
  - Modes: `smart` (an LLM judges risk), `manual` and `off`, with a hard blocklist that always applies.
  - **The Docker backend skips the dangerous-command check.**
  - Open issue #60505: "Always" allowlist entries bypass `cron_mode: deny`.
- **CVEs in 2026:** at least six. Guard and injection-scanner bypasses, an `execute_code` sandbox issue, and an **RCE in the TUI gateway** (CVE-2026-14625, fixed version unverified).
- **Skills are self-written and self-edited.** Pinning stops deletion, not edits.
- **Its cron runs only while its gateway daemon runs.**

**OpenClaw:** Node. Its sandbox is **off by default**. CVE-2026-25253, a one-click RCE through the Control UI with CVSS 8.8, was fixed 2026-01-29. Its skill marketplace suffered a malicious-skill campaign in January 2026.

---

## 4. Candidate solutions

All three keep the same skeleton (§1.3). They differ in what runs the LLM step.

### Option 1 — the brief as written: Hermes on the mini, Parquet + DuckDB, Markdown findings

- **Fits:** the data design is sound and fits N14: GSC facts in Parquet with DuckDB, deterministic detectors before the LLM, and findings as Markdown with YAML frontmatter in git. So is the tool boundary (narrow `seo.*` tools, never raw SQL or shell), and so is its principle: *files own the facts, SQL owns the calculations, the agent investigates, humans decide*. All of that should carry over to any option.
- **Breaks:**
  - Hermes cannot run natively on the Intel mini. It can run as its official Linux amd64 Docker image inside colima. At 64 GB the memory (1–4 GB) fits, but its Docker backend skips the dangerous-command check. See §6 for the runtime comparison.
  - Self-editing skills and the approval gaps conflict with N9 and N10: a behaviour change would no longer be reviewed in git.
  - Its default web search breaks N6.
  - It is a framework adoption (N7) on a project with six or more CVEs in 2026 and weekly releases.
- **Verdict:** keep the data and tool design, and do not put Hermes on the mini.

### Option 2 — no new framework: deterministic collectors plus a narrow LLM step, run like our fleets

- **What it is:**
  - Collectors (GSC, Bing, sitemap and crawl, Umami, Cloudflare) run under launchd and write Parquet, plus freshness gauges for N4.
  - DuckDB detectors produce candidates.
  - An LLM step answers each candidate through LiteLLM, on the X3 model for routine work and the DGX for weekly depth. It uses structured output, or a fixed set of read-only tools served over MCP, and writes a finding file.
  - `fleetd` runs it with a budget, the shadow → propose → live stages and a STOP flag (N9).
  - Findings live in git, the Hub shows the backlog, and the operator approves.
  - The same skeleton serves the briefs (C) and the infra reviews (B2), and replaces the prompts that run them by hand today.
- **Fits:** N1–N15 as they are; it is how the briefing and the triage fleet already work. Replayable (N10), observable (N4), local (N6), no new framework (N7).
- **Costs:** less open-ended investigation. The agent cannot wander and discover; it answers the questions the detectors pose. Every new skill is code we write.

### Option 3 — Option 2's data layer, plus a sandboxed agent runtime for the investigations

- **What it is:** everything in Option 2, plus an agent runtime as the investigator for open-ended work: A5 content proposals, B3 incidents. It is OpenClaw or Hermes (§6), or opencode or Claude Code headless against local models.
  - **Where:** a Linux container, either on the mini (64 GB, its dev engine for trials) or on the X3.
  - **Toolsets:** cut down to an MCP client against our read-only `seo.*` and `obs.*` tools, plus write access to a findings directory.
  - **Off:** shell, web search (or a self-hosted SearXNG), fallback providers, chat channels and marketplace installs.
  - **Approvals and skills:** unattended approvals denied, skills frozen from a git checkout.
  - **Scheduling:** launchd/fleetd invokes it per run.
- **Fits:** it gives open-ended investigation where it pays, and keeps collection, scheduling and gating deterministic.
- **Costs:**
  - A framework under review (N7), with upgrade churn and a CVE stream.
  - Self-improvement, the main selling point of these runtimes (Hermes' especially), is the part we would switch off for N9 and N10.

### How they compare

| | Option 1 | Option 2 | Option 3 |
|---|---|---|---|
| Runs on the hardware we have | only in Docker on the mini (native Intel macOS unsupported) | yes | yes (Docker on the 64 GB mini, or the X3) |
| Meets N1, N9, N10 (gated, replayable) | weak (self-editing skills) | yes | yes, with skills frozen |
| Local only (N6) | needs config (search, fallback) | yes | needs config |
| Open-ended investigation | yes | no | yes |
| New framework (N7) | yes | no | yes, behind an ADR |
| Effort to first value (Orrery GSC) | high | lowest | medium |

---

## 5. Recommendation (for discussion)

1. **Start with Option 2's data layer for Orrery, now.** It is needed by every option and its data
   is time-sensitive (N14).
   - **Operator action:** create a Google Cloud project with the Search Console API enabled, and
     either a service account added as a restricted user on the Orrery property, or an OAuth
     client with the `webmasters.readonly` scope.
   - **Then homelab builds:**
     - a launchd GSC collector writing Parquet, with a stale alert;
     - a sitemap and hreflang checker;
     - two DuckDB detectors (A1 regressions, A3 opportunities);
     - a weekly finding report on the Hub.
   - **Start the BigQuery bulk export the same day:** it has no backfill.
2. **Run the LLM step on the X3's always-on Qwen3-30B** through a new LiteLLM alias **without**
   cloud fallback. The `assistant` alias falls back to OpenRouter, so it should not be reused for
   site data. Use the DGX prod model for weekly depth only after the operator decides on enabling
   its tool-call parser, which means a prod vLLM restart in a quiet window.
3. **Put an agent runtime through a bounded Phase 0, OpenClaw first and Hermes as the
   challenger (§6).** Run it in Docker on the mini's dev engine, after the 64 GB is fitted, or on
   the X3. Give it the same read-only MCP tools and one week of Orrery data, beside the Option 2
   step on the same candidates. Judge both by:
   - finding quality, against explicit evidence;
   - false positives;
   - whether any traffic left the tailnet;
   - whether the approval controls held.

   Adopt it only by ADR (N7), and only if it beats Option 2 on A5- and B3-type work. That is
   Option 3.
4. **Fold the hand-run reviews (B2) and the briefs (C) into the same skeleton** once A1–A3 run,
   with one runner, one findings format and one surface (the Hub).

## 6. OpenClaw versus Hermes Agent, for this job

### 6.1 What the job asks of a runtime

The job is scheduled runs that call a few read-only tools (our MCP servers), write findings files,
and use only local models. A human approves anything outward, and behaviour changes are reviewed
in git. That makes the deciding qualities:

- it runs on our hardware;
- it speaks MCP under a tool policy;
- local models work;
- it sends nothing out of the tailnet by default;
- unattended runs are denied anything risky;
- it does not rewrite its own behaviour;
- it is observable;
- the security churn is manageable.

Chat channels, self-improvement and skill marketplaces are worth nothing here, or are a risk.

### 6.2 The facts side by side

Web research of 2026-11-08: vendor docs, release pages, CVE databases, and two independent
comparisons. Neither runtime has been installed here.

| | OpenClaw | Hermes Agent |
|---|---|---|
| What it is | Node gateway as the control plane: agents, plugins, CLI/TUI, chat channels, apps. MIT, ~394k stars, OpenClaw Foundation since Feb 2026 (founder joined OpenAI). | Python+Node "self-improving" agent with a learning loop (writes its own skills, searches past sessions). MIT, ~262k stars, Nous Research. |
| Release cadence | calendar versions, several stable and beta per week (v2026.11.1 on 11-05) | several a month (v0.23.0 on 11-05) |
| **Intel Mac mini (macOS 15.7)** | **npm gateway:** no stated OS or arch limit, Node 26.5 already on the mini; 15.7/Intel itself unverified. **Docker:** official amd64 image, so yes inside colima. **macOS app:** no (needs macOS 26.2). | **Native:** unsupported (no Intel macOS build or CI). **Docker:** yes (amd64 image) inside colima. |
| Linux (X3) | yes | yes |
| Footprint | ~150–500 MB idle, 2 GB+ recommended (third-party) | 1–4 GB, 2 GB+ with a browser (third-party) |
| Local models | any OpenAI-compatible server (vLLM, LiteLLM). Ollama through its native API only: its `/v1` breaks tool calls. Docs warn about small local models; a field report found 25k-token system prompts overflowing small contexts. | custom OpenAI-compatible endpoints; vLLM needs tool-call flags; set Ollama's context server-side |
| Cloud egress by default | a daily version check. Web search only with a configured key; keyless providers never auto-selected. LLM fallback only if configured. | **keyless cloud web search rotation** (Exa, Parallel, Firecrawl, Keenable) unless SearXNG is set. LLM fallback only if configured. |
| MCP | full client (HTTP, SSE, stdio), subject to the tool policy | client; server mode since v0.5 |
| Unattended runs | exec security deny / allowlist / full. With no approver connected, a request is **denied** (unless `askFallback` says otherwise). | `cron_mode: deny` by default, but **"Always" allowlist entries bypass it** (open issue #60505) |
| Sandbox | **off by default**. Docker, Podman or SSH when on; the gateway always runs on the host; `tools.elevated` escapes it. | local, Docker, SSH or Modal backends. **The Docker backend skips the dangerous-command check.** |
| Self-modification | skill writing ("Skill Workshop") is **experimental, off by default**, with a pending-approval option | **core feature**: the agent creates and edits skills; pinning stops deletion, not edits |
| Skills marketplace | ClawHub, hit by the ClawHavoc campaign (1,184 malicious skills; some passed scanning after Feb). Install policy and verify commands now exist. | community skills; not researched |
| Scheduler | in the gateway, persisted in SQLite; the gateway must run; **missed runs are rescheduled, not replayed** | in the gateway daemon, a 60 s tick; must be running |
| Observability | official OpenTelemetry plugin (traces, metrics, logs over OTLP), a Prometheus diagnostics endpoint | opt-in OpenTelemetry plugin |
| **2026 security record** | **131 CVEs (5 critical, 67 high), all five criticals fixed**; ~700 GitHub advisories; ~40k instances found exposed on the internet | 6+ CVEs, guard and scanner bypasses; CVE-2026-14625 is an authenticated RCE (CVSS 6.3) with a public PoC and **no confirmed fix; the vendor did not respond**; no published GitHub advisories |
| Independent tests | one homelab bake-off (2026-06-11, 14B local model, MCP tools): OpenClaw 91.0 vs Hermes 75.8 of 500, OpenClaw won 4 of 5 tasks; "local models are for tinkerers". Reviews: OpenClaw for reliable scheduled automation, Hermes for self-improvement. | |

### 6.3 Judgement for this job

**OpenClaw fits the job better than Hermes. Neither is needed for the core, and OpenClaw's security
churn is the price.**

- **Hardware.** OpenClaw is the only one with a chance of running natively on the mini, and both
  run in Docker inside colima. With 64 GB either fits. Prefer Docker on both counts: one supported
  path, and isolation from the host.
- **Our rules (N6, N9, N10).** OpenClaw's defaults are closer:
  - self-modification is off;
  - search does not silently go to the cloud;
  - an unattended run with nobody to approve is denied.

  Hermes's defining feature, the learning loop that rewrites its skills, is exactly what we would
  have to switch off. Its unattended-approval gap (#60505) is open, and its Docker backend drops the
  command check.
- **Security.** OpenClaw has a vastly larger CVE volume, fixed fast but needing weekly upgrades, and a
  marketplace that has been attacked. Hermes has far fewer, but one RCE has an unconfirmed fix and a
  silent vendor. Fewer CVEs is partly a smaller install base, not proof of safety. For us the
  exposure is set by configuration:
  - the gateway bound to loopback inside the container;
  - no chat channels;
  - no marketplace installs (skills from our git checkout only);
  - exec denied, sandbox on, and only our MCP tools enabled.

  Either needs a pinned version and a weekly upgrade check.
- **Local models.** Both work with our OpenAI-compatible endpoints through LiteLLM. OpenClaw
  documents the small-model pitfalls (prompt size, fake tool calls) and did better in the one local
  bake-off. Neither has been measured with Qwen3-30B-A3B on our tasks.
- **Scheduling.** Both schedulers live inside their own daemon and do not replay missed runs. That
  is not N4/N5. Keep scheduling in launchd/fleetd and invoke the agent per run, and keep the
  freshness metric and stale alert on our side.

**So:** if Phase 0 shows that open-ended investigation is worth a runtime (A5 content proposals, B3
incidents), trial **OpenClaw first, Hermes as the challenger**, both on the same tools and data, and
adopt one by ADR (N7). Until then, Option 2 needs neither.

### 6.4 Can OpenClaw run on the Mac mini?

**Yes, in Docker; probably natively; not as the app.**

- **Docker:** the official image is built for linux/amd64, and colima runs linux/amd64 containers.
  This is the supported path and the one to use: it isolates the agent from the host and the
  operator's files, and fits N8 when run as its own container. Memory is 150–500 MB idle, 2 GB+
  recommended. After the 64 GB upgrade that is no concern; today, at 1.3 GB unused, it is.
- **Native npm gateway:** OpenClaw needs Node 24.16+ or 26.1+, and the mini has Node 26.5.0 for
  both the operator and the `claude` account. No doc limits the gateway's OS version or architecture,
  but no source confirms macOS 15.7 on Intel either. Unverified; a 10-minute install on the dev
  account would settle it. Running natively on the host is the riskier option anyway (the gateway
  is never sandboxed).
- **macOS app:** no. It needs macOS 26.2 Tahoe, and the 2018 Intel mini runs 15.7.

### Decisions for the operator

- Which Google access to set up: a service account added to each Search Console property, or an
  OAuth client. And which sites first: Orrery, then which?
- Whether to add Bing Webmaster (API key) alongside.
- Cloud inference for this platform: none (the brief's rule), or allowed per key with a budget as
  elsewhere.
- Whether and when to enable tool calling on the DGX prod vLLM, which needs a restart.
- Whether the X3 model may become a 24/7 service dependency, given that the X3 is a workstation.
- Where findings live: a new repo `seo-intelligence` as the brief proposes, or a directory in an
  existing one.

### Not covered by this evaluation

- I have not installed or run Hermes or OpenClaw. Everything about them comes from their docs,
  release pages, CVE databases and two independent comparisons; third-party footprint figures are
  unverified.
- I have not checked:
  - whether OpenClaw's npm gateway runs on macOS 15.7 Intel;
  - whether OpenClaw's onboarding pre-fills a cloud provider;
  - whether Hermes runs automatic update checks or telemetry;
  - the OpenClaw Foundation's funding and council.
- I have not checked the fixed version for Hermes's CVE-2026-14625; none is confirmed.
- I have not measured tool-call reliability of Qwen3-30B-A3B, on Ollama or on vLLM, on our own
  tasks.
- I have not checked which of the sites besides Orrery and humancopilot.eu are verified in Search
  Console.
- I have not costed the mini's memory for Parquet, DuckDB and a crawler; that depends on site count
  and crawl size.
