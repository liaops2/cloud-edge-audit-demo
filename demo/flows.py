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
    CrewPiFreeformResult,
    crewpi_enabled,
    crewpi_mode_for_demo,
    crewpi_payload,
    run_crewpi_freeform_task,
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
            self.emitter.skip("recall", message="Demo mode: memory recall disabled")
            self.emitter.skip("plan", message="Local Agent: skip cloud planning")
            self.emitter.skip("audit", message="Local Agent: skip cloud audit")
            return self._run_local_direct()
        except RunCancelled:
            self._emit_cancelled()
            return self.state

    def _guard_cancel(self) -> None:
        check_cancelled(self.state.run_id)

    def _run_crewpi_backend(self) -> DemoRunState:
        crewpi_mode = crewpi_mode_for_demo(self.state.mode)
        if not self.state.pinchbench_task_id:
            # Free-form user question: no PinchBench rubric, surface audit verdict.
            return self._run_crewpi_freeform(crewpi_mode)

        self.emitter.skip("recall", message="CrewPi memory off by default")
        # Light each pipeline box only when its stage actually starts. For crewpi
        # the trace poller streams plan->execute->audit transitions live (see
        # _crewpi_progress); pi_only has no cloud stages, so only execute runs.
        if crewpi_mode == "pi_only":
            self.emitter.skip("plan", message="CrewPi Pi-only: skip cloud planning")
            self.emitter.skip("audit", message="CrewPi Pi-only: skip cloud audit")
            self._guard_cancel()
            self.emitter.running(
                "execute",
                message="CrewPi Pi-only → local Pi agent…",
                payload={"prompt_preview": preview_text(self.state.user_request, 400)},
            )
            on_progress = None
        else:
            self._guard_cancel()
            self.emitter.running("plan", message="CrewPi cloud planning…")
            on_progress = self._crewpi_progress

        result = run_crewpi_pinchbench_task(
            task_id=self.state.pinchbench_task_id,
            mode=crewpi_mode,
            run_id=self.state.run_id,
            on_progress=on_progress,
        )
        self._guard_cancel()
        self.state.execution_result = result.execution_result
        self.state.grade = result.grade
        if crewpi_mode == "crewpi":
            self.emitter.pass_("plan", message="CrewPi planning done")
            audit_status = "pass" if result.status == "done" else "fail"
            # Show the cloud audit's OWN verdict (findings/confidence), judged from
            # reported results under the privacy boundary — not the PinchBench issues.
            conf = result.audit_confidence
            audit_payload = {
                "pass": result.status == "done",
                "score": 10 if result.status == "done" else 0,
                "confidence": conf,
                "summary": f"Cloud audit verdict: {result.audit_status or result.status}",
                "issues": result.audit_findings or [],
            }
            conf_note = f" (confidence {conf * 100:.0f}%)" if conf is not None else ""
            if audit_status == "pass":
                self.emitter.pass_("audit", message=f"CrewPi audit passed{conf_note}", payload=audit_payload)
            else:
                self.emitter.fail("audit", message=f"CrewPi audit failed{conf_note}", payload=audit_payload)

        execute_payload = crewpi_payload(result)
        execution_passed = result.status == "done" and result.grade.combined_pass
        if execution_passed:
            self.emitter.pass_(
                "execute",
                message="CrewPi execution done",
                payload=execute_payload,
            )
        else:
            reason = result.execution_error or f"execution below bar: {result.status}"
            self.emitter.fail(
                "execute",
                message=f"CrewPi execution failed — {reason}",
                payload={
                    **execute_payload,
                    "issues": result.grade.issues,
                    "reason": reason,
                },
            )
        self._emit_score(result.grade)
        return self.state

    def _crewpi_progress(self, stage: str, status: str) -> None:
        """Stream live stage transitions from the crewpi trace poller.

        Called from a background thread; the emitter marshals events back onto
        the event loop, so this is safe to call off-thread. The authoritative
        pass/fail resolution still happens after run_task returns.
        """
        messages = {
            ("plan", "pass"): "CrewPi planning done",
            ("execute", "running"): "CrewPi executing on local Pi agent…",
            ("audit", "running"): "CrewPi cloud audit reviewing reported results…",
        }
        message = messages.get((stage, status), "")
        if status == "pass":
            self.emitter.pass_(stage, message=message)
        else:
            self.emitter.running(stage, message=message)

    def _run_crewpi_freeform(self, crewpi_mode: str) -> DemoRunState:
        self.emitter.skip("recall", message="CrewPi memory off by default")
        # Same sequential-lighting rule as the pinchbench path: light each box
        # only when its stage actually starts (see _crewpi_progress).
        if crewpi_mode == "pi_only":
            self.emitter.skip("plan", message="CrewPi Pi-only: skip cloud planning")
            self.emitter.skip("audit", message="CrewPi Pi-only: skip cloud audit")
            self._guard_cancel()
            self.emitter.running(
                "execute",
                message="CrewPi Pi-only → local Pi agent…",
                payload={"prompt_preview": preview_text(self.state.user_request, 400)},
            )
            on_progress = None
        else:
            self._guard_cancel()
            self.emitter.running("plan", message="CrewPi cloud planning…")
            on_progress = self._crewpi_progress

        result = run_crewpi_freeform_task(
            goal=self.state.user_request,
            mode=crewpi_mode,
            run_id=self.state.run_id,
            on_progress=on_progress,
        )
        self._guard_cancel()
        self.state.execution_result = result.execution_result
        execution_ok = result.status == "done"

        if crewpi_mode == "crewpi":
            self.emitter.pass_("plan", message="CrewPi planning done")
            audit_payload = {
                "pass": bool(result.audit_pass),
                "confidence": result.audit_confidence,
                "summary": f"CrewPi audit status={result.audit_status}",
                "issues": result.audit_findings,
            }
            if result.audit_pass:
                self.emitter.pass_("audit", message="CrewPi audit passed", payload=audit_payload)
            else:
                self.emitter.fail("audit", message="CrewPi audit failed", payload=audit_payload)

        exec_payload = {"execution_preview": preview_text(result.execution_result, 1200)}
        if execution_ok:
            self.emitter.pass_("execute", message="CrewPi execution done", payload=exec_payload)
        else:
            reason = result.execution_error or f"execution incomplete: {result.status}"
            self.emitter.fail(
                "execute",
                message=f"CrewPi execution failed — {reason}",
                payload={**exec_payload, "reason": reason},
            )

        self._emit_audit_score(crewpi_mode, result)
        return self.state

    def _emit_audit_score(self, crewpi_mode: str, result: CrewPiFreeformResult) -> None:
        if crewpi_mode == "pi_only":
            # Local direct has no audit gate; a free-form question has no PinchBench rubric.
            self.emitter.skip("score", message="Local direct has no audit gate · free-form has no PinchBench score")
            self.emitter.pass_(
                "done",
                message="Run finished",
                payload={"mode": self.state.mode, "task_id": self.state.task_id},
            )
            return

        passed = bool(result.audit_pass)
        confidence = result.audit_confidence
        payload = {
            # Audit is a binary gate; headline reflects pass/fail, not a rubric %.
            "score": 10 if passed else 0,
            "pass": passed,
            "pinchbench_type": "Audit gate",
            "issues": result.audit_findings,
        }
        conf_note = ""
        if confidence is not None and abs(confidence - 0.5) > 1e-9:
            conf_note = f" (confidence {confidence * 100:.0f}%)"
        msg = f"{'Pass' if passed else 'Fail'} · Audit gate{conf_note}"
        if passed:
            self.emitter.pass_("score", message=msg, payload=payload)
        else:
            self.emitter.fail("score", message=msg, payload=payload)
        self.emitter.pass_(
            "done",
            message="Run finished",
            payload={"mode": self.state.mode, "task_id": self.state.task_id},
        )

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
        self.emitter.skip("recall", message="Demo simplified: no memory-server")
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
                message=f"Audit/score failed, rework {self.state.rework_count}/{self.state.max_reworks}",
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
        self.emitter.running("audit", message="DeepSeek main-audit reviewing execution…")
        llm = build_llm()
        auditor = Agent(
            role="Auditor",
            goal="Judge whether the edge actually completed the task; reject reports that only ask questions without executing",
            backstory="You are a strict main-audit auditor; you only review and never modify files.",
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
            self.emitter.fail("audit", message=f"Audit parse failed: {exc}")
            report = AuditReport(
                pass_=False,
                score=0,
                summary=str(exc),
                issues=["Audit JSON parse failed"],
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
            self.emitter.pass_("audit", message=f"Audit score={report.score}/10", payload=payload)
        else:
            self.emitter.fail("audit", message=f"Audit score={report.score}/10", payload=payload)
        return report

    def _run_plan(self) -> None:
        self._guard_cancel()
        self.emitter.running("plan", message="DeepSeek generating structured plan…")
        llm = build_llm()
        planner = Agent(
            role="Planner",
            goal="Produce a structured plan the local execution agent can run",
            backstory="You know the M1c planning spec; you only plan and never execute.",
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
            message="Planning done",
            payload={"plan_preview": preview_text(self.state.plan_text, 800)},
        )

    def _run_execute(self, *, prompt: str) -> None:
        prompt = self._normalize_execution_prompt(prompt)
        self.emitter.running(
            "execute",
            message="OpenClaw A2A → local execution agent…",
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
                message="Local Agent execution done",
                payload={"execution_preview": preview_text(self.state.execution_result)},
            )
        except RunCancelled:
            raise
        except Exception as exc:
            if _should_cancel() or "cancelled by user" in str(exc).lower():
                raise RunCancelled("User cancelled the run") from exc
            self.state.execution_result = str(exc)
            self.emitter.fail(
                "execute",
                message=f"Execution failed: {exc}",
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
            message="Cancelled",
            payload={"cancelled": True},
        )
        self.emitter.fail(
            "done",
            message="User cancelled the run",
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
        msg = f"{'Pass' if passed else 'Fail'} · {pct:.0f}% ({grade.combined_score:.3f}/1.0)"
        if passed:
            self.emitter.pass_("score", message=msg, payload=payload)
        else:
            self.emitter.fail("score", message=msg, payload=payload)
        self.emitter.pass_(
            "done",
            message="Run finished",
            payload={
                "mode": self.state.mode,
                "task_id": self.state.task_id,
                "pinchbench_task_id": self.state.pinchbench_task_id,
            },
        )
