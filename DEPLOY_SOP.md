# 端云审计 Demo · 异机部署 SOP（crewpi 后端版）

> 版本：v1.0 · 日期：2026-07-10
> 目标：在一台**全新电脑**上把「本地直连 vs 端云规划+审计」这套 Demo 跑起来。
> 后端：`crewpi` 执行内核（非旧版 OpenClaw A2A）。旧版流程见同目录 `SOP.md`。

---

## 0. 一句话架构 & 两个仓库的关系

这套系统由**两个 Git 仓库**组成，它们是「前端壳 + 执行内核」的关系：

| 仓库 | 角色 | 远端 / 分支 | 作用 |
|------|------|------------|------|
| **`cloud-edge-audit-demo`** | 前端 / 演示壳 | `git@github.com:liaops2/cloud-edge-audit-demo.git` · `main` | FastAPI + SSE 网页 UI、流水线三段动画、评分卡片、启动脚本 |
| **`crewpi`** | 执行内核 / 后端 | `git@github.com:liaops2/Crewpi.git` · `codex/crewpi-backend-integration` | 云端规划器、端侧执行器、云端审计/评审、PinchBench 跑分、内置 Pi CLI |

**它们如何连接（关键）**：

```
┌──────────────────────────────┐        import crewpi.*          ┌───────────────────────────────┐
│  cloud-edge-audit-demo        │  ───── (PYTHONPATH) ─────────▶  │  crewpi (作为 Python 包被导入)  │
│  demo/server.py  (FastAPI)    │                                 │  crewpi/pinchbench/runner.py    │
│  demo/flows.py   (SSE 编排)   │                                 │  crewpi/agent_collab/*          │
│  demo/crewpi_adapter.py  ─────┼── CREWPI_HOME 环境变量定位 ────▶│  $CREWPI_HOME 目录              │
└──────────────────────────────┘                                 │   └ vendor/pi/.../dist/cli.js   │◀─ 端侧 Pi 执行
                                                                  │   └ .env  (云端 API 密钥)       │◀─ 云端规划/审计
                                                                  └───────────────────────────────┘
```

- Demo **不 vendor** crewpi 的代码，而是运行时通过 `CREWPI_HOME`（默认 `/home/admin/crewpi`，可用环境变量覆盖）+ `PYTHONPATH` 把 crewpi 当 Python 包 `import`。
  - 代码入口：`demo/crewpi_adapter.py` → `crewpi_home_path()`（读 `CREWPI_HOME`），并 `import crewpi.pinchbench.runner` / `crewpi.agent_collab.*`。
- **端侧执行**走 crewpi 里内置的 Pi CLI：`$CREWPI_HOME/vendor/pi/packages/coding-agent/dist/cli.js`（node 程序，调用本机 Ollama）。
- **云端密钥**（规划器 / 审计器）由启动脚本从 `$CREWPI_HOME/.env` 读取。

> 结论：部署时**两个仓库都要克隆**，而且 crewpi 必须能被 `CREWPI_HOME` 找到（推荐同放 `$HOME` 下）。

一次完整请求的数据流：
**网页 chip → demo(SSE) → 云端规划器(GLM-5.2/SiliconFlow) → 端侧执行器(Ollama qwen 0.8B, 经 Pi CLI) → 云端审计+评审(TaoToken deepseek-v4-pro) → PinchBench 打分 → 回传网页卡片**。
`本地直连` 模式跳过云端，只有端侧模型独跑。

---

## 1. 前置软件清单

