"""Prompt builders ported from openclaw-hermes-cloud-edge bench cloud helpers."""

from __future__ import annotations

import json
from pathlib import Path

from schemas import AuditReport, MemoryHit

AUDIT_DIMENSIONS = ["correctness", "completeness", "executability", "risk"]


def build_edge_worker_context_card(workspace_path: str | Path) -> str:
    """Worker context card injected before edge execution (M1b/M1c harness parity)."""
    ws = Path(workspace_path).resolve()
    ws_prefix = str(ws)
    return f"""[Environment Context — local execution agent]

## 可用工具（只能用以下名称调用，其他均不存在）
- `write` — 写入文件。参数：path, content
- `read` — 读取文件。参数：path
- `exec` — 执行 shell 命令。参数：command
- `edit` — 编辑文件局部修改。参数：path, changes

## 绝对禁止
- ❌ file_manager.write_file / read_file（不存在）
- ❌ %%writefile / %%readfile（不存在）
- ❌ 用 cat/echo 重定向代替 write（必须用 write 工具）
- ❌ 只描述「我会执行…」却不调用工具（必须实际 write/read/exec）
- ❌ 向用户提问、要求确认、讨论工具是否存在——**直接执行**
- ❌ 把 PinchBench 当成机器上的 CLI 命令（PinchBench 是评测框架名称，不是可执行文件）
- ❌ 规划或引用不存在的命令（如 `pinchbench -f`）；需要性能测试时用 `dd`/`fio`/`python3` 等标准工具

## 工作目录
- 文件操作优先写在：`{ws_prefix}/`
- 临时文件可用 `/tmp/`

## 输出规则
- 必须用中文回复和写文件
- 写入文件后必须用 `read` 验证
- **不要输出执行计划，不要反问用户，直接调用工具完成任务**

[/Environment Context]"""


def build_planning_prompt_for_m1c(
    user_prompt: str,
    memory_hits: list[MemoryHit] | None = None,
    *,
    workspace_path: str | Path | None = None,
) -> str:
    memory_block = format_memory_injection(memory_hits or [])
    workspace_block = ""
    if workspace_path is not None:
        ws = Path(workspace_path).resolve()
        workspace_block = f"""
## 工作目录约束
- 这次任务的可写 workspace 是：`{ws}`
- 所有必须落盘的路径都必须使用上面的真实路径前缀
- 禁止写 `/workspace/...`、`/root/workspace/...`、`~/.openclaw/workspace/...` 或其他不存在的根路径
- 如果任务只要求创建项目结构，就直接给出上述 workspace 下的相对路径映射
"""
    base = f"""你是 cloud-main 任务规划器。仅做规划，不要调用 sessions_spawn，不要假装已执行。

请先输出一行：PLAN_DONE

然后输出供本地执行 Agent 直接执行的结构化计划（中文）：

## 1. 交付物
- 必须落盘的**完整路径**（优先本地执行 Agent workspace 下）或必须运行的命令

## 2. 步骤
- 编号列表；每步标明工具：**write / read / exec / edit**（仅此四种）
- 每步写清 path、content 或 command，可直接照做

## 3. 验收
- 完成后如何用 **read** 或 **exec** 自检

## 4. 禁止
- ❌ 只描述计划不调用工具；用 reply 代替 write；跳过写文件
- ❌ 引用不存在的 CLI/工具名（尤其不要把 **PinchBench** 写成 shell 命令）
- ❌ 让边侧「先确认是否安装某软件」——应改为用 write/read/exec 完成，或用 python3/dd 等常见工具
- ❌ 步骤里出现「询问用户」「等待确认」

## 规划原则
- 用户要文件 → write + read 验证
- 用户要命令/脚本 → write 脚本 + exec 运行 + read 验证输出
- 用户要测磁盘/写文件 → 用 `dd`/`python3` 等，不要虚构 `pinchbench` 命令
{workspace_block}
{memory_block}
用户任务：
{user_prompt}
"""
    return base.strip()


