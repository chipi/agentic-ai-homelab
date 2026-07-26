// fleetd chain — Fleet 1's PRODUCTION orchestrator (Track B, rollout plan).
//
// Go owns: intake (GitHub), state machine, all GitHub writes, ledger, metrics.
// LLM episodes stay external leaf executors (the measured lab instruments):
//   triage  → bugfix-fleet/bakeoff/triage_run.sh (TRIAGE_BASE=origin/main)
//   fix     → bugfix-fleet/bakeoff/harnesses/pi.sh (one episode, no oracle)
// Production has no hidden oracle (RFC-0002 go-live): acceptance =
// repro-first (a new/changed test in the diff — enforced MECHANICALLY here)
// + the full vitest suite green + reviewer + operator merge.
//
// Stages: shadow  = nothing leaves the machine (no GH writes, no push)
//         propose = verdict labels + comments + DRAFT PR
//         live    = ready PR
//
// Usage: fleetd chain -config chain.json [-once] [-issue N]
package main

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"strings"
	"time"
)

func contextWithTimeout(d time.Duration) (context.Context, context.CancelFunc) {
	return context.WithTimeout(context.Background(), d)
}

type ChainConfig struct {
	Repo        string `json:"repo"`         // chipi/orrery
	IntakeQuery string `json:"intake_query"` // label filter for gh issue list
	BakeoffDir  string `json:"bakeoff_dir"`  // .../bugfix-fleet/bakeoff (leaf executors)
	Worktree    string `json:"worktree"`     // production worktree (node env ready)
	SrcClone    string `json:"src_clone"`    // the clone the worktree belongs to
	Stage       string `json:"stage"`        // shadow | propose | live
	// suite command with one %s = JSON report path. Grading is DELTA-based
	// (the bake-off protocol, production edition): real repos may carry
	// pre-existing red — the gate is "no NEW failures + the new test passes",
	// never naive "suite green". (Learned live: orrery main has 39 red.)
	SuiteCmd       string  `json:"suite_cmd"`
	KickbackMax    int     `json:"kickback_max"`     // default 3 (measured)
	ChainBudgetUSD float64 `json:"chain_budget_usd"` // est-$ cap per chain, default 3
	EpisodeTimeout string  `json:"episode_timeout"`  // per fix episode, default 20m
	Advisor        string  `json:"advisor"`          // "off" disables §4.2 consultations
	WorkerModel    string  `json:"worker_model"`     // default deepseek-v4-flash (promoted 2026-07-26)
	ReviewerModel  string  `json:"reviewer_model"`   // e.g. claude-sonnet-4-6; ""/off disables
	LedgerDir   string `json:"ledger_dir"`
	VMURL       string `json:"vm_url"`
}

func chainMain(args []string) {
	fs := newFlagSet("chain")
	cfgPath := fs.String("config", "chain.json", "chain config")
	once := fs.Bool("once", true, "process current intake then exit")
	issueOnly := fs.Int("issue", 0, "process only this issue number")
	_ = once
	fs.Parse(args)

	raw, err := os.ReadFile(*cfgPath)
	if err != nil {
		log.Fatalf("chain config: %v", err)
	}
	var cc ChainConfig
	if err := json.Unmarshal(raw, &cc); err != nil {
		log.Fatalf("chain config parse: %v", err)
	}
	if cc.Stage == "" {
		cc.Stage = "shadow"
	}
	log.Printf("chain %s: repo=%s stage=%s", version, cc.Repo, cc.Stage)

	issues := chainIntake(cc, *issueOnly)
	if len(issues) == 0 {
		log.Printf("chain: intake empty (query: %s) — nothing to do", cc.IntakeQuery)
		return
	}
	for _, is := range issues {
		processIssue(cc, is)
	}
}

type ghIssue struct {
	Number int    `json:"number"`
	Title  string `json:"title"`
	Body   string `json:"body"`
	URL    string `json:"url"`
}

