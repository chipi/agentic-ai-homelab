---
name: extraction-rebase
description: Rebase a branch that deletes extracted code (code moved to another repo) onto a new trunk. It sorts the stopped rebase's conflicts: a trunk-modified file the branch deletes gets deleted, with the trunk commits that must be ported to the extracted repo listed; content conflicts are shown hunk by hunk for a decision, never taken blindly. After the rebase it lists every kept file and test that still points at a deleted path. Use when rebasing an extraction PR (podcast_scraper PR 2138, any "remove what moved to repo X" branch), when a rebase stops on modify/delete conflicts, or when asked "what still references the deleted files".
---

# extraction-rebase

PR 2138 removes what moved from `chipi/podcast_scraper` to `chipi/infra` (+461/−47k).
Every time main moved, it was rebased again (2026-10-14, 10-16, 10-17). The same conflicts came
back each time, and so did the same hand-written scripts (`take_ours.py`, `take_theirs.py`,
`resolve1.py`, `refs.py`, `deadrefs.py`):

- modify/delete on files main kept editing and the PR deletes (`deploy-player.yml`,
  `player.alloy`, the obs guides, `docker-compose.homelab.yml`);
- content conflicts in `mkdocs.yml`, `AGENTS.md`, `pyproject.toml`;
- after the rebase, kept files and tests still naming a deleted path.

The modify/delete case carries a trap. Resolving it by deleting is right for the PR, **but the
trunk's edit to that file is then lost from this repo**. It has to reach the extracted repo
(for podcast_scraper: the infra port). The script lists those trunk commits for that reason.

## During the rebase

```bash
git rebase origin/main            # stops on conflicts
K=~/.claude/skills/extraction-rebase/scripts
python3 $K/rebase_conflicts.py            # classify, changes nothing
python3 $K/rebase_conflicts.py --apply    # delete only the safe kinds
python3 $K/rebase_conflicts.py --show mkdocs.yml   # hunks with line numbers, then Edit by hand
git add <resolved> && GIT_EDITOR=true git rebase --continue    # repeat per stopped commit
```

| status | meaning in a rebase | what the script does |
| --- | --- | --- |
| UD, path in the branch's delete set | trunk modified, branch deleted | DELETE; lists the trunk commits to port |
| UD, path not in the delete set | as above, but the branch never meant to delete it | MANUAL |
| DD | both deleted | DELETE |
| DU | trunk deleted, branch modified | MANUAL |
| UU / AA / AU / UA | content conflict | MANUAL, with a hunk count |

The delete set is what the branch deletes: `diff --diff-filter=D --no-renames` from the old base
to `orig-head`. `--delete-set FILE` overrides it. Exit 3 means something is left for a human,
0 means nothing is.

## After the rebase

```bash
python3 $K/dangling_refs.py --base origin/main [--exclude docs/history/]
```

1. Kept files that mention a deleted path, split into **code and config** and **prose**. The
   full path always counts. A bare file name counts only when it is distinctive (8+ chars, not
   generic like `README.md`, no kept file with the same name).
2. Test files that build a path (`"infra/…"` literals or `ROOT / "infra" / …`) to something the
   branch deleted.

Every line is a candidate. A history note naming a moved file is usually correct as it is. Read
the code/config group first: a runtime reference there breaks something after the cutover.

## Tested 2026-10-17

- **`rebase_conflicts.py`**, synthetic repo whose rebase stops with UD (in the delete set, trunk
  edited it), DU and UU:
  - classify → 1 DELETE (listing the trunk commit), 2 MANUAL, exit 3;
  - `--show` printed the one hunk;
  - `--apply` deleted only the UD path;
  - after the hand fixes → exit 0 and `rebase --continue` finished;
  - outside a rebase → exit 2.
- **`dangling_refs.py`** on the same repo: found the README mention, the test literal and the
  `ROOT / …` join, exit 1. On PR 2138 (`acdfed1b` vs `b0edbb94`): 272 deleted paths, 64
  code/config and 116 prose candidates, 0 tests building a deleted path. The run was read-only;
  `git status` stayed clean.
- On that run the code/config group held a real runtime reference that the prose noise had
  hidden. Splitting the groups is what made it visible.

## Not covered

- **DD:** git's merge resolves both-deleted without a conflict in the test, so the DD branch of
  the script has never run.
- Rename detection: with `--no-renames`, a file the branch *moved* inside the repo counts as
  deleted. If git reports modify/delete on a moved file, deleting it drops the trunk's edit. Move
  the edit by hand.
- `dangling_refs.py` matches text only. It misses paths built from variables or globs, and it
  cannot tell a live reference from a "this moved to X" note.
- Neither script ports anything to the extracted repo. They list what needs porting.
