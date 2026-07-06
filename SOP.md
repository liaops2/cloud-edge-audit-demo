# 端云审计 Demo · 标准作业程序（SOP）

> 版本：v0.1 · 适用仓库：`cloud-edge-audit-demo`  
> 目标：两台机器投屏对比「本地直连」与「端云规划+审计」，使用 PinchBench 官方任务与评分。

---

## 1. 演示目标

| 机器 | 模式 | 规划 | 执行 | 审计/评分 |
|------|------|------|------|-----------|
| **机器 A** | 本地直连 | 跳过 | A2A → edge-worker (0.8b-64k) | PinchBench automated only |
| **机器 B** | 端云规划+审计 | DeepSeek | A2A → edge-worker (0.8b-64k) | main-audit + PinchBench |

**对比要点**：同一 PinchBench 官方 Prompt（推荐 `task_files`），边侧模型相同，差异在是否有结构化规划与云端审计。

---

## 2. 角色与分工

| 角色 | 职责 |
|------|------|
| 讲解人 | 切换浏览器标签、口述流水线阶段 |
| 机器 A 操作员 | 启动 `start-demo-local.sh`，浏览器打开 A 的 `:8765` |
| 机器 B 操作员 | 启动 `start-demo-cloud.sh`，配置 SiliconFlow，浏览器打开 B 的 `:8765` |

---

## 3. 环境前置条件（两台共性）

### 3.1 软件

