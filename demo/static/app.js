const STAGES = [
  { id: "recall", label: "记忆召回" },
  { id: "plan", label: "规划" },
  { id: "execute", label: "执行" },
  { id: "audit", label: "审计" },
  { id: "score", label: "评分" },
];

const STAGE_LABELS = Object.fromEntries(STAGES.map((s) => [s.id, s.label]));

let config = null;
let busy = false;
let selectedMode = "local_direct";
let activeRunId = null;
let activeEs = null;
let pinchbenchTasks = [];
let selectedPromptTaskId = "task_cron_organizer";
let welcomeBubbleEl = null;
let modeSummaryEl = null;

const DEFAULT_OFFICIAL_PROMPT = `Create a project structure with: src/ directory, src/main.py with hello world, README.md with project title, and .gitignore ignoring __pycache__.`;

const MODE_HINTS = {
  local_direct: "OpenClaw + Qwen 0.8B 64K",
  cloud_edge: "OpenClaw + DeepSeek + Qwen 0.8B 64K",
};

const MODE_LABELS = {
  local_direct: "本地 Agent",
  cloud_edge: "端云审计",
};

const MODE_RUBRIC_NOTES = {
  local_direct: "规则评分。",
  cloud_edge: "规划 + 审计。",
};

const CRITERIA_SUMMARIES = {
  "Directory `src/` created": "创建 src/ 目录",
  "File `src/main.py` created": "创建 src/main.py",
  "`src/main.py` contains valid Python hello world code": "main.py 能输出 hello world",
  "File `README.md` created": "创建 README.md",
  "`README.md` contains a project title/heading": "README.md 包含项目标题",
  "File `.gitignore` created": "创建 .gitignore",
  "`.gitignore` contains `__pycache__` entry": ".gitignore 忽略 __pycache__",
};

function $(id) {
  return document.getElementById(id);
}

