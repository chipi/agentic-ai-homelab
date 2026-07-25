// fleetd — the fleet supervisor daemon (RFC-0004).
//
// One static binary supervising N fleets. Deliberately dumb: scheduling,
// kill-switch, budget guard, metrics, digest transport. All intelligence
// lives in the fleets' own cycle commands (evaled Python cores). No LLM
// calls happen here, ever.
//
// Config is JSON (stdlib-only; ADR-0008 forbids casual deps — TOML would
// need one). See fleetd.json.example.
package main

import (
	"bytes"
	"context"
	"encoding/json"
	"flag"
	"fmt"
	"log"
	"net/http"
	"os"
	"os/exec"
	"os/signal"
	"path/filepath"
	"strings"
	"sync"
	"syscall"
	"time"
)

type FleetConfig struct {
	Name         string  `json:"name"`
	Enabled      bool    `json:"enabled"`
	Interval     string  `json:"interval"`      // Go duration, e.g. "10m"
	CycleCmd     string  `json:"cycle_cmd"`     // run via sh -c
	Workdir      string  `json:"workdir"`
	EnvFile      string  `json:"env_file"`      // KEY=VAL lines, optional
	StopFlag     string  `json:"stop_flag"`     // file present => skip cycles
	BudgetDayUSD float64 `json:"budget_day_usd"`
	SpendFile    string  `json:"spend_file"`    // cycle writes last-cycle USD here, optional
	Stage        string  `json:"stage"`         // shadow | propose | live
	CycleTimeout string  `json:"cycle_timeout"` // Go duration, default 30m
}

type Config struct {
	VMURL     string        `json:"vm_url"`     // VictoriaMetrics import base, "" disables
	StateFile string        `json:"state_file"` // day-spend persistence
	Fleets    []FleetConfig `json:"fleets"`
}

// dayState persists per-fleet daily spend across restarts.
type dayState struct {
	Day   string             `json:"day"` // YYYY-MM-DD local
	Spend map[string]float64 `json:"spend"`
}

type supervisor struct {
	cfg   Config
	mu    sync.Mutex
	state dayState
}

func main() {
	cfgPath := flag.String("config", "fleetd.json", "path to config")
	once := flag.Bool("once", false, "run one cycle per enabled fleet, then exit (smoke/test)")
	flag.Parse()

	raw, err := os.ReadFile(*cfgPath)
	if err != nil {
		log.Fatalf("config: %v", err)
	}
	var cfg Config
	if err := json.Unmarshal(raw, &cfg); err != nil {
		log.Fatalf("config parse: %v", err)
	}
	s := &supervisor{cfg: cfg}
	s.loadState()

	ctx, cancel := context.WithCancel(context.Background())
	go func() {
		ch := make(chan os.Signal, 1)
		signal.Notify(ch, syscall.SIGINT, syscall.SIGTERM)
		sig := <-ch
		log.Printf("signal %v — draining in-flight cycles, then exit", sig)
		cancel()
	}()

	var wg sync.WaitGroup
	for _, f := range cfg.Fleets {
		if !f.Enabled {
			log.Printf("[%s] disabled", f.Name)
			continue
		}
		wg.Add(1)
		go func(f FleetConfig) {
			defer wg.Done()
			if *once {
				s.runCycle(ctx, f)
				return
			}
			s.loop(ctx, f)
		}(f)
	}
	wg.Wait()
	log.Printf("fleetd exit")
}

func (s *supervisor) loop(ctx context.Context, f FleetConfig) {
	ival, err := time.ParseDuration(f.Interval)
	if err != nil || ival <= 0 {
		log.Printf("[%s] bad interval %q — fleet not started", f.Name, f.Interval)
		return
	}
	log.Printf("[%s] loop started: every %s, stage=%s, budget=$%.2f/day",
		f.Name, ival, f.Stage, f.BudgetDayUSD)
	// first cycle immediately, then tick
	s.runCycle(ctx, f)
	t := time.NewTicker(ival)
	defer t.Stop()
	for {
		select {
		case <-ctx.Done():
			log.Printf("[%s] loop stopped", f.Name)
			return
		case <-t.C:
			s.runCycle(ctx, f)
		}
	}
}

