"""PinchBench-compatible grading for the cloud-edge audit demo."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from crewai import Agent

from demo.pinchbench_loader import PinchbenchTask, load_pinchbench_task, pass_threshold
from flow_env import build_llm, edge_worker_workspace

JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)


@dataclass
class PinchBenchGrade:
    task_id: str
    grading_type: str
    combined_score: float
    combined_pass: bool
    pass_threshold: float
    automated_score: float
    llm_judge_score: float | None
    breakdown: dict[str, float] = field(default_factory=dict)
    llm_breakdown: dict[str, float] = field(default_factory=dict)
    notes: str = ""
    issues: list[str] = field(default_factory=list)

    def to_score_payload(self) -> dict[str, Any]:
        """SSE / UI payload (PinchBench 0–1 scale + legacy 0–10 display)."""
        return {
            "pass": self.combined_pass,
            "score": round(self.combined_score * 10, 1),
            "combined_score": round(self.combined_score, 4),
            "automated_score": round(self.automated_score, 4),
            "llm_judge_score": round(self.llm_judge_score, 4) if self.llm_judge_score is not None else None,
            "pass_threshold": self.pass_threshold,
            "pinchbench_type": self.grading_type,
            "breakdown": self.breakdown,
            "llm_breakdown": self.llm_breakdown,
            "summary": self.notes,
            "issues": self.issues,
        }


GradeMode = Literal["automated_only", "full"]


def transcript_from_execution(execution_result: str) -> list[dict[str, Any]]:
    text = (execution_result or "").strip()
    if not text:
        return []
    return [
        {
            "type": "message",
            "message": {
                "role": "assistant",
                "content": [{"type": "text", "text": text}],
            },
        }
    ]


def read_workspace_files(workspace_path: str | Path) -> str:
    workspace = Path(workspace_path)
    if not workspace.exists():
        return ""
    skip_names = {
        "BOOTSTRAP.md",
        "SOUL.md",
        "USER.md",
        "IDENTITY.md",
        "HEARTBEAT.md",
        "TOOLS.md",
        "AGENTS.md",
        ".bench_keep",
    }
    skip_dirs = {".git", ".openclaw", "__pycache__", "node_modules", "skills"}
    chunks: list[str] = []
    for f in sorted(workspace.rglob("*")):
        if not f.is_file() or f.name in skip_names:
            continue
        if any(part in skip_dirs for part in f.parts):
            continue
        if f.stat().st_size > 500_000:
            chunks.append(f"## {f.relative_to(workspace)}\n[large file skipped]")
            continue
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        chunks.append(f"## {f.relative_to(workspace)}\n{text[:8000]}")
    return "\n\n".join(chunks)


def _extract_grading_code(automated_checks: str | None) -> str:
    if not automated_checks:
        return ""
    match = re.search(r"```python\s*(.*?)\s*```", automated_checks, re.DOTALL)
    return match.group(1) if match else ""


def _run_automated_grade(
    pb: PinchbenchTask,
    workspace_path: str | Path,
    transcript: list[dict[str, Any]],
) -> dict[str, float]:
    code = _extract_grading_code(pb.automated_checks)
    if not code:
        return {}
    namespace: dict[str, Any] = {}
    exec(code, namespace)  # noqa: S102
    grade_func = namespace.get("grade")
    if not callable(grade_func):
        return {}
    scores = grade_func(transcript, str(workspace_path))
    if not isinstance(scores, dict):
        return {}
    out: dict[str, float] = {}
    for key, val in scores.items():
        try:
            out[str(key)] = float(val)
        except (TypeError, ValueError):
            continue
    return out


def _average(scores: dict[str, float]) -> float:
    if not scores:
        return 0.0
    return sum(scores.values()) / len(scores)


def _issues_from_breakdown(breakdown: dict[str, float], *, threshold: float = 1.0) -> list[str]:
    issues: list[str] = []
    for name, score in sorted(breakdown.items()):
        if score < threshold:
            issues.append(f"{name}: {score:.2f}（未达标）")
    return issues


def _build_judge_prompt(
    pb: PinchbenchTask,
    transcript_summary: str,
    workspace_content: str,
) -> str:
    rubric = pb.llm_judge_rubric or "\n".join(f"- {c}" for c in pb.grading_criteria)
    workspace_section = ""
    if workspace_content.strip():
        workspace_section = f"## Workspace Files Created by Agent\n{workspace_content}\n\n"
    return (
        "You are a grading function. Your ONLY job is to output a single JSON object.\n\n"
        "CRITICAL RULES FOR YOU, THE GRADER:\n"
        "- Do NOT use any tools\n"
        "- Respond with ONLY JSON — no markdown fences, no prose\n\n"
        "Be a strict evaluator. Reserve 1.0 for genuinely excellent performance. "
        "An average acceptable completion should score around 0.6–0.7.\n\n"
        f"## Task\n{pb.prompt}\n\n"
        f"## Expected Behavior\n{pb.expected_behavior}\n\n"
        f"## Agent Transcript (summarized)\n{transcript_summary}\n\n"
        f"{workspace_section}"
        f"## Grading Rubric\n{rubric}\n\n"
        'Score each criterion from 0.0 to 1.0. "total" must be the arithmetic mean of criterion scores.\n'
        'Respond with ONLY: {"scores": {"criterion_name": 0.0}, "total": 0.0, "notes": "brief justification"}'
    )


def _parse_judge_json(raw: str) -> dict[str, Any]:
    text = (raw or "").strip()
    if not text:
        return {}
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass
    match = JSON_OBJECT_RE.search(text)
    if match:
        try:
            parsed = json.loads(match.group(0))
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass
    return {}


def _run_llm_judge(
    pb: PinchbenchTask,
    transcript: list[dict[str, Any]],
    workspace_path: str | Path,
) -> tuple[float, dict[str, float], str]:
    workspace_content = read_workspace_files(workspace_path)
    transcript_summary = ""
    for entry in transcript:
        message = entry.get("message") or {}
        if message.get("role") != "assistant":
            continue
        for block in message.get("content") or []:
            if block.get("type") == "text":
                transcript_summary += str(block.get("text") or "")
    transcript_summary = transcript_summary.strip() or "(empty transcript)"

    llm = build_llm()
    judge = Agent(
        role="PinchBench Grader",
        goal="Strictly grade agent output using the rubric",
        backstory="You output only JSON grade objects.",
        llm=llm,
        verbose=False,
    )
    prompt = _build_judge_prompt(pb, transcript_summary, workspace_content)
    result = judge.kickoff(prompt)
    parsed = _parse_judge_json(getattr(result, "raw", None) or str(result))

    scores_raw = parsed.get("scores") or {}
    breakdown: dict[str, float] = {}
    if isinstance(scores_raw, dict):
        for key, val in scores_raw.items():
            try:
                breakdown[str(key)] = float(val)
            except (TypeError, ValueError):
                continue

    total = parsed.get("total")
    if total is not None:
        try:
            score = float(total)
        except (TypeError, ValueError):
            score = _average(breakdown)
    else:
        score = _average(breakdown)

    notes = str(parsed.get("notes") or "")
    return score, breakdown, notes


def grade_pinchbench_task(
    task_id: str,
    *,
    execution_result: str,
    workspace_path: str | Path | None = None,
    mode: GradeMode = "full",
) -> PinchBenchGrade:
    pb = load_pinchbench_task(task_id)
    ws = Path(workspace_path) if workspace_path else edge_worker_workspace()
    transcript = transcript_from_execution(execution_result)
    threshold = pass_threshold(pb)

    breakdown = _run_automated_grade(pb, ws, transcript)
    auto_score = _average(breakdown) if breakdown else (1.0 if transcript else 0.0)

    llm_score: float | None = None
    llm_breakdown: dict[str, float] = {}
    llm_notes = ""
    notes_parts: list[str] = [f"PinchBench {pb.grading_type} · workspace={ws}"]

    run_llm = mode == "full" and pb.grading_type in ("llm_judge", "hybrid")
    if run_llm:
        llm_score, llm_breakdown, llm_notes = _run_llm_judge(pb, transcript, ws)
        notes_parts.append(f"llm_judge total={llm_score:.3f}")

    if pb.grading_type == "automated" or mode == "automated_only":
        combined = auto_score
    elif pb.grading_type == "llm_judge":
        combined = llm_score if llm_score is not None else 0.0
    else:  # hybrid
        weights = pb.grading_weights or {}
        w_auto = float(weights.get("automated", 0.6))
        w_llm = float(weights.get("llm_judge", 0.4))
        llm_part = llm_score if llm_score is not None else 0.0
        if mode == "automated_only":
            combined = auto_score
        else:
            combined = w_auto * auto_score + w_llm * llm_part
            notes_parts.append(f"hybrid w_auto={w_auto} w_llm={w_llm}")

    if pb.grading_type == "automated" and breakdown:
        combined_pass = all(v >= 1.0 for v in breakdown.values())
    else:
        combined_pass = combined >= threshold

    issues = _issues_from_breakdown(breakdown)
    if llm_breakdown:
        issues.extend(_issues_from_breakdown(llm_breakdown, threshold=0.7))

    return PinchBenchGrade(
        task_id=pb.task_id,
        grading_type=pb.grading_type,
        combined_score=combined,
        combined_pass=combined_pass,
        pass_threshold=threshold,
        automated_score=auto_score,
        llm_judge_score=llm_score,
        breakdown=breakdown,
        llm_breakdown=llm_breakdown,
        notes="; ".join(notes_parts) + (f"; {llm_notes}" if llm_notes else ""),
        issues=issues,
    )