func chainIntake(cc ChainConfig, only int) []ghIssue {
	if only > 0 { // direct fetch — a numbered ask must not depend on list order
		out, err := exec.Command("gh", "issue", "view", fmt.Sprint(only), "-R", cc.Repo,
			"--json", "number,title,body,url").Output()
		if err != nil {
			log.Printf("chain intake (#%d) failed: %v", only, err)
			return nil
		}
		var one ghIssue
		if json.Unmarshal(out, &one) == nil && one.Number == only {
			return []ghIssue{one}
		}
		return nil
	}
	args := []string{"issue", "list", "-R", cc.Repo, "--state", "open",
		"--json", "number,title,body,url", "--limit", "10"}
	for _, l := range strings.Split(cc.IntakeQuery, ",") {
		if l = strings.TrimSpace(l); l != "" {
			args = append(args, "--label", l)
		}
	}
	out, err := exec.Command("gh", args...).Output()
	if err != nil {
		log.Printf("chain intake failed: %v", err)
		return nil
	}
	var all []ghIssue
	_ = json.Unmarshal(out, &all)
	if only > 0 {
		var f []ghIssue
		for _, i := range all {
			if i.Number == only {
				f = append(f, i)
			}
		}
		return f
	}
	return all
}

type chainLedger struct{ path string }

func (l chainLedger) add(issue int, state, detail string) {
	_ = os.MkdirAll(filepath.Dir(l.path), 0o755)
	f, err := os.OpenFile(l.path, os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0o644)
	if err != nil {
		return
	}
	defer f.Close()
	fmt.Fprintf(f, "%s\t%d\t%s\t%s\n", time.Now().UTC().Format(time.RFC3339), issue, state,
		strings.ReplaceAll(detail, "\n", " "))
	log.Printf("chain #%d: %s%s", issue, state, map[bool]string{true: " (" + detail + ")", false: ""}[detail != ""])
	pushChainMetric(issue, state)
}

var chainVM string

func pushChainMetric(issue int, state string) {
	if chainVM == "" {
		return
	}
	body := fmt.Sprintf("bugfix_fleet_flow{ticket=\"real-%d\",state=%q,tag=\"production\",service=\"bugfix-fleet\",environment=\"operations\"} 1\n", issue, state)
	cmd := exec.Command("curl", "-s", "-m", "5", "-X", "POST",
		chainVM+"/api/v1/import/prometheus", "--data-binary", body)
	_ = cmd.Run()
}

func run(dir, name string, args ...string) (string, error) {
	c := exec.Command(name, args...)
	c.Dir = dir
	out, err := c.CombinedOutput()
	return string(out), err
}

