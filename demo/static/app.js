const STAGES = [
  { id: "recall", label: "Recall" },
  { id: "plan", label: "Plan" },
  { id: "execute", label: "Execute" },
  { id: "audit", label: "Audit" },
  { id: "score", label: "Score" },
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
  local_direct: "Edge only · Qwen 0.8B 64K",
  cloud_edge: "Cloud plan+audit (DeepSeek) · Qwen 0.8B edge",
};

const MODE_LABELS = {
  local_direct: "Local Agent",
  cloud_edge: "Cloud-Edge Audit",
};

const MODE_RUBRIC_NOTES = {
  local_direct: "Rule-based grading.",
  cloud_edge: "Plan + audit.",
};

const CRITERIA_SUMMARIES = {
  "Directory `src/` created": "Create src/ directory",
  "File `src/main.py` created": "Create src/main.py",
  "`src/main.py` contains valid Python hello world code": "main.py prints hello world",
  "File `README.md` created": "Create README.md",
  "`README.md` contains a project title/heading": "README.md has a project title",
  "File `.gitignore` created": "Create .gitignore",
  "`.gitignore` contains `__pycache__` entry": ".gitignore ignores __pycache__",
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
  avatar.textContent = role === "user" ? "You" : "AI";

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
  // Keep only key info: audit/execution findings. Drop verbose plan/prompt/exec dumps.
  if (payload.issues?.length) return `[Issues]\n${payload.issues.join("\n")}`;
  return "";
}

function renderRubricPanel(container, rubric, { before } = {}) {
  if (!rubric) return null;

  const existing = container.querySelector(".rubric-panel");
  if (existing) existing.remove();

  const panel = document.createElement("details");
  panel.className = "rubric-panel";
  panel.open = true;

  const summary = document.createElement("summary");
  summary.textContent = `Grading summary · ${rubric.name || rubric.task_id}`;
  panel.appendChild(summary);

  const body = document.createElement("div");
  body.className = "rubric-panel__body";

  const meta = document.createElement("p");
  meta.className = "rubric-meta";
  meta.textContent = summarizePassRule(rubric);
  body.appendChild(meta);

  if (rubric.grading_criteria?.length) {
    body.appendChild(rubricSectionTitle("Checklist"));
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
    return "Pass when: src/main.py, README.md and .gitignore are created and all content checks pass.";
  }
  if (rubric.task_id === "task_weather") {
    return "Pass when: a runnable weather.py is created that fetches SF weather and prints a summary.";
  }
  if (rubric.task_id === "task_sanity") {
    return "Pass when: the agent returns the requested ready confirmation.";
  }
  if (rubric.grading_type === "automated") {
    return "Pass when: all rule-based checks pass.";
  }
  if (rubric.grading_type === "hybrid") {
    return "Pass when: the combined rule + LLM-judge score meets the threshold.";
  }
  return "Pass when: the LLM-judge score meets the threshold.";
}

function summarizeCriteria(criteria) {
  if (
    criteria.includes("File `src/main.py` created") &&
    criteria.includes("File `.gitignore` created")
  ) {
    return [
      "Create src/ directory and src/main.py",
      "main.py prints hello world",
      "Create README.md",
      "README.md has a project title",
      ".gitignore ignores __pycache__",
    ];
  }

  const summarized = criteria.map((item) => CRITERIA_SUMMARIES[item] || item);
  if (summarized.length <= 5) return summarized;

  const mustHave = summarized.filter((item) =>
    /create|contain|print|fetch|confirm|hello world|README|gitignore|weather/i.test(item)
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
      <div class="score-inline__state">${passed ? "Pass" : "Fail"}</div>
      <div class="score-inline__value">${pct}%</div>
      <div class="score-inline__label">${passed ? "Done" : "Score"}${type}</div>
    </div>
  `;
  const breakdown = payload.breakdown || {};
  const entries = Object.entries(breakdown);
  if (entries.length) {
    // Show every sub-criterion with its score (pass/fail), not just failures.
    const ul = document.createElement("ul");
    ul.className = "breakdown-list";
    ul.innerHTML = entries
      .map(([k, v]) => {
        const ok = Number(v) >= 1;
        const val = Number.isInteger(Number(v)) ? Number(v) : Number(v).toFixed(2);
        return `<li class="${ok ? "bd-ok" : "bd-fail"}"><span class="bd-mark">${ok ? "✓" : "✗"}</span><span class="bd-name">${escapeHtml(k)}</span><span class="bd-score">${val}</span></li>`;
      })
      .join("");
    block.appendChild(ul);
  } else {
    const issues = payload.issues || [];
    if (issues.length) {
      const ul = document.createElement("ul");
      ul.className = "issue-list";
      ul.innerHTML = issues.map((i) => `<li>${escapeHtml(i)}</li>`).join("");
      block.appendChild(ul);
    }
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
  statusLine.innerHTML = "<strong>Processing</strong> …";

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
    <div class="mode-summary__eyebrow">Current mode</div>
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
  btn.title = next ? "Cancel" : "Send";
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
  // If the message is an unedited PinchBench prompt, bind its task_id so the
  // backend runs the graded pinchbench path (with a full sub-criteria
  // breakdown) instead of falling back to the free-form audit-gate path.
  const selectedTask = getSelectedPromptTask();
  if (selectedTask && text === (selectedTask.request || "").trim()) {
    body.task_id = selectedTask.id;
  }

  let res;
  try {
    res = await fetch("/api/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  } catch {
    runUi.statusLine.innerHTML = "<strong>Error</strong> cannot reach server";
    runUi.indicator.remove();
    setBusy(false);
    return;
  }

  if (!res.ok) {
    const err = await res.text();
    runUi.bubble.classList.remove("streaming");
    runUi.statusLine.innerHTML = `<strong>Start failed</strong> ${escapeHtml(err)}`;
    runUi.indicator.remove();
    setBusy(false);
    return;
  }

  const runData = await res.json();
  const { run_id } = runData;
  activeRunId = run_id;
  runUi.statusLine.innerHTML = `<strong>Running</strong> <span style="color:var(--muted)">${escapeHtml(run_id)}</span>`;

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
    }

    if (event.stage === "done") {
      runUi.bubble.classList.remove("streaming");
      runUi.indicator.remove();
      runUi.statusLine.innerHTML = `<strong>Done</strong> · ${escapeHtml(event.message || "Run finished")}`;
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
    runUi.statusLine.innerHTML = "<strong>Interrupted</strong> SSE disconnected";
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
