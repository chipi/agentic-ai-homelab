# Eval skeleton — the verbs. `make help` is the entry point.
#
# Drop this directory into a project, point `data/sources/` at your inputs, and
# the loop below works without editing any script except `run_item()` in
# scripts/experiment_run.py.

PYTHON ?= python3
DATASET_ID ?= smoke_v1
CONFIG ?= data/configs/demo.yaml
REPEAT ?= 1
NOISE ?= 0

.PHONY: help demo dataset-create dataset-materialize experiment-run runs-list \
        run-compare promote baselines-list validate judge clean

help:
	@echo "Eval skeleton — a frozen dataset, a run, a comparison, a baseline."
	@echo ""
	@echo "START HERE"
	@echo "  make demo                     the whole loop on the bundled sample data"
	@echo ""
	@echo "YOUR DATA"
	@echo "  1. put your inputs in data/sources/"
	@echo "  2. make dataset-create  DATASET_ID=my_v1     freeze a selection (+ hashes)"
	@echo "  3. make dataset-materialize DATASET_ID=my_v1 verify hashes, build run inputs"
	@echo "  4. edit scripts/experiment_run.py run_item() to call YOUR system"
	@echo "  5. make experiment-run  CONFIG=data/configs/demo.yaml"
	@echo ""
	@echo "MEASURE HONESTLY"
	@echo "  make experiment-run REPEAT=3                 the arm's own spread"
	@echo "  make run-compare BASE=<run> CAND=<run> NOISE=0.01"
	@echo "  make promote RUN=<run> REASON=\"...\""
	@echo ""
	@echo "INSPECT"
	@echo "  make runs-list | baselines-list | validate | judge"
	@echo ""
	@echo "Read docs/RUNBOOK.md — it walks the same path with the reasoning."

demo:
	@test -n "$$(ls data/sources/*.txt 2>/dev/null)" || { \
	  echo "make demo needs the bundled sample data in data/sources/."; \
	  echo "If you stripped it for a real project, skip the demo and start at"; \
	  echo "step 1 of docs/RUNBOOK.md: put your inputs in data/sources/, then"; \
	  echo "  make dataset-create DATASET_ID=my_v1"; exit 1; }
	@$(MAKE) --no-print-directory dataset-create DATASET_ID=$(DATASET_ID) ARGS="--force"
	@$(MAKE) --no-print-directory dataset-materialize DATASET_ID=$(DATASET_ID)
	@$(MAKE) --no-print-directory experiment-run CONFIG=$(CONFIG) REPEAT=3
	@$(MAKE) --no-print-directory validate
	@echo ""
	@echo "Now: make runs-list, then compare two of them, then promote one."

dataset-create:
	$(PYTHON) scripts/dataset_create.py --dataset-id $(DATASET_ID) $(ARGS)

dataset-materialize:
	$(PYTHON) scripts/materialize.py --dataset-id $(DATASET_ID) $(ARGS)

experiment-run:
	$(PYTHON) scripts/experiment_run.py --config $(CONFIG) --repeat $(REPEAT) $(ARGS)

runs-list:
	@$(PYTHON) scripts/list_runs.py

baselines-list:
	@$(PYTHON) scripts/list_runs.py --baselines

# BASE/CAND are run ids from `make runs-list`.
# NOISE should be the spread `make experiment-run REPEAT=3` reported.
run-compare:
	@test -n "$(BASE)" || { echo "BASE=<run_id> is required (see: make runs-list)"; exit 1; }
	@test -n "$(CAND)" || { echo "CAND=<run_id> is required (see: make runs-list)"; exit 1; }
	$(PYTHON) scripts/compare_runs.py --baseline $(BASE) --candidate $(CAND) --noise $(NOISE)

promote:
	@test -n "$(RUN)" || { echo "RUN=<run_id> is required (see: make runs-list)"; exit 1; }
	@test -n "$(REASON)" || { echo "REASON=\"why this run earned it\" is required"; exit 1; }
	$(PYTHON) scripts/promote_baseline.py --run $(RUN) --reason "$(REASON)" $(ARGS)

validate:
	$(PYTHON) scripts/validate_tree.py

# The judging harness this skeleton grew around: promote -> judge -> aggregate
# -> report over many candidate runs. Keyless by default (FakeJudge).
judge:
	$(PYTHON) runner.py --config config.example.yaml --use-fake-judge

clean:
	rm -rf data/materialized/* data/runs/* out/
	@echo "cleaned materialized/, runs/ and out/ — sources, datasets and baselines kept"
