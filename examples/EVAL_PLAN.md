# Eval plan — making the 20-article experiment correct

Companion to `EVAL_NOTES.md`. The notes are an append-only journal of what happened;
this is the forward plan, and it **is** edited as we go. When a phase completes, the
outcome gets appended to the journal, not written back here.

Scope decision (journal entry 17): **n stays at 20.** We are not scaling. The goal is
not to rank 24 models — it is proven impossible at this n — but to make a small
experiment *correct*, and to report honestly what it can and cannot support.

---

## Part 1 — Concepts, explained

Terms used in the journal without being defined. Each one matters for a decision
below, so none of this is decoration.

### Why "significance" is doing so much work here

Every arm's score is a sample. Run it again and you get a different number — at
temperature 0, 11 of our 24 arms produced *zero* byte-identical repeats. So when arm A
scores 0.2682 and arm B scores 0.2550, the real question is not "is 0.2682 bigger"
(it is) but "if I ran this again, would A still be ahead?" A significance test answers
that second question. Everything below is machinery for asking it properly.

### Paired vs unpaired

Unpaired: average A's 20 scores, average B's 20 scores, compare the averages. Paired:
compare A and B **on article 1**, then on article 2, and so on, and look at the 20
differences. Pairing is stronger because it cancels the article — and in our data
**66% of all variance is between articles** versus 3% between arms, so refusing to
cancel it means drowning the signal in the thing we do not care about.

### The permutation test (our "global test")

Question: is there *any* arm effect at all, or could this table have come from 24
identical models? Method: inside each article, randomly shuffle which arm got which
score — this is exactly what the world looks like if arms do not matter. Recompute the
spread between arm means. Repeat thousands of times. If the real spread is bigger than
almost every shuffled one, arms matter.

Result on our data: p = 0.007 across all 24 arms — **something is real**. p = 0.58
restricted to the top 12 — **nothing is real up there**. It is a yes/no gate before
any ranking is attempted, and our top 12 fail it.

### Rank confidence intervals (replacing bands)

Resample the 20 articles with replacement 5000 times. Each time, recompute every arm's
mean and re-rank all 24 from scratch. Arm X lands at rank 1 in some resamples, rank 7
in others. Report the middle 95% of the ranks it visits.

```
  llama_l      P(rank 1) = 0.68    95% rank interval [ 1, 10]
  qwen_m                           95% rank interval [20, 24]
```

No walk, no starting point, no threshold. This is the direct fix for the
direction-dependence defect: there is no direction to depend on.

### Multiplicity, Holm, and the winner's curse

With 24 arms there are 276 possible pairs. At a 5% error rate you expect ~14
false "significant" results from pure noise. We observed 39 raw, which is more than
14 — so there is structure — but **Holm correction leaves zero** of the 276 standing.
Holm is the standard adjustment: sort the p-values, demand progressively stricter
thresholds down the list.

Winner's curse: the arm that happens to top a noisy table is disproportionately likely
to have been *lucky*, so its measured lead overstates its true lead. Ours moves between
0.005 and 0.019 under leave-one-article-out, which is most of the lead itself.

### The length confound, and what "recall@37" fixes

ROUGE compares n-grams between the model's summary and the reference.

- **Precision** — what fraction of what the model wrote appears in the reference. Write
  less, score higher. ρ(words, precision) = **−0.845**.
- **Recall** — what fraction of the reference the model covered. Write more, score
  higher. ρ(words, recall) = **+0.795**.
- **F1** — their harmonic mean, still length-sensitive: ρ = **−0.400**.

So picking recall over F1 does not remove the length effect, it *flips* it. Both are
contaminated. **recall@37** — score recall using only the first 37 words of each output
(37 = the gold mean) — removes the length advantage by construction, because every arm
is judged on the same budget. ρ(words, recall@37) falls to **+0.36**. Under it,
`anthropic_l` drops from 1st to 8th: its recall crown was length, not content placed
early.

### rougeL vs rougeLsum