- [uv](https://docs.astral.sh/uv/)（Python 包管理）
- [Ollama](https://ollama.com/)，已创建 **`qwen3.5:0.8b-64k-demo`**
- [OpenClaw](https://github.com/openclaw/openclaw) Gateway + **a2a-gateway** 插件（`:18800`）
- `edge-worker` agent，模型指向 `qwen3.5:0.8b-64k-demo`
- [PinchBench skill](https://github.com/pinchbench/skill) 克隆到本机，例如 `~/skill`

### 3.2 检查命令

推荐一键检查（覆盖本节与 §9 Checklist）：

```bash
bash scripts/check-demo-env.sh              # 全部项
bash scripts/check-demo-env.sh --profile local   # 机器 A
bash scripts/check-demo-env.sh --profile cloud   # 机器 B
bash scripts/check-demo-env.sh --strict     # 警告也视为失败
```

手动抽查：

```bash
ollama list | grep 'qwen3.5:0.8b-64k-demo'
curl -sf http://127.0.0.1:18800/.well-known/agent-card.json | head -c 80
openclaw gateway status
test -f ~/skill/tasks/task_files.md && echo "PinchBench OK"
```

### 3.3 edge-worker 模型（演示期间）

确认 `~/.openclaw/openclaw.json` 中 `edge-worker` 使用 `qwen3.5:0.8b-64k-demo`（或演示专用配置）。  
演示脚本**不会**修改 OpenClaw 源码，仅做启动前警告。

### 3.4 机器 B 额外依赖

- SiliconFlow API（或兼容 OpenAI 的 DeepSeek 端点）
- 环境文件，默认：`~/openclaw-hermes-cloud-edge/.env`

```bash
# .env 示例（勿提交密钥）
SILICONFLOW_API_KEY=sk-...
SILICONFLOW_BASE_URL=https://api.siliconflow.cn/v1
DEEPSEEK_MODEL=deepseek-ai/DeepSeek-V4-Flash
```

可通过 `OPENCLAW_ENV_FILE` 覆盖路径：

```bash
export OPENCLAW_ENV_FILE=/path/to/.env
```

---

## 4. 部署 Demo 服务

### 4.1 克隆仓库

```bash
git clone https://github.com/liaops2/cloud-edge-audit-demo.git
cd cloud-edge-audit-demo
```

### 4.2 环境变量

```bash
export PINCHBENCH_SKILL_DIR=$HOME/skill    # 必填：PinchBench 任务 markdown 目录
export DEMO_PORT=8765                      # 可选，默认 8765
export DEMO_HOST=0.0.0.0                   # 投屏时允许局域网访问
```

### 4.3 启动

**机器 A（本地直连）**

```bash
bash scripts/start-demo-local.sh
# 浏览器 http://<机器A-IP>:8765
```

**机器 B（端云规划+审计）**

```bash
bash scripts/start-demo-cloud.sh
# 浏览器 http://<机器B-IP>:8765
```

首次启动 `uv run` 会自动安装依赖，可能需要 1–2 分钟。

---

## 5. 演示操作流程（推荐 15–20 分钟）

### 5.1 开场（1 min）

1. 两台浏览器并排：左 A「本地直连」，右 B「端云规划+审计」
2. 说明：边侧同为 0.8b，任务与 PinchBench 评分规则一致

### 5.2 选择官方任务（1 min）

页面底部 **「PinchBench 官方 Prompt」** 面板：

1. 点击 **File Structure Creation**（`task_files`）
2. 确认展示官方英文 Prompt
3. 点击 **「填入输入框」**（两台各操作一次）

官方 Prompt：

```text
Create a project structure with: src/ directory, src/main.py with hello world, README.md with project title, and .gitignore ignoring __pycache__.
```

### 5.3 机器 A 运行（3–5 min）

1. 右上角确认 **本地直连**
2. 发送消息
3. 讲解流水线：**执行 → 评分**（规划/审计为灰色跳过）
4. 展开 **PinchBench 评分标准**，对照分项结果
5. 常见现象：无规划时 0.8b 易漏文件或只回复不建文件 → 低分

### 5.4 机器 B 运行（5–8 min）

1. 右上角切换 **端云规划+审计**
2. 同一官方 Prompt，发送
3. 讲解：**规划 → 执行 → 审计 → 评分**
4. 规划阶段展示结构化步骤（write/read/exec）
5. 审计阶段展示 main-audit 是否「只提问不执行」
6. PinchBench 分项与通过线（automated：各项须 1.0）

### 5.5 收尾对比（2 min）

| 维度 | 机器 A | 机器 B |
|------|--------|--------|
| 流水线 | 短 | 完整 |
| 规划可见性 | 无 | 有 |
| 审计 | 无 | main-audit JSON |
| 评分 | PinchBench automated | audit + PinchBench |

---

## 6. 页面操作说明

| 操作 | 说明 |
|------|------|
| 模式切换 | 右上角「本地直连 / 端云规划+审计」 |
| 官方 Prompt | 底部面板切换任务、填入输入框 |
| 发送 | Enter 发送，Shift+Enter 换行 |
| **终止** | 运行中发送钮变红 ■，点击终止当前任务 |
| 评分标准 | 可折叠查看 Grading Criteria / Expected Behavior |

---

## 7. 评分规则摘要

- **PinchBench automated**（如 `task_files`）：`grade()` 分项 0–1，**全部 1.0 才通过**
- **本地直连**：仅跑 automated 检查（不调用 LLM Judge）
- **端云模式**：DeepSeek **main-audit**（0–10）+ PinchBench 评分；两者均通过才算成功
- 自由对话（未匹配 PinchBench 任务）：通用粗评，**不推荐演示使用**

---

## 8. 故障排查

| 现象 | 处理 |
|------|------|
| 启动失败 500 | 重启服务；检查 `POST /api/run` 是否返回 `run_id` |
| 端云无法规划 | 检查 `SILICONFLOW_API_KEY`、`.env` 路径 |
| 执行一直转圈 | A2A/edge-worker 未响应；`curl :18800`；看 OpenClaw 日志 |
| 边侧只聊天不建文件 | 重试端云模式；确认 Worker Context Card 已注入（本仓库 `prompts.py`） |
| 提到 `pinchbench` 命令不存在 | 模型误把评测框架当 CLI；务必用底部**官方 Prompt**，勿手写 `pinchbench` 命令 |
| 评分为 chat / 低分 | 未匹配 PinchBench 任务；使用官方 Prompt 或含 `src/main.py` 等关键词 |
| PinchBench 任务找不到 | 设置 `PINCHBENCH_SKILL_DIR` 指向 skill 克隆目录 |
| 终止无效 | 规划/LLM 阶段需等当前请求结束；执行阶段可立即杀 A2A 子进程 |

### 8.1 日志与重启

```bash
# 前台调试
cd cloud-edge-audit-demo
export PYTHONPATH=$PWD PINCHBENCH_SKILL_DIR=$HOME/skill
uv run python demo/server.py

# 释放端口
lsof -ti :8765 | xargs -r kill
```

---

## 9. 演示前检查清单（Checklist）

- [ ] 运行 `bash scripts/check-demo-env.sh` 全部通过（或 `--profile local` / `cloud`）
- [ ] 两台均已 `git pull` 最新 Demo
- [ ] Ollama `qwen3.5:0.8b` 就绪
- [ ] OpenClaw Gateway + A2A `:18800` 正常
- [ ] `PINCHBENCH_SKILL_DIR` 已设置
- [ ] 机器 B `.env` 中 SiliconFlow 有效
- [ ] 浏览器可访问 `:8765`
- [ ] 官方 `task_files` Prompt 已预填
- [ ] 备用：第二条网线 / 热点，防止局域网隔离

---

## 10. 演示后

- 无需清理 OpenClaw 配置；可选删除 edge-worker workspace 下演示生成的 `src/`、`README.md` 等
- 问题反馈：提交 [GitHub Issues](https://github.com/liaops2/cloud-edge-audit-demo/issues)

---

## 附录 A：API 速查

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/config` | GET | 默认 profile |
| `/api/tasks` | GET | PinchBench 任务列表 + 官方 Prompt |
| `/api/pinchbench/{id}/rubric` | GET | 评分标准 |
| `/api/run` | POST | 启动任务 `{"message":"...","mode":"cloud_edge"}` |
| `/api/runs/{id}/events` | GET | SSE 事件流 |
| `/api/runs/{id}/cancel` | POST | 终止任务 |

## 附录 B：与生产 M1c 的关系

本 Demo 为 **可视化简化版**：

- 无 memory-server recall/persist
- 无 Hermes Harness 全链路
- 提示词与评分对齐 `openclaw-hermes-cloud-edge` / PinchBench

生产评测请参阅 `openclaw-hermes-cloud-edge` 与 `crewai-study` 仓库。
