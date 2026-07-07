#!/usr/bin/env bash
# 机器 A：本地直连 Demo（无规划/无云端审计）
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export DEMO_PROFILE="${DEMO_PROFILE:-local_direct}"
export DEMO_PORT="${DEMO_PORT:-8765}"
export DEMO_HOST="${DEMO_HOST:-0.0.0.0}"
export CREWPI_HOME="${CREWPI_HOME:-$HOME/crewpi}"
export PYTHONPATH="${ROOT}${PYTHONPATH:+:$PYTHONPATH}"
if [[ -d "$CREWPI_HOME/crewpi" ]]; then
  export PYTHONPATH="${CREWPI_HOME}:$PYTHONPATH"
fi

echo "=== 端云审计 Demo · 本地直连模式 ==="
echo "DEMO_PROFILE=$DEMO_PROFILE"
echo "DEMO_BACKEND=${DEMO_BACKEND:-a2a}"
if [[ "${DEMO_BACKEND:-}" == "crewpi" ]]; then
  echo "DEMO_CREWPI_LOCAL_AGENT=${DEMO_CREWPI_LOCAL_AGENT:-ollama/qwen3.5:0.8b-64k-demo}"
  echo "DEMO_CREWPI_LOCAL_TIMEOUT_S=${DEMO_CREWPI_LOCAL_TIMEOUT_S:-15}"
fi
echo "URL: http://127.0.0.1:${DEMO_PORT}"

if ! ollama list 2>/dev/null | grep -q 'qwen3.5:0.8b-64k-demo'; then
  echo "警告: 未找到 ollama 模型 qwen3.5:0.8b-64k-demo，请先创建新模型"
fi

if ! curl -sf "http://127.0.0.1:18800/.well-known/agent-card.json" >/dev/null 2>&1; then
  echo "警告: A2A Gateway :18800 不可达，请确认 openclaw gateway 与 a2a-gateway 已启动"
fi

cd "$ROOT"
exec uv run python demo/server.py
