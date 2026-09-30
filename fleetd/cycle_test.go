package main

import (
	"context"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"syscall"
	"testing"
	"time"
)

// alive reports whether pid still exists (signal 0 probes without killing).
func alive(pid int) bool {
	return syscall.Kill(pid, 0) == nil
}

func readPID(t *testing.T, path string) int {
	t.Helper()
	deadline := time.Now().Add(3 * time.Second)
	for time.Now().Before(deadline) {
		if b, err := os.ReadFile(path); err == nil {
			if pid, err := strconv.Atoi(strings.TrimSpace(string(b))); err == nil && pid > 0 {
				return pid
			}
		}
		time.Sleep(20 * time.Millisecond)
	}
	t.Fatalf("no pid written to %s", path)
	return 0
}

func withGrace(t *testing.T, d time.Duration) {
	t.Helper()
	old := cycleKillGrace
	cycleKillGrace = d
	t.Cleanup(func() { cycleKillGrace = old })
}

func TestExecCycle_OK(t *testing.T) {
	out, outcome := execCycle(context.Background(), FleetConfig{Name: "t", CycleCmd: "echo hello"}, os.Environ())
	if outcome != "ok" || strings.TrimSpace(string(out)) != "hello" {
		t.Fatalf("outcome=%q out=%q", outcome, out)
	}
}

func TestExecCycle_NonZeroExitIsError(t *testing.T) {
	_, outcome := execCycle(context.Background(), FleetConfig{Name: "t", CycleCmd: "exit 3"}, os.Environ())
	if outcome != "error" {
		t.Fatalf("outcome=%q, want error", outcome)
	}
}

// The 2026-09-30 finding: on timeout, a child the cycle started must die with
// it, and the call must return instead of waiting for the child.
func TestExecCycle_TimeoutKillsChildren(t *testing.T) {
	withGrace(t, 2*time.Second)
	pidFile := filepath.Join(t.TempDir(), "child.pid")
	cmd := "sleep 300 & echo $! > " + pidFile + "; sleep 300"
	ctx, cancel := context.WithTimeout(context.Background(), 500*time.Millisecond)
	defer cancel()

	start := time.Now()
	_, outcome := execCycle(ctx, FleetConfig{Name: "t", CycleCmd: cmd}, os.Environ())
	took := time.Since(start)

	if outcome != "timeout" {
		t.Fatalf("outcome=%q, want timeout", outcome)
	}
	if took > 500*time.Millisecond+cycleKillGrace+time.Second {
		t.Fatalf("returned after %s; want within timeout + grace", took)
	}
	child := readPID(t, pidFile)
	time.Sleep(100 * time.Millisecond)
	if alive(child) {
		_ = syscall.Kill(child, syscall.SIGKILL)
		t.Fatalf("child %d survived the cycle timeout", child)
	}
}

// A child that ignores SIGTERM is SIGKILLed once the grace period is over.
func TestExecCycle_TimeoutKillsTermIgnoringChild(t *testing.T) {
	withGrace(t, time.Second)
	pidFile := filepath.Join(t.TempDir(), "child.pid")
	cmd := "sh -c 'trap \"\" TERM; echo $$ > " + pidFile + "; while :; do sleep 1; done' & sleep 300"
	ctx, cancel := context.WithTimeout(context.Background(), 500*time.Millisecond)
	defer cancel()

	start := time.Now()
	_, outcome := execCycle(ctx, FleetConfig{Name: "t", CycleCmd: cmd}, os.Environ())
	took := time.Since(start)

	if outcome != "timeout" {
		t.Fatalf("outcome=%q, want timeout", outcome)
	}
	if took > 500*time.Millisecond+cycleKillGrace+2*time.Second {
		t.Fatalf("returned after %s; want within timeout + grace", took)
	}
	child := readPID(t, pidFile)
	time.Sleep(200 * time.Millisecond)
	if alive(child) {
		_ = syscall.Kill(child, syscall.SIGKILL)
		t.Fatalf("SIGTERM-ignoring child %d survived", child)
	}
}

// A cycle that exits 0 but leaves a background child holding its output must
// not block the fleet loop: it returns after the grace period, still "ok".
func TestExecCycle_LingeringChildDoesNotBlock(t *testing.T) {
	withGrace(t, time.Second)
	pidFile := filepath.Join(t.TempDir(), "child.pid")
	cmd := "sleep 300 & echo $! > " + pidFile + "; echo done"

	start := time.Now()
	out, outcome := execCycle(context.Background(), FleetConfig{Name: "t", CycleCmd: cmd}, os.Environ())
	took := time.Since(start)

	child := readPID(t, pidFile)
	defer syscall.Kill(child, syscall.SIGKILL)
	if outcome != "ok" || !strings.Contains(string(out), "done") {
		t.Fatalf("outcome=%q out=%q", outcome, out)
	}
	if took > cycleKillGrace+2*time.Second {
		t.Fatalf("blocked %s on a lingering child", took)
	}
}