func (s *supervisor) runCycle(ctx context.Context, f FleetConfig) {
	if _, err := os.Stat(f.StopFlag); f.StopFlag != "" && err == nil {
		log.Printf("[%s] STOP flag present (%s) — cycle skipped", f.Name, f.StopFlag)
		s.pushMetric(f, "skipped_stopflag", 0)
		return
	}
	if spent := s.daySpend(f.Name); f.BudgetDayUSD > 0 && spent >= f.BudgetDayUSD {
		log.Printf("[%s] daily budget reached ($%.2f/$%.2f) — paused until midnight",
			f.Name, spent, f.BudgetDayUSD)
		s.pushMetric(f, "skipped_budget", 0)
		return
	}

	timeout := 30 * time.Minute
	if f.CycleTimeout != "" {
		if d, err := time.ParseDuration(f.CycleTimeout); err == nil {
			timeout = d
		}
	}
	cctx, cancel := context.WithTimeout(ctx, timeout)
	defer cancel()

	cmd := exec.CommandContext(cctx, "sh", "-c", f.CycleCmd)
	cmd.Dir = f.Workdir
	cmd.Env = append(os.Environ(),
		"FLEETD_STAGE="+f.Stage,
		fmt.Sprintf("FLEETD_BUDGET_LEFT=%.4f", f.BudgetDayUSD-s.daySpend(f.Name)),
	)
	cmd.Env = append(cmd.Env, readEnvFile(f.EnvFile)...)

	start := time.Now()
	out, err := cmd.CombinedOutput()
	dur := time.Since(start)
	outcome := "ok"
	if cctx.Err() == context.DeadlineExceeded {
		outcome = "timeout"
	} else if err != nil {
		outcome = "error"
	}
	log.Printf("[%s] cycle %s in %s (%d bytes output)", f.Name, outcome, dur.Round(time.Second), len(out))
	if outcome != "ok" {
		// keep the tail for forensics — cycles log their own detail in their ledgers
		tail := out
		if len(tail) > 800 {
			tail = tail[len(tail)-800:]
		}
		log.Printf("[%s] output tail: %s", f.Name, strings.TrimSpace(string(tail)))
	}

	if spend := s.readSpend(f); spend > 0 {
		s.addSpend(f.Name, spend)
		log.Printf("[%s] cycle spend $%.4f (day total $%.4f)", f.Name, spend, s.daySpend(f.Name))
	}
	s.pushMetric(f, outcome, dur.Seconds())
}

// readSpend consumes (and truncates) the cycle's spend report, if configured.
func (s *supervisor) readSpend(f FleetConfig) float64 {
	if f.SpendFile == "" {
		return 0
	}
	b, err := os.ReadFile(f.SpendFile)
	if err != nil {
		return 0
	}
	_ = os.Truncate(f.SpendFile, 0)
	var v float64
	fmt.Sscanf(strings.TrimSpace(string(b)), "%f", &v)
	return v
}

func (s *supervisor) pushMetric(f FleetConfig, outcome string, durSec float64) {
	if s.cfg.VMURL == "" {
		return
	}
	body := fmt.Sprintf(
		"fleetd_cycle{fleet=%q,outcome=%q,stage=%q,service=\"fleetd\",environment=\"operations\"} 1\n"+
			"fleetd_cycle_seconds{fleet=%q,stage=%q,service=\"fleetd\",environment=\"operations\"} %.1f\n"+
			"fleetd_spend_day{fleet=%q,service=\"fleetd\",environment=\"operations\"} %.4f\n",
		f.Name, outcome, f.Stage, f.Name, f.Stage, durSec, f.Name, s.daySpend(f.Name))
	req, _ := http.NewRequest("POST", s.cfg.VMURL+"/api/v1/import/prometheus", bytes.NewBufferString(body))
	c := &http.Client{Timeout: 8 * time.Second}
	if resp, err := c.Do(req); err != nil {
		log.Printf("[%s] metric push failed: %v", f.Name, err)
	} else {
		resp.Body.Close()
	}
}

// ---- day-spend state (tiny, restart-safe) ----

func today() string { return time.Now().Format("2006-01-02") }

func (s *supervisor) loadState() {
	s.state = dayState{Day: today(), Spend: map[string]float64{}}
	if s.cfg.StateFile == "" {
		return
	}
	if b, err := os.ReadFile(s.cfg.StateFile); err == nil {
		var st dayState
		if json.Unmarshal(b, &st) == nil && st.Day == today() && st.Spend != nil {
			s.state = st
		}
	}
}

func (s *supervisor) saveState() {
	if s.cfg.StateFile == "" {
		return
	}
	_ = os.MkdirAll(filepath.Dir(s.cfg.StateFile), 0o755)
	b, _ := json.Marshal(s.state)
	_ = os.WriteFile(s.cfg.StateFile, b, 0o644)
}

func (s *supervisor) rolloverLocked() {
	if s.state.Day != today() {
		s.state = dayState{Day: today(), Spend: map[string]float64{}}
	}
}

func (s *supervisor) daySpend(fleet string) float64 {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.rolloverLocked()
	return s.state.Spend[fleet]
}

func (s *supervisor) addSpend(fleet string, usd float64) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.rolloverLocked()
	s.state.Spend[fleet] += usd
	s.saveState()
}

func readEnvFile(path string) []string {
	if path == "" {
		return nil
	}
	b, err := os.ReadFile(path)
	if err != nil {
		log.Printf("env file %s: %v", path, err)
		return nil
	}
	var out []string
	for _, line := range strings.Split(string(b), "\n") {
		line = strings.TrimSpace(line)
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}
		line = strings.TrimPrefix(line, "export ")
		if strings.Contains(line, "=") {
			out = append(out, strings.Trim(line, `"`))
		}
	}
	return out
}
