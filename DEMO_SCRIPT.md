# 端云审计 Demo · 现场讲解脚本（对齐 Lenovo 三页 PPT）

> **Slide 41** Claw Agent Harness  
> **Slide 42** Cloud-Edge Audit — Quality-Gated Completion · **本页 Live Demo**  
> **Slide 43** How It Works — Event-Driven Verify → Evolve Loop  
>  
> **建议时长**：12–15 分钟 · **核心**：Slide 42 边指架构边跑双机，同一问句、不同 Quality Gate。

---

## 上场前 30 秒

| | 左屏 A | 右屏 B |
|---|--------|--------|
| 标签 | 「无 Cloud-Edge Audit」 | 「Cloud-Edge Audit 完整链路」 |
| 模式 | **本地直连** | **端云规划+审计** |
| 预填 | File Structure Creation → **填入输入框** | 同上 |

**投屏布局（从 Slide 42 起）**：左 1/3 保留 PPT 42 · 右 2/3 双浏览器并排；或 PPT PiP 左上角。

**标准问句（整场不改字）**：
```text
Create a project structure with: src/ directory, src/main.py with hello world, README.md with project title, and .gitignore ignoring __pycache__.
```

---

## 三页时间轴

| Slide | 标题 | 时长 | 画面 |
|-------|------|------|------|
| **41** | Claw Agent Harness | 3–4 min | PPT 全屏 |
| **42** | Cloud-Edge Audit | 8–10 min | **PPT + Demo 同屏** |
| **43** | Verify → Evolve Loop | 2–3 min | PPT 全屏 |

---

# 【Slide 41】Claw Agent Harness · 3–4 分钟

**画面**：PPT 全屏 —— 中间 **Agent Core（DingClaw）**，外围五个 Guard，底部 **Hook Engine + MD Memory Base**。

---

### 口播（开场 + 标题）

> 大家好。这页叫 **Claw Agent Harness** —— 一句话：**A reliability scaffold wrapped around the agent**；不是改 Agent 本身，而是在外面套一层**可靠性脚手架**。  
> 中间是我们的 **Agent Core**，DingClaw；外面是四加一道 **Guard**，共用同一套 Core。

---

### 口播（五个 Guard —— 按 PPT 位置指）

> **正上方 — Cloud-Edge Audit**，Quality · cloud-verified：  
> **Cloud plans → edge executes → cloud audits**。今天 Demo 主要验的就是这一条。  
>  
> **左侧 — Watchdog**，Liveness · always-on：挂死检测、stop kicking、硬件复位，保证**活着**。  
>  
> **左下 — Self-Verification**，Correctness · trust now：本地校验 claim、抓死循环，保证**当下可信**。  
>  
> **右侧 — Context Compression**，Efficiency · load control：MD 瘦身 + runtime compaction，15K → 10K，控制**负载**。  
>  
> **右下 — Self-Evolution**，Growth · long-term：错误日志 → 持久规则，跨 session 进化，负责**长期成长**。  
>  
> 底部 **Hook Engine + MD Memory Base** 托住上面所有 Guard：SOUL、TOOLS、AGENTS、LEARNINGS、ERRORS、FEATURE_REQ —— 事件从 Hook 进，记忆从 MD 出。

---

### 口播（过渡到 Slide 42）

> 五道 Guard 里，**Cloud-Edge Audit** 解决的是：**任务能不能在独立门禁下算「完成」** —— 不是 Agent 自己说 done 就算 done。  
> 下一页我展开这条 Guard 的架构，并且**直接在这页上开 Live Demo**，用同一句话走「有审计 / 无审计」两条路。  
>  
> （**翻页 → Slide 42**）

**操作**：翻 PPT 到 Slide 42。

---

# 【Slide 42】Cloud-Edge Audit + Live Demo · 8–10 分钟

**画面**：**Slide 42 与双浏览器同时可见**（不切页直到 Demo 跑完）。

**PPT 要点（口播时可反复指）**：
- 副标题：*Plan in the cloud, execute on the edge, audit in the cloud — an independent gate before any task is marked done.*
- 上 **CLOUD** / 下 **EDGE**，虚线 **device ⇄ cloud**
- ① Plan → ② Local Execution（DingClaw）→ ③ Cloud Audit → **Quality Gate**（Pass / Fail rework）
- 页脚：*Why it matters: an independent cloud audit catches what local self-check can't — a hard quality gate, not a self-reported 'done'.*