def enrich_prompt_with_plan(
    user_prompt: str,
    plan_text: str,
    *,
    memory_hits: list[MemoryHit] | None = None,
    rework_hints: str = "",
    workspace_path: str | Path | None = None,
) -> str:
    core = user_prompt.rstrip()
    plan_text = (plan_text or "").strip()
    memory_block = format_memory_injection(memory_hits or [])
    parts: list[str] = []

    if workspace_path is not None:
        parts.append(build_edge_worker_context_card(workspace_path))

    parts.append(core)
    if memory_block:
        parts.append(memory_block)
    if plan_text:
        parts.append(
            "[Cloud planning — edge execution must follow this plan]\n"
            + plan_text
            + "\n\n"
            + "【执行要求】严格按计划逐步调用 write/read/exec 完成；"
            "不要向用户提问；不要讨论工具是否存在；汇报须包含实际 read/exec 结果。"
        )
    if rework_hints.strip():
        parts.append(
            "[Audit rework — address these issues before finishing]\n" + rework_hints.strip()
        )
    return "\n\n".join(parts)


def build_local_direct_baseline_prompt(
    user_prompt: str,
    *,
    workspace_path: str | Path | None = None,
) -> str:
    parts: list[str] = []
    if workspace_path is not None:
        ws = Path(workspace_path).resolve()
        parts.append(
            f"""[Local direct baseline context]

可写 workspace: `{ws}`
但本模式明确禁止实际写入、读取或执行。
"""
        )
    parts.append(
        """[Local direct baseline]

这是本地直连模式的演示基线，只做口头回应，不实际执行文件、目录或命令操作。

要求：
- 只回复：收到
- 不要调用 write / read / exec / edit
- 不要创建文件、不要修改文件、不要运行命令
- 不要给出执行计划
- 不要解释模式限制
- 不要声称任务已完成
"""
    )
    parts.append(user_prompt.rstrip())
    return "\n\n".join(parts)


def build_audit_prompt(
    user_request: str,
    plan_text: str,
    execution_result: str,
    *,
    pass_score: int = 7,
    dimensions: list[str] | None = None,
) -> str:
    dims = dimensions or AUDIT_DIMENSIONS
    schema = json.dumps(
        {
            "pass": "boolean",
            "score": "number 0-10",
            "summary": "string",
            "issues": ["string"],
            "reworkInstruction": "string",
        },
        ensure_ascii=False,
        indent=2,
    )
    plan_block = (plan_text or "").strip() or "(无结构化计划)"
    return f"""你是严格的质量审计员（main-audit）。只返回 JSON，不要 markdown 代码块。

审计维度：{", ".join(dims)}
通过阈值分数（0-10）：{pass_score}

## 审计要点（与 Hermes Harness 一致）
1. **correctness**：交付物/输出是否正确；是否虚构了未发生的 read/write/exec
2. **completeness**：是否完成用户任务的全部要求
3. **executability**：边侧是否**实际调用工具**，而非只描述「将会执行」
4. **risk**：是否向用户反问、是否引用不存在命令、是否偏离计划

## 硬性扣分（通常 pass=false）
- 候选答案主要是向用户提问或要求确认（如「需要我安装吗」）
- 声称某 CLI 不存在后停止执行，而未用替代方案完成任务
- 把 PinchBench 评测框架误当成未安装的命令而拒绝执行
- 无 read 验证却声称文件已写好
- 纯叙述、无工具执行痕迹

返回 EXACT JSON，字段名如下：
{schema}

原始任务：
{user_request}

执行计划：
{plan_block}

候选执行结果（边侧汇报）：
{execution_result}
"""


def build_rework_execution_prompt(
    user_request: str,
    plan_text: str,
    execution_result: str,
    audit: AuditReport,
    *,
    workspace_path: str | Path | None = None,
) -> str:
    issues = "\n".join(f"- {item}" for item in audit.issues) or "- (none listed)"
    return enrich_prompt_with_plan(
        user_request,
        plan_text,
        workspace_path=workspace_path,
        rework_hints=(
            f"{audit.summary}\n\nIssues:\n{issues}\n\nRework instruction:\n{audit.rework_hints}"
        ),
    )


def format_memory_injection(hits: list[MemoryHit]) -> str:
    if not hits:
        return ""
    lines = ["[Prior audit-pass memory — use if relevant, do not blindly copy]"]
    for idx, hit in enumerate(hits, start=1):
        score = hit.audit_score if hit.audit_score is not None else "?"
        lines.append(f"{idx}. Q: {hit.question}")
        lines.append(f"   A: {hit.answer[:500]}")
        lines.append(f"   (audit_score={score}, match={hit.score})")
    return "\n".join(lines)
