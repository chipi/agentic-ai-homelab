package main

import (
	"encoding/json"
	"fmt"
	"os"
	"strings"
	"testing"
)

// ── parseUsageFull ────────────────────────────────────────────────────────────

func TestParseUsageFull_HappyPath(t *testing.T) {
	// Two assistant turns: (in=100,out=50) and (in=200,out=80).
	// Expected: turns=2, outTok=130, inMax=200, cost=200*4.35e-7 + 130*8.7e-7
	lines := []string{
		`{"type":"message_end","message":{"role":"assistant","usage":{"input":100,"output":50}}}`,
		`{"type":"message_end","message":{"role":"assistant","usage":{"input":200,"output":80}}}`,
	}
	stream := []byte(strings.Join(lines, "\n"))
	turns, outTok, inMax, cost := parseUsageFull(stream)

	if turns != 2 {
		t.Errorf("turns: want 2 got %d", turns)
	}
	if outTok != 130 {
		t.Errorf("outTok: want 130 got %d", outTok)
	}
	if inMax != 200 {
		t.Errorf("inMax: want 200 got %d", inMax)
	}
	wantCost := float64(200)*4.35e-7 + float64(130)*8.7e-7
	if fmt.Sprintf("%.10f", cost) != fmt.Sprintf("%.10f", wantCost) {
		t.Errorf("cost: want %g got %g", wantCost, cost)
	}
}

func TestParseUsageFull_EmptyStream(t *testing.T) {
	turns, outTok, inMax, cost := parseUsageFull([]byte{})
	if turns != 0 || outTok != 0 || inMax != 0 || cost != 0 {
		t.Errorf("empty stream: want all zeros, got turns=%d outTok=%d inMax=%d cost=%g",
			turns, outTok, inMax, cost)
	}
}

func TestParseUsageFull_NonJSONLines(t *testing.T) {
	// Lines that aren't JSON objects are silently skipped.
	stream := []byte("not json\n  \nstill not json\n")
	turns, outTok, inMax, cost := parseUsageFull(stream)
	if turns != 0 || outTok != 0 || inMax != 0 || cost != 0 {
		t.Errorf("non-json stream: want all zeros, got turns=%d outTok=%d inMax=%d cost=%g",
			turns, outTok, inMax, cost)
	}
}

func TestParseUsageFull_SkipsNonAssistantAndNonMessageEnd(t *testing.T) {
	// message_start with role=user, and message_end with role=user — both ignored.
	lines := []string{
		`{"type":"message_start","message":{"role":"user","usage":{"input":999,"output":999}}}`,
		`{"type":"message_end","message":{"role":"user","usage":{"input":500,"output":200}}}`,
		// this one counts
		`{"type":"message_end","message":{"role":"assistant","usage":{"input":10,"output":5}}}`,
	}
	stream := []byte(strings.Join(lines, "\n"))
	turns, outTok, inMax, cost := parseUsageFull(stream)
	if turns != 1 {
		t.Errorf("turns: want 1 got %d", turns)
	}
	if outTok != 5 {
		t.Errorf("outTok: want 5 got %d", outTok)
	}
	if inMax != 10 {
		t.Errorf("inMax: want 10 got %d", inMax)
	}
	wantCost := float64(10)*4.35e-7 + float64(5)*8.7e-7
	if fmt.Sprintf("%.10f", cost) != fmt.Sprintf("%.10f", wantCost) {
		t.Errorf("cost: want %g got %g", wantCost, cost)
	}
}

func TestParseUsageFull_MixedValidAndInvalidJSON(t *testing.T) {
	// Malformed JSON lines are skipped; valid ones counted.
	lines := []string{
		`{"type":"message_end","message":{"role":"assistant","usage":{"input":10,"output":3}}}`,
		`{broken json`,
		`{"type":"message_end","message":{"role":"assistant","usage":{"input":20,"output":7}}}`,
	}
	stream := []byte(strings.Join(lines, "\n"))
	turns, outTok, inMax, _ := parseUsageFull(stream)
	if turns != 2 {
		t.Errorf("turns: want 2 got %d", turns)
	}
	if outTok != 10 {
		t.Errorf("outTok: want 10 got %d", outTok)
	}
	if inMax != 20 {
		t.Errorf("inMax: want 20 got %d", inMax)
	}
}

