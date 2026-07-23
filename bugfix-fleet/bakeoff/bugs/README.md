# Bug manifests — the upping-level matrix

Levels per BAKEOFF §6.1 (L0 raw · L1 normalized+acceptance, no file/function ·
L2 localized). The **canonical files** (no suffix) are the gate set — all 5
verified PASS on `pi + deepseek-v4-pro` 2026-07-23 — and each *is* one cell of
the matrix; `-LN` variants fill the rest. Never edit a canonical description
without re-running the gate.

| Bug | L0 | L1 | L2 |
|---|---|---|---|
| fly-physics | `-L0` | `-L1-noctx` *(pure)* · `-L1` *(+doc substrate)* | **canonical** |
| credits | `-L0` | `-L1` | **canonical** |
| look-angles | `-L0` *(= original wrong-layer RA/Dec ticket)* | `-L1` | **canonical** |
| 335-mission-event-merge | `-L0` | **canonical** | `-L2` |
| mission-arc | `-L0` | **canonical** | `-L2` |

Measured (pi+v4-pro, n=1 per cell, 2026-07-23 — full matrix, BAKEOFF §6.3):
all 5 canonical PASS (the gate); L0: only 335 PASS, other four FAIL;
L1 variants: credits + look-angles PASS, fly-physics `-L1-noctx` FAIL /
`-L1` (+doc substrate) PASS; L2 variants (335, mission-arc): PASS.
Min upping-level per bug: 335=L0 · credits/look-angles/mission-arc=L1 ·
fly-physics=L2-or-L1+doc.

k=3 (2026-07-24, five decisive cells, BAKEOFF §6.3): credits-L1 3/3 PASS ·
look-angles-L1 3/3 PASS · mission-arc-L0 0/3 (scope=yes in 2/3 — acceptance
gap, not localization) · fly-physics-L1-noctx 0/3 (decoy `orbital.ts` every
run) · fly-physics-L1+doc **1/3** — the doc-flip PASS was the outlier;
fly-physics' effective min level is L2.

Doc-flip cells (`-L0-doc`, same L0 tickets + module docs from
`../substrates/`): 0/4 verdict flips, 3/4 scope flips to the correct file
(all but fly-physics). Docs rescue localization; acceptance must come from
the ticket — see BAKEOFF §6.3.

Authoring rules used:
- **L0** — realistic degraded reporter ticket: true symptom, visible layer,
  no acceptance criteria, no localization. Never invents facts.
- **L1** — symptom + expected behavior + acceptance + domain facts the repo
  can't supply (e.g. credits' agency→section mapping). Data-level identifiers
  (section ids, WGS84 radii) are acceptance criteria, allowed; file/function
  names and implementation hints (e.g. "match on token boundaries") are not.
- **L2** — L1 + exact target file and function pinned; decoys warned off
  where they exist.
- Substrate (`context_files` in the manifest) is a separate axis from the
  level — substrate files live in `../substrates/`, injected by `run.sh` as
  committed problem state.

`dropped/` holds bugs that failed the solution-agnostic-oracle bar (see its
README).
