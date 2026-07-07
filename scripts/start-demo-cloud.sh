#!/usr/bin/env bash
# 机器 B：端云规划+审计 Demo（DeepSeek 规划/审计 + 边侧 0.8b 执行）
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export DEMO_PROFILE="${DEMO_PROFILE:-cloud_edge}"
export DEMO_PORT="${DEMO_PORT:-8765}"
export DEMO_HOST="${DEMO_HOST:-0.0.0.0}"
export CREWPI_HOME="${CREWPI_HOME:-$HOME/crewpi}"
export PYTHONPATH="${ROOT}${PYTHONPATH:+:$PYTHONPATH}"
if [[ -d "$CREWPI_HOME/crewpi" ]]; then
  export PYTHONPATH="${CREWPI_HOME}:$PYTHONPATH"
fi

if [[ "${DEMO_BACKEND:-}" == "crewpi" ]]; then
  ENV_FILE="${CREWPI_ENV_FILE:-$CREWPI_HOME/.env}"
else
  ENV_FILE="${OPENCLAW_ENV_FILE:-$HOME/openclaw-hermes-cloud-edge/.env}"
fi
if [[ -f "$ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
fi

echo "=== 端云审计 Demo · 端云规划+审计模式 ==="
echo "DEMO_PROFILE=$DEMO_PROFILE"
echo "DEMO_BACKEND=${DEMO_BACKEND:-a2a}"
if [[ "${DEMO_BACKEND:-}" == "crewpi" ]]; then
  echo "DEMO_CREWPI_LOCAL_AGENT=${DEMO_CREWPI_LOCAL_AGENT:-ollama/qwen3.5:0.8b-64k-demo}"
  echo "DEMO_CREWPI_CLOUD_AGENT=${DEMO_CREWPI_CLOUD_AGENT:-ollama/qwen3.5:0.8b-64k-demo}"
  echo "DEMO_CREWPI_LOCAL_TIMEOUT_S=${DEMO_CREWPI_LOCAL_TIMEOUT_S:-15}"
  echo "DEMO_CREWPI_CLOUD_TIMEOUT_S=${DEMO_CREWPI_CLOUD_TIMEOUT_S:-180}"
fi
echo "URL: http://127.0.0.1:${DEMO_PORT}"

if [[ "${DEMO_BACKEND:-}" == "crewpi" ]]; then
  if [[ -z "${PLANNER_API_KEY:-${SILICONFLOW_API_KEY:-}}" ]]; then
    echo "错误: 未设置 PLANNER_API_KEY 或 SILICONFLOW_API_KEY（请在 $ENV_FILE 配置）"
    exit 1
  fi
else
  if [[ -z "${SILICONFLOW_API_KEY:-}" ]]; then
    echo "错误: 未设置 SILICONFLOW_API_KEY（请在 $ENV_FILE 配置）"
    exit 1
  fi
fi

if ! ollama list 2>/dev/null | grep -q 'qwen3.5:0.8b-64k-demo'; then
  echo "警告: 未找到 ollama 模型 qwen3.5:0.8b-64k-demo"
fi

if [[ "${DEMO_BACKEND:-}" != "crewpi" ]] && ! curl -sf "http://127.0.0.1:18800/.well-known/agent-card.json" >/dev/null 2>&1; then
  echo "警告: A2A Gateway :18800 不可达"
fi

cd "$ROOT"
exec uv run python demo/server.py
