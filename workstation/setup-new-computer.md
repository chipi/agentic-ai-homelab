# Set up a new computer

Bootstrap a fresh Mac to the operator's global agent-config baseline. Ordered;
each step is safe to re-run. Assumes macOS (Apple Silicon, `/opt/homebrew`).

## 1. System prerequisites

```bash
xcode-select --install                       # Command Line Tools
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
brew install git gh node
```

## 2. Agent toolchain

```bash
brew install --cask claude                   # Claude Code CLI (Homebrew is canonical)
npm i -g opencode-ai                          # opencode
brew install rtk                              # OPTIONAL: manual 'rtk <cmd>' only — retired from the Claude hook path (D-0010)
# lean-ctx: auto-installs on first MCP use, or:
curl -fsSL https://raw.githubusercontent.com/yvgude/lean-ctx/main/skills/lean-ctx/scripts/install.sh | bash
lean-ctx setup
```

Confirm each is on `PATH` (the hooks call `/opt/homebrew/bin/lean-ctx` by
absolute path): `claude --version`, `opencode --version`, `lean-ctx --version`
(and `rtk --version` only if you opted into the manual rtk tool above).

## 3. Clone this repo and symlink the config

```bash
git clone https://github.com/chipi/agentic-ai-homelab.git ~/Projects/agentic-ai-homelab
cd ~/Projects/agentic-ai-homelab
./workstation/install.sh --dry-run           # preview: what gets linked / backed up
./workstation/install.sh                     # symlink ~/.config + ~/.claude into the repo
```

This links the **non-secret** files (`AGENTS.md`, `CLAUDE.md`,
lean-ctx/ponytail config, the `docs-preflight` skill). Existing files are backed
up as `*.bak.<timestamp>`.

## 4. Fill the secret-bearing templates

Not symlinked — copy and edit by hand:

```bash
cp workstation/config/opencode/opencode.json.example ~/.config/opencode/opencode.json
#   → set baseURL to your DGX tailnet host
cp workstation/claude/settings.json.example ~/.claude/settings.json
#   → set the ponytail <VERSION> path; permissions.allow starts empty and re-accrues
```

Secrets that live in the **environment**, not in any tracked file — add to your
shell profile:

```bash
export OPENROUTER_API_KEY="..."              # opencode fleet (OpenRouter roster)
```

## 5. Authenticate the credentialed tools

```bash
gh auth login                                 # GitHub
gcloud auth application-default login         # only if you use the gcloud tooling
# higgsfield / grafana-assistant: log in through their own flows as needed
```

## 6. Plugins and marketplaces

The `ponytail` statusline and `oh-my-openagent` fleet plugin are referenced by
the config. Install via their marketplaces (ponytail source is pinned in
`settings.json.example` → `extraKnownMarketplaces`). In Claude Code, add the
marketplace and enable the plugin; `oh-my-openagent@latest` is pulled by
opencode from `opencode.json`.

## 7. Verify

```bash
claude --version                              # matches the standardized Homebrew build
ls -l ~/.config/AGENTS.md                     # → symlink into workstation/config/
ls -l ~/.claude/CLAUDE.md                     # → symlink into workstation/claude/
```

- Open Claude Code: the ponytail statusline renders, and `/docs-preflight` shows
  in the skills list (proves `~/.claude/skills/docs-preflight` is linked).
- Run something that triggers a Bash tool: the lean-ctx `PreToolUse` hook fires
  (compression/rewrite active). Try a `git commit` that stages a fake key
  (`api_key=AKIA...`) in a throwaway repo — the `secrets-guard` hook blocks it.
- In any docs repo, `make docs-build` (or the `docs-preflight` skill) runs green.

Details and the home↔repo map: [`README.md`](README.md).
