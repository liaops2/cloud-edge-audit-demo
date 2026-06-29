"""Shared environment and LLM helpers for crewAI-study flows."""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path

from crewai import LLM

OPENCLAW_CONFIG = Path.home() / ".openclaw" / "openclaw.json"
_DEFAULT_ENV = Path.home() / "openclaw-hermes-cloud-edge" / ".env"
ENV_FILE = Path(os.environ.get("OPENCLAW_ENV_FILE", str(_DEFAULT_ENV)))
A2A_SEND_SCRIPT = Path.home() / ".openclaw/extensions/a2a-gateway/skill/scripts/a2a-send.mjs"


def load_env_file(path: Path = ENV_FILE) -> None:
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def load_a2a_token() -> str:
    token = os.environ.get("LOCAL_A2A_TOKEN") or os.environ.get("OPENCLAW_A2A_TOKEN")
    if token:
        return token
    if OPENCLAW_CONFIG.is_file():
        cfg = json.loads(OPENCLAW_CONFIG.read_text(encoding="utf-8"))
        token = (
            cfg.get("plugins", {})
            .get("entries", {})
            .get("a2a-gateway", {})
            .get("config", {})
            .get("security", {})
            .get("token", "")
        )
        if token:
            return token
    raise RuntimeError("Set LOCAL_A2A_TOKEN or configure a2a-gateway in openclaw.json")


def build_llm() -> LLM:
    load_env_file()
    api_key = os.environ.get("SILICONFLOW_API_KEY") or os.environ.get("OPENAI_API_KEY")
    base_url = os.environ.get("SILICONFLOW_BASE_URL") or os.environ.get("OPENAI_API_BASE")
    model = os.environ.get("DEEPSEEK_MODEL", "deepseek-ai/DeepSeek-V4-Flash")
    if not api_key or not base_url:
        raise RuntimeError("Missing LLM credentials in env or .env file")
    os.environ.setdefault("OPENAI_API_KEY", api_key)
    os.environ.setdefault("OPENAI_API_BASE", base_url)
    model_name = model if model.startswith("openai/") else f"openai/{model}"
    return LLM(model=model_name, base_url=base_url, api_key=api_key)


def new_run_id() -> str:
    return os.environ.get("FLOW_RUN_ID") or str(uuid.uuid4())


def edge_worker_workspace() -> Path:
    load_env_file()
    override = os.environ.get("EDGE_WORKER_WORKSPACE", "").strip()
    if override:
        return Path(override)
    if OPENCLAW_CONFIG.is_file():
        cfg = json.loads(OPENCLAW_CONFIG.read_text(encoding="utf-8"))
        for agent in cfg.get("agents", {}).get("list", []):
            if agent.get("id") == "edge-worker" and agent.get("workspace"):
                return Path(agent["workspace"])
    return Path.home() / ".openclaw" / "workspace"