func processIssue(cc ChainConfig, is ghIssue) {
	led := chainLedger{path: filepath.Join(cc.LedgerDir, "chain.tsv")}
	chainVM = cc.VMURL
	led.add(is.Number, "intake", is.Title)

	// ── 1 · triage episode (leaf: the measured lab triager, base = main) ──
	ticket := map[string]any{
		"id":          fmt.Sprintf("real-orrery-%d", is.Number),
		"repo":        "orrery",
		"level":       "L0-real",
		"source_url":  is.URL,
		"description": is.Title + "\n\n" + is.Body,
		"oracle_test_file": "", "code_files": []string{},
	}
	tj, _ := json.Marshal(ticket)
	tpath := filepath.Join(cc.BakeoffDir, "bugs", "real", fmt.Sprintf("real-orrery-%d.json", is.Number))
	_ = os.MkdirAll(filepath.Dir(tpath), 0o755)
	_ = os.WriteFile(tpath, tj, 0o644)

	led.add(is.Number, "triaging", "")
	tc := exec.Command(filepath.Join(cc.BakeoffDir, "triage_run.sh"), tpath, "pi")
	tc.Dir = cc.BakeoffDir
	tc.Env = append(os.Environ(), "TRIAGE_BASE=origin/main")
	if out, err := tc.CombinedOutput(); err != nil {
		led.add(is.Number, "stuck", "triage episode crashed: "+tail(string(out), 200))
		return
	}
	tjPath := filepath.Join(os.Getenv("HOME"), ".bugfix-fleet", "bakeoff", "results",
		fmt.Sprintf("real-orrery-%d-triage", is.Number), "pi", "triage.json")
	traw, err := os.ReadFile(tjPath)
	if err != nil {
		led.add(is.Number, "stuck", "no triage verdict")
		return
	}
	var verdict struct {
		Verdict string `json:"verdict"`
		Missing []string
		Problem struct {
			Symptom    any `json:"symptom"`
			Expected   any `json:"expected"`
			Acceptance any `json:"acceptance"`
		} `json:"problem"`
	}
	_ = json.Unmarshal(traw, &verdict)

	switch verdict.Verdict {
	case "actionable":
		ghVerdict(cc, is.Number, "triage-fleet/actionable", triageComment(traw))
	case "needs-info":
		ghVerdict(cc, is.Number, "triage-fleet/needs-info", triageComment(traw))
		led.add(is.Number, "needs-info", strings.Join(verdict.Missing, " | "))
		return
	default:
		ghVerdict(cc, is.Number, "triage-fleet/rejected", triageComment(traw))
		led.add(is.Number, "rejected", "")
		return
	}

	// ── 2 · fix attempts with the measured kick-back loop (advisor + kb triage) ──
	branch := fmt.Sprintf("fleet/fix-%d-%s", is.Number, time.Now().Format("0102T1504"))
	if out, err := run(cc.SrcClone, "git", "fetch", "origin", "main"); err != nil {
		led.add(is.Number, "stuck", "fetch: "+tail(out, 120))
		return
	}
	run(cc.Worktree, "git", "checkout", "-q", "--detach", "origin/main")
	run(cc.Worktree, "git", "branch", "-D", branch)
	if out, err := run(cc.Worktree, "git", "checkout", "-q", "-b", branch, "origin/main"); err != nil {
		led.add(is.Number, "stuck", "branch: "+tail(out, 120))
		return
	}
	run(cc.Worktree, "git", "clean", "-fdq")

	// baseline the suite BEFORE any fix — delta-grading needs the base red-set
	led.add(is.Number, "baselining", "")
	baseFails, err := suiteFailures(cc)
	if err != nil {
		led.add(is.Number, "stuck", "baseline suite run failed: "+err.Error())
		return
	}

	tid := fmt.Sprintf("real-orrery-%d", is.Number)
	manifest := filepath.Join(cc.BakeoffDir, "bugs", "triaged", tid+"-triaged.json")
	priorTriage := tjPath
	kbMax := cc.KickbackMax
	if kbMax <= 0 {
		kbMax = 3 // measured: pin → fail-at-pin → acceptance needs round 3
	}
	budget := cc.ChainBudgetUSD
	if budget <= 0 {
		budget = 3.0
	}
	spent := 0.0
	var pins []string // every advisor pin issued this chain (a pivot must not erase the first pin)

	for round := 0; ; round++ {
		mraw, err := os.ReadFile(manifest)
		if err != nil {
			led.add(is.Number, "stuck", "no triaged manifest ("+manifest+")")
			return
		}
		var m struct {
			Description string `json:"description"`
		}
		_ = json.Unmarshal(mraw, &m)
		desc := m.Description + "\n\nIMPORTANT: write a failing regression test FIRST (repro-first), then fix. Both must be in your final diff."

		// discard any prior failed attempt; every attempt starts from base
		run(cc.Worktree, "git", "reset", "--hard", "origin/main")
		run(cc.Worktree, "git", "clean", "-fdq")

		led.add(is.Number, "fixing", fmt.Sprintf("round=%d branch=%s", round, branch))
		fxout, fxerr := runEpisode(cc, filepath.Join(cc.BakeoffDir, "harnesses", "pi.sh"), cc.Worktree, desc)
		turns, outTok, cost := parseUsage(fxout)
		spent += cost
		if fxerr != nil && len(fxout) == 0 {
			led.add(is.Number, "stuck", "fix episode crashed with no output")
			return
		}

		// mechanical gates → a failure reason (empty = clean)
		reason := ""
		diffOut, _ := run(cc.Worktree, "git", "diff", "--name-only")
		if !regexp.MustCompile(`(?m)\.(test|spec)\.[tj]s$`).MatchString(diffOut) {
			reason = "repro-first violated: no test in the diff"
		} else {
			led.add(is.Number, "testing", "delta vs base red-set")
			afterFails, err := suiteFailures(cc)
			if err != nil {
				reason = "suite run failed post-fix: " + err.Error()
			} else {
				var newFails []string
				for f := range afterFails {
					if !baseFails[f] {
						newFails = append(newFails, f)
					}
				}
				if len(newFails) > 0 {
					reason = fmt.Sprintf("%d NEW failures (delta gate): %s", len(newFails), tail(strings.Join(newFails, "; "), 150))
				}
			}
		}
		if reason == "" {
			led.add(is.Number, "delta-clean", fmt.Sprintf("round=%d base-red=%d", round, len(baseFails)))
			deliver(cc, is, branch, led)
			return
		}

		// ── kick-back: synthesize the evidence contract the measured leaves expect ──
		led.add(is.Number, "kick-back", fmt.Sprintf("round=%d: %s", round+1, reason))
		if round+1 > kbMax {
			led.add(is.Number, "stuck", fmt.Sprintf("kick-back budget exhausted (%d) — operator", kbMax))
			return
		}
		if spent > budget {
			led.add(is.Number, "stuck", fmt.Sprintf("chain $ budget exhausted ($%.2f > $%.2f)", spent, budget))
			return
		}
		evDir := filepath.Join(cc.LedgerDir, "results", fmt.Sprintf("%s-r%d", tid, round))
		_ = os.MkdirAll(evDir, 0o755)
		touched := ""
		for _, f := range strings.Split(diffOut, "\n") {
			if f != "" && !regexp.MustCompile(`\.(test|spec)\.`).MatchString(f) {
				touched += f + "\n"
			}
		}
		_ = os.WriteFile(filepath.Join(evDir, "touched.txt"), []byte(touched), 0o644)
		_ = os.WriteFile(filepath.Join(evDir, "harness.json"), fxout, 0o644)
		_ = os.WriteFile(filepath.Join(evDir, "result.tsv"), []byte(fmt.Sprintf(
			"%s\tpi\tFAIL (%s)\t0\t%.4f\t%d\t%d\tno\t0\n", tid, reason, cost, turns, outTok)), 0o644)

		// acceptance-transition (measured 2026-07-26, advfull k=3 all stuck): a
		// fix AT the advisor's pin that still fails is an acceptance gap by
		// definition — re-consulting the advisor only invents a new location.
		// Route to the reporter (= the operator) deterministically.
		accGap := false
		accPin := ""
		for _, p := range pins {
			for _, f := range strings.Split(touched, "\n") {
				if f == p {
					accGap, accPin = true, p
					break
				}
			}
		}
		if accGap {
			led.add(is.Number, "acceptance-gap", "fixed at pin "+accPin+", still failing — reporter")
		}
		if cc.Advisor != "off" && !accGap {
			led.add(is.Number, "advising", "model="+advisorModel())
			ac := exec.Command(filepath.Join(cc.BakeoffDir, "advisor_run.sh"), tpath, evDir)
			ac.Dir = cc.BakeoffDir
			if aout, aerr := ac.CombinedOutput(); aerr != nil {
				led.add(is.Number, "advising", "no usable advisor output: "+tail(string(aout), 80))
			}
			if araw, err := os.ReadFile(filepath.Join(evDir, "advisor.json")); err == nil {
				var av struct {
					File string `json:"file"`
				}
				_ = json.Unmarshal(araw, &av)
				if av.File != "" {
					pins = append(pins, av.File)
				}
			}
		}

		kb := exec.Command(filepath.Join(cc.BakeoffDir, "triage_run.sh"), tpath, "pi", evDir, priorTriage)
		kb.Dir = cc.BakeoffDir
		kb.Env = append(os.Environ(), "TRIAGE_BASE=origin/main",
			fmt.Sprintf("ACCEPTANCE_GAP=%d", boolToInt(accGap)))
		if out, err := kb.CombinedOutput(); err != nil {
			led.add(is.Number, "stuck", "kb triage crashed: "+tail(string(out), 160))
			return
		}
		kbID := fmt.Sprintf("%s-triage-kb%d", tid, round+1)
		kbJSON := filepath.Join(os.Getenv("HOME"), ".bugfix-fleet", "bakeoff", "results", kbID, "pi", "triage.json")
		kraw, err := os.ReadFile(kbJSON)
		if err != nil {
			led.add(is.Number, "stuck", "no kb triage verdict")
			return
		}
		var kv struct {
			Verdict string `json:"verdict"`
		}
		_ = json.Unmarshal(kraw, &kv)
		// mechanical enforcement — acceptance mode may not re-pin (prompt is a hope)
		if accGap && kv.Verdict == "actionable" {
			led.add(is.Number, "downgrade", "acceptance-gap triage returned actionable — forcing needs-info")
			kv.Verdict = "needs-info"
		}
		switch kv.Verdict {
		case "actionable":
			manifest = filepath.Join(cc.BakeoffDir, "bugs", "triaged", fmt.Sprintf("%s-triaged-kb%d.json", tid, round+1))
			priorTriage = kbJSON
		case "needs-info":
			// PRODUCTION reporter = the operator: park the issue on them
			ghVerdict(cc, is.Number, "triage-fleet/needs-info", triageComment(kraw))
			led.add(is.Number, "needs-info", "parked on operator (production reporter)")
			return
		default:
			ghVerdict(cc, is.Number, "triage-fleet/rejected", triageComment(kraw))
			led.add(is.Number, "rejected", "after kick-back")
			return
		}
	}
}

