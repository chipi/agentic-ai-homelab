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
	SuiteCmd string `json:"suite_cmd"`
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

	// ── 2 · fix episode on a fresh branch from origin/main ──
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

	// baseline the suite BEFORE the fix — delta-grading needs the base red-set
	led.add(is.Number, "baselining", "")
	baseFails, err := suiteFailures(cc)
	if err != nil {
		led.add(is.Number, "stuck", "baseline suite run failed: "+err.Error())
		return
	}

	// the manifest the worker sees = the triaged L1 candidate (rendered by triage_run.sh)
	manifest := filepath.Join(cc.BakeoffDir, "bugs", "triaged", fmt.Sprintf("real-orrery-%d-triaged.json", is.Number))
	mraw, err := os.ReadFile(manifest)
	if err != nil {
		led.add(is.Number, "stuck", "no triaged manifest")
		return
	}
	var m struct {
		Description string `json:"description"`
	}
	_ = json.Unmarshal(mraw, &m)
	desc := m.Description + "\n\nIMPORTANT: write a failing regression test FIRST (repro-first), then fix. Both must be in your final diff."

	led.add(is.Number, "fixing", "branch="+branch)
	fx := exec.Command(filepath.Join(cc.BakeoffDir, "harnesses", "pi.sh"), cc.Worktree, desc)
	fx.Dir = cc.BakeoffDir
	fxout, fxerr := fx.CombinedOutput()
	if fxerr != nil {
		led.add(is.Number, "stuck", "fix episode: "+tail(string(fxout), 160))
		return
	}

	// ── 3 · mechanical gates: repro-first, then the suite ──
	diffOut, _ := run(cc.Worktree, "git", "diff", "--name-only")
	if !regexp.MustCompile(`(?m)\.(test|spec)\.[tj]s$`).MatchString(diffOut) {
		led.add(is.Number, "kick-back", "no test in diff — repro-first violated; not proceeding")
		return
	}
	led.add(is.Number, "testing", "delta vs base red-set")
	afterFails, err := suiteFailures(cc)
	if err != nil {
		led.add(is.Number, "kick-back", "suite run failed post-fix: "+err.Error())
		return
	}
	var newFails []string
	for f := range afterFails {
		if !baseFails[f] {
			newFails = append(newFails, f)
		}
	}
	if len(newFails) > 0 {
		led.add(is.Number, "kick-back", fmt.Sprintf("%d NEW failures (delta gate): %s",
			len(newFails), tail(strings.Join(newFails, "; "), 180)))
		return
	}
	led.add(is.Number, "delta-clean", fmt.Sprintf("base red=%d, after red=%d, new=0", len(baseFails), len(afterFails)))

	// ── 4 · deliver: commit; propose/live → push + PR (draft at propose) ──
	run(cc.Worktree, "git", "add", "-A")
	run(cc.Worktree, "git", "-c", "user.email=fleet@homelab", "-c", "user.name=bugfix-fleet",
		"commit", "-q", "-m", fmt.Sprintf("fix #%d: %s\n\nAutomated fix by the bug-fix fleet (repro-first + suite green).", is.Number, is.Title))
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
		"--body", fmt.Sprintf("Automated fix for #%d by the bug-fix fleet.\n\n- repro-first: regression test included\n- full suite green locally\n- chain ledger: `~/.bugfix-fleet/real/chain.tsv`\n\nOperator merges — the fleet never does.", is.Number)}
	if cc.Stage == "propose" {
		prArgs = append(prArgs, "--draft")
	}
	out, err := exec.Command("gh", prArgs...).CombinedOutput()
	if err != nil {
		led.add(is.Number, "stuck", "pr: "+tail(string(out), 160))
		return
	}
	led.add(is.Number, "shipped", strings.TrimSpace(tail(string(out), 90)))
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