`rougeL` finds the longest common subsequence across the whole text as one string, so
it punishes a model for ordering the same facts differently across sentences.
`rougeLsum` does it per sentence and combines. Our outputs are 2–3 sentences and the
CNN/DailyMail literature reports `rougeLsum`. Using `rougeL` makes our numbers
non-comparable to every published number on this dataset for no benefit.

### Why grounding is not the neutral facet I implied

`grounding` = share of the summary's bigrams that also appear in the source article.
High means extractive (copied), low means abstractive (rephrased) — and it cannot tell
a good paraphrase from a fabrication. It is also **not length-neutral**:
ρ(words, grounding) = +0.25, ρ(recall, grounding) = +0.48. Keep it, but state this.

### Pareto frontier / dominated

An arm is **dominated** if some other arm is at least as good on quality *and* cheaper
*and* faster. Dominated arms are off the table regardless of your budget. The rest form
the **frontier** — the real menu. Our frontier changed completely between F1 and
recall, but since both are length artifacts, neither frontier is currently meaningful.
It must be recomputed on length-controlled facets.

### Reasoning tokens, `usage`, `finish_reason`

A reasoning model produces hidden tokens before its visible answer. You are billed for
them and they are reported in the API response under
`usage.completion_tokens_details.reasoning_tokens` — but only if you keep the response.
We do not, so we have to infer from the ratio of billed tokens to visible words:
`anthropic_l` 2.24, `anthropic_m` 2.21, everything else 1.27–1.47, including
`anthropic_s` at 1.42. `finish_reason` separately tells us whether output was cut off
at `max_tokens`, which would silently truncate a summary and score it as bad writing.

---

## Part 2 — The plan

Phases are ordered by dependency. Everything in phases A–C is free and offline.

### Phase A — Instrumentation (no API calls, $0)

**A1. Persist the raw response metadata.** Store `usage` in full (including
`completion_tokens_details`) and `finish_reason` on every prediction row. *Gates the
entire reasoning question — nothing else in phase D can be answered without it.*

**A2. Record the upstream model, not our alias.** The fingerprint currently stores
`eval-opus-5`, a name we invented. Resolve it through the proxy's `/model/info` at run
time and store the upstream id plus whatever version string the response carries.
Re-pointing an alias must change the fingerprint.

**A3. Fix `model.declared`.** It is a boolean named as though it holds a value, and it
is identical across all 24 arms because it means "yes". Either give it the declared
string or rename it.

**A4. One dirty flag, and make it loud.** `build.dirty: false` and
`instrument.harness.dirty: true` currently coexist in one `metrics.json` meaning
different things. Reconcile to one, and print a visible warning when a run executes
against a dirty tree — all 72 of our runs did, so `harness.commit` does not identify
the code that produced them.

**A5. Fix the silver manifest.** Today it records an alias (`eval-claude-opus`) that is
not in `model_provenance.json`, no params, no prompt sha, no reasoning setting — and an
**absolute home path** (`/Users/claude/projects/...`) committed to a public repo. Make
paths repo-relative, and record what was actually sent.

### Phase B — Scoring (no API calls, $0)

**B1. Format compliance as a real metric.** Chain-of-thought markers, label prefixes,
bullets, leading markdown — computed over every output inside `score()`, not read by
eye. This is the direct fix for the mistake in journal entry 8, where 5 outputs were
read and 65 were contaminated.

**B2. Length-controlled facets.** Replace the current quality set with:
coverage = **rougeLsum recall@37**, concision = **rougeLsum precision**, plus
`grounding` kept with its caveat stated. Drop one of rouge2/rougeL F — they correlate
at 0.83 and therefore do not disagree, which was the whole point of having facets.
Print `summary_words` beside every quality column.

**B3. Rank intervals and the global test replace bands.** Delete the band logic. The
leaderboard prints the permutation p-value first, and refuses to present an ordering at
all when it fails. Then rank intervals per arm.

**B4. Recompute the Pareto frontier** on the length-controlled facets.

### Phase C — Naming ($0)

**C1. `tier` → `price_tier`** in every config, and delete every size claim from docs and
from the journal's forward-looking text. All eight families confound tier with model
generation (entry 9); the axis is the vendor's price ladder, nothing more.