// deliver: commit; propose/live → push + PR (draft at propose) + reviewer gate.
func deliver(cc ChainConfig, is ghIssue, branch string, led chainLedger) {
	run(cc.Worktree, "git", "add", "-A")
	run(cc.Worktree, "git", "-c", "user.email=fleet@homelab", "-c", "user.name=bugfix-fleet",
		"commit", "-q", "-m", fmt.Sprintf("fix #%d: %s\n\nAutomated fix by the bug-fix fleet (repro-first + delta-clean suite).", is.Number, is.Title))
	if cc.Stage == "shadow" {
		led.add(is.Number, "shipped-local", "branch="+branch+" (shadow: not pushed)")
		return
	}
	if out, err := run(cc.Worktree, "git", "push", "-u", "origin", branch); err != nil {
		led.add(is.Number, "stuck", "push: "+tail(out, 160))
		return
	}
	prArgs := []string{"pr", "create", "-R", cc.Repo, "--head", branch,
		"--title", fmt.Sprintf("fix #%d: %s", is.Number, is.Title),
		"--body", fmt.Sprintf("Automated fix for #%d by the bug-fix fleet.\n\n- repro-first: regression test included\n- suite delta-clean vs branch base\n- chain ledger: `~/.bugfix-fleet/real/chain.tsv`\n\nOperator merges — the fleet never does.", is.Number)}
	if cc.Stage == "propose" {
		prArgs = append(prArgs, "--draft")
	}
	out, err := exec.Command("gh", prArgs...).CombinedOutput()
	if err != nil {
		led.add(is.Number, "stuck", "pr: "+tail(string(out), 160))
		return
	}
	prURL := strings.TrimSpace(tail(string(out), 90))
	led.add(is.Number, "shipped", prURL)

	// reviewer gate (RFC-0002): Claude reviews the whole diff, comment-only in
	// MVP — the operator remains the only merger. Best-effort.
	if cc.ReviewerModel != "" && cc.ReviewerModel != "off" {
		led.add(is.Number, "reviewing", cc.ReviewerModel)
		diff, _ := run(cc.Worktree, "git", "diff", "origin/main...HEAD")
		rev := exec.Command("claude", "-p",
			fmt.Sprintf("Review this automated bug-fix PR for issue #%d (%s).\n\nDIFF:\n%s\n\nGive a concise review: correctness risks, edge cases the fix misses, test adequacy. End with VERDICT: approve|request-changes.", is.Number, is.Title, tail(diff, 60000)),
			"--model", cc.ReviewerModel, "--output-format", "json")
		rout, rerr := rev.Output()
		if rerr == nil {
			var rr struct {
				Result string `json:"result"`
			}
			if json.Unmarshal(rout, &rr) == nil && rr.Result != "" {
				body := "## Fleet reviewer (" + cc.ReviewerModel + ")\n\n" + rr.Result
				_ = exec.Command("gh", "pr", "comment", "--repo", cc.Repo, branch, "--body", body).Run()
				led.add(is.Number, "reviewed", tail(rr.Result, 80))
			}
		} else {
			led.add(is.Number, "reviewing", "reviewer episode failed (non-blocking)")
		}
	}
}

