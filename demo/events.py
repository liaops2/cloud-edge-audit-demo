"""SSE stage events for the cloud-edge audit demo."""

from __future__ import annotations

import json
from typing import Any, Callable, Literal

from pydantic import BaseModel, Field

StageName = Literal["recall", "plan", "execute", "audit", "score", "done"]
StageStatus = Literal["pending", "running", "pass", "fail", "skipped"]

StageCallback = Callable[["StageEvent"], None]


class StageEvent(BaseModel):
    run_id: str
    stage: StageName
    status: StageStatus
    message: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)

    def to_sse(self) -> str:
        return f"data: {self.model_dump_json()}\n\n"


class StageEmitter:
    def __init__(self, run_id: str, callback: StageCallback | None = None) -> None:
        self.run_id = run_id
        self._callback = callback

    def emit(
        self,
        stage: StageName,
        status: StageStatus,
        *,
        message: str = "",
        payload: dict[str, Any] | None = None,
    ) -> StageEvent:
        event = StageEvent(
            run_id=self.run_id,
            stage=stage,
            status=status,
            message=message,
            payload=payload or {},
        )
        if self._callback is not None:
            self._callback(event)
        return event

    def skip(self, stage: StageName, message: str = "") -> StageEvent:
        return self.emit(stage, "skipped", message=message)

    def running(
        self,
        stage: StageName,
        message: str = "",
        payload: dict[str, Any] | None = None,
    ) -> StageEvent:
        return self.emit(stage, "running", message=message, payload=payload)

    def pass_(
        self,
        stage: StageName,
        message: str = "",
        payload: dict[str, Any] | None = None,
    ) -> StageEvent:
        return self.emit(stage, "pass", message=message, payload=payload)

    def fail(
        self,
        stage: StageName,
        message: str = "",
        payload: dict[str, Any] | None = None,
    ) -> StageEvent:
        return self.emit(stage, "fail", message=message, payload=payload)


def preview_text(text: str, limit: int = 1200) -> str:
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit] + "\n…(truncated)"
