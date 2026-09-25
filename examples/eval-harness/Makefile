# Eval harness — the verbs. `make help` is the entry point.
#
# Drop this directory into a project, point `data/sources/` at your inputs, edit
# ONE function in scripts/adapter.py, and the loop below works.
#
# Target names deliberately mirror the conventions of the project this pattern
# came from, so muscle memory transfers: dataset-create, dataset-materialize,
# experiment-dry-run, experiment-run, run-compare, run-promote, runs-list,
# baselines-list, validate, check, ci.

# Prefer the venv `make install` creates, so `make install` is not immediately followed by
# having to pass PYTHON=.venv/bin/python to every other target. Overridable as before.
PYTHON ?= $(shell [ -x .venv/bin/python ] && echo .venv/bin/python || echo python3)
VENV ?= .venv
DATASET_ID ?= smoke_v1
CONFIG ?= data/configs/demo.yaml
REPEAT ?= 1
NOISE ?=
TIER ?= silver

.PHONY: help demo env-check install venv-init \
        dataset-create dataset-materialize reference-create \
        experiment-dry-run experiment-run sweep \
        runs-list baselines-list run-compare leaderboard run-promote \
        validate judge check ci test clean clean-cache

# ── getting started ─────────────────────────────────────────────────────────
help:
	@echo "Eval harness — a frozen dataset, a run, a comparison, a baseline."
	@echo ""
	@echo "START HERE"
	@echo "  make install                  create $(VENV) and install deps"
	@echo "  make demo                     the whole loop on bundled data (no API key)"
	@echo "  make env-check                are my keys and caps set?"
	@echo ""
	@echo "YOUR DATA"
	@echo "  1. put your inputs in data/sources/"
	@echo "  2. cp .env.example .env       and fill in the keys you need"
	@echo "  3. make dataset-create  DATASET_ID=my_v1"
	@echo "  4. make dataset-materialize DATASET_ID=my_v1"
	@echo "  5. edit scripts/adapter.py    call_system() -> YOUR system"
	@echo "  6. make reference-create DATASET_ID=my_v1 CONFIG=<trusted model>"
	@echo ""
	@echo "MEASURE  (dry-run first — it costs nothing and tells you what the sweep will)"
	@echo "  make experiment-dry-run CONFIG=data/configs/arm_a.yaml"
	@echo "  make experiment-run     CONFIG=data/configs/arm_a.yaml REPEAT=3"
	@echo "  make sweep CONFIGS=\"data/configs/arm_*.yaml\" REPEAT=2"
	@echo ""
	@echo "DECIDE"
	@echo "  make leaderboard DATASET_ID=my_v1        rank every arm: quality, cost, speed"
	@echo "  make run-compare BASE=<run> CAND=<run> NOISE=<measured spread>"
	@echo "  make run-promote RUN=<run> REASON=\"...\""
	@echo ""
	@echo "INSPECT / GATE"
	@echo "  make runs-list | baselines-list | validate | judge"
	@echo "  make check                    validate + test"
	@echo ""
	@echo "Read docs/INTEGRATION.md first, then docs/RUNBOOK.md."

install venv-init:
	@test -d $(VENV) || $(PYTHON) -m venv $(VENV)
	$(VENV)/bin/pip install -q --upgrade pip
	$(VENV)/bin/pip install -q -r requirements.txt
	@echo "$(VENV) ready. Use it with:  make <target> PYTHON=$(VENV)/bin/python"

env-check:
	@$(PYTHON) scripts/env_check.py

demo:
	@test -n "$$(ls data/sources/*.txt 2>/dev/null)" || { \
	  echo "make demo needs the bundled sample data in data/sources/."; \
	  echo "If you stripped it for a real project, start at step 1 of docs/RUNBOOK.md:"; \
	  echo "  make dataset-create DATASET_ID=my_v1"; exit 1; }
	@$(MAKE) --no-print-directory dataset-create DATASET_ID=$(DATASET_ID) ARGS="--force"
	@$(MAKE) --no-print-directory dataset-materialize DATASET_ID=$(DATASET_ID)
	@$(MAKE) --no-print-directory experiment-run CONFIG=$(CONFIG) REPEAT=3
	@$(MAKE) --no-print-directory validate
	@echo ""
	@echo "Now: make runs-list, then make leaderboard DATASET_ID=$(DATASET_ID)"

