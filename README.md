# 端云审计 Demo

两台机器 live 对比演示：**本地直连**（任务直发 edge-worker + PinchBench 规则分）vs **端云规划+审计**（DeepSeek 规划 → 边侧执行 → main-audit + PinchBench 评分）。

- 前端：自建对话页（`http://<host>:8765`），SSE 实时流水线
- 执行：OpenClaw A2A `:18800` → `edge-worker` + Ollama `qwen3.5:0.8b-64k-demo`
- 评分：对齐 [pinchbench/skill](https://github.com/pinchbench/skill)

## 快速启动

```bash
# 依赖：uv、Ollama、OpenClaw Gateway、a2a-gateway、PinchBench skill 克隆
git clone https://github.com/liaops2/cloud-edge-audit-demo.git
cd cloud-edge-audit-demo
export PINCHBENCH_SKILL_DIR=$HOME/skill   # pinchbench/skill 仓库路径

# 机器 A
bash scripts/start-demo-local.sh

# 机器 B（需 SiliconFlow）
bash scripts/start-demo-cloud.sh

# 演示前环境检查（两台通用）
bash scripts/check-demo-env.sh
bash scripts/check-demo-env.sh --profile cloud   # 仅机器 B
```

详细步骤见 [SOP.md](./SOP.md)。  
**现场讲解分镜稿**见 [DEMO_SCRIPT.md](./DEMO_SCRIPT.md)（PPT + 双机 Demo 口播脚本）。

## 目录

```
├── demo/              # FastAPI + SSE + 前端
├── scripts/           # 启动脚本
├── flow_env.py        # LLM / A2A 环境
├── prompts.py         # M1c 规划 + main-audit 提示词
├── openclaw_a2a_client.py
└── SOP.md             # 演示标准作业程序
```

## 相关仓库

- [crewai-study](https://github.com/liaops2/crewai-study) — 完整 CrewAI 端云 Flow CLI
- [openclaw-hermes-cloud-edge](https://github.com/liaops2/openclaw-hermes-cloud-edge) — M1c 生产级 Harness（本 Demo 为简化可视化版）