---

## 42-A · 对着 PPT 讲架构 · 约 1 分钟（Demo 未动）

**口播**：

> 这页标题 **Cloud-Edge Audit — Quality-Gated Completion**。  
> 三步闭环：  
>  
> **① Cloud Planning** — 把任务拆成步骤，加上** explicit acceptance criteria**（验收标准）；`plan + criteria` 下发到 Edge。  
> **② Local Execution** — Edge 上 **DingClaw** 按计划在本地执行，并逐步 self-verify；执行结果和 evidence 回传 Cloud。  
> **③ Cloud Audit** — Cloud **独立审查**结果是否满足 criteria，给出 score，进入 **Quality Gate**：  
> - **Pass** → task marked complete  
> - **Fail** → returned to edge for rework（虚线回到执行）  
>  
> 页脚那句是今天 Demo 的题眼：**独立云审计能抓住本地 self-check 抓不住的** —— 是 hard quality gate，不是 self-reported done。  
>  
> 下面用两台机器对照：左屏**没有** Cloud-Edge Audit 完整链路；右屏**走** ①②③ + Quality Gate（我们用 PinchBench automated 做客观门禁）。

**操作**：
1. 激光笔走一遍 ① → ② → ③ → Quality Gate。
2. 露出双浏览器；指左 **本地直连**、右 **端云规划+审计**。
3. 指底部 PinchBench **File Structure Creation**，确认两边输入框同一句英文。

---

## 42-B · Demo：无 Cloud-Edge Audit · 左屏 A · 约 3–4 min

**口播（指 PPT，对比「缺哪几步」）**：

> 左屏模拟的是：**跳过 Cloud Planning 和 Cloud Audit**，任务直达 Edge —— 接近「只有 Local Execution + 自己报 done」，没有 independent gate。  
> 发送后看 Demo 顶栏四格：**规划、执行、审计、评分** —— 左屏 **规划/审计应灰色**，只有 **执行 → 评分**。

**操作**：左屏 **发送**。

---

**执行中 · 口播（指 PPT ② Local Execution / DingClaw）**：

> 对应 Slide 42 中间 **DingClaw runs the plan locally** —— 但这里没有上游 plan + criteria，0.8b 裸接任务，self-verify 能力有限。

**评分出结果 · 口播（指 PPT Quality Gate / 页脚）**：

> 最后到 **Score / Quality Gate**。我们接 PinchBench **task_files** 作客观 criteria：每项必须 1.0。  
> **（按实际结果选一句）**  
> - 未全满：「没有 Cloud Audit，本地 self-check 拦不住 —— 到 gate 才暴露漏项，这就是 self-reported done 的问题。」  
> - 只说不做：「典型 failure：话说了，workspace 证据不齐。」  
> - 意外全过：「这次碰巧过了，但 live 里无 Audit 链路不稳定 —— 看右屏 hard gate。」

**操作**：展开 PinchBench 分项，点 1–2 个未达标项。

---

## 42-C · Demo：完整 Cloud-Edge Audit · 右屏 B · 约 4–5 min

**口播（指 PPT ①→②→③ 全链路）**：

> 右屏 **同一句话**，走 Slide 42 完整三步 + Quality Gate。

**操作**：右屏 **发送**。

---

**① 规划亮 · 口播（指 PPT Cloud / Step 1）**：

> **Cloud Planning** — DeepSeek 拆步骤 + acceptance criteria；`plan + criteria` 下到 Edge。对应 Demo **规划** 格。

**② 执行亮 · 口播（指 PPT Edge / DingClaw）**：

> **Local Execution** — 还是 DingClaw / edge-worker、还是 0.8b；差别是有 plan 带着跑，results + evidence 准备回 Cloud。

**③ 审计亮 · 口播（指 PPT Cloud Audit /  scales —— 本页重点）**：

> **Cloud Audit — Independent review**。main-audit 对照 criteria：有没有只提问不执行？计划是否落地？  
> 这就是页脚说的：** catches what local self-check can't**。  
> **（按 audit 输出略读 pass / 问题一句）**

**评分亮 · 口播（指 Quality Gate Pass/Fail）**：

