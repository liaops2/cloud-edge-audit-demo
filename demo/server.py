"""FastAPI server for cloud-edge audit demo with SSE."""

from __future__ import annotations

import asyncio
import os
import sys
import threading
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

# Ensure crewAI-study root is importable
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from demo.events import StageEvent
from demo.flows import DemoMode, DemoRunner
from demo.pinchbench_rubric import rubric_payload
from demo.run_registry import RunCancelled, register, request_cancel, unregister
from demo.task_loader import get_task, load_tasks, task_from_message
from flow_env import load_env_file

load_env_file()

app = FastAPI(title="Cloud-Edge Audit Demo", version="1.0.0")

STATIC_DIR = Path(__file__).resolve().parent / "static"
_run_queues: dict[str, asyncio.Queue[StageEvent | None]] = {}
_run_lock = threading.Lock()


class RunRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=8000)
    task_id: str | None = None
    mode: DemoMode | None = None
    pass_score: int = Field(default=7, ge=0, le=10)
    max_reworks: int = Field(default=1, ge=0, le=3)


class ConfigResponse(BaseModel):
    profile: str
    profile_label: str
    default_mode: DemoMode
    pass_score: int


class RunResponse(BaseModel):
    run_id: str
    mode: DemoMode
    task_id: str | None = None
    pinchbench_task_id: str | None = None
    rubric: dict[str, Any] | None = None


def _default_mode() -> DemoMode:
    profile = os.environ.get("DEMO_PROFILE", "local_direct").strip()
    return "cloud_edge" if profile == "cloud_edge" else "local_direct"


def _profile_label(mode: DemoMode) -> str:
    if mode == "cloud_edge":
        return "机器 B · 端云审计（云端规划/审计门禁）"
    return "机器 A · 本地 Agent（直连执行）"


@app.get("/api/config")
def api_config() -> ConfigResponse:
    mode = _default_mode()
    return ConfigResponse(
        profile=os.environ.get("DEMO_PROFILE", mode),
        profile_label=_profile_label(mode),
        default_mode=mode,
        pass_score=int(os.environ.get("DEMO_PASS_SCORE", "7")),
    )


@app.get("/api/tasks")
def api_tasks() -> list[dict[str, Any]]:
    tasks = load_tasks()
    return [
        {
            "id": t["id"],
            "name": t.get("name", t["id"]),
            "description": t.get("description", ""),
            "request": t.get("request", ""),
            "pinchbench_task_id": t.get("pinchbench_task_id"),
        }
        for t in tasks
    ]


@app.get("/api/pinchbench/{task_id}/rubric")
def api_pinchbench_rubric(task_id: str, mode: DemoMode | None = None) -> dict[str, Any]:
    try:
        task = get_task(task_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    pb_id = str(task.get("pinchbench_task_id") or task_id)
    try:
        return rubric_payload(pb_id, mode=mode or _default_mode())
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/run")
async def api_run(body: RunRequest) -> RunResponse:
    try:
        task = task_from_message(body.message, task_id=body.task_id)
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    mode = body.mode or _default_mode()
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[StageEvent | None] = asyncio.Queue()
    runner = DemoRunner(
        mode=mode,
        task=task,
        on_stage=lambda ev: asyncio.run_coroutine_threadsafe(queue.put(ev), loop),
        pass_score=body.pass_score,
        max_reworks=body.max_reworks,
    )
    run_id = runner.state.run_id
    register(run_id, runner)
    _run_queues[run_id] = queue

    def _worker() -> None:
        try:
            runner.kickoff()
        except RunCancelled:
            pass
        except Exception as exc:
            err = StageEvent(
                run_id=run_id,
                stage="done",
                status="fail",
                message=f"运行异常: {exc}",
                payload={"error": str(exc)},
            )
            asyncio.run_coroutine_threadsafe(queue.put(err), loop)
        finally:
            unregister(run_id)
            asyncio.run_coroutine_threadsafe(queue.put(None), loop)

    threading.Thread(target=_worker, daemon=True).start()
    rubric: dict[str, Any] | None = None
    pb_id = str(task.get("pinchbench_task_id") or "")
    if pb_id:
        try:
            rubric = rubric_payload(pb_id, mode=mode)
        except FileNotFoundError:
            rubric = None
    return RunResponse(
        run_id=run_id,
        mode=mode,
        task_id=str(task.get("id")) if task.get("id") else None,
        pinchbench_task_id=pb_id or None,
        rubric=rubric,
    )


@app.post("/api/runs/{run_id}/cancel")
async def api_run_cancel(run_id: str) -> dict[str, bool]:
    if run_id not in _run_queues:
        raise HTTPException(status_code=404, detail="Unknown run_id")
    return {"cancelled": request_cancel(run_id)}


@app.get("/api/runs/{run_id}/events")
async def api_run_events(run_id: str) -> StreamingResponse:
    queue = _run_queues.get(run_id)
    if queue is None:
        raise HTTPException(status_code=404, detail="Unknown run_id")

    async def event_stream():
        while True:
            item = await queue.get()
            if item is None:
                yield "data: {\"stage\":\"done\",\"status\":\"pass\",\"message\":\"stream closed\"}\n\n"
                break
            yield item.to_sse()

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


if STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def main() -> None:
    import uvicorn

    host = os.environ.get("DEMO_HOST", "0.0.0.0")
    port = int(os.environ.get("DEMO_PORT", "8765"))
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
