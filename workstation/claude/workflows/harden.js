export const meta = {
  name: 'harden',
  description: 'Pre-close hardening audit — scope the delta since the last harden, audit code/tests/docs/deferrals in parallel, run the repo gates, adversarially verify each finding, apply only the safe fixes to the working tree, and surface what needs a decision. Never commits, never pushes. Model-tiered (haiku/sonnet, opus only for high-sev verify), batched verify, a hard deterministic exclude guard. Optional args.budgetTokens (output-token cap → graceful degradation) and args.brief (main-agent scope+intent → skips cold rediscovery). Portable: detects the repo pre-commit / build target / follow-up lists.',
  phases: [
    { title: 'Scope', model: 'haiku' },
    { title: 'Audit', model: 'sonnet' },
    { title: 'Gates', model: 'haiku' },
    { title: 'Verify', model: 'sonnet' },
    { title: 'Fix', model: 'sonnet' },
    { title: 'Guard', model: 'haiku' },
  ],
}

// args: { repo, exclude:[...], budgetTokens?:N (output-token cap), brief?:{base,head,files,commits,summary,intent} }
const A = (typeof args === 'string' ? (()=>{try{return JSON.parse(args)}catch(e){return {}}})() : (args || {}))
const REPO = A.repo || '.'
const MARK = `${REPO}/.git/harden-mark`
const EXCLUDE = A.exclude || []
const EXCL = EXCLUDE.length ? EXCLUDE.join(', ') : '(none)'
// path-boundary exclude match (not naive substring: "docs/wip/x" must not match "docs/wip/x-archive/…")
const isExcluded = (p) => {
  if (!p) return false
  const q = '/' + String(p).replace(/^\/+/, '')
  return EXCLUDE.some(e => { const s = '/' + String(e).replace(/^\/+/, ''); return q === s || q.endsWith(s) || q.includes(s + '/') })
}
const chunk = (a, n) => { const o = []; for (let i = 0; i < a.length; i += n) o.push(a.slice(i, i + n)); return o }

// budget: cap is an OUTPUT-token ceiling (the only in-script spend signal). START isolates this
// workflow's own output from anything the main loop spent earlier this turn.
const CAP = A.budgetTokens || null
const START = budget.spent()
const used = () => budget.spent() - START
const over = (frac) => !!(CAP && used() > CAP * frac)
const degraded = []

// brief: main-agent-authored scope+intent — inherits what we know, so agents don't rediscover cold.
const BRIEF = A.brief || null
const CONTEXT = BRIEF
  ? `\nSESSION CONTEXT (authoritative — what was done this session and WHY; do NOT rediscover it, and do NOT flag intentional/decided choices as issues):\n${BRIEF.summary || ''}\nINTENT & DECISIONS: ${BRIEF.intent || ''}\n`
  : ''

const SCOPE = { type: 'object', properties: {
  mark: { type: 'string' }, head: { type: 'string' }, empty: { type: 'boolean' },
  commits: { type: 'array', items: { type: 'string' } }, files: { type: 'array', items: { type: 'string' } }, summary: { type: 'string' },
}, required: ['head', 'empty', 'files'] }
const FINDINGS = { type: 'object', properties: { findings: { type: 'array', items: { type: 'object', properties: {
  title: { type: 'string' }, file: { type: 'string' }, detail: { type: 'string' },
  severity: { type: 'string', enum: ['high', 'medium', 'low'] }, autoFixable: { type: 'boolean' }, proposedFix: { type: 'string' },
}, required: ['title', 'severity', 'autoFixable'] } } }, required: ['findings'] }
const VERDICT = { type: 'object', properties: {
  real: { type: 'boolean' }, classification: { type: 'string', enum: ['auto-fix', 'needs-decision', 'follow-up'] }, reason: { type: 'string' },
}, required: ['real', 'classification'] }
const VERDICTS = { type: 'object', properties: { verdicts: { type: 'array', items: { type: 'object', properties: {
  id: { type: 'integer' }, real: { type: 'boolean' }, classification: { type: 'string', enum: ['auto-fix', 'needs-decision', 'follow-up'] }, reason: { type: 'string' },
}, required: ['id', 'real', 'classification'] } } }, required: ['verdicts'] }
const GATES = { type: 'object', properties: {
  ran: { type: 'array', items: { type: 'string' } }, pass: { type: 'boolean' },
  failures: { type: 'array', items: { type: 'string' } }, preExisting: { type: 'array', items: { type: 'string' } }, evidence: { type: 'string' },
}, required: ['pass'] }
const FIX = { type: 'object', properties: {
  applied: { type: 'array', items: { type: 'string' } }, skipped: { type: 'array', items: { type: 'string' } }, reGatePass: { type: 'boolean' },
}, required: ['applied'] }
const GUARD = { type: 'object', properties: { touched: { type: 'array', items: { type: 'string' } } }, required: ['touched'] }