func boolToInt(b bool) int {
	if b {
		return 1
	}
	return 0
}

func advisorModel() string {
	if m := os.Getenv("ADVISOR_MODEL"); m != "" {
		return m
	}
	return "z-ai/glm-5.2"
}

// runEpisode executes a leaf harness episode with a hard timeout.
func runEpisode(cc ChainConfig, script, wt, desc string) ([]byte, error) {
	timeout := 20 * time.Minute
	if cc.EpisodeTimeout != "" {
		if d, err := time.ParseDuration(cc.EpisodeTimeout); err == nil {
			timeout = d
		}
	}
	ctx, cancel := contextWithTimeout(timeout)
	defer cancel()
	cmd := exec.CommandContext(ctx, script, wt, desc)
	cmd.Dir = cc.BakeoffDir
	// worker seat: flash promoted 2026-07-26 (3/3 closed-loop, ties v4-pro on
	// every replay cell at ~1/4 price). Lab pi.sh default stays v4-pro — that
	// is the measured base config; production pins its own worker here.
	worker := cc.WorkerModel
	if worker == "" {
		worker = "deepseek/deepseek-v4-flash"
	}
	cmd.Env = append(os.Environ(), "PI_MODEL="+worker)
	return cmd.CombinedOutput()
}

// parseUsage sums the pi event stream: turns, output tokens, est cost
// (v4-pro rates, cache-blind upper bound — Langfuse holds precision).
func parseUsage(stream []byte) (turns, outTok int, cost float64) {
	var inMax int
	for _, line := range strings.Split(string(stream), "\n") {
		line = strings.TrimSpace(line)
		if line == "" || !strings.HasPrefix(line, "{") {
			continue
		}
		var e struct {
			Type    string `json:"type"`
			Message struct {
				Role  string `json:"role"`
				Usage struct {
					Input  int `json:"input"`
					Output int `json:"output"`
				} `json:"usage"`
			} `json:"message"`
		}
		if json.Unmarshal([]byte(line), &e) != nil {
			continue
		}
		if e.Type == "message_end" && e.Message.Role == "assistant" {
			turns++
			outTok += e.Message.Usage.Output
			if e.Message.Usage.Input > inMax {
				inMax = e.Message.Usage.Input
			}
		}
	}
	cost = float64(inMax)*4.35e-7 + float64(outTok)*8.7e-7
	return
}

