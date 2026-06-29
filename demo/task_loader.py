"""Load demo tasks from tasks.yaml and PinchBench skill."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from demo.pinchbench_loader import load_pinchbench_task

TASKS_FILE = Path(__file__).resolve().parent / "tasks.yaml"


def load_tasks() -> list[dict[str, Any]]:
    data = yaml.safe_load(TASKS_FILE.read_text(encoding="utf-8"))
    items = list(data.get("tasks") or [])
    out: list[dict[str, Any]] = []
    for item in items:
        out.append(_resolve_task(item))
    return out


def _resolve_task(item: dict[str, Any]) -> dict[str, Any]:
    if item.get("source") == "pinchbench":
        pb_id = str(item.get("pinchbench_task_id") or item.get("id"))
        pb = load_pinchbench_task(pb_id)
        return {
            "id": item.get("id", pb.task_id),
            "name": item.get("name", pb.name),
            "description": item.get("description", pb.category),
            "request": (item.get("request") or pb.prompt).strip(),
            "source": "pinchbench",
            "pinchbench_task_id": pb.task_id,
            "grading_type": pb.grading_type,
            "expected_behavior": pb.expected_behavior,
            "grading_criteria": pb.grading_criteria,
        }
    return dict(item)


def get_task(task_id: str) -> dict[str, Any]:
    for task in load_tasks():
        if task.get("id") == task_id:
            return task
    raise KeyError(f"Unknown demo task: {task_id}")


def match_task_for_message(message: str) -> dict[str, Any] | None:
    text = message.strip()
    if not text:
        return None
    lowered = text.lower()
    path_hints = {
        "task_files": ("src/main.py", "readme.md", "gitignore"),
        "task_sanity": ("hello, i'm ready",),
        "task_weather": ("weather.py", "wttr.in"),
    }
    for task in load_tasks():
        pb_id = str(task.get("pinchbench_task_id") or task.get("id") or "")
        hints = path_hints.get(pb_id, ())
        if hints and any(h in lowered for h in hints):
            return task
    if "src/main.py" in lowered or ("readme.md" in lowered and "gitignore" in lowered):
        return get_task("task_files")
    if "hello, i'm ready" in lowered:
        return get_task("task_sanity")
    if "weather.py" in lowered or "wttr.in" in lowered:
        return get_task("task_weather")
    return None


def task_from_message(message: str, *, task_id: str | None = None) -> dict[str, Any]:
    text = message.strip()
    if not text:
        raise ValueError("消息不能为空")

    if task_id:
        base = get_task(task_id)
        return {**base, "request": text}

    matched = match_task_for_message(text)
    if matched:
        return {**matched, "request": text}

    return {
        "id": "chat",
        "name": "对话任务",
        "request": text,
        "source": "chat",
    }
