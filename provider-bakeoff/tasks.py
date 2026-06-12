"""Task specs — prompts, dataset loaders, per-task scoring routing.

Two tasks ship:
    json-extraction  → structured data extraction from prose; gold JSON exists,
                       primary scoring is exact-field match, LLM judge is the
                       secondary check on mismatches.
    commit-message   → write a conventional commit message from a code diff;
                       no exact gold (multiple correct messages exist), LLM
                       judge is primary against a criteria rubric.

Adding a third task: register it in TASKS at the bottom + write a JSONL
data file under data/.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List


@dataclass
class Item:
    """One unit of work: an input prompt + the gold/criteria the scorer uses."""

    id: str
    user_prompt: str
    gold: Dict[str, Any]


@dataclass
class TaskSpec:
    """Everything the runner needs to handle one task type."""

    name: str
    description: str
    data_file: str               # under data/, relative to this dir
    system_prompt: str
    primary_scorer: str          # "exact_field_match" | "llm_judge_rubric"
    has_gold: bool


# ---------------------------------------------------------------------------
# Task: JSON extraction


JSON_EXTRACTION_SYSTEM = (
    "You extract structured data from short prose. "
    "Return STRICT JSON only — no prose, no markdown fences, no commentary. "
    "Match the gold's field names and value types as closely as you can. "
    "Use null for unknowable fields rather than guessing.\n\n"
    "Example input:\n"
    "  'Alice called Monday from 555-0100 about the bathroom renovation.'\n"
    "Example output:\n"
    '  {"name": "Alice", "date": "Monday", "phone": "555-0100", "topic": "bathroom renovation"}'
)


JSON_EXTRACTION_USER_TEMPLATE = "Extract structured JSON from:\n\n{prompt}"


def load_json_extraction(data_dir: Path) -> List[Item]:
    """Load `data/json_extraction.jsonl`."""
    path = data_dir / "json_extraction.jsonl"
    items: List[Item] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            blob = json.loads(line)
            items.append(
                Item(
                    id=blob["id"],
                    user_prompt=JSON_EXTRACTION_USER_TEMPLATE.format(prompt=blob["prompt"]),
                    gold={"expected_json": blob["gold"]},
                )
            )
    return items


# ---------------------------------------------------------------------------
# Task: commit-message generation


COMMIT_MESSAGE_SYSTEM = (
    "You write conventional-commit messages from a code diff.\n\n"
    "Output STRICT format: a single line of the form\n"
    "  <type>(<optional-scope>): <subject>\n"
    "where <type> is one of: feat, fix, refactor, perf, docs, test, chore, build, ci.\n"
    "Keep the subject under 72 characters. No body, no trailers, no markdown — "
    "just the one-line subject. Match the diff's actual change; don't invent context.\n\n"
    "Example diff:\n"
    "  diff --git a/src/util.py b/src/util.py\n"
    "  @@ -10,5 +10,7 @@ def slugify(text):\n"
    "  +    text = text.strip().lower()\n"
    "      return re.sub(r'[^a-z0-9]+', '-', text)\n"
    "Example output:\n"
    "  fix(util): lower-case and strip text before slugifying"
)


COMMIT_MESSAGE_USER_TEMPLATE = (
    "Write a conventional-commit message for this diff:\n\n```diff\n{diff}\n```"
)


def load_commit_message(data_dir: Path) -> List[Item]:
    """Load `data/commit_message.jsonl`."""
    path = data_dir / "commit_message.jsonl"
    items: List[Item] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            blob = json.loads(line)
            items.append(
                Item(
                    id=blob["id"],
                    user_prompt=COMMIT_MESSAGE_USER_TEMPLATE.format(diff=blob["diff"]),
                    gold={"criteria": blob["criteria"]},
                )
            )
    return items


# ---------------------------------------------------------------------------
# Registry


TASKS: Dict[str, TaskSpec] = {
    "json-extraction": TaskSpec(
        name="json-extraction",
        description="Extract structured JSON from short prose. Exact-field match is primary; LLM judge falls back on mismatches.",
        data_file="json_extraction.jsonl",
        system_prompt=JSON_EXTRACTION_SYSTEM,
        primary_scorer="exact_field_match",
        has_gold=True,
    ),
    "commit-message": TaskSpec(
        name="commit-message",
        description="Write a conventional-commit message from a diff. LLM judge is primary against a per-item criteria rubric.",
        data_file="commit_message.jsonl",
        system_prompt=COMMIT_MESSAGE_SYSTEM,
        primary_scorer="llm_judge_rubric",
        has_gold=False,
    ),
}


LOADERS: Dict[str, Callable[[Path], List[Item]]] = {
    "json-extraction": load_json_extraction,
    "commit-message": load_commit_message,
}


def load_task(task_name: str, data_dir: Path) -> List[Item]:
    """Load items for `task_name` from `data_dir`."""
    if task_name not in LOADERS:
        raise ValueError(f"unknown task: {task_name}. Known: {list(LOADERS)}")
    return LOADERS[task_name](data_dir)
