"""Demo flows: local direct vs cloud-edge plan/execute/audit."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import Any, Literal

from crewai import Agent, Crew, Process, Task
from pydantic import ValidationError

from demo.crewpi_adapter import (
    crewpi_enabled,
    crewpi_mode_for_demo,
    crewpi_payload,
    run_crewpi_pinchbench_task,
)
from demo.events import StageCallback, StageEmitter, preview_text
from demo.pinchbench_rubric import rubric_payload
from demo.pinchbench_scoring import GradeMode, PinchBenchGrade, grade_pinchbench_task
from demo.run_registry import RunCancelled, check_cancelled, get, set_a2a_proc
from demo.scoring import score_case
from flow_env import build_llm, demo_run_workspace, new_run_id
from openclaw_a2a_client import send_a2a_message
from prompts import (
    build_audit_prompt,
    build_local_direct_baseline_prompt,
    build_planning_prompt_for_m1c,
    build_rework_execution_prompt,
    enrich_prompt_with_plan,
)
from schemas import AuditReport

JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)

DemoMode = Literal["local_direct", "cloud_edge"]


@dataclass
class DemoRunState:
    run_id: str = ""
    mode: DemoMode = "local_direct"
    task_id: str = ""
    pinchbench_task_id: str = ""
    user_request: str = ""
    plan_text: str = ""
    execution_result: str = ""
    audit_report: AuditReport | None = None
    grade: PinchBenchGrade | None = None
    pass_score: int = 7
    max_reworks: int = 1
    rework_count: int = 0
    final_output: str = ""


class DemoRunner:
    def __init__(
        self,
        *,
        mode: DemoMode,
        task: dict[str, Any],
        on_stage: StageCallback | None = None,
        pass_score: int = 7,
        max_reworks: int = 1,
    ) -> None:
        pb_id = str(task.get("pinchbench_task_id") or "")
        if not pb_id and task.get("source") == "pinchbench":
            pb_id = str(task.get("id") or "")
        self.state = DemoRunState(
            run_id=new_run_id(),
            mode=mode,
            task_id=str(task["id"]),
            pinchbench_task_id=pb_id,
            user_request=str(task["request"]).strip(),
            pass_score=pass_score,
            max_reworks=max_reworks,
        )
        self.emitter = StageEmitter(self.state.run_id, on_stage)
        self._workspace = demo_run_workspace(self.state.run_id)

    @staticmethod
    def _parse_audit_report(crew_result: object) -> AuditReport:
        if hasattr(crew_result, "pydantic") and crew_result.pydantic is not None:
            return AuditReport.model_validate(crew_result.pydantic)
        raw = getattr(crew_result, "raw", None) or str(crew_result)
        if isinstance(raw, dict):
            return AuditReport.model_validate(raw)
        text = str(raw)
        match = JSON_OBJECT_RE.search(text)
        if not match:
            raise ValueError(f"Auditor did not return JSON: {text[:500]}")
        data = json.loads(match.group(0))
        return AuditReport.model_validate(data)

    def _execution_prompt(self, *, rework: bool = False) -> str:
        if self.state.mode == "cloud_edge":
            if rework and self.state.audit_report is not None:
                return build_rework_execution_prompt(
                    self.state.user_request,
                    self.state.plan_text,
                    self.state.execution_result,
                    self.state.audit_report,
                    workspace_path=self._workspace,
                )
            return enrich_prompt_with_plan(
                self.state.user_request,
                self.state.plan_text,
                workspace_path=self._workspace,
            )
        return build_local_direct_baseline_prompt(
            self.state.user_request,
            workspace_path=self._workspace,
        )

    def kickoff(self) -> DemoRunState:
        try:
            if crewpi_enabled():
                return self._run_crewpi_backend()
            if self.state.mode == "cloud_edge":
                return self._run_cloud_edge()
            self.emitter.skip("recall", message="Demo 模式不启用记忆召回")
            self.emitter.skip("plan", message="本地 Agent：跳过云端规划")
            self.emitter.skip("audit", message="本地 Agent：跳过云端审计")
            return self._run_local_direct()
        except RunCancelled:
            self._emit_cancelled()
            return self.state

    def _guard_cancel(self) -> None:
        check_cancelled(self.state.run_id)

    def _run_crewpi_backend(self) -> DemoRunState:
        if not self.state.pinchbench_task_id:
            raise RuntimeError("CrewPi backend requires a PinchBench task id.")

        crewpi_mode = crewpi_mode_for_demo(self.state.mode)
        self.emitter.skip("recall", message="CrewPi memory 默认关闭")
        if crewpi_mode == "pi_only":
            self.emitter.skip("plan", message="CrewPi Pi-only：跳过云端规划")
            self.emitter.skip("audit", message="CrewPi Pi-only：跳过云端审计")
        else:
            self.emitter.running("plan", message="CrewPi 云端规划中…")
            self.emitter.running("audit", message="CrewPi 云端审计待执行…")

        self._guard_cancel()
        self.emitter.running(
            "execute",
            message=(
                "CrewPi Pi-only → 本地 Pi Agent…"
                if crewpi_mode == "pi_only"
                else "CrewPi 规划/执行/审计 → 本地 Pi Agent…"
            ),
            payload={"prompt_preview": preview_text(self.state.user_request, 400)},
        )
        result = run_crewpi_pinchbench_task(
            task_id=self.state.pinchbench_task_id,
            mode=crewpi_mode,
            run_id=self.state.run_id,
        )
        self._guard_cancel()
        self.state.execution_result = result.execution_result
        self.state.grade = result.grade
        if crewpi_mode == "crewpi":
            self.emitter.pass_("plan", message="CrewPi 规划完成")
            audit_status = "pass" if result.status == "done" else "fail"
            audit_payload = {
                "pass": result.status == "done",
                "score": 10 if result.status == "done" else 0,
                "summary": f"CrewPi status={result.status}",
                "issues": result.grade.issues,
            }
            if audit_status == "pass":
                self.emitter.pass_("audit", message="CrewPi 审计通过", payload=audit_payload)
            else:
                self.emitter.fail("audit", message=f"CrewPi 审计未通过: {result.status}", payload=audit_payload)

        execute_payload = crewpi_payload(result)
        execution_passed = result.status == "done" and result.grade.combined_pass
        if execution_passed:
            self.emitter.pass_(
                "execute",
                message="CrewPi 执行完成",
                payload=execute_payload,
            )
        else:
            self.emitter.fail(
                "execute",
                message=f"CrewPi 执行未达标: {result.status}",
                payload={
                    **execute_payload,
                    "issues": result.grade.issues,
                },
            )
        self._emit_score(result.grade)
        return self.state

    def _run_local_direct(self) -> DemoRunState:
        self._guard_cancel()
        try:
            self._run_execute(prompt=self._execution_prompt())
        except RunCancelled:
            raise
        except Exception:
            if not self.state.execution_result:
                self.state.execution_result = ""
        self._guard_cancel()
        grade = self._grade(mode="automated_only")
        self._emit_score(grade)
        return self.state

    def _run_cloud_edge(self) -> DemoRunState:
        self.emitter.skip("recall", message="Demo 简化：未接 memory-server")
        self._guard_cancel()
        self._run_plan()

        while True:
            self._guard_cancel()
            rework = self.state.rework_count > 0 and self.state.audit_report is not None
            try:
                self._run_execute(prompt=self._execution_prompt(rework=rework))
            except RunCancelled:
                raise
            except Exception:
                if not self.state.execution_result:
                    self.state.execution_result = ""
            self._guard_cancel()
            self._run_audit()
            grade = self._grade(mode="full")
            audit_ok = (
                self.state.audit_report is not None
                and self.state.audit_report.passed(self.state.pass_score)
            )
            if audit_ok and grade.combined_pass:
                self._emit_score(grade)
                return self.state
            if self.state.rework_count >= self.state.max_reworks:
                self._emit_score(grade)
                return self.state
            self.state.rework_count += 1
            hints = self.state.audit_report.rework_hints if self.state.audit_report else ""
            self.emitter.running(
                "execute",
                message=f"审计/评分未通过，rework {self.state.rework_count}/{self.state.max_reworks}",
                payload={
                    **grade.to_score_payload(),
                    "audit_pass": audit_ok,
                    "rework_hints": hints,
                },
            )

    def _grade(self, *, mode: GradeMode) -> PinchBenchGrade:
        if self.state.pinchbench_task_id:
            grade = grade_pinchbench_task(
                self.state.pinchbench_task_id,
                execution_result=self.state.execution_result,
                workspace_path=self._workspace,
                mode=mode,
            )
        else:
            grade = self._fallback_grade()
        self.state.grade = grade
        return grade

    def _fallback_grade(self) -> PinchBenchGrade:
        report = score_case(
            self.state.task_id,
            {},
            execution_result=self.state.execution_result,
            pass_score=self.state.pass_score,
        )
        combined = report.score / 10.0
        threshold = self.state.pass_score / 10.0
        return PinchBenchGrade(
            task_id=self.state.task_id,
            grading_type="generic",
            combined_score=combined,
            combined_pass=report.passed(self.state.pass_score),
            pass_threshold=threshold,
            automated_score=combined,
            llm_judge_score=None,
            breakdown={"rule_score": combined},
            notes=report.summary,
            issues=report.issues,
        )

    def _run_audit(self) -> AuditReport:
        self.emitter.running("audit", message="DeepSeek main-audit 审计执行结果…")
        llm = build_llm()
        auditor = Agent(
            role="审计员",
            goal="评审边侧是否实际完成任务，拒绝只提问不执行的汇报",
            backstory="你是严格的 main-audit 审计员，只评审不改文件。",
            llm=llm,
            verbose=False,
        )
        audit_prompt = build_audit_prompt(
            self.state.user_request,
            self.state.plan_text,
            self.state.execution_result,
            pass_score=self.state.pass_score,
        )
        audit_task = Task(
            description=audit_prompt,
            expected_output="JSON audit report",
            agent=auditor,
            output_pydantic=AuditReport,
        )
        crew = Crew(agents=[auditor], tasks=[audit_task], process=Process.sequential, verbose=False)
        try:
            report = self._parse_audit_report(crew.kickoff())
        except (ValueError, ValidationError, json.JSONDecodeError) as exc:
            self.emitter.fail("audit", message=f"审计解析失败: {exc}")
            report = AuditReport(
                pass_=False,
                score=0,
                summary=str(exc),
                issues=["审计 JSON 解析失败"],
                rework_hints="",
            )

        self.state.audit_report = report
        payload = {
            "pass": report.pass_,
            "score": report.score,
            "summary": report.summary,
            "issues": report.issues,
            "rework_hints": report.rework_hints,
        }
        if report.passed(self.state.pass_score):
            self.emitter.pass_("audit", message=f"审计 score={report.score}/10", payload=payload)
        else:
            self.emitter.fail("audit", message=f"审计 score={report.score}/10", payload=payload)
        return report

    def _run_plan(self) -> None:
        self._guard_cancel()
        self.emitter.running("plan", message="DeepSeek 生成结构化计划…")
        llm = build_llm()
        planner = Agent(
            role="规划师",
            goal="输出可供本地执行 Agent 执行的结构化计划",
            backstory="你熟悉 M1c 规划规范，只规划不执行。",
            llm=llm,
            verbose=False,
        )
        prompt = build_planning_prompt_for_m1c(
            self.state.user_request,
            workspace_path=self._workspace,
        )
        result = planner.kickoff(prompt)
        self._guard_cancel()
        self.state.plan_text = (result.raw or "").strip()
        self.emitter.pass_(
            "plan",
            message="规划完成",
            payload={"plan_preview": preview_text(self.state.plan_text, 800)},
        )

    def _run_execute(self, *, prompt: str) -> None:
        prompt = self._normalize_execution_prompt(prompt)
        self.emitter.running(
            "execute",
            message="OpenClaw A2A → 本地执行 Agent…",
            payload={"prompt_preview": preview_text(prompt, 400)},
        )
        timeout_s = int(os.environ.get("DEMO_EXECUTE_TIMEOUT_S", "300"))
        run_id = self.state.run_id

        def _should_cancel() -> bool:
            active = get(run_id)
            return active is not None and active.cancel.is_set()

        try:
            result = send_a2a_message(
                text=prompt,
                blocking=True,
                timeout_s=timeout_s,
                should_cancel=_should_cancel,
                on_proc=lambda proc: set_a2a_proc(run_id, proc),
            )
            self.state.execution_result = result.text.strip()
            self.emitter.pass_(
                "execute",
                message="本地 Agent 执行完成",
                payload={"execution_preview": preview_text(self.state.execution_result)},
            )
        except RunCancelled:
            raise
        except Exception as exc:
            if _should_cancel() or "cancelled by user" in str(exc).lower():
                raise RunCancelled("用户已终止任务") from exc
            self.state.execution_result = str(exc)
            self.emitter.fail(
                "execute",
                message=f"执行失败: {exc}",
                payload={"error": str(exc)},
            )
            raise
        finally:
            set_a2a_proc(run_id, None)

    def _normalize_execution_prompt(self, prompt: str) -> str:
        text = prompt or ""
        text = re.sub(
            r"(?<![\w./-])/workspace(?P<suffix>(?:/[^\s`\"')\]]+)?)",
            lambda m: str(self._workspace) + m.group("suffix"),
            text,
        )
        text = re.sub(
            r"(?<![\w./-])/root/workspace(?P<suffix>(?:/[^\s`\"')\]]+)?)",
            lambda m: str(self._workspace.parent.parent) + m.group("suffix"),
            text,
        )
        text = re.sub(
            r"~/.openclaw/workspace(?P<suffix>(?:/[^\s`\"')\]]+)?)",
            lambda m: str(self._workspace.parent.parent) + m.group("suffix"),
            text,
        )
        return text

    def _emit_cancelled(self) -> None:
        self.emitter.fail(
            "execute",
            message="已终止",
            payload={"cancelled": True},
        )
        self.emitter.fail(
            "done",
            message="用户已终止任务",
            payload={"cancelled": True, "mode": self.state.mode, "task_id": self.state.task_id},
        )

    def _emit_score(self, grade: PinchBenchGrade) -> None:
        payload = grade.to_score_payload()
        if self.state.pinchbench_task_id:
            try:
                payload["rubric"] = rubric_payload(
                    self.state.pinchbench_task_id,
                    mode=self.state.mode,
                )
            except FileNotFoundError:
                pass
        pct = grade.combined_score * 100
        passed = grade.combined_pass
        audit = self.state.audit_report
        audit_line = ""
        if audit is not None:
            audit_line = f"Audit: {audit.score}/10 pass={audit.passed(self.state.pass_score)}\n{audit.summary}\n"
        self.state.final_output = (
            f"{self.state.execution_result}\n\n---\n"
            f"{audit_line}"
            f"PinchBench {grade.combined_score:.3f}/1.0 "
            f"(threshold {grade.pass_threshold}) pass={passed}\n"
            f"{grade.notes}"
        )
        msg = f"{'通过' if passed else '未通过'} · {pct:.0f}% ({grade.combined_score:.3f}/1.0)"
        if passed:
            self.emitter.pass_("score", message=msg, payload=payload)
        else:
            self.emitter.fail("score", message=msg, payload=payload)
        self.emitter.pass_(
            "done",
            message="运行结束",
            payload={
                "mode": self.state.mode,
                "task_id": self.state.task_id,
                "pinchbench_task_id": self.state.pinchbench_task_id,
            },
        )