| 依赖 | 用途 | 备注 |
|------|------|------|
| **Python 3.11+** | crewpi 内核 + demo 服务 | 建议 3.11/3.12 |
| **[uv](https://docs.astral.sh/uv/)** | demo 侧包管理（`uv run`） | crewpi 侧可用 pip/venv |
| **Node.js 20+**（本机验证 v24）+ npm | 构建并运行内置 Pi CLI | 无 node 端侧无法执行 |
| **[Ollama](https://ollama.com/)** | 端侧模型推理 | 需能拉 `qwen3.5:0.8b` 基座 |
| **git**（含子模块支持） | 拉取 crewpi 的 `vendor/pi` 子模块 | 子模块约 475MB |
| 网络 | 云端 API（SiliconFlow / TaoToken 国内直连） | 见 §7 代理注意 |

---

## 2. 克隆两个仓库

```bash
cd "$HOME"
git clone -b main            git@github.com:liaops2/cloud-edge-audit-demo.git
git clone -b codex/crewpi-backend-integration git@github.com:liaops2/Crewpi.git crewpi
```

> 目录名建议就叫 `crewpi`（小写），与默认 `CREWPI_HOME=$HOME/crewpi` 一致；否则务必 `export CREWPI_HOME=<你的路径>`。

---

## 3. 构建 crewpi 内核

### 3.1 拉子模块 + 构建 Pi CLI（端侧执行器）

`vendor/pi`、`vendor/mem0` 是 **git 子模块**，克隆主仓不会自动带内容；`dist/cli.js` 是**构建产物**，需现场构建。

```bash
cd "$HOME/crewpi"
git submodule update --init --recursive        # 拉取 vendor/pi, vendor/mem0
scripts/build_pi_source.sh                      # 装 npm 依赖 + 构建，产出 dist/cli.js
```

构建成功的标志（**必须存在**，否则端侧执行会报错）：

```bash
test -f vendor/pi/packages/coding-agent/dist/cli.js && echo "Pi CLI OK"
```

> `build_pi_source.sh` 默认 `offline` 模式，逐包构建 tui/ai/agent/coding-agent；需要 node+npm。若报缺子模块，按提示重跑 `git submodule update --init --recursive vendor/pi`。

### 3.2 Python 依赖

```bash
cd "$HOME/crewpi"
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
# 或（若统一用 uv）：uv pip install -r requirements.txt
```

### 3.3 云端密钥 `.env`（含密钥，绝不入 git）

```bash
cd "$HOME/crewpi"
cp .env.example .env
```

编辑 `.env`，**重点修改以下几项**（`.env.example` 里的 `DeepSeek-V4-Flash` 已失效/挂起，必须换成 GLM-5.2）：

```ini
# —— 云端规划器：SiliconFlow ——
PLANNER_BASE_URL=https://api.siliconflow.cn/v1
PLANNER_API_KEY=sk-<你的 SiliconFlow key>
PLANNER_MODEL=zai-org/GLM-5.2          # ← 关键：不要用 .env.example 里的 DeepSeek-V4-Flash（会挂起）

# 兼容老代码路径的默认结构化 LLM（同一把 SiliconFlow key 即可）
SILICONFLOW_BASE_URL=https://api.siliconflow.cn/v1
SILICONFLOW_API_KEY=sk-<你的 SiliconFlow key>

# —— 云端审计 + 评审：TaoToken ——
AUDIT_JUDGE_BASE_URL=https://taotoken.net/api/v1
AUDIT_JUDGE_API_KEY=sk-<你的 TaoToken key>
AUDIT_JUDGE_MODEL=deepseek-v4-pro
```

> - **`.env` 不在 git 里**，密钥必须在新机手动填。GLM-5.2 这条改动只存在于本机 `.env`，异机复现时务必照抄。
> - GLM-5.2 是推理模型，crewpi 已在代码里对规划器注入 `enable_thinking:false`（`runner.build_default_planner_client`），无需手动配。

---

## 4. Ollama 端侧模型

演示用的轻量模型 `qwen3.5:0.8b-64k-demo`（1GB、常驻 GPU、快），由 `cloud-edge-audit-demo/ollama/` 下的 Modelfile 复刻：

```bash
ollama pull qwen3.5:0.8b                                    # 拉基座
cd "$HOME/cloud-edge-audit-demo"
ollama create qwen3.5:0.8b-64k-demo -f ollama/Modelfile-qwen3.5-0.8b-64k-demo
ollama list | grep 'qwen3.5:0.8b-64k-demo'                 # 验证
```

> Modelfile 内容就是 `FROM qwen3.5:0.8b` + `PARAMETER num_ctx 65536`。跑实验（非演示）才用 23GB 的 `qwen3.6:35b-32k`，演示不需要。

---

## 5. PinchBench 任务集（评分依据）

评分用的 149 个任务放在一个 skill 目录（本机 `/home/admin/skill`）。在新机把它克隆/拷到任意路径，并告诉 demo：

```bash
# 放到 $HOME/skill，或任意路径后 export PINCHBENCH_SKILL_DIR
export PINCHBENCH_SKILL_DIR="$HOME/skill"
test -f "$PINCHBENCH_SKILL_DIR/tasks/task_files.md" && echo "PinchBench OK"
```

> demo 读取顺序：`PINCHBENCH_SKILL_DIR` → `PINCHBENCH_DIR` → 兜底 `/home/admin/skill`。新机若不在默认路径，**必须** export。

---

## 6. Demo 前端依赖

```bash
cd "$HOME/cloud-edge-audit-demo"
uv sync            # 按 uv.lock 装 demo 依赖（FastAPI 等）
```

---

## 7. 代理注意（容易踩坑）

- 云端 SiliconFlow / TaoToken 是**国内直连**，若 shell 里带了 `HTTPS_PROXY` 等代理会导致连不上或超时。启动前清掉：

```bash
unset ALL_PROXY all_proxy HTTP_PROXY http_proxy HTTPS_PROXY https_proxy
```

- Ollama、Pi CLI 都是本机 `127.0.0.1`，无需代理。

---

## 8. 启动

设置 demo 侧环境变量并启动云端模式（启动脚本会自动 `source $CREWPI_HOME/.env`、把 `CREWPI_HOME` 加进 `PYTHONPATH`）：

```bash
cd "$HOME/cloud-edge-audit-demo"
unset ALL_PROXY all_proxy HTTP_PROXY http_proxy HTTPS_PROXY https_proxy

export CREWPI_HOME="$HOME/crewpi"
export DEMO_BACKEND=crewpi
export DEMO_CREWPI_SEGMENTED=1              # 分段执行（段内热会话 + 段末全量审计）
export DEMO_PROFILE=cloud_edge
export PINCHBENCH_SKILL_DIR="$HOME/skill"
export DEMO_PORT=8765
export DEMO_HOST=0.0.0.0
# 端侧模型 / 超时（一般用默认即可）
export DEMO_CREWPI_LOCAL_AGENT=ollama/qwen3.5:0.8b-64k-demo
export DEMO_CREWPI_CLOUD_AGENT=ollama/qwen3.5:0.8b-64k-demo
export DEMO_CREWPI_LOCAL_TIMEOUT_S=15       # 本地直连端侧超时
export DEMO_CREWPI_CLOUD_TIMEOUT_S=180      # 端云模式端侧超时

bash scripts/start-demo-cloud.sh
```

浏览器打开 `http://<本机IP>:8765`。

> 只演示「本地直连」用 `scripts/start-demo-local.sh`（同样需 `DEMO_BACKEND=crewpi`）。两种模式也可在同一页面切换。

---

## 9. 部署后自检 Checklist

一键检查：

```bash
cd "$HOME/cloud-edge-audit-demo"
bash scripts/check-demo-env.sh --profile cloud
```

手动抽查：

```bash
# 1. 两仓与内核
test -f "$HOME/crewpi/vendor/pi/packages/coding-agent/dist/cli.js" && echo "✓ Pi CLI"
python -c "import sys; sys.path.insert(0,'$HOME/crewpi'); import crewpi.pinchbench.runner; print('✓ crewpi 可导入')"
# 2. 模型
ollama list | grep -q 'qwen3.5:0.8b-64k-demo' && echo "✓ 端侧模型"
# 3. 任务集
test -f "${PINCHBENCH_SKILL_DIR:-$HOME/skill}/tasks/task_files.md" && echo "✓ PinchBench"
# 4. 密钥
grep -q 'GLM-5.2' "$HOME/crewpi/.env" && echo "✓ 规划器已设 GLM-5.2"
# 5. 云端连通（清代理后）
curl -sf https://api.siliconflow.cn/v1/models >/dev/null && echo "✓ SiliconFlow 可达"
```

推荐冒烟：网页里点最快的 chip（`task_weather` / `task_sanity`）跑一次，端云模式应出现三段动画（规划→执行→审计）和带 breakdown 的评分卡片。

---

## 10. 常见坑速查

| 症状 | 原因 / 处理 |
|------|-------------|
| 端侧执行报 `cli.js not found` | 没建 Pi：`git submodule update --init --recursive` + `scripts/build_pi_source.sh` |
| `ModuleNotFoundError: crewpi` | `CREWPI_HOME` 没指对，或没克隆 crewpi；启动脚本靠它加 PYTHONPATH |
| 规划超时 / cron 类任务失败 | `PLANNER_MODEL` 仍是 `DeepSeek-V4-Flash`（会挂起）→ 改 `zai-org/GLM-5.2` |
| 云端连不上 / 一直转 | 代理没清：`unset ...PROXY...`（SiliconFlow/TaoToken 国内直连） |
| 打分卡片没有子项 breakdown | 确认走的是 chip（原样未编辑）→ 命中 PinchBench 评分路径 |
| PinchBench 找不到任务 | 未 `export PINCHBENCH_SKILL_DIR`（默认兜底 `/home/admin/skill` 新机不存在） |

---

## 附：新机最小命令序列（从零到跑起来）

```bash
# 0) 前置：装好 python3.11+ / uv / node+npm / ollama / git
cd "$HOME"
git clone -b main git@github.com:liaops2/cloud-edge-audit-demo.git
git clone -b codex/crewpi-backend-integration git@github.com:liaops2/Crewpi.git crewpi

# 1) 内核
cd "$HOME/crewpi"
git submodule update --init --recursive
scripts/build_pi_source.sh
python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
cp .env.example .env && $EDITOR .env      # 填 key，PLANNER_MODEL 改 zai-org/GLM-5.2

# 2) 模型
ollama pull qwen3.5:0.8b
cd "$HOME/cloud-edge-audit-demo"
ollama create qwen3.5:0.8b-64k-demo -f ollama/Modelfile-qwen3.5-0.8b-64k-demo

# 3) 任务集（克隆/拷贝 skill 到 $HOME/skill）

# 4) demo 依赖 + 启动
uv sync
unset ALL_PROXY all_proxy HTTP_PROXY http_proxy HTTPS_PROXY https_proxy
export CREWPI_HOME="$HOME/crewpi" DEMO_BACKEND=crewpi DEMO_CREWPI_SEGMENTED=1 \
       DEMO_PROFILE=cloud_edge PINCHBENCH_SKILL_DIR="$HOME/skill"
bash scripts/start-demo-cloud.sh
```