// ── Phase 0 · Scope (from brief if provided, else a cheap haiku agent) ────────
phase('Scope')
let scope
if (BRIEF && BRIEF.head) {
  scope = { mark: BRIEF.base, head: BRIEF.head, empty: false, commits: BRIEF.commits || [], files: BRIEF.files || [], summary: BRIEF.summary }
  log('scope: using provided brief — cold scope agent skipped')
} else {
  scope = await agent(
    `Scope a hardening audit in the git repo at ${REPO}. READ-ONLY — modify nothing.
     1. Base marker: cat ${MARK} 2>/dev/null. If missing/empty use \`git -C ${REPO} merge-base origin/main HEAD\` (or the root commit if no origin/main). The base MUST be a commit SHA, never a branch name.
     2. Delta: \`git -C ${REPO} log <mark>..HEAD --oneline\` + \`git -C ${REPO} status --porcelain\` + \`git -C ${REPO} diff HEAD\`.
     3. If NO commits since <mark> AND clean working tree → empty=true.
     4. List every changed file (committed + uncommitted).
     OUT-OF-BOUNDS (exclude, never flag; you MAY read NEXT_STEPS/HANDOVER as reference): ${EXCL}.`,
    { schema: SCOPE, model: 'haiku', label: 'scope', phase: 'Scope' }
  )
}
if (!scope || scope.empty) { log('nothing new since the last harden mark — clean.'); return { empty: true } }
const base = scope.mark || 'origin/main'
log(`hardening ${(scope.commits || []).length} commit(s) + working tree; base ${base}, ${scope.files.length} file(s)${CAP ? `; budget ${CAP} out-tok` : ''}${BRIEF ? '; briefed' : ''}`)

// ── Phase 1 · Audit (sonnet, parallel by dimension) ───────────────────────────
phase('Audit')
const DIMS = [
  { key: 'code', p: `correctness bugs, half-finished edits, newly-added TODO/FIXME, and obvious regressions in the CHANGED code (shell/python/js) only` },
  { key: 'docs', p: `documentation DRIFT: stale references, doc-vs-code divergence, broken cross-refs/links, and stale mentions of removed/renamed things. Include docs OUTSIDE the delta that reference delta files` },
  { key: 'tests', p: `TEST/coverage GAPS: changed logic or a fixed bug without a corresponding test/validation. If infra/docs-heavy with few unit tests, note genuine gaps — do NOT invent a suite` },
  { key: 'deferrals', p: `DEFERRALS not tracked. Find parked language in the delta ("later", "deferred", "TODO", "follow-up", "punt", "revisit") and cross-check the repo's tracked lists (docs/wip/NEXT_STEPS.md, TODO.md, docs/wip/HANDOVER.md, or \`gh issue list\`). Report ONLY if NOT already tracked` },
]
const audits = await parallel(DIMS.map(d => () =>
  agent(
    `READ-ONLY audit of the git delta since ${base} in ${REPO}. Modify nothing.${CONTEXT}
     Look for: ${d.p}.
     Scope strictly to the delta (\`git -C ${REPO} diff ${base}..HEAD\` + working tree). Ignore these OUT-OF-BOUNDS paths entirely — never flag them: ${EXCL}. For each issue give file, detail, severity, autoFixable, and a concrete proposedFix. Empty array if clean.`,
    { schema: FINDINGS, model: 'sonnet', label: `audit:${d.key}`, phase: 'Audit' })
    .then(r => (r && r.findings || []).map(f => ({ ...f, dim: d.key }))).catch(() => [])
))
let raw = audits.filter(Boolean).flat()
const droppedExcluded = raw.filter(f => isExcluded(f.file)).length
raw = raw.filter(f => !isExcluded(f.file))
log(`${raw.length} finding(s) after exclude guard (dropped ${droppedExcluded})`)