### Phase D — Reasoning (~$0.50, after A1)

**D1. Probe.** For `opus-5`, `sonnet-5` and `glm-5`: one article each under
`reasoning: {enabled: false}`, then `reasoning_effort: "none"` / `"minimal"`, then with
no reasoning field at all. Compare `usage.completion_tokens_details.reasoning_tokens`
across the four. ~20 calls.

**D2. Decide per model, by the rule we already applied.** If a model cannot be made to
answer without reasoning, it does not belong in a reasoning-off comparison — the same
rule that excluded opus-5.5 and qwen3.8-max. Either it runs clean, or it is dropped
with the reason recorded.

**D3. Re-run only the affected arms** at n=20/r=3 (~$0.30), and count `glm_l`'s four
leaked outputs as format failures rather than quietly averaging them in.

### Phase E — Silver as a measured proxy (~$1.00)

Treated properly in Part 3 below.

---

## Part 3 — Silver, reframed

The earlier critique — "silver is circular" — attacked a use we are not making. It is
right about one thing only: **an author that also competes will score itself first.**
Opus authored silver and ranked 1st against its own references while gold ranks it
13th. That is an artifact of letting a contestant be the judge, and it is fixable by
not doing that.

The actual purpose stands, and it is the normal case in practice:

> When there is no human ground truth — which is most of the time — silver is the best
> available proxy for what a human would have written. It is chosen on **quality alone**,
> ignoring cost and latency, because the author is a labeller that runs once offline,
> not a system that runs a million times in production. You then use it to find the
> best arm you can actually *afford*.

This example is unusual and valuable precisely because **gold exists here**. So we can
do what almost nobody does: measure how good the proxy is.

### The experiment

1. **Pick candidate authors.** Three, chosen for different reasons: the arm closest to
   gold (`llama_l`), the most expensive arm (`anthropic_l` — the assumption we want to
   test), and one cheap strong arm (`deepseek_s`).
2. **Author silver with each**, using the same `prompt.txt`, same temperature, same
   reasoning setting as the arms. Three silver reference sets, 20 items each. ~$1.00.
3. **Score all 24 arms against each silver**, exactly as they were scored against gold.
4. **Measure the proxy.** For each silver: Spearman ρ between its arm ranking and
   gold's; how far the top-5 moves; and whether it preserves the *decision* (which
   affordable arm you would pick).
5. **Exclude the author's own row** from its own correlation. A contestant does not
   judge itself.

### What each outcome teaches

- **High ρ for all three** → silver is a sound proxy on this task, and the choice of
  author barely matters. Strongest possible result for the method.
- **High ρ only for the gold-closest author** → silver works, but choosing the author
  requires gold, which defeats the purpose. That is a *limitation finding*, and an
  important one.
- **High ρ for the expensive author** → the "most expensive is the ceiling" heuristic
  is vindicated, and we would say so despite having argued against it.
- **Low ρ for all** → LLM-authored references do not proxy human ones on this task.
  Also publishable, also useful.

### Known bias to measure, not assume

Silver runs **1.70× longer than gold** (62.4 vs 36.7 words). Given Part 1's length
analysis, a longer reference systematically favours verbose arms. So every silver
correlation gets computed **twice** — raw, and on recall@37 — and the gap between
those two numbers *is* the length-bias measurement.

Note: my earlier claim that gold-vs-silver ρ was +0.125 was wrong; it is **+0.473**
(F1) and **+0.739** (recall). Silver is a better proxy than I said, which makes this
experiment more interesting, not less.

---

## Part 4 — What we are deliberately not doing

- **Not scaling past 20 articles.** Decided. The honest finding at n=20 is a statement
  about what a small eval supports, and that is the lesson worth teaching.
- **Not correcting the journal.** It is append-only; wrong entries stay, with
  corrections appended beneath them.
- **Not adding a guard against `make clean`.** The rule (nothing is deleted without
  agreement) is the fix; more machinery is not.
- **Not chasing a ranked top-6.** It needs n in the low thousands and would resolve
  differences that are output-length policy, not quality.
- **Not adding more quality metrics** until the length confound is controlled. More
  contaminated numbers is not more information.