# ── data lifecycle ──────────────────────────────────────────────────────────
dataset-create:
	$(PYTHON) scripts/dataset_create.py --dataset-id $(DATASET_ID) $(ARGS)

dataset-materialize:
	$(PYTHON) scripts/materialize.py --dataset-id $(DATASET_ID) $(ARGS)

# Author ground truth with a model you trust. SILVER by default (model-generated);
# TIER=gold once a human has reviewed it.
reference-create:
	@test -n "$(CONFIG)" || { echo "CONFIG=<config naming the reference model> is required"; exit 1; }
	$(PYTHON) scripts/reference_create.py --dataset-id $(DATASET_ID) --config $(CONFIG) --tier $(TIER) $(ARGS)

# ── experiments ─────────────────────────────────────────────────────────────
experiment-dry-run:
	$(PYTHON) scripts/experiment_run.py --config $(CONFIG) --repeat $(REPEAT) --dry-run

experiment-run:
	$(PYTHON) scripts/experiment_run.py --config $(CONFIG) --repeat $(REPEAT) $(ARGS)

# CONFIGS is a glob: make sweep CONFIGS="data/configs/arm_*.yaml"
sweep:
	@test -n "$(CONFIGS)" || { echo 'CONFIGS="data/configs/arm_*.yaml" is required'; exit 1; }
	$(PYTHON) scripts/sweep.py --configs $(CONFIGS) --repeat $(REPEAT) $(ARGS)

# ── inspect and decide ──────────────────────────────────────────────────────
runs-list:
	@$(PYTHON) scripts/list_runs.py

baselines-list:
	@$(PYTHON) scripts/list_runs.py --baselines

leaderboard:
	$(PYTHON) scripts/leaderboard.py --dataset-id $(DATASET_ID) $(ARGS)

run-compare:
	@test -n "$(BASE)" || { echo "BASE=<run_id> is required (see: make runs-list)"; exit 1; }
	@test -n "$(CAND)" || { echo "CAND=<run_id> is required (see: make runs-list)"; exit 1; }
	$(PYTHON) scripts/compare_runs.py --baseline $(BASE) --candidate $(CAND) \
	  $(if $(NOISE),--noise $(NOISE),) $(ARGS)

run-promote:
	@test -n "$(RUN)" || { echo "RUN=<run_id> is required (see: make runs-list)"; exit 1; }
	@test -n "$(REASON)" || { echo 'REASON="why this run earned it" is required'; exit 1; }
	$(PYTHON) scripts/promote_baseline.py --run $(RUN) --reason "$(REASON)" $(ARGS)

# ── gates ───────────────────────────────────────────────────────────────────
validate:
	$(PYTHON) scripts/validate_tree.py

test:
	$(PYTHON) scripts/self_test.py

check: validate test
	@echo ""
	@echo "check: tree valid, self-tests pass"

ci: check
	@echo "ci: green"

# The judge panel: promote -> judge -> aggregate -> report over candidate runs.
# Keyless by default (FakeJudge).
judge:
	$(PYTHON) runner.py --config config.example.yaml --use-fake-judge $(ARGS)

# ── housekeeping ────────────────────────────────────────────────────────────
clean:
	# NEVER delete a tracked file. `rm -rf data/runs/*` used to take data/runs/README.md with
	# it — the file documenting what a run directory IS — while the line below reassured you
	# about the directories it had NOT touched; four per-directory READMEs were lost that way.
	# It would now also delete the shipped worked example, and with it the run the committed
	# baseline points at, so `make clean` would leave the tree failing its own V6.
	#
	# "Is it tracked?" is the right question, not "is it named README.md": git already knows
	# which files someone decided to keep.
	@find data/materialized data/runs -mindepth 1 -maxdepth 1 -print 2>/dev/null \
	  | while read -r f; do \
	      git ls-files --error-unmatch "$$f" >/dev/null 2>&1 || rm -rf "$$f"; \
	    done
	@rm -rf out/
	@echo "cleaned materialized/, runs/ and out/ — every TRACKED file kept (READMEs, the shipped worked example, sources, datasets, references, baselines)"

clean-cache:
	find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
	@echo "cleaned __pycache__"