func TestParseUsageFull_SingleTurnMaxInput(t *testing.T) {
	// inMax is the peak input, not the sum.
	lines := []string{
		`{"type":"message_end","message":{"role":"assistant","usage":{"input":50,"output":10}}}`,
		`{"type":"message_end","message":{"role":"assistant","usage":{"input":300,"output":20}}}`,
		`{"type":"message_end","message":{"role":"assistant","usage":{"input":150,"output":15}}}`,
	}
	stream := []byte(strings.Join(lines, "\n"))
	_, _, inMax, _ := parseUsageFull(stream)
	if inMax != 300 {
		t.Errorf("inMax: want 300 (peak) got %d", inMax)
	}
}

// ── suiteFailures ─────────────────────────────────────────────────────────────
//
// suiteFailures executes a shell command and reads the result from a temp file
// whose path is substituted for the single %s in SuiteCmd. We test it by
// writing fixture JSON to a known temp file and using `cp <fixture> %s` as
// the SuiteCmd — exactly one %s, no shell-escaping fights with fmt.Sprintf.

// writeTempFixture writes content to a temp file and returns its path.
// The caller is responsible for removing it after the test.
func writeTempFixture(t *testing.T, content []byte) string {
	t.Helper()
	f, err := os.CreateTemp("", "suite-fixture-*.json")
	if err != nil {
		t.Fatalf("writeTempFixture: %v", err)
	}
	if _, err := f.Write(content); err != nil {
		f.Close()
		os.Remove(f.Name())
		t.Fatalf("writeTempFixture write: %v", err)
	}
	f.Close()
	return f.Name()
}

// suiteCmd builds a SuiteCmd that copies the fixture to the report path (%s).
// Exactly one %s → safe for fmt.Sprintf inside suiteFailures.
func suiteCmd(fixturePath string) string {
	return "cp " + fixturePath + " %s"
}

func buildViTestReport(results []struct {
	Name             string
	AssertionResults []struct {
		Status   string
		FullName string
	}
}) []byte {
	type ar struct {
		Status   string `json:"status"`
		FullName string `json:"fullName"`
	}
	type tr struct {
		Name             string `json:"name"`
		AssertionResults []ar   `json:"assertionResults"`
	}
	type report struct {
		TestResults []tr `json:"testResults"`
	}
	rep := report{}
	for _, r := range results {
		t := tr{Name: r.Name}
		for _, a := range r.AssertionResults {
			t.AssertionResults = append(t.AssertionResults, ar{Status: a.Status, FullName: a.FullName})
		}
		rep.TestResults = append(rep.TestResults, t)
	}
	b, _ := json.Marshal(rep)
	return b
}

func TestSuiteFailures_HappyPath(t *testing.T) {
	reportJSON := buildViTestReport([]struct {
		Name             string
		AssertionResults []struct {
			Status   string
			FullName string
		}
	}{
		{
			Name: "src/foo.test.ts",
			AssertionResults: []struct {
				Status   string
				FullName string
			}{
				{Status: "failed", FullName: "foo > bar fails"},
				{Status: "passed", FullName: "foo > bar passes"},
			},
		},
		{
			Name: "src/baz.test.ts",
			AssertionResults: []struct {
				Status   string
				FullName string
			}{
				{Status: "failed", FullName: "baz > thing fails"},
			},
		},
	})
	fix := writeTempFixture(t, reportJSON)
	defer os.Remove(fix)

	cc := ChainConfig{
		SuiteCmd: suiteCmd(fix),
		Worktree: "/tmp",
	}
	fails, err := suiteFailures(cc)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	want := map[string]bool{
		"src/foo.test.ts::foo > bar fails":   true,
		"src/baz.test.ts::baz > thing fails": true,
	}
	if len(fails) != len(want) {
		t.Errorf("len(fails): want %d got %d — map: %v", len(want), len(fails), fails)
	}
	for k := range want {
		if !fails[k] {
			t.Errorf("missing expected failure key: %q", k)
		}
	}
	// passed entries must not appear
	if fails["src/foo.test.ts::foo > bar passes"] {
		t.Error("passed entry incorrectly included in failures")
	}
}

func TestSuiteFailures_AllPassing(t *testing.T) {
	reportJSON := buildViTestReport([]struct {
		Name             string
		AssertionResults []struct {
			Status   string
			FullName string
		}
	}{
		{
			Name: "src/ok.test.ts",
			AssertionResults: []struct {
				Status   string
				FullName string
			}{
				{Status: "passed", FullName: "ok > all good"},
			},
		},
	})
	fix := writeTempFixture(t, reportJSON)
	defer os.Remove(fix)

	cc := ChainConfig{
		SuiteCmd: suiteCmd(fix),
		Worktree: "/tmp",
	}
	fails, err := suiteFailures(cc)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(fails) != 0 {
		t.Errorf("want empty failures map, got %v", fails)
	}
}

