"""PinchBench rubric metadata for demo UI."""

from __future__ import annotations

from typing import Any

from demo.pinchbench_loader import load_pinchbench_task, pass_threshold


def rubric_payload(task_id: str, *, mode: str = "local_direct") -> dict[str, Any]:
    pb = load_pinchbench_task(task_id)
    local = mode == "local_direct"
    active_rules: list[str] = []
    if pb.grading_criteria:
        active_rules.append("Grading Criteria（检查清单）")
    if pb.automated_checks:
        active_rules.append("Automated Checks（Python grade 函数）")
    if pb.llm_judge_rubric and not local:
        active_rules.append("LLM Judge Rubric（端云模式）")
    elif pb.llm_judge_rubric and local:
        active_rules.append("LLM Judge Rubric（本地直连跳过）")

    return {
        "task_id": pb.task_id,
        "name": pb.name,
        "grading_type": pb.grading_type,
        "pass_threshold": pass_threshold(pb),
        "pass_rule": _pass_rule_text(pb),
        "grading_criteria": pb.grading_criteria,
        "expected_behavior": pb.expected_behavior,
        "llm_judge_rubric": pb.llm_judge_rubric or "",
        "mode": mode,
        "active_rules": active_rules,
        "mode_note": (
            "本地直连：仅运行 PinchBench Automated Checks，不调用 LLM Judge。"
            if local
            else "端云模式：Automated Checks +（若任务为 hybrid/llm_judge）LLM Judge Rubric。"
        ),
    }


def _pass_rule_text(pb) -> str:
    if pb.grading_type == "automated":
        return "automated：所有分项得分必须 = 1.0 才算通过。"
    if pb.grading_type == "hybrid":
        return "hybrid：综合分 ≥ 0.75（默认 w_auto=0.6, w_llm=0.4）。"
    return "llm_judge：综合分 ≥ 0.7。"
