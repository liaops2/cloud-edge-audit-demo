"""OpenClaw A2A client for local edge-worker execution."""

from __future__ import annotations

import json
import os
import re
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

from typing import Callable

from flow_env import A2A_SEND_SCRIPT, load_a2a_token
from schemas import A2AResult

TASK_LINE_RE = re.compile(
    r"^\[task\]\s+id=(?P<task_id>\S+)\s+contextId=(?P<context_id>\S+)",
    re.MULTILINE,
)


def default_peer_url() -> str:
    return os.environ.get("LOCAL_A2A_URL", "http://127.0.0.1:18800").rstrip("/")


def send_a2a_message(
    *,
    text: str,
    token: str | None = None,
    peer_url: str | None = None,
    agent_id: str | None = None,
    blocking: bool = True,
    timeout_s: int = 300,
    poll_ms: int = 1000,
    should_cancel: Callable[[], bool] | None = None,
    on_proc: Callable[[subprocess.Popen[str]], None] | None = None,
) -> A2AResult:
    """Send a message to local OpenClaw A2A gateway and return assistant text."""
    peer = (peer_url or default_peer_url()).rstrip("/")
    auth = token or load_a2a_token()
    script = _resolve_a2a_script()
    if script is not None:
        return _send_via_script(
            script=script,
            peer_url=peer,
            token=auth,
            text=text,
            agent_id=agent_id,
            blocking=blocking,
            timeout_s=timeout_s,
            poll_ms=poll_ms,
            should_cancel=should_cancel,
            on_proc=on_proc,
        )
    return _send_via_jsonrpc(
        peer_url=peer,
        token=auth,
        text=text,
        timeout_s=timeout_s,
    )


def _resolve_a2a_script() -> Path | None:
    if A2A_SEND_SCRIPT.is_file():
        return A2A_SEND_SCRIPT
    alt = Path("/home/admin/.openclaw/workspace/plugins/a2a-gateway/skill/scripts/a2a-send.mjs")
    if alt.is_file():
        return alt
    return None


def _send_via_script(
    *,
    script: Path,
    peer_url: str,
    token: str,
    text: str,
    agent_id: str | None,
    blocking: bool,
    timeout_s: int,
    poll_ms: int,
    should_cancel: Callable[[], bool] | None = None,
    on_proc: Callable[[subprocess.Popen[str]], None] | None = None,
) -> A2AResult:
    cmd = [
        "node",
        str(script),
        "--peer-url",
        peer_url,
        "--token",
        token,
        "--message",
        text,
        "--timeout-ms",
        str(timeout_s * 1000),
        "--poll-ms",
        str(poll_ms),
    ]
    if agent_id:
        cmd.extend(["--agent-id", agent_id])
    if blocking:
        cmd.append("--non-blocking")
        cmd.append("--wait")

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if on_proc is not None:
        on_proc(proc)

    deadline = time.time() + timeout_s + 30
    while proc.poll() is None:
        if should_cancel is not None and should_cancel():
            proc.kill()
            proc.wait(timeout=5)
            raise RuntimeError("A2A execution cancelled by user")
        if time.time() > deadline:
            proc.kill()
            proc.wait(timeout=5)
            raise RuntimeError(f"A2A send timed out after {timeout_s}s")
        time.sleep(0.3)

    stdout, stderr = proc.communicate()
    combined = (stdout or "") + ("\n" + stderr if stderr else "")
    if should_cancel is not None and should_cancel():
        raise RuntimeError("A2A execution cancelled by user")
    if proc.returncode != 0:
        raise RuntimeError(f"A2A send failed (exit {proc.returncode}): {combined.strip()}")

    match = TASK_LINE_RE.search(stdout or "")
    if match:
        task_id = match.group("task_id")
        context_id = match.group("context_id")
    else:
        task_id = ""
        context_id = ""

    lines = []
    for line in (stdout or "").splitlines():
        if line.startswith("[task]") or line.startswith("[stream]"):
            continue
        if line.strip():
            lines.append(line)
    text_out = "\n".join(lines).strip()
    if not text_out:
        raise RuntimeError(f"A2A send returned empty text: {combined.strip()}")
    return A2AResult(text=text_out, task_id=task_id, context_id=context_id, raw=stdout or "")


def _send_via_jsonrpc(
    *,
    peer_url: str,
    token: str,
    text: str,
    timeout_s: int,
) -> A2AResult:
    import uuid

    url = f"{peer_url}/a2a/jsonrpc"
    payload = {
        "jsonrpc": "2.0",
        "id": "1",
        "method": "message/send",
        "params": {
            "message": {
                "role": "user",
                "parts": [{"kind": "text", "text": text}],
                "messageId": str(uuid.uuid4()),
            }
        },
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        raise RuntimeError(f"A2A JSON-RPC failed: {exc}") from exc

    text_out = _extract_text_from_jsonrpc(body)
    if not text_out:
        raise RuntimeError(f"A2A JSON-RPC empty response: {json.dumps(body, ensure_ascii=False)[:500]}")
    return A2AResult(text=text_out, raw=json.dumps(body, ensure_ascii=False))


def _extract_text_from_jsonrpc(body: dict) -> str:
    result = body.get("result") if isinstance(body, dict) else None
    if not isinstance(result, dict):
        return ""
    if result.get("kind") == "message":
        return _parts_to_text(result.get("parts"))
    status = result.get("status") if isinstance(result.get("status"), dict) else {}
    return _parts_to_text(status.get("message", {}).get("parts"))


def _parts_to_text(parts: object) -> str:
    if not isinstance(parts, list):
        return ""
    chunks: list[str] = []
    for part in parts:
        if isinstance(part, dict) and part.get("kind") == "text":
            text = part.get("text")
            if isinstance(text, str) and text.strip():
                chunks.append(text.strip())
    return "\n".join(chunks)