// ── Phase 2 · Gates (haiku; pass reflects delta-introduced failures only) ─────
phase('Gates')
const gates = await agent(
  `Run the repo's mechanical gates in ${REPO}, scoped to the delta since ${base}. Do NOT fix anything.
   1. If .pre-commit-config.yaml exists AND \`pre-commit\` is installed: \`pre-commit run --from-ref ${base} --to-ref HEAD\` (else --all-files). If NOT installed: \`shellcheck --severity=warning\` on changed *.sh, and \`docker compose -f <f> config -q\` for changed docker-compose*.yml when docker is up (skip w/ a note otherwise).
   2. Detect + run the repo's docs/test build if the delta touches it: make docs-build / make test / npm test / pytest.
   3. Secrets: \`git -C ${REPO} diff ${base}..HEAD\` via gitleaks if present, else a high-signal regex scan.
   CRITICAL: pass=false ONLY if the DELTA introduced a failure. A failure on a line NOT in the delta, or a missing gitignored precondition (e.g. absent .env), goes in preExisting[] and does NOT fail the gate.`,
  { schema: GATES, model: 'haiku', label: 'gates', phase: 'Gates' }
)
const gateFindings = (gates && !gates.pass ? (gates.failures || []).map(fx => ({ title: `gate failure (delta): ${fx}`, detail: fx, severity: 'high', autoFixable: false, dim: 'gates' })) : [])

// ── Phase 3 · Verify (budget-aware: skip / all-sonnet-batched / normal) ───────
phase('Verify')
const candidate = raw.concat(gateFindings)
candidate.forEach((f, i) => { f._id = i })
const byId = new Map(candidate.map(f => [f._id, f]))
const one = (f) => `Adversarially verify this finding in ${REPO}. Confirm REAL by reading the file, or declare false positive. Classify: "auto-fix" (mechanical/unambiguous/in-delta), "needs-decision" (design/scope/behavior/deps/shared-infra/ambiguous — never auto-apply), "follow-up" (real, out of scope). When in doubt → needs-decision.${CONTEXT}\nFinding: ${JSON.stringify(f)}`
const batch = (b) => `Adversarially verify these findings in ${REPO}. For EACH (by id), read the file to confirm REAL or false positive, then classify: "auto-fix" / "needs-decision" / "follow-up" (when in doubt → needs-decision). Return one verdict per finding, echoing its id.${CONTEXT}\nFindings: ${JSON.stringify(b.map(f => ({ id: f._id, title: f.title, file: f.file, detail: f.detail, severity: f.severity })))}`

