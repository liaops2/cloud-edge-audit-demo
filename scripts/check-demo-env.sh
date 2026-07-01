#!/usr/bin/env bash
# 演示前环境检查（对齐 SOP §3 / §9）
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PROFILE="${DEMO_PROFILE:-all}"
STRICT=0
FAILURES=0
WARNINGS=0

usage() {
  cat <<'EOF'
用法: check-demo-env.sh [选项]

选项:
  --profile local|cloud|all   检查范围（默认 all，或读取 DEMO_PROFILE）
  --strict                    警告也视为失败（exit 1）
  -h, --help                  显示帮助

示例:
  bash scripts/check-demo-env.sh
  bash scripts/check-demo-env.sh --profile cloud
  DEMO_PROFILE=local_direct bash scripts/check-demo-env.sh
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --profile)
      PROFILE="${2:-}"
      shift 2
      ;;
    --strict)
      STRICT=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "未知参数: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

case "$PROFILE" in
  local|local_direct) PROFILE=local ;;
  cloud|cloud_edge) PROFILE=cloud ;;
  all) ;;
  *)
    echo "无效 profile: $PROFILE（可用 local / cloud / all）" >&2
    exit 2
    ;;
esac

pass() { echo "  ✓ $*"; }
warn() { echo "  ⚠ $*"; WARNINGS=$((WARNINGS + 1)); }
fail() { echo "  ✗ $*"; FAILURES=$((FAILURES + 1)); }

section() {
  echo
  echo "== $1 =="
}

need_cmd() {
  local name="$1"
  if command -v "$name" >/dev/null 2>&1; then
    pass "$name 已安装 ($("$name" --version 2>/dev/null | head -1 || echo ok))"
  else
    fail "缺少命令: $name"
  fi
}

check_common() {
  section "通用 · 仓库与工具"
  if [[ -f "$ROOT/pyproject.toml" && -f "$ROOT/demo/server.py" ]]; then
    pass "Demo 仓库结构完整 ($ROOT)"
  else
    fail "未在 Demo 仓库根目录找到 pyproject.toml / demo/server.py"
  fi

  need_cmd uv
  need_cmd curl
  need_cmd python3

  section "通用 · PinchBench skill"
  local skill_dir="${PINCHBENCH_SKILL_DIR:-$HOME/skill}"
  if [[ -d "$skill_dir/tasks" ]]; then
    pass "PINCHBENCH_SKILL_DIR=$skill_dir"
  else
    fail "PinchBench skill 目录不存在: $skill_dir（请 export PINCHBENCH_SKILL_DIR）"
  fi

  local task_file="$skill_dir/tasks/task_files.md"
  if [[ -f "$task_file" ]]; then
    pass "官方任务 task_files.md 可读"
  else
    fail "缺少 $task_file"
  fi

  section "通用 · Ollama 边侧模型"
  if command -v ollama >/dev/null 2>&1; then
    if ollama list 2>/dev/null | grep -q 'qwen3.5:0.8b'; then
      pass "Ollama 模型 qwen3.5:0.8b 已就绪"
    else
      warn "未找到 qwen3.5:0.8b，请执行: ollama pull qwen3.5:0.8b"
    fi
  else
    fail "未安装 ollama"
  fi

  section "通用 · OpenClaw A2A"
  if curl -sf "http://127.0.0.1:18800/.well-known/agent-card.json" >/dev/null 2>&1; then
    pass "A2A Gateway :18800 可达"
  else
    fail "A2A Gateway :18800 不可达（请启动 openclaw gateway + a2a-gateway）"
  fi

  if command -v openclaw >/dev/null 2>&1; then
    if openclaw gateway status 2>/dev/null | grep -qiE 'running|online|active|listening'; then
      pass "OpenClaw Gateway 运行中"
    else
      warn "openclaw gateway status 未显示运行中，请手动确认"
    fi
  else
    warn "未找到 openclaw CLI，跳过 gateway status 检查"
  fi

  local a2a_send="$HOME/.openclaw/extensions/a2a-gateway/skill/scripts/a2a-send.mjs"
  if [[ -f "$a2a_send" ]]; then
    pass "a2a-send 脚本存在"
  else
    warn "未找到 $a2a_send（执行阶段可能失败）"
  fi

  section "通用 · Demo 端口"
  local port="${DEMO_PORT:-8765}"
  if curl -sf "http://127.0.0.1:${port}/api/config" >/dev/null 2>&1; then
    local cfg
    cfg="$(curl -sf "http://127.0.0.1:${port}/api/config")"
    pass "Demo 服务已在 :${port} 运行 ($cfg)"
  else
    warn "Demo 服务未启动（演示前执行 start-demo-*.sh，当前端口 ${port}）"
  fi
}

check_cloud() {
  section "机器 B · 云端 LLM（SiliconFlow / DeepSeek）"
  local env_file="${OPENCLAW_ENV_FILE:-$HOME/openclaw-hermes-cloud-edge/.env}"
  if [[ -f "$env_file" ]]; then
    pass "环境文件存在: $env_file"
    # shellcheck disable=SC1090
    set -a && source "$env_file" && set +a
  else
    fail "未找到环境文件: $env_file（可设置 OPENCLAW_ENV_FILE）"
  fi

  if [[ -n "${SILICONFLOW_API_KEY:-}" ]]; then
    pass "SILICONFLOW_API_KEY 已设置"
  else
    fail "未设置 SILICONFLOW_API_KEY"
  fi

  if [[ -n "${SILICONFLOW_BASE_URL:-}" ]]; then
    pass "SILICONFLOW_BASE_URL=${SILICONFLOW_BASE_URL}"
  else
    warn "未设置 SILICONFLOW_BASE_URL（将依赖代码默认值）"
  fi

  if [[ -n "${DEEPSEEK_MODEL:-}" ]]; then
    pass "DEEPSEEK_MODEL=${DEEPSEEK_MODEL}"
  else
    warn "未设置 DEEPSEEK_MODEL（将使用 deepseek-ai/DeepSeek-V4-Flash）"
  fi
}

check_local() {
  section "机器 A · 本地直连模式"
  pass "本地模式无需 SiliconFlow；边侧 A2A + PinchBench automated 即可"
}

echo "端云审计 Demo · 环境检查"
echo "仓库: $ROOT"
echo "范围: $PROFILE"

check_common
if [[ "$PROFILE" == "local" || "$PROFILE" == "all" ]]; then
  check_local
fi
if [[ "$PROFILE" == "cloud" || "$PROFILE" == "all" ]]; then
  check_cloud
fi

echo
echo "----------------------------------------"
if [[ "$FAILURES" -gt 0 ]]; then
  echo "结果: 失败 — ${FAILURES} 项错误, ${WARNINGS} 项警告"
  exit 1
fi
if [[ "$WARNINGS" -gt 0 && "$STRICT" -eq 1 ]]; then
  echo "结果: 严格模式失败 — ${WARNINGS} 项警告"
  exit 1
fi
if [[ "$WARNINGS" -gt 0 ]]; then
  echo "结果: 通过（含 ${WARNINGS} 项警告，可用 --strict 视为失败）"
else
  echo "结果: 全部通过，可以开始演示"
fi
