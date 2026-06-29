"""Pydantic models for the cloud-edge CrewAI flow."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class AuditReport(BaseModel):
    """Structured audit result aligned with Hermes Harness main-audit JSON."""

    pass_: bool = Field(alias="pass")
    score: int = Field(ge=0, le=10)
    summary: str
    issues: list[str] = Field(default_factory=list)
    rework_hints: str = Field(
        default="",
        validation_alias="reworkInstruction",
        serialization_alias="reworkInstruction",
    )

    model_config = {"populate_by_name": True}

    def passed(self, pass_score: int = 7) -> bool:
        return self.pass_ or self.score >= pass_score


class MemoryHit(BaseModel):
    """Single row from audit-memory search."""

    id: str = ""
    question: str = ""
    answer: str = ""
    audit_score: float | None = None
    audit_pass: bool = False
    score: float = 0.0
    source: str = ""


class MemoryRecord(BaseModel):
    """Payload for audit-pass persistence."""

    question: str
    answer: str
    plan_text: str = ""
    audit_score: int
    audit_pass: bool = True
    attempts_used: int = 1
    run_id: str = ""
    source: str = "crewai-flow-d"
    max_answer_chars: int = 2000

    def to_upsert_payload(self) -> dict[str, Any]:
        answer = self.answer[: self.max_answer_chars]
        return {
            "question": self.question,
            "answer": answer,
            "audit_score": self.audit_score,
            "audit_pass": self.audit_pass,
            "attempts_used": self.attempts_used,
            "run_id": self.run_id,
            "source": self.source,
            "max_answer_chars": self.max_answer_chars,
        }


class CloudEdgeState(BaseModel):
    """Flow state for plan → execute → audit → persist."""

    user_request: str = ""
    memory_hits: list[MemoryHit] = Field(default_factory=list)
    plan_text: str = ""
    execution_result: str = ""
    audit_report: AuditReport | None = None
    rework_count: int = 0
    max_reworks: int = 2
    pass_score: int = 7
    min_audit_score_to_save: int = 6
    run_id: str = ""
    final_output: str = ""
    memory_persisted: bool = False


class A2AResult(BaseModel):
    """Result from OpenClaw A2A send."""

    text: str
    task_id: str = ""
    context_id: str = ""
    raw: str = ""
