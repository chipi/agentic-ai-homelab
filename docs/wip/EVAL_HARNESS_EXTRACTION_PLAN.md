# Extracting the eval harness into its own public repo

**Written 2026-09-26.** Follows the playbook in
`podcast_scraper:docs/guides/SPLITTING_A_SURFACE_INTO_A_PRIVATE_REPO.md`, which was written
from what the eval-data split cost. This is the second use of it, and the first where both
sides stay public.

Target repo: **`chipi/eval-harness`**, public.

---

## The one rule that decides everything

**The harness is the product; the summarisation run is one example of using it; the
findings are neither.**

That sentence decides every placement below. It is also why the current layout is wrong:
the harness lives *inside* `examples/`, which reads as though it were an example. Its own
Makefile header already contradicts that — "Drop this directory into a project … and the
loop below works."

What does NOT move: `infra/litellm/`. The proxy declares the 24 `eval-*` aliases the
harness calls, and it is runtime infrastructure this homelab owns. The new repo will
depend on a proxy it does not own — the same shape `podcast-scraper` has as a pinned
dependency of the eval-data repo, and the same shape that has worked there.

## Why this split is unusually cheap

Verified, not assumed. The harness and the example reference **nothing** outside
themselves — no `../..`, no `agentic-ai-homelab`, no `infra/` paths:

```
$ grep -rn '\.\./\.\./\|agentic-ai-homelab\|infra/' eval-harness/scripts eval-harness/Makefile \
    summarization-cnn-dailymail/*.py summarization-cnn-dailymail/*.toml
(no matches)
```

The only outward contract is `.env`: `LITELLM_BASE_URL`, `LITELLM_API_KEY`, and provider
keys. Dependency runs one way — homelab → harness — and never back.

## History: fresh commits, not a filter-repo transplant

The 24 commits stay in homelab, where they are now merged into `main` and permanent. The
new repo receives the files with commits that explain what arrived and why, which is how
`podcast-scraper-eval-data` was built ("Receive the rest of the eval surface: 202 paths").

The cost is real and stated: `git log` in the new repo will not explain why
`_TIE_TOL` is `1e-9`, or why the band-walk was deleted. `research/NOTES.md` — the
append-only journal, 46 entries — carries that reasoning and travels with the code, which
is the mitigation. A reader who needs the commit-level record has it in homelab.

---

## Target structure

```
eval-harness/
├── README.md              what an eval is, and the loop
├── LICENSE                new — the repo is standalone
├── CONTRIBUTING.md        new — how to add an example
├── harness/               was examples/eval-harness   (75 tracked files)
├── examples/
│   ├── _shared/hf_identity.py
│   └── summarization-cnn-dailymail/                   (59 tracked files)
└── research/
    ├── REPORT.md  NOTES.md  PLAN.md  HANDOVER.md
```

`research/` is separate from `examples/` because the report and journal are findings about
24 models on one corpus: the most interesting thing in the repo and the least reusable.
Someone adopting the harness should not have to step over 1,600 lines of journal to reach
`INTEGRATION.md`.

---

## Arc 1 — make the new repo real. Change NOTHING in homelab.

Copying *in* does not authorise deleting *there*. Arc 1 can be wrong without breaking
anything, and it gives the window in which equivalence is proved while both copies exist.

| # | step | done when |
| --- | --- | --- |
| 1 | create `chipi/eval-harness`, public, empty | clone exists |
| 2 | copy the three surfaces into the new layout | `git status` shows only intended paths |
| 3 | rewrite the paths that assume the old layout — `_ROOT`/`parents[N]` in scripts, `fetch.py`'s `parents[1]`, the Makefile's relative `CONFIGS`, the `_shared` import | no path resolves outside the repo |
| 4 | README, LICENSE, CONTRIBUTING | a stranger can run `make demo` from the README alone |
| 5 | **`make ci` green in the new repo** | validate + self-tests pass there |
| 6 | **`make demo` green from a fresh clone** | the bundled synthetic loop runs with no keys |
| 7 | **one real arm end to end** against the proxy | a run directory with a valid fingerprint |
| 8 | `gitleaks` over the whole new history | no leaks |

**Gate for arc 2: steps 5, 6 and 7 all pass.** Not 5 alone — `make ci` passes on a repo
whose data directory is empty, which is exactly how the flan-t5 cache bug hid.

## Arc 2 — delete from homelab, fix every caller.

Only after the arc-1 gate. A pure deletion, reviewable as one.

| # | step | note |
| --- | --- | --- |
| 1 | three sweeps for references — by the word `eval-harness`, by the word `eval-` alias names, and **by path** | the third is the one that works; the first two missed whole directories in the last split |
| 2 | who **writes** here, not just reads | grep the paths as write targets, not only as imports |
| 3 | update the four docs that link the harness | `docs/index.md`, `cloud-ai-workflow.md`, `reading/llm-end-to-end.md` |
| 4 | leave `docs/history/0003-v0.2-arc.md` factual | history says what was true then; it is not updated to match the present |
| 5 | `git rm -r examples/eval-harness examples/summarization-cnn-dailymail examples/_shared` and the four top-level docs | |
| 6 | **delete the empty directories** | an empty leftover makes `import pkg.sub` still succeed as a namespace package |
| 7 | keep `infra/litellm/` and point its README at the new repo | the proxy stays; its consumer moved |
| 8 | homelab `README`/`docs/index.md` gain one line pointing at the new repo | |

**Port first, then rebase.** While arc 2 is open, homelab `main` keeps moving. A
delete/modify conflict git shows you; an **add** on the homelab side into a directory arc 2
deletes shows you *nothing* and is silently lost. That happened in the last split.

---

## Verify by breaking

Per the playbook: when a check passes, ask what would make it fail. For each arc-1 gate:

- `make ci` — plant a schema violation; it must fail. It passed for weeks over a data
  directory with nothing in it.
- `make demo` — remove a bundled source item; it must fail, not skip. **Never skip on a
  missing committed fixture.**
- the real arm — point `LITELLM_BASE_URL` at a dead port; warm-up must refuse before the
  first billable call, which is the behaviour that already saved this project once.

## Open, not mine to decide

- **Does journal entry 43 travel?** It names `podcast-scraper-eval-data` and reproduces
  its judge research — the dual-judge design, the score blend, the trust-matrix
  correlations. That is already public in homelab, so extraction discloses nothing new,
  but a standalone repo reads as a deliberate publication in a way a folder in a homelab
  does not.
- **Licence.** The repo ships no corpus (download recipe only), so the choice is about the
  harness code and the findings, not about data.
- **Does `claude-api-with-caching` / `mcp-tool-template` follow later?** They stay for now;
  nothing here depends on them.
