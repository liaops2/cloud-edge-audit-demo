"""Load PinchBench task definitions from pinchbench/skill markdown files."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass
class PinchbenchTask:
    task_id: str
    name: str
    category: str
    grading_type: str
    timeout_seconds: int
    workspace_files: list[Any]
    prompt: str
    expected_behavior: str
    grading_criteria: list[str]
    automated_checks: str | None
    llm_judge_rubric: str | None
    grading_weights: dict[str, float] | None
    frontmatter: dict[str, Any]
    file_path: Path


def skill_dir() -> Path:
    raw = os.environ.get("PINCHBENCH_SKILL_DIR", "/home/admin/skill").strip()
    candidate = Path(raw).expanduser()
    if (candidate / "tasks" / "manifest.yaml").exists():
        return candidate
    raise FileNotFoundError(
        f"PinchBench skill not found at {candidate}. "
        "Clone pinchbench/skill or set PINCHBENCH_SKILL_DIR."
    )


def load_pinchbench_task(task_id: str) -> PinchbenchTask:
    path = skill_dir() / "tasks" / f"{task_id}.md"
    if not path.exists():
        raise FileNotFoundError(f"PinchBench task not found: {path}")
    content = path.read_text(encoding="utf-8")
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", content, re.DOTALL)
    if not match:
        raise ValueError(f"No YAML frontmatter in {path}")
    meta = yaml.safe_load(match.group(1)) or {}
    sections = _parse_sections(match.group(2))
    return PinchbenchTask(
        task_id=meta.get("id", task_id),
        name=meta.get("name", task_id),
        category=meta.get("category", ""),
        grading_type=meta.get("grading_type", "automated"),
        timeout_seconds=int(meta.get("timeout_seconds", 120)),
        workspace_files=meta.get("workspace_files") or [],
        prompt=sections.get("Prompt", "").strip(),
        expected_behavior=sections.get("Expected Behavior", "").strip(),
        grading_criteria=_extract_grading_criteria(sections.get("Grading Criteria", "")),
        automated_checks=sections.get("Automated Checks"),
        llm_judge_rubric=sections.get("LLM Judge Rubric"),
        grading_weights=meta.get("grading_weights"),
        frontmatter=meta,
        file_path=path,
    )


def pass_threshold(pb: PinchbenchTask) -> float:
    if pb.grading_type == "automated":
        return 1.0
    if pb.grading_type == "hybrid" and pb.automated_checks:
        return 0.75
    return 0.7


def _extract_grading_criteria(criteria_text: str) -> list[str]:
    items: list[str] = []
    for line in (criteria_text or "").splitlines():
        line = line.strip()
        if not line:
            continue
        line = re.sub(r"^[-*]\s*\[[ xX]?\]\s*", "", line)
        line = re.sub(r"^[-*]\s+", "", line)
        if line:
            items.append(line)
    return items


def _parse_sections(body: str) -> dict[str, str]:
    sections: dict[str, str] = {}
    current: str | None = None
    buf: list[str] = []
    for line in body.split("\n"):
        header = re.match(r"^##\s+(.+)$", line)
        if header:
            if current:
                sections[current] = "\n".join(buf).strip()
            current = header.group(1)
            buf = []
        elif current:
            buf.append(line)
    if current:
        sections[current] = "\n".join(buf).strip()
    return sections