---

## Part 5 — How we compare, decided

The band-walk is deleted. It was a sequential pairwise algorithm whose answer depended
on traversal direction — a sorting artifact, not a comparison. Replaced by three
order-independent readings, all computed over the whole table at once.

**1. Friedman test — the gate.** Rank every arm *within* each article (1 = best), then
ask whether the average ranks are further apart than chance. No arm is privileged, no
pair is visited in sequence. Verdict on our data: permutation p = **0.0316** — an arm
effect exists.

**2. Nemenyi critical difference — all pairs, one threshold.** From k (arms) and N
(articles) alone, a single number: how far apart two average ranks must be before the
pair is distinguishable. Applied to all 276 pairs simultaneously, symmetric, no
ordering. Verdict: CD = **8.13** rank positions against an observed span of **7.85**.
**0 of 276 pairs separated.**

**3. Bootstrap rank intervals — the reporting view.** Resample the 20 articles 5000
times, re-rank all 24 arms from scratch each time, report the middle 95% of ranks each
arm visits. `llama_l` [1, 11], `qwen_m` [20, 24].

**These disagree, and the conservative one wins.** Rank intervals are *marginal*
("where does this arm land"), Nemenyi is *simultaneous* ("is this pair distinguishable,
accounting for all the other comparisons"). `llama_l` [1,11] and `qwen_m` [20,24] not
overlapping is suggestive, not a controlled claim. We report **nothing is separated**,
and show the intervals as context rather than as evidence.

### The lever that failed, recorded because it is informative

Nemenyi's threshold grows with the number of arms compared, so comparing fewer arms
should buy power at no data cost. Tested:

```
  24 arms   CD 8.13  span 7.85   0/276 separated
   8 arms   CD 2.35  span 2.15   0/28
   4 arms   CD 1.05  span 1.00   0/6
   2 arms   CD 0.44  span 0.20   0/1   <- best vs worst, head to head
```

**It fails at every size, including two arms with no multiplicity penalty at all.** So
the top of the table is not an artifact of testing too many things. At n=20 on rougeL
these models are genuinely indistinguishable. That closes the question instead of
leaving "maybe with fewer arms" open.

---

## Part 6 — Execution protocol

**Validate with a smoke subset, not the full sweep.** Re-running 24 arms to check that
a harness change did not break anything is slow and wasteful. Two named subsets:

- **`smoke`** — `qwen_s`, `glm_s`, `gemma_m`, `mistral_s`. Four arms, cheapest and
  fastest in the field, ~**$0.005** per pass at r=1. Purpose: does the plumbing still
  work — configs load, adapter runs, metrics write, fingerprint populates, leaderboard
  renders. Run after every harness change.
- **`smoke-reasoning`** — `anthropic_l`, `anthropic_m`, `anthropic_s`, `glm_l`. The four
  arms where reasoning or format is actually in question: the two hidden-token
  suspects, the one deterministic Anthropic arm as a control, and the visible leaker.
  ~**$0.35** per pass at r=1. Purpose: read `usage` and `finish_reason` once A1 lands.

**Full 24-arm sweep only when the harness is settled.** ~$1.45 at r=3.

### Order of execution

```
A1 persist usage + finish_reason      -> smoke
A2 upstream model id, not alias       -> smoke   (fingerprint must change)
A3 fix model.declared                 -> smoke
A4 one dirty flag, loud               -> smoke
A5 silver manifest + absolute path    -> (no run needed)
B1 format compliance metric           -> smoke   (must flag glm_l's 4 outputs)
B2 length-controlled facets           -> smoke
B3 Friedman + Nemenyi + rank intervals-> rescore existing runs, no calls
B4 Pareto on new facets               -> no calls
C1 tier -> price_tier                 -> smoke
D1 reasoning probe                    -> smoke-reasoning
D2 decide per model
D3 re-run affected arms               -> targeted, ~$0.30
E  silver calibration                 -> ~$1.00
FULL SWEEP                            -> ~$1.45
```

Each step: make the change, run its check, append the outcome to `EVAL_NOTES.md`.
Nothing is deleted at any point.
