"""CrewPi backend adapter for the live demo."""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from demo.events import preview_text
from demo.pinchbench_scoring import PinchBenchGrade

CrewPiMode = Literal["pi_only", "crewpi"]


@dataclass(slots=True)
class CrewPiDemoResult:
    run_id: str
    task_id: str
    mode: CrewPiMode
    status: str
    workspace: Path
    trace_path: Path
    transcript_path: Path
    result_path: Path
    execution_result: str
    grade: PinchBenchGrade
    raw: dict[str, Any]


def crewpi_enabled() -> bool:
    return os.environ.get("DEMO_BACKEND", "").strip().lower() == "crewpi"


def run_crewpi_pinchbench_task(
    *,
    task_id: str,
    mode: CrewPiMode,
    run_id: str,
) -> CrewPiDemoResult:
    _prepare_crewpi_imports()
    _load_crewpi_env()

    from crewpi.pinchbench.runner import (  # type: ignore
        build_default_audit_judge_client,
        build_default_planner_client,
        build_runner,
        run_task,
    )
    import crewpi.pinchbench.runner as crewpi_runner  # type: ignore

    crewpi_home = crewpi_home_path()
    data_root = Path(os.environ.get("DEMO_CREWPI_DATA_DIR", ".demo-crewpi")).expanduser().resolve()
    pinchbench_dir = Path(
        os.environ.get("PINCHBENCH_SKILL_DIR")
        or os.environ.get("PINCHBENCH_DIR", "/home/admin/skill")
    ).expanduser()
    runner_kind = os.environ.get("DEMO_CREWPI_RUNNER", "source-built-pi").strip()
    source_built_pi = runner_kind in {"source-built-pi", "source_built_pi", "source"}
    dry_run = runner_kind in {"dry-run", "dry_run"}
    if source_built_pi:
        os.environ.setdefault("PI_OFFLINE", "1")
    pi_entrypoint = Path(
        os.environ.get(
            "CREWPI_PI_ENTRYPOINT",
            str(crewpi_home / "vendor/pi/packages/coding-agent/dist/cli.js"),
        )
    ).expanduser()
    agent_model = _agent_model_for_mode(mode)

    runner = build_runner(
        dry_run=dry_run,
        source_built_pi=source_built_pi,
        agent=agent_model,
        pi_entrypoint=pi_entrypoint,
    )
    if source_built_pi and hasattr(runner, "timeout_seconds"):
        runner.timeout_seconds = _pi_timeout_for_mode(mode)
    runner = _CanonicalToolRunner(runner)

    planner_client = build_default_planner_client() if mode == "crewpi" else None
    audit_judge_client = build_default_audit_judge_client() if mode == "crewpi" else None
    if mode == "crewpi":
        crewpi_runner.build_planning_goal = _build_demo_planning_goal

    result = run_task(
        pinchbench_dir=pinchbench_dir,
        task_id=task_id,
        workspace_root=data_root / "workspaces",
        trace_dir=data_root / "traces",
        results_dir=data_root / "results",
        runner=runner,
        run_id=run_id,
        planner_client=planner_client,
        auditor_client=audit_judge_client,
        judge_client=audit_judge_client if mode == "crewpi" else None,
        cloud_control_max_validation_retries=int(os.environ.get("DEMO_CREWPI_VALIDATION_RETRIES", "5")),
        judge_max_validation_retries=int(os.environ.get("DEMO_CREWPI_JUDGE_RETRIES", "5")),
        execution_mode=mode,
    )
    raw = result.to_dict()
    transcript_path = Path(raw["transcript_path"])
    execution_result = _read_transcript_text(transcript_path)
    grade = _grade_from_crewpi(raw)
    return CrewPiDemoResult(
        run_id=str(raw["run_id"]),
        task_id=str(raw["task_id"]),
        mode=mode,
        status=str(raw["status"]),
        workspace=Path(raw["workspace"]),
        trace_path=Path(raw["crewpi_trace_path"]),
        transcript_path=transcript_path,
        result_path=Path(raw["result_path"]),
        execution_result=execution_result,
        grade=grade,
        raw=raw,
    )


def crewpi_mode_for_demo(mode: str) -> CrewPiMode:
    return "pi_only" if mode == "local_direct" else "crewpi"


def _build_demo_planning_goal(task: Any) -> str:
    criteria = "\n".join(f"- {item}" for item in task.grading_criteria) or "- Complete the task and return evidence."
    return (
        f"PinchBench task id: {task.task_id}\n"
        f"Name: {task.name}\n"
        f"Category: {task.category}\n"
        f"Prompt:\n{task.prompt}\n\n"
        f"Expected behavior:\n{task.expected_behavior}\n\n"
        f"Acceptance criteria / grading criteria:\n{criteria}\n\n"
        "Produce exactly one edge-executable step for this demo. "
        "The step must use only the exec tool. "
        "Put artifact creation and evidence verification in the same shell command, for example with mkdir, printf, test, grep, cat, and echo. "
        "The execution process current working directory is already the task workspace. "
        "Use only relative paths such as src/main.py, README.md, and .gitignore. "
        "Do not create a separate read-only verification step. "
        "Do not use /workspace, /tmp, /home, or host-specific absolute paths unless the task explicitly requires an absolute path. "
        "The step output must include concise evidence that every grading criterion is satisfied."
    )


