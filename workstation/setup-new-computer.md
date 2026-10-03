# Set up a new computer

Bootstrap a fresh machine to the operator's global agent-config baseline.
Ordered; each step is safe to re-run. Two supported platforms:

- **macOS** — Apple Silicon, Homebrew under `/opt/homebrew`.
- **Linux** — Omarchy (Arch), tools from `pacman` and [mise](https://mise.jdx.dev).

Steps 1–2 are per-platform. Steps 3–7 are shared, apart from the platform notes
marked inline: the agent config itself (`AGENTS.md`, `CLAUDE.md`, skills,
subagents, hooks, workflows) is identical on both.

## 1. System prerequisites

### macOS

```bash
xcode-select --install                       # Command Line Tools
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
brew install git gh node jq
```

### Linux (Omarchy / Arch)

Omarchy ships `git`, `tmux`, `jq` and `mise`. Add `lsof`: the `session-reap` and
`session-orphan-report` hooks use it to read a process's working directory, and
without it they silently do nothing.

```bash
sudo pacman -S --needed git jq lsof
mise use -g node gh                          # global toolchain in ~/.config/mise/config.toml
```

## 2. Agent toolchain

### macOS

```bash
brew install --cask claude                   # Claude Code CLI (Homebrew is canonical)
npm i -g opencode-ai                          # opencode
brew install rtk                              # OPTIONAL: manual 'rtk <cmd>' only — retired from the Claude hook path (D-0010)
# lean-ctx: auto-installs on first MCP use, or:
curl -fsSL https://raw.githubusercontent.com/yvgude/lean-ctx/main/skills/lean-ctx/scripts/install.sh | bash
lean-ctx setup
```

### Linux (Omarchy / Arch)

```bash
mise use -g claude opencode                  # Claude Code CLI + opencode
# lean-ctx: installs to ~/.local/bin/lean-ctx
curl -fsSL https://raw.githubusercontent.com/yvgude/lean-ctx/main/skills/lean-ctx/scripts/install.sh | bash
lean-ctx setup
```

### Both

Confirm each is on `PATH`: `claude --version`, `opencode --version`,
`lean-ctx --version` (and `rtk --version` only if you opted into the manual rtk
tool above). The Claude Code hooks and the opencode MCP entry call bare
`lean-ctx`, resolved through the `PATH` the agent was started with
(`/opt/homebrew/bin` on macOS, `~/.local/bin` on Linux). An agent started
without it on `PATH` loses the lean-ctx hooks.

## 3. Clone this repo and symlink the config

```bash
git clone https://github.com/chipi/agentic-ai-homelab.git ~/Projects/agentic-ai-homelab
cd ~/Projects/agentic-ai-homelab
./workstation/install.sh --dry-run           # preview: what gets linked / backed up
./workstation/install.sh                     # symlink ~/.config + ~/.claude into the repo
```

The clone location is free; on Linux the repo usually lives under `/work/`.
`install.sh` detects the platform (the `platform:` line of its output).

This links the **non-secret** files (`AGENTS.md`, `CLAUDE.md`,
lean-ctx/ponytail config, every skill/subagent/hook/workflow). Existing files
are backed up as `*.bak.<timestamp>`. `--dry-run` changes nothing on disk.

- **macOS only:** also links the [workbench](workbench/README.md) (`~/bin/wb`,
  `~/bin/wb-session.sh`, `~/.tmux.conf`, the `com.chipi.workbench` LaunchAgent),
  which needs a one-off `launchctl bootstrap` afterwards (see that README).
- **Linux:** no workbench and no `~/.tmux.conf`: one tmux session per project,
  and Omarchy's `~/.config/tmux/tmux.conf` stays in charge. To preview the Mac
  plan from Linux (or the reverse): `WS_OS=macos ./workstation/install.sh --dry-run`.

## 4. Fill the secret-bearing templates

Not symlinked — copy and edit by hand:

```bash
cp workstation/config/opencode/opencode.json.example ~/.config/opencode/opencode.json
#   → set baseURL to your DGX tailnet host
cp workstation/claude/settings.json.example ~/.claude/settings.json
#   → set the ponytail <VERSION> path; permissions.allow starts empty and re-accrues
```

If `~/.claude/settings.json` already exists (e.g. `lean-ctx setup` in step 2
wrote it), don't overwrite it: `install.sh` (step 3) already merged the
workstation hooks (`secrets-guard`, `session-orphan-report`, `session-reap`)
into it — see
[`claude/hooks/README.md` → Wiring into settings.json](claude/hooks/README.md#wiring-into-settingsjson).
If you copy the template instead, they come with it. Either way, check they are wired:
`jq -r '.. | .command? // empty' ~/.claude/settings.json | grep .claude/hooks/`
should list all three.

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
claude --version                              # macOS: the standardized Homebrew build; Linux: mise
ls -l ~/.config/AGENTS.md                     # → symlink into workstation/config/
ls -l ~/.claude/CLAUDE.md                     # → symlink into workstation/claude/
command -v lean-ctx lsof                      # Linux: both must resolve (hooks need them)
```

- Open Claude Code: the ponytail statusline renders, and `/docs-preflight` shows
  in the skills list (proves `~/.claude/skills/docs-preflight` is linked).
- Run something that triggers a Bash tool: the lean-ctx `PreToolUse` hook fires
  (compression/rewrite active). Try a `git commit` that stages a fake key
  (`api_key=AKIA...`) in a throwaway repo — the `secrets-guard` hook blocks it.
- In any docs repo, `make docs-build` (or the `docs-preflight` skill) runs green.

Details and the home↔repo map: [`README.md`](README.md).