function escapeHtml(s) {
  return String(s)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function createChatGroup(role) {
  const group = document.createElement("div");
  group.className = `chat-group ${role}`;

  const avatar = document.createElement("div");
  avatar.className = "chat-avatar";
  avatar.textContent = role === "user" ? "你" : "AI";

  const messages = document.createElement("div");
  messages.className = "chat-group-messages";

  group.appendChild(avatar);
  group.appendChild(messages);
  return { group, messages };
}

function appendBubble(messagesEl, text, extraClass = "") {
  const bubble = document.createElement("div");
  bubble.className = `chat-bubble${extraClass ? ` ${extraClass}` : ""}`;
  bubble.textContent = text;
  messagesEl.appendChild(bubble);
  scrollToBottom();
  return bubble;
}

function scrollToBottom() {
  const thread = $("chatThread");
  thread.scrollTop = thread.scrollHeight;
}

function buildPipelineStrip() {
  const strip = document.createElement("div");
  strip.className = "pipeline-strip";
  const stepEls = {};
  STAGES.forEach((stage) => {
    const el = document.createElement("span");
    el.className = "step pending";
    el.id = `step-${stage.id}`;
    el.textContent = stage.label;
    strip.appendChild(el);
    stepEls[stage.id] = el;
  });
  return { strip, stepEls };
}

function setStep(stepEls, stage, status) {
  const el = stepEls[stage];
  if (!el) return;
  el.className = `step ${status}`;
}

function formatStageDetail(event) {
  const payload = event.payload || {};
  if (event.stage === "score") return "";
  const parts = [];
  if (payload.plan_preview) parts.push(`【计划】\n${payload.plan_preview}`);
  if (payload.prompt_preview) parts.push(`【下发】\n${payload.prompt_preview}`);
  if (payload.execution_preview) parts.push(`【执行】\n${payload.execution_preview}`);
  if (payload.issues?.length) parts.push(`【问题】\n${payload.issues.join("\n")}`);
  return parts.join("\n\n");
}

function renderRubricPanel(container, rubric, { before } = {}) {
  if (!rubric) return null;

  const existing = container.querySelector(".rubric-panel");
  if (existing) existing.remove();

  const panel = document.createElement("details");
  panel.className = "rubric-panel";
  panel.open = true;

  const summary = document.createElement("summary");
  summary.textContent = `评分摘要 · ${rubric.name || rubric.task_id}`;
  panel.appendChild(summary);

  const body = document.createElement("div");
  body.className = "rubric-panel__body";

  const meta = document.createElement("p");
  meta.className = "rubric-meta";
  meta.textContent = summarizePassRule(rubric);
  body.appendChild(meta);

  if (rubric.grading_criteria?.length) {
    body.appendChild(rubricSectionTitle("检查要点"));
    const ul = document.createElement("ul");
    ul.className = "rubric-list";
    ul.innerHTML = summarizeCriteria(rubric.grading_criteria)
      .map((c) => `<li>${escapeHtml(c)}</li>`)
      .join("");
    body.appendChild(ul);
  }

  const modeNote = document.createElement("p");
  modeNote.className = "rubric-mode-note";
  modeNote.textContent = MODE_RUBRIC_NOTES[rubric.mode || getSelectedMode()];
  body.appendChild(modeNote);

  panel.appendChild(body);
  if (before) {
    container.insertBefore(panel, before);
  } else {
    container.appendChild(panel);
  }
  return panel;
}

function summarizePassRule(rubric) {
  if (rubric.task_id === "task_files") {
    return "通过条件：创建 src/main.py、README.md、.gitignore，且关键内容检查全部通过。";
  }
  if (rubric.task_id === "task_weather") {
    return "通过条件：创建可运行的 weather.py，并能获取旧金山天气数据后输出摘要。";
  }
  if (rubric.task_id === "task_sanity") {
    return "通过条件：Agent 能按要求返回准备就绪的确认消息。";
  }
  if (rubric.grading_type === "automated") {
    return "通过条件：规则检查项全部通过。";
  }
  if (rubric.grading_type === "hybrid") {
    return "通过条件：规则检查和模型评审的综合评分达到门禁。";
  }
  return "通过条件：模型评审分数达到门禁。";
}

function summarizeCriteria(criteria) {
  if (
    criteria.includes("File `src/main.py` created") &&
    criteria.includes("File `.gitignore` created")
  ) {
    return [
      "创建 src/ 目录和 src/main.py",
      "main.py 能输出 hello world",
      "创建 README.md",
      "README.md 包含项目标题",
      ".gitignore 忽略 __pycache__",
    ];
  }

  const summarized = criteria.map((item) => CRITERIA_SUMMARIES[item] || item);
  if (summarized.length <= 5) return summarized;

  const mustHave = summarized.filter((item) =>
    /创建|包含|输出|获取|确认|hello world|README|gitignore|weather/i.test(item)
  );
  const picked = (mustHave.length ? mustHave : summarized).slice(0, 5);
  return [...new Set(picked)];
}

function rubricSectionTitle(text) {
  const h = document.createElement("h4");
  h.className = "rubric-section-title";
  h.textContent = text;
  return h;
}

function renderScoreBlock(container, payload, status) {
  const combined =
    payload.combined_score !== undefined ? payload.combined_score : (payload.score ?? 0) / 10;
  if (combined === undefined && payload.score === undefined) return;
  const passed = payload.pass === true || status === "pass";
  const block = document.createElement("div");
  block.className = `score-inline ${passed ? "pass" : "fail"}`;
  const pct = Math.round(combined * 100);
  const type = payload.pinchbench_type ? ` · ${payload.pinchbench_type}` : "";
  block.innerHTML = `
    <div class="score-inline__head">
      <div class="score-inline__state">${passed ? "通过" : "未通过"}</div>
      <div class="score-inline__value">${pct}%</div>
      <div class="score-inline__label">${passed ? "完成" : "评分"}${type}</div>
    </div>
  `;
  const issues = payload.issues || [];
  if (issues.length) {
    const ul = document.createElement("ul");
    ul.className = "issue-list";
    ul.innerHTML = issues.map((i) => `<li>${escapeHtml(i)}</li>`).join("");
    block.appendChild(ul);
  }
  container.appendChild(block);
}

function createAssistantRunBubble() {
  const { group, messages } = createChatGroup("assistant");
  const bubble = document.createElement("div");
  bubble.className = "chat-bubble streaming";

  const { strip, stepEls } = buildPipelineStrip();
  const statusLine = document.createElement("div");
  statusLine.className = "stage-line";
  statusLine.innerHTML = "<strong>处理中</strong> …";

  const detail = document.createElement("pre");
  detail.className = "stage-detail";
  detail.textContent = "";

  const indicator = document.createElement("div");
  indicator.className = "chat-reading-indicator";
  indicator.innerHTML = "<span></span><span></span><span></span>";

  bubble.appendChild(strip);
  bubble.appendChild(statusLine);
  bubble.appendChild(detail);
  bubble.appendChild(indicator);
  messages.appendChild(bubble);

  $("chatThread").appendChild(group);
  scrollToBottom();

  return { bubble, stepEls, statusLine, detail, indicator };
}

function getSelectedMode() {
  return selectedMode;
}

function setSelectedMode(mode) {
  selectedMode = mode;
  $("modeLocal").classList.toggle("active", mode === "local_direct");
  $("modeCloud").classList.toggle("active", mode === "cloud_edge");
  renderModeSummary();
  renderPromptPanel();
}

function welcomeMessage() {
  const { group, messages } = createChatGroup("assistant");
  const bubble = appendBubble(messages, "");
  welcomeBubbleEl = bubble;
  renderModeSummary();
  $("chatThread").appendChild(group);
}

function renderModeSummary() {
  if (!welcomeBubbleEl) return;

  if (!modeSummaryEl) {
    modeSummaryEl = document.createElement("div");
    modeSummaryEl.className = "mode-summary";
    welcomeBubbleEl.appendChild(modeSummaryEl);
  }

  modeSummaryEl.innerHTML = `
    <div class="mode-summary__eyebrow">当前对比模式</div>
    <div class="mode-summary__title">${escapeHtml(MODE_LABELS[selectedMode])}</div>
    <div class="mode-summary__body">${escapeHtml(MODE_HINTS[selectedMode])}</div>
  `;
}

async function loadDefaultRubric(bubbleEl) {
  try {
    const mode = getSelectedMode();
    const res = await fetch(`/api/pinchbench/task_files/rubric?mode=${mode}`);
    if (!res.ok) return;
    const rubric = await res.json();
    renderRubricPanel(bubbleEl, rubric);
  } catch {
    /* ignore */
  }
}

async function loadPinchbenchPrompts() {
  try {
    const res = await fetch("/api/tasks");
    if (!res.ok) return;
    pinchbenchTasks = await res.json();
    renderPromptPanel();
  } catch {
    $("officialPrompt").textContent = DEFAULT_OFFICIAL_PROMPT;
  }
}

function getSelectedPromptTask() {
  return (
    pinchbenchTasks.find((t) => t.id === selectedPromptTaskId) ||
    pinchbenchTasks[0] ||
    null
  );
}

function renderPromptPanel() {
  const chips = $("promptChips");
  const pre = $("officialPrompt");
  if (!pinchbenchTasks.length) {
    pre.textContent = DEFAULT_OFFICIAL_PROMPT;
    return;
  }
  if (!pinchbenchTasks.some((t) => t.id === selectedPromptTaskId)) {
    selectedPromptTaskId = pinchbenchTasks[0].id;
  }
  chips.innerHTML = pinchbenchTasks
    .map(
      (t) =>
        `<button type="button" class="prompt-chip ${t.id === selectedPromptTaskId ? "active" : ""}" data-task-id="${escapeHtml(t.id)}">${escapeHtml(t.name || t.id)}</button>`
    )
    .join("");
  chips.querySelectorAll(".prompt-chip").forEach((btn) => {
    btn.addEventListener("click", () => {
      selectedPromptTaskId = btn.dataset.taskId;
      renderPromptPanel();
    });
  });
  const task = getSelectedPromptTask();
  pre.textContent = (task?.request || DEFAULT_OFFICIAL_PROMPT).trim();
}

function fillOfficialPrompt() {
  if (busy) return;
  const task = getSelectedPromptTask();
  const text = (task?.request || DEFAULT_OFFICIAL_PROMPT).trim();
  $("messageInput").value = text;
  autoResizeInput();
  $("messageInput").focus();
}

async function loadConfig() {
  const res = await fetch("/api/config");
  config = await res.json();
  setSelectedMode(config.default_mode || "local_direct");
}

function setBusy(next) {
  busy = next;
  const btn = $("sendBtn");
  btn.disabled = false;
  btn.classList.toggle("is-cancel", next);
  btn.title = next ? "终止任务" : "发送";
  $("messageInput").disabled = next;
  $("modeLocal").disabled = next;
  $("modeCloud").disabled = next;
  $("usePromptBtn").disabled = next;
  document.querySelectorAll(".prompt-chip").forEach((btn) => {
    btn.disabled = next;
  });
}

function clearActiveRun() {
  activeRunId = null;
  if (activeEs) {
    activeEs.close();
    activeEs = null;
  }
}

async function cancelActiveRun() {
  if (!activeRunId) return;
  const runId = activeRunId;
  try {
    await fetch(`/api/runs/${runId}/cancel`, { method: "POST" });
  } catch {
    /* ignore */
  }
}

function autoResizeInput() {
  const el = $("messageInput");
  el.style.height = "auto";
  el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
}

async function sendMessage() {
  if (busy) return;
  const input = $("messageInput");
  const text = input.value.trim();
  if (!text) return;

  const { group, messages } = createChatGroup("user");
  appendBubble(messages, text);
  $("chatThread").appendChild(group);

  input.value = "";
  autoResizeInput();
  setBusy(true);

  const runUi = createAssistantRunBubble();

  const body = {
    message: text,
    mode: getSelectedMode(),
    pass_score: config?.pass_score ?? 7,
    max_reworks: 1,
  };

  let res;
  try {
    res = await fetch("/api/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  } catch {
    runUi.statusLine.innerHTML = "<strong>错误</strong> 无法连接服务";
    runUi.indicator.remove();
    setBusy(false);
    return;
  }

  if (!res.ok) {
    const err = await res.text();
    runUi.bubble.classList.remove("streaming");
    runUi.statusLine.innerHTML = `<strong>启动失败</strong> ${escapeHtml(err)}`;
    runUi.indicator.remove();
    setBusy(false);
    return;
  }

  const runData = await res.json();
  const { run_id, rubric } = runData;
  activeRunId = run_id;
  if (rubric) {
    renderRubricPanel(runUi.bubble, rubric, { before: runUi.bubble.firstChild });
  }
  runUi.statusLine.innerHTML = `<strong>运行中</strong> <span style="color:var(--muted)">${escapeHtml(run_id)}</span>`;

  const es = new EventSource(`/api/runs/${run_id}/events`);
  activeEs = es;

  es.onmessage = (msg) => {
    let event;
    try {
      event = JSON.parse(msg.data);
    } catch {
      return;
    }
    if (!event.stage) return;

    if (STAGE_LABELS[event.stage]) {
      setStep(runUi.stepEls, event.stage, event.status);
    }

    const label = STAGE_LABELS[event.stage] || event.stage;
    runUi.statusLine.innerHTML = `<strong>${escapeHtml(label)}</strong> · ${escapeHtml(event.message || event.status)}`;

    const detailText = formatStageDetail(event);
    if (detailText) runUi.detail.textContent = detailText;

    if (event.stage === "score") {
      const payload = event.payload || {};
      renderScoreBlock(runUi.bubble, payload, event.status);
      if (payload.rubric) {
        renderRubricPanel(runUi.bubble, payload.rubric, { before: runUi.bubble.firstChild });
      }
    }

    if (event.stage === "done") {
      runUi.bubble.classList.remove("streaming");
      runUi.indicator.remove();
      runUi.statusLine.innerHTML = `<strong>完成</strong> · ${escapeHtml(event.message || "运行结束")}`;
      es.close();
      clearActiveRun();
      setBusy(false);
      scrollToBottom();
    }
  };

  es.onerror = () => {
    es.close();
    runUi.bubble.classList.remove("streaming");
    runUi.indicator.remove();
    runUi.statusLine.innerHTML = "<strong>中断</strong> SSE 连接断开";
    clearActiveRun();
    setBusy(false);
  };
}

loadConfig().then(() => {
  welcomeMessage();
  loadPinchbenchPrompts();
  scrollToBottom();
});

$("usePromptBtn").addEventListener("click", fillOfficialPrompt);

$("modeLocal").addEventListener("click", () => {
  if (busy || selectedMode === "local_direct") return;
  setSelectedMode("local_direct");
});

$("modeCloud").addEventListener("click", () => {
  if (busy || selectedMode === "cloud_edge") return;
  setSelectedMode("cloud_edge");
});

$("sendBtn").addEventListener("click", () => {
  if (busy) {
    cancelActiveRun();
    return;
  }
  sendMessage();
});

$("messageInput").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    if (!busy) sendMessage();
  }
});

$("messageInput").addEventListener("input", autoResizeInput);