def _agent_model_for_mode(mode: CrewPiMode) -> str:
    if os.environ.get("DEMO_CREWPI_AGENT"):
        return os.environ["DEMO_CREWPI_AGENT"]
    if mode == "pi_only":
        return os.environ.get(
            "DEMO_CREWPI_LOCAL_AGENT",
            os.environ.get("DEMO_CREWPI_PI_MODEL", "ollama/qwen3.5:0.8b-64k-demo"),
        )
    return os.environ.get(
        "DEMO_CREWPI_CLOUD_AGENT",
        os.environ.get("DEMO_CREWPI_PI_MODEL", "ollama/qwen3.5:0.8b-64k-demo"),
    )


def _pi_timeout_for_mode(mode: CrewPiMode) -> int:
    if os.environ.get("DEMO_CREWPI_PI_TIMEOUT_S"):
        return int(os.environ["DEMO_CREWPI_PI_TIMEOUT_S"])
    if mode == "pi_only":
        return int(os.environ.get("DEMO_CREWPI_LOCAL_TIMEOUT_S", "15"))
    return int(os.environ.get("DEMO_CREWPI_CLOUD_TIMEOUT_S", "180"))


def crewpi_home_path() -> Path:
    return Path(os.environ.get("CREWPI_HOME", "/home/admin/crewpi")).expanduser().resolve()


def _prepare_crewpi_imports() -> None:
    crewpi_home = crewpi_home_path()
    if not (crewpi_home / "crewpi").is_dir():
        raise RuntimeError(f"CrewPi repo not found: {crewpi_home}")
    path = str(crewpi_home)
    if path not in sys.path:
        sys.path.insert(0, path)


def _load_crewpi_env() -> None:
    env_file = Path(os.environ.get("CREWPI_ENV_FILE", str(crewpi_home_path() / ".env"))).expanduser()
    if not env_file.is_file():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        item = line.strip()
        if not item or item.startswith("#") or "=" not in item:
            continue
        key, _, value = item.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))
    for key in ("ALL_PROXY", "all_proxy", "HTTP_PROXY", "http_proxy", "HTTPS_PROXY", "https_proxy"):
        if os.environ.get(key, "").startswith("socks://"):
            os.environ.pop(key, None)


def _read_transcript_text(path: Path) -> str:
    if not path.is_file():
        return ""
    chunks: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        message = event.get("message") or {}
        if message.get("role") != "assistant":
            continue
        for block in message.get("content") or []:
            if isinstance(block, dict) and block.get("type") == "text":
                text = str(block.get("text") or "").strip()
                if text:
                    chunks.append(text)
    return "\n\n".join(chunks)


def _grade_from_crewpi(raw: dict[str, Any]) -> PinchBenchGrade:
    grading = raw.get("grading") or {}
    score = _float(grading.get("score"), 0.0)
    max_score = _float(grading.get("max_score"), 1.0) or 1.0
    combined = max(0.0, min(1.0, score / max_score))
    breakdown = _flatten_breakdown(grading.get("breakdown") or {})
    threshold = 1.0 if raw.get("task_id") in {"task_files", "task_weather", "task_sanity"} else 0.75
    issues = [f"{key}: {value:.2f}" for key, value in breakdown.items() if value < threshold]
    status = str(grading.get("status") or raw.get("status") or "")
    notes = str(grading.get("notes") or f"CrewPi {status} · {raw.get('mode')}")
    return PinchBenchGrade(
        task_id=str(raw.get("task_id") or ""),
        grading_type=f"crewpi:{raw.get('mode') or 'unknown'}",
        combined_score=combined,
        combined_pass=combined >= threshold,
        pass_threshold=threshold,
        automated_score=combined,
        llm_judge_score=None,
        breakdown=breakdown,
        llm_breakdown={},
        notes=notes,
        issues=issues,
    )


def _flatten_breakdown(data: dict[str, Any], prefix: str = "") -> dict[str, float]:
    out: dict[str, float] = {}
    for key, value in data.items():
        name = f"{prefix}.{key}" if prefix else str(key)
        if isinstance(value, dict):
            if "score" in value:
                out[name] = _float(value.get("score"), 0.0)
            else:
                out.update(_flatten_breakdown(value, name))
            continue
        out[name] = _float(value, 0.0)
    return out


def _float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


class _CanonicalToolRunner:
    """Normalize Pi-native tool names back to CrewPi policy names for auditing."""

    _TO_CREWPI_TOOL = {
        "bash": "exec",
        "edit": "apply_patch",
    }

    def __init__(self, runner: Any) -> None:
        self._runner = runner

    def __getattr__(self, name: str) -> Any:
        return getattr(self._runner, name)

    async def run_step(self, *args: Any, **kwargs: Any) -> Any:
        result = await self._runner.run_step(*args, **kwargs)
        for call in getattr(result, "tool_calls", []) or []:
            for key in ("tool_name", "name"):
                tool = call.get(key)
                if tool in self._TO_CREWPI_TOOL:
                    call[key] = self._TO_CREWPI_TOOL[tool]
        return result


def crewpi_payload(result: CrewPiDemoResult) -> dict[str, Any]:
    return {
        "crewpi_status": result.status,
        "crewpi_mode": result.mode,
        "workspace": str(result.workspace),
        "trace_path": str(result.trace_path),
        "transcript_path": str(result.transcript_path),
        "result_path": str(result.result_path),
        "execution_preview": preview_text(result.execution_result, 1200),
    }