let confirmed
if (over(1.0)) {
  degraded.push('verify skipped (over budget) — findings reported unverified as needs-decision')
  log(`budget: ${used()}/${CAP} out-tok — SKIPPING verify; all findings → needs-decision (unverified)`)
  confirmed = candidate.map(f => ({ ...f, verdict: { real: true, classification: 'needs-decision', reason: 'unverified — budget cap; review manually' } }))
} else {
  const tightV = over(0.7)
  if (tightV) { degraded.push('verify degraded — all-sonnet, larger batches, no per-finding opus'); log(`budget: ${used()}/${CAP} out-tok — verify all-sonnet, no opus`) }
  const highSev = tightV ? [] : candidate.filter(f => f.severity === 'high')
  const bulk = tightV ? candidate : candidate.filter(f => f.severity !== 'high')
  const VBATCH = tightV ? 10 : 5
  const hiV = await parallel(highSev.map(f => () =>
    agent(one(f), { schema: VERDICT, model: 'opus', label: `verify.hi:${f.dim}`, phase: 'Verify' })
      .then(v => ({ id: f._id, real: v.real, classification: v.classification })).catch(() => null)))
  const bkV = (await parallel(chunk(bulk, VBATCH).map((b, i) => () => {
    const ids = new Set(b.map(f => f._id))
    return agent(batch(b), { schema: VERDICTS, model: 'sonnet', label: `verify.bulk${i}`, phase: 'Verify' })
      .then(r => (r && r.verdicts || []).filter(v => ids.has(v.id))).catch(() => [])   // per-batch id validation
  }))).flat()
  const verdicts = hiV.filter(Boolean).concat(bkV)
  confirmed = verdicts.filter(v => v && v.real && byId.has(v.id)).map(v => ({ ...byId.get(v.id), verdict: v })).filter(f => f.title)
}
const autoFix = confirmed.filter(f => f.verdict.classification === 'auto-fix' && !isExcluded(f.file))
const needsDecision = confirmed.filter(f => f.verdict.classification === 'needs-decision')
const followUps = confirmed.filter(f => f.verdict.classification === 'follow-up')

// ── Phase 4 · Fix (sonnet; allowlist-framed; skipped if over budget) ──────────
phase('Fix')
let fix = { applied: [], skipped: [], reGatePass: null }
if (autoFix.length && !over(1.0)) {
  const allow = [...new Set(autoFix.map(f => f.file).filter(Boolean))]
  fix = await agent(
    `You may ONLY modify files on this ALLOWLIST: ${JSON.stringify(allow)}. Touching ANY other path — especially ${EXCL} — is a critical error; if a fix needs a non-allowlisted file, SKIP it and record in skipped[]. Apply ONLY these confirmed auto-fixable findings to the working tree in ${REPO}. Do NOT commit, do NOT push. After applying, re-run the specific gate covering each fix and report pass/fail.\nItems: ${JSON.stringify(autoFix.map(f => ({ id: f._id, title: f.title, file: f.file, proposedFix: f.proposedFix, dim: f.dim })))}`,
    { schema: FIX, model: 'sonnet', label: 'fix', phase: 'Fix' }
  ) || fix
} else if (autoFix.length) {
  degraded.push(`fix skipped (over budget) — ${autoFix.length} auto-fixable item(s) reported as proposals`)
  fix = { applied: [], skipped: autoFix.map(f => `${f.title} (proposed, not applied — budget)`), reGatePass: null }
}

// ── Phase 5 · Guard (haiku; skipped if over budget) ───────────────────────────
phase('Guard')
let violations = []
if (EXCLUDE.length && !over(1.0)) {
  const g = await agent(
    `In ${REPO}, run \`git -C ${REPO} status --porcelain\` and report which of these OUT-OF-BOUNDS paths, if any, were modified or created: ${EXCL}. READ-ONLY — do not change or revert anything; just report. Empty if none.`,
    { schema: GUARD, model: 'haiku', label: 'guard', phase: 'Guard' }
  )
  violations = (g && g.touched) || []
}

return {
  base, head: scope.head, commitsHardened: (scope.commits || []).length,
  mode: { briefed: !!BRIEF, budgetCap: CAP, outputUsed: used(), degraded },
  gates, fixed: fix,
  droppedExcludedFindings: droppedExcluded, excludeViolations: violations,
  needsDecision: needsDecision.map(f => ({ severity: f.severity, dim: f.dim, title: f.title, file: f.file, detail: f.detail })),
  followUps: followUps.map(f => ({ dim: f.dim, title: f.title, file: f.file, detail: f.detail })),
  markToAdvance: scope.head,
}
