"""Track in-flight demo runs for cancellation."""

from __future__ import annotations

import subprocess
import threading
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from demo.flows import DemoRunner


class RunCancelled(Exception):
    """Raised when a demo run is cancelled by the user."""


@dataclass
class ActiveRun:
    runner: DemoRunner
    cancel: threading.Event = field(default_factory=threading.Event)
    a2a_proc: subprocess.Popen[str] | None = None
    lock: threading.Lock = field(default_factory=threading.Lock)


_registry: dict[str, ActiveRun] = {}
_registry_lock = threading.Lock()


def register(run_id: str, runner: DemoRunner) -> threading.Event:
    active = ActiveRun(runner=runner)
    with _registry_lock:
        _registry[run_id] = active
    return active.cancel


def get(run_id: str) -> ActiveRun | None:
    with _registry_lock:
        return _registry.get(run_id)


def unregister(run_id: str) -> None:
    with _registry_lock:
        _registry.pop(run_id, None)


def request_cancel(run_id: str) -> bool:
    active = get(run_id)
    if active is None:
        return False
    active.cancel.set()
    with active.lock:
        proc = active.a2a_proc
    if proc is not None and proc.poll() is None:
        proc.kill()
    return True


def set_a2a_proc(run_id: str, proc: subprocess.Popen[str] | None) -> None:
    active = get(run_id)
    if active is None:
        return
    with active.lock:
        active.a2a_proc = proc


def check_cancelled(run_id: str) -> None:
    active = get(run_id)
    if active is not None and active.cancel.is_set():
        raise RunCancelled("用户已终止任务")
