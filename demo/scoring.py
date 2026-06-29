"""Rule-based scoring for local-direct demo mode."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from schemas import AuditReport


def score_case(
    case_id: str,
    rubric: dict[str, Any],
    *,
    execution_result: str,
    pass_score: int = 7,
) -> AuditReport:
    if not rubric:
        return _score_generic(execution_result=execution_result, pass_score=pass_score)
    rubric_type = rubric.get("type", "")
    if rubric_type == "file_lines":
        return _score_file_lines(rubric, execution_result=execution_result, pass_score=pass_score)
    if rubric_type == "numeric_file":
        return _score_numeric_file(rubric, execution_result=execution_result, pass_score=pass_score)
    return AuditReport(
        pass_=False,
        score=0,
        summary=f"未知 rubric 类型: {rubric_type} (case={case_id})",
        issues=["未配置评分规则"],
        rework_hints="",
    )


def _score_file_lines(
    rubric: dict[str, Any],
    *,
    execution_result: str,
    pass_score: int,
) -> AuditReport:
    path = Path(rubric["path"])
    expected: list[str] = list(rubric.get("lines") or [])
    issues: list[str] = []
    score = 0

    if not path.is_file():
        issues.append(f"目标文件不存在: {path}")
    else:
        content = path.read_text(encoding="utf-8", errors="replace")
        score += 2
        for line in expected:
            if line in content:
                score += 2
            else:
                issues.append(f"文件缺少期望行: {line}")

    transcript = execution_result or ""
    if "read" not in transcript.lower() and "读取" not in transcript:
        issues.append("执行汇报中未见 read/读取 验证描述")
    else:
        score += 1

    for line in expected:
        if line in transcript:
            score += 1

    score = min(score, 10)
    passed = score >= pass_score
    summary = (
        f"规则评分 {score}/10：文件与内容检查。"
        if passed
        else f"规则评分 {score}/10：未达通过线 {pass_score}。"
    )
    return AuditReport(
        pass_=passed,
        score=score,
        summary=summary,
        issues=issues,
        rework_hints="按任务要求写入全部行并 read 验证后再汇报。",
    )


def _score_numeric_file(
    rubric: dict[str, Any],
    *,
    execution_result: str,
    pass_score: int,
) -> AuditReport:
    path = Path(rubric["path"])
    issues: list[str] = []
    score = 0

    if not path.is_file():
        issues.append(f"结果文件不存在: {path}")
    else:
        raw = path.read_text(encoding="utf-8", errors="replace").strip()
        score += 3
        if raw.isdigit():
            score += 4
        else:
            issues.append(f"结果文件内容不是纯数字: {raw[:80]!r}")

    if "read" not in (execution_result or "").lower():
        issues.append("未见 read 验证步骤")
    else:
        score += 2

    score = min(score, 10)
    passed = score >= pass_score
    return AuditReport(
        pass_=passed,
        score=score,
        summary=f"规则评分 {score}/10（目录统计任务）",
        issues=issues,
        rework_hints="确保写入纯数字并 read 验证。",
    )


def _score_generic(*, execution_result: str, pass_score: int) -> AuditReport:
    text = (execution_result or "").strip()
    if not text:
        return AuditReport(
            pass_=False,
            score=0,
            summary="规则评分 0/10：边侧未返回有效输出。",
            issues=["无执行输出"],
            rework_hints="",
        )

    lowered = text.lower()
    fail_markers = ("失败", "error", "exception", "timeout", "无法", "failed")
    if any(marker in lowered for marker in fail_markers):
        score = 3
        issues = ["执行汇报中包含失败或错误迹象"]
    else:
        score = 5
        issues = ["自由对话任务无结构化验收规则，仅按执行是否完成粗评"]

    passed = score >= pass_score
    summary = (
        f"规则评分 {score}/10：自由任务（无匹配 rubric）。"
        if not passed
        else f"规则评分 {score}/10：自由任务。"
    )
    return AuditReport(
        pass_=passed,
        score=score,
        summary=summary,
        issues=issues,
        rework_hints="如需精确评分，请在消息中包含可验收的文件路径与内容要求。",
    )
