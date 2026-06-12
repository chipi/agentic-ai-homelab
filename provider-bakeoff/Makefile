# provider-bakeoff — compare 10 LLM providers on 2 tasks.
#
# Convention (per the parent repo's global AGENTS.md #17): each invocation
# ends with an unambiguous exit signal. Use:
#   make <target>; echo "MAKE_EXIT=$?"
# when running unattended.

SHELL          := /usr/bin/env bash
.SHELLFLAGS    := -eu -o pipefail -c
.DEFAULT_GOAL  := help

PYTHON         ?= python3
VENV_DIR       ?= .venv
VENV_BIN       := $(VENV_DIR)/bin
PIP            := $(VENV_BIN)/pip
PY             := $(VENV_BIN)/python

# Loads .env into the shell environment for the Python process — no
# python-dotenv dep required. Provider classes read os.environ directly.
ENV_LOAD       := set -a; [ -f .env ] && source .env; set +a;

TASK           ?= json-extraction      # json-extraction | commit-message
PROVIDERS      ?=
OUT            ?= out

# ---- Meta --------------------------------------------------------------------

.PHONY: help
help: ## Show this help
	@awk 'BEGIN {FS = ":.*##"; printf "Targets:\n"} \
		/^[a-zA-Z0-9_.-]+:.*##/ {printf "  \033[36m%-22s\033[0m %s\n", $$1, $$2}' \
		$(MAKEFILE_LIST)

# ---- Setup -------------------------------------------------------------------

$(VENV_DIR):
	$(PYTHON) -m venv $(VENV_DIR)
	$(PIP) install --quiet --upgrade pip

.PHONY: setup
setup: $(VENV_DIR) ## Create .venv and install deps
	$(PIP) install --quiet -r requirements.txt
	@echo "deps installed → $(VENV_DIR)"
	@if [ ! -f .env ]; then \
		echo ""; \
		echo "→ No .env yet. Run:  cp .env.example .env  then fill in keys you have."; \
		echo "  Bake-off skips providers whose env vars are unset."; \
	fi

# ---- Run the bake-off --------------------------------------------------------

.PHONY: bakeoff
bakeoff: setup ## Run bake-off (TASK=json-extraction|commit-message, PROVIDERS=label1,label2)
	@$(ENV_LOAD) $(PY) bakeoff.py --task $(TASK) \
		$(if $(PROVIDERS),--providers $(PROVIDERS),) \
		--out $(OUT)

.PHONY: bakeoff-fake
bakeoff-fake: setup ## Run bake-off with FakeProvider only — no API calls
	@$(PY) bakeoff.py --task $(TASK) --use-fake --out $(OUT)

.PHONY: bakeoff-all-tasks
bakeoff-all-tasks: setup ## Run bake-off across both tasks
	@$(ENV_LOAD) $(PY) bakeoff.py --task json-extraction \
		$(if $(PROVIDERS),--providers $(PROVIDERS),) --out $(OUT)
	@$(ENV_LOAD) $(PY) bakeoff.py --task commit-message \
		$(if $(PROVIDERS),--providers $(PROVIDERS),) --out $(OUT)

# ---- Discoverability ---------------------------------------------------------

.PHONY: providers
providers: setup ## List which providers would be discovered given current env
	@$(ENV_LOAD) $(PY) -c "from providers import discover_providers; \
		ps = discover_providers(); \
		print('\n'.join(f'  {p.org}  ({p.label})' for p in ps))"

.PHONY: tasks
tasks: ## List registered tasks
	@$(PY) -c "from tasks import TASKS; \
		print('\n'.join(f'  {name}: {spec.description}' for name, spec in TASKS.items()))"

# ---- Maintenance -------------------------------------------------------------

.PHONY: clean
clean: ## Remove venv + all bake-off output
	rm -rf $(VENV_DIR) $(OUT) __pycache__ .pytest_cache
	@echo "cleaned"