> **Quality Gate** — PinchBench automated 给 objective score：全 1.0 → Pass，task marked complete；否则 Fail，生产里会 rework 回 Edge。  
> **（按结果）** 右屏通常更易 Pass —— 不是换了 Edge 模型，是补上了 **Plan + Cloud Audit** 两道独立门禁。

**操作**：展示 audit 块 + PinchBench 分项；与左屏并排对比 5 秒。

---

## 42-D · 仍在 Slide 42 · 小结 · 30 秒

**口播（指 PPT 全图，不翻页）**：

> 还在 42 页：同一 acceptance criteria（PinchBench task_files）、同一 Edge 模型；  
> 左：缺 ①③，无 hard quality gate；  
> 右：Plan → Execute → Audit → Gate，符合 **Cloud plans → edge executes → cloud audits**。  
>  
> （**翻页 → Slide 43**）

---

# 【Slide 43】Event-Driven Verify → Evolve Loop · 2–3 分钟

**画面**：PPT 全屏 —— 左 DingClaw，右四步循环 + 底部 Watchdog / Compression。

---

### 口播

> 最后一页：**How It Works — Event-Driven Verify → Evolve Loop**。  
> Gateway Hook 拦截生命周期事件，本地检查，写可见 notice，下一 session 再注入 learnings —— 这是 **Harness 在工程里怎么落地**。  
>  
> 四步：  
> **① Trigger Events** — 监听 `/new`、`agent:bootstrap`、assistant reply、compact after。  
> **② Hook Intercepts** — `handler.ts` 在最终回复前介入：跑 checks、写 notices。  
> **③ Local Verification** — `local_context` / `pre_check` / `loop_detector`：验 claim、抓 loop。  
> **④ Persist & Evolve** — 修正写入 LEARNINGS / ERRORS，下次 bootstrap 自动加载。  
>  
> 底部 **Watchdog**（system liveness）和 **Compression**（threshold compaction）对应 Slide 41 里另外两道 Guard。  
>  
> 和刚才 Demo 的关系：  
> - **Slide 42 Cloud-Edge Audit** = 任务级 **Quality Gate**（规划 + 独立云审 + Pass/Fail）。  
> - **Slide 43 Verify → Evolve** = 会话级 **Hook 流水线**（每条回复前的本地 verify + 跨 session 进化）。  
> 两者同属 **Claw Agent Harness**，一个管「这次任务过没过」，一个管「Agent 长期可不可信」。  
>  
> 今天 Live Demo 是 Slide 42 的可视化简化版；完整 Harness 见 **openclaw-hermes-cloud-edge**，评分对齐 **PinchBench**。

**操作**：Q&A；可选切回最后一帧双屏对比截图。

---

## PPT ↔ Demo 对照速查（贴提词器）

| Slide 42 框 | Demo 右屏 B | Demo 左屏 A |
|-------------|-------------|-------------|
| ① Cloud Planning | **规划** 亮 | **规划** 灰 |
| ② Local Execution (DingClaw) | **执行** 亮 | **执行** 亮 |
| ③ Cloud Audit | **审计** 亮 | **审计** 灰 |
| Quality Gate / Score | **评分** + PinchBench | **评分** only |
| Fail → rework | （Demo 简化为单次 run） | — |

| Slide 41 Guard | 今天是否 Demo |
|----------------|---------------|
| **Cloud-Edge Audit** | ✅ Slide 42 主 Demo |
| Watchdog | ❌ 仅 Slide 43 口述 |
| Self-Verification | ⚠️ Edge 自带，Demo 不单独展示 |
| Context Compression | ❌ 口述 |
| Self-Evolution | ❌ Slide 43 Persist & Evolve 口述 |

---

## 备用话术

| 情况 | 口播 |
|------|------|
| A 太慢 | 「Edge 0.8b live 有波动；先看 B 完整 ①②③，A 结果留屏对比 Quality Gate。」 |
| B 规划/API 失败 | 「Cloud Planning 依赖云端可用性 —— 重试；生产要监控 Step 1。」 |
| 观众问 Self-Verification vs Cloud Audit | 「Self-Verification 是 Edge 上 trust now；Cloud Audit 是独立第三方门禁 —— 页脚那句。」 |

---

## 与 SOP 的关系

- 环境部署 → [SOP.md](./SOP.md)  
- 本文件 → **Slide 41/42/43 口播 + Slide 42 嵌 Demo**