func TestSuiteFailures_EmptyReport(t *testing.T) {
	// Command writes an empty file — suiteFailures must return an error,
	// not silently return an empty map (which would falsely pass the delta gate).
	fix := writeTempFixture(t, []byte{}) // empty
	defer os.Remove(fix)
	cc := ChainConfig{
		SuiteCmd: suiteCmd(fix),
		Worktree: "/tmp",
	}
	_, err := suiteFailures(cc)
	if err == nil {
		t.Fatal("expected error for empty report file, got nil — delta gate would silently pass")
	}
}

func TestSuiteFailures_MalformedJSON(t *testing.T) {
	// Command writes garbage JSON — suiteFailures must return an error.
	fix := writeTempFixture(t, []byte("not json at all"))
	defer os.Remove(fix)
	cc := ChainConfig{
		SuiteCmd: suiteCmd(fix),
		Worktree: "/tmp",
	}
	_, err := suiteFailures(cc)
	if err == nil {
		t.Fatal("expected error for malformed JSON report, got nil")
	}
}

func TestSuiteFailures_EmptyTestResults(t *testing.T) {
	// Valid JSON but no test results — returns empty map (no failures), no error.
	fix := writeTempFixture(t, []byte(`{"testResults":[]}`))
	defer os.Remove(fix)
	cc := ChainConfig{
		SuiteCmd: suiteCmd(fix),
		Worktree: "/tmp",
	}
	fails, err := suiteFailures(cc)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(fails) != 0 {
		t.Errorf("want empty map, got %v", fails)
	}
}

// ── triageComment ─────────────────────────────────────────────────────────────

func TestTriageComment_HappyPath(t *testing.T) {
	input := []byte(`{
		"verdict": "actionable",
		"problem": {
			"symptom": "test fails",
			"expected": "test passes",
			"acceptance": "regression test green"
		}
	}`)
	out := triageComment(input)

	if !strings.Contains(out, "**Triage fleet — actionable.**") {
		t.Errorf("missing verdict header; got: %s", out)
	}
	if !strings.Contains(out, "```json") {
		t.Error("missing json code fence")
	}
	if !strings.Contains(out, "bugfix-fleet chain") {
		t.Error("missing fleet attribution")
	}
	// The problem object should be rendered as JSON in the block.
	if !strings.Contains(out, "symptom") {
		t.Error("problem content missing from output")
	}
}

func TestTriageComment_MissingVerdict(t *testing.T) {
	// No "verdict" key — should not panic; verdict becomes empty string.
	input := []byte(`{"problem": {"symptom": "x"}}`)
	out := triageComment(input)
	if !strings.Contains(out, "**Triage fleet — .**") {
		t.Errorf("expected empty verdict in output; got: %s", out)
	}
}

func TestTriageComment_MissingProblem(t *testing.T) {
	// No "problem" key — json.MarshalIndent of nil produces "null".
	input := []byte(`{"verdict": "rejected"}`)
	out := triageComment(input)
	if !strings.Contains(out, "**Triage fleet — rejected.**") {
		t.Errorf("missing verdict; got: %s", out)
	}
	// null is valid JSON — the block should still be present.
	if !strings.Contains(out, "```json") {
		t.Error("missing code fence even with nil problem")
	}
}

func TestTriageComment_EmptyInput(t *testing.T) {
	// Empty/invalid JSON — must not panic.
	out := triageComment([]byte{})
	if out == "" {
		t.Error("expected non-empty output even for empty input")
	}
}

func TestTriageComment_MalformedJSON(t *testing.T) {
	// json.Unmarshal fails; v stays nil → output has empty verdict and null problem.
	out := triageComment([]byte("not json"))
	if out == "" {
		t.Error("expected non-empty output for malformed JSON input")
	}
}

func TestTriageComment_LongProblemTruncated(t *testing.T) {
	// tail() caps at 1800 chars. Build a problem value that would exceed it.
	long := strings.Repeat("x", 2000)
	input, _ := json.Marshal(map[string]any{
		"verdict": "actionable",
		"problem": map[string]any{"symptom": long},
	})
	out := triageComment(input)
	// The total length of the json block portion must be ≤ 1800 chars.
	// Find the content between the fences.
	start := strings.Index(out, "```json\n") + len("```json\n")
	end := strings.Index(out[start:], "\n```")
	if end < 0 {
		t.Fatal("could not locate json block end fence")
	}
	block := out[start : start+end]
	if len(block) > 1800 {
		t.Errorf("json block not truncated: len=%d want ≤1800", len(block))
	}
}
