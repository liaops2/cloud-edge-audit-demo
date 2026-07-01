# 端云审计 Demo · 现场讲解脚本

**第一页 Harness → 第二页 架构+Demo → 第三页 收束 · 约 12–15 分钟**

---

## 上场前（30 秒）

- 左屏 A：**本地直连**
- 右屏 B：**端云规划+审计**
- 底部选 **File Structure Creation** → **填入输入框**（两边同一句，不改字）
- **第二页起**：PPT 与双浏览器同屏（PPT 约 1/3 + Demo 2/3）

**标准问句：**

```text
Create a project structure with: src/ directory, src/main.py with hello world, README.md with project title, and .gitignore ignoring __pycache__.
```

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
- **口播：** 缺 ①③，接近 self-reported done，gate 才暴露问题

### 右屏 B · 完整链路

- **同一句话发送**
- 规划亮 → 指 ① Cloud Planning
- 执行亮 → 指 ② DingClaw（同一 0.8b）
- 审计亮 → 指 ③ Cloud Audit（**重点：main-audit**）
- 评分亮 → Quality Gate / PinchBench 全 1.0 才 Pass

### 小结（不翻页）

同 criteria、同 Edge 模型；差在 Plan + Cloud Audit → **翻第三页**

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
