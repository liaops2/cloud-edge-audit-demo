# 端云审计 Demo · 现场讲解脚本

**第一页 Harness → 第二页 架构+Demo → 第三页 收束 · 约 12–15 分钟**

---

## 上场前（30 秒）

- 左屏 A：**本地直连**
- 右屏 B：**端云规划+审计**
- 底部选 **Cron Expression Generator** → **填入输入框**（两边同一句，不改字）
- **第二页起**：PPT 与双浏览器同屏（PPT 约 1/3 + Demo 2/3）

**标准问句：** 把 10 条自然语言排班转成 cron 表达式，写入 `cron_expressions.json`（JSON 数组，含 description/cron/explanation）。

```text
Convert the following natural language schedule descriptions into properly formatted cron expressions. Save the results to `cron_expressions.json` as a JSON array.
（含 10 条排班：weekday 9AM、每 15 分钟、每月 1 号 0 点、周日 15:30、每 6 小时、Mon-Fri 17:00、每天 8AM/8PM、工作日 9-17 点每刻钟、每月最后工作日 18:00、周六 2-4AM 每 5 分钟）
```

> **为何换这道题**：`task_files` 太简单，本地直连也能 1.0，演示不出价值。cron 这道题**本地 0.8b 会崩、端云能精确完成**，对比才成立。实测：本地直连 **0.1**（JSON 结构崩+多条 cron 写错），端云 **0.9 通过**（10 条 cron 全对，仅因基准评分器 "mon" 误匹配 "month" 的 bug 扣 0.1）。

---

## 第一页 · Claw Agent Harness（约 3 分钟）

**口播要点：**

- Harness = 套在 Agent Core（DingClaw）外的可靠性脚手架
- 五道 Guard：**Cloud-Edge Audit**（今天 Demo）、Watchdog、Self-Verification、Context Compression、Self-Evolution
- 底部 Hook Engine + MD Memory Base 托住全局

**过渡：** Cloud-Edge Audit 解决「任务是否在独立门禁下算完成」→ **翻第二页**

---

## 第二页 · Cloud-Edge Audit + Live Demo（约 8 分钟）

### 先指 PPT（30 秒）

1. **Cloud Planning**：拆步骤 + acceptance criteria → plan + criteria 下 Edge  
2. **Local Execution**：DingClaw 本地执行 → results + evidence 回 Cloud  
3. **Cloud Audit**：独立审查 → Quality Gate（Pass=完成 / Fail=rework）

**页脚：** 独立云审抓得住 local self-check 抓不住的 —— hard gate，不是 self-reported done

### 左屏 A · 无完整 Audit

- **发送**
- 规划/审计灰色 → 执行 → PinchBench 评分
- **口播：** 缺 ①③，本地 0.8b 直接干 —— **结构崩（不是 JSON 数组）、多条 cron 写错**，评分 **0.1 未通过**；没有 gate 时这类错误只会被 self-reported done 盖住

### 右屏 B · 完整链路

- **同一句话发送**
- 规划亮 → 指 ① Cloud Planning（云端 DeepSeek 拆出精确的生成步骤）
- 执行亮 → 指 ② DingClaw（同一 0.8b，按云端计划**确定性落地** cron JSON）
- 审计亮 → 指 ③ Cloud Audit（**重点：main-audit** 独立判是否真完成）
- 评分亮 → Quality Gate / PinchBench **≥0.75 才 Pass**（本题端云 **0.9 通过**，10 条 cron 全对）

### 小结（不翻页）

同一句话、同一个 0.8b Edge 模型；差在 **Plan + Cloud Audit** —— 本地 0.1、端云 0.9 → **翻第三页**

---

## 第三页 · Verify → Evolve Loop（约 2 分钟）

**口播要点：**

- Gateway Hook 拦截事件 → 本地 verify → 写 notice → 下 session 注入 learnings
- 四步：Trigger → Hook Intercepts → Local Verification → Persist & Evolve
- 与第二页关系：**第二页** = 任务级 Quality Gate；**第三页** = 会话级 Hook 流水线，同属 Harness

**收束：** Demo 是第二页架构的可视化演示；完整见 openclaw-hermes-cloud-edge + PinchBench

---

## 备忘 / 应急

| 情况 | 处理 |
|------|------|
| 三句备忘 | 同 Prompt · 同 0.8b · 同 PinchBench \| 左 2 步右 4 步 \| Audit=独立门禁 |
| A 太慢 | 先看 B 完整链路，A 结果留屏对比 |
| B 规划失败 | 重试，强调 Cloud Planning 依赖云端可用性 |