// suiteFailures runs the suite (JSON reporter) and returns the failed-test set
// keyed file::title. The exit code is deliberately ignored — a red suite is
// DATA for the delta gate, not an error; only a missing/unparsable report is.
func suiteFailures(cc ChainConfig) (map[string]bool, error) {
	tmp, err := os.CreateTemp("", "suite-*.json")
	if err != nil {
		return nil, err
	}
	tmp.Close()
	defer os.Remove(tmp.Name())
	cmd := exec.Command("sh", "-c", fmt.Sprintf(cc.SuiteCmd, tmp.Name()))
	cmd.Dir = cc.Worktree
	_, _ = cmd.CombinedOutput() // red suite exits nonzero — expected
	raw, err := os.ReadFile(tmp.Name())
	if err != nil || len(raw) == 0 {
		return nil, fmt.Errorf("no suite report produced")
	}
	var rep struct {
		TestResults []struct {
			Name             string `json:"name"`
			AssertionResults []struct {
				Status   string `json:"status"`
				FullName string `json:"fullName"`
			} `json:"assertionResults"`
		} `json:"testResults"`
	}
	if err := json.Unmarshal(raw, &rep); err != nil {
		return nil, fmt.Errorf("suite report parse: %v", err)
	}
	fails := map[string]bool{}
	for _, tr := range rep.TestResults {
		for _, ar := range tr.AssertionResults {
			if ar.Status == "failed" {
				fails[tr.Name+"::"+ar.FullName] = true
			}
		}
	}
	return fails, nil
}

func triageComment(traw []byte) string {
	var v map[string]any
	_ = json.Unmarshal(traw, &v)
	pretty, _ := json.MarshalIndent(v["problem"], "", "  ")
	verdict, _ := v["verdict"].(string)
	return fmt.Sprintf("**Triage fleet — %s.**\n\n```json\n%s\n```\n\n_bugfix-fleet chain · %s_",
		verdict, tail(string(pretty), 1800), time.Now().UTC().Format(time.RFC3339))
}

func ghVerdict(cc ChainConfig, issue int, label, comment string) {
	if cc.Stage == "shadow" {
		log.Printf("chain #%d: shadow — would label %s", issue, label)
		return
	}
	_ = exec.Command("gh", "issue", "edit", fmt.Sprint(issue), "-R", cc.Repo, "--add-label", label).Run()
	_ = exec.Command("gh", "issue", "comment", fmt.Sprint(issue), "-R", cc.Repo, "--body", comment).Run()
}

func tail(s string, n int) string {
	s = strings.TrimSpace(s)
	if len(s) <= n {
		return s
	}
	return s[len(s)-n:]
}
