"use strict";
// RX web UI. Every piece of model/tool text goes through textContent — never innerHTML.
(() => {
  const $ = (id) => document.getElementById(id);
  const el = (tag, cls, text) => { const n = document.createElement(tag); if (cls) n.className = cls; if (text !== undefined) n.textContent = text; return n; };

  const params = new URLSearchParams(location.hash.slice(1));
  if (params.get("token")) sessionStorage.setItem("rx.token", params.get("token"));
  if (params.get("workspace")) $("workspace").value = params.get("workspace");
  history.replaceState(null, "", location.pathname);   // keep the token out of history/screenshots

  const state = { ws: null, ready: false, running: false, sessionId: null, bubble: null, cards: new Map(), prompt: 0, output: 0, limits: {}, retry: 0 };
  const log = $("log");

  function scroll() { const near = log.scrollHeight - log.scrollTop - log.clientHeight < 120; if (near) log.scrollTop = log.scrollHeight; }
  function add(node) { $("empty")?.remove(); log.appendChild(node); scroll(); return node; }
  function note(text, kind) { return add(el("div", "note" + (kind ? " " + kind : ""), text)); }
  function setRunning(on) {
    state.running = on;
    $("go").hidden = on; $("stop").hidden = !on; $("task").disabled = false;
    $("mode").disabled = on;   // the mode is fixed for the duration of a run; don't let the dropdown lie
    $("hint").textContent = on ? (state.runMode || "") + " mode · Esc to stop" : "";
  }
  function setConn(s, title) { const c = $("conn"); c.dataset.state = s; c.title = title; }

  // ---- text rendering: paragraphs + ``` fences, nothing else ---------------------------------------
  function renderText(node, text) {
    node.textContent = "";
    const parts = text.split("```");
    parts.forEach((part, i) => {
      if (i % 2 === 1) { const nl = part.indexOf("\n"); node.appendChild(el("pre", "", nl >= 0 ? part.slice(nl + 1) : part)); }
      else if (part) node.appendChild(document.createTextNode(part));
    });
  }
  function renderDiff(pre, diff) {
    pre.textContent = ""; pre.classList.add("diff");
    diff.split("\n").slice(0, 200).forEach((line) => {
      const cls = line.startsWith("+++") || line.startsWith("---") ? "" : line.startsWith("+") ? "add" : line.startsWith("-") ? "del" : line.startsWith("@@") ? "hunk" : "";
      pre.appendChild(el("span", cls, line || " "));
    });
  }

  // ---- connection -----------------------------------------------------------------------------------
  function connect() {
    const token = sessionStorage.getItem("rx.token");
    if (!token) { $("tokenDialog").showModal(); return; }
    setConn("wait", "connecting…");
    const ws = new WebSocket((location.protocol === "https:" ? "wss://" : "ws://") + location.host + "/ws");
    state.ws = ws;
    ws.onopen = () => ws.send(JSON.stringify({ type: "auth", token }));
    ws.onmessage = (ev) => { try { handle(JSON.parse(ev.data)); } catch (e) { console.error(e); } };
    ws.onclose = () => {
      state.ready = false; setConn("off", "disconnected"); setRunning(false); [...pending.keys()].forEach((id) => closeApproval(id));
      if (state.retry >= 0) setTimeout(connect, Math.min(8000, 500 * 2 ** state.retry++));
    };
  }
  function send(obj) { if (state.ws && state.ws.readyState === 1) state.ws.send(JSON.stringify(obj)); }

  // ---- event handling -------------------------------------------------------------------------------
  function toolCard(e) {
    const card = el("div", "card"); card.dataset.state = "run";
    const head = el("header"); head.append(el("span", "dot"), el("span", "summary", e.summary));
    const body = el("pre", "body");
    card.append(head, body); state.cards.set(e.id, { card, body }); add(card);
  }
  const pending = new Map();   // approval id -> {card, timer}
  function refreshTitle() { document.title = pending.size ? "(!) Approval needed · RX" : "RX · coding agent"; }
  function closeApproval(id, text, kind) {
    const p = pending.get(id); if (!p) return;
    clearInterval(p.timer); p.card.remove(); pending.delete(id); refreshTitle();
    if (text) note(text, kind);
  }
  function approvalCard(e) {
    const card = el("div", "card approval"); card.dataset.risk = e.risk;
    const head = el("header"); const count = el("span", "count");
    head.append(el("span", "dot"), el("span", "summary", "Approval needed · " + e.summary), count);
    card.appendChild(head);
    if (e.reason) card.appendChild(el("div", "why", e.reason));
    if (e.preview) { const pre = el("pre", "body"); /^(---|\+\+\+|@@)/m.test(e.preview) ? renderDiff(pre, e.preview) : (pre.textContent = e.preview); card.appendChild(pre); }
    const actions = el("div", "actions");
    const answer = (approved, remember, message) => {
      send({ type: "approval_response", id: e.id, approved, remember: !!remember, message });
      closeApproval(e.id, (approved ? "Approved · " : "Denied · ") + e.summary);
    };
    const yes = el("button", "go", "Approve"); yes.onclick = () => answer(true, false);
    actions.appendChild(yes);
    if (e.can_remember) { const always = el("button", "", "Always allow this kind"); always.onclick = () => answer(true, true); actions.appendChild(always); }
    const msg = el("input"); msg.placeholder = "Deny, with a note for the agent (optional)"; msg.setAttribute("aria-label", "Denial note");
    const no = el("button", "", "Deny"); no.onclick = () => answer(false, false, msg.value || undefined);
    actions.append(msg, no); card.appendChild(actions);
    let left = e.timeout ? Math.round(e.timeout) : 0;
    const tick = () => { if (left > 0) { count.textContent = "auto-denies in " + Math.floor(left / 60) + ":" + String(left % 60).padStart(2, "0"); left -= 1; } };
    tick();
    const timer = left ? setInterval(tick, 1000) : null;
    pending.set(e.id, { card, timer });
    $("dock").appendChild(card); refreshTitle(); yes.focus({ preventScroll: true });
  }
  function renderList(id, items, fmt, emptyText) {
    const ul = $(id); ul.textContent = "";
    if (!items.length) { ul.appendChild(el("li", "muted", emptyText)); return; }
    items.forEach((it) => { const li = fmt(it); ul.appendChild(li); });
  }
  const checks = [];

  function handle(m) {
    switch (m.type) {
      case "ready":
        state.ready = true; state.retry = 0; state.limits = m.limits || {}; setConn("on", "connected · " + m.model);
        [...$("mode").options].forEach((o) => { o.disabled = !m.modes.includes(o.value); });
        if (!m.modes.includes($("mode").value)) $("mode").value = m.modes[m.modes.length - 1];
        if (!$("workspace").value) $("workspace").value = m.roots[0] || "";
        break;
      case "task_started": state.bubble = null; state.runMode = m.mode; state.prompt = 0; state.output = 0; setRunning(true); break;
      case "assistant_delta":
        if (!state.bubble) { state.bubble = add(el("div", "msg assistant")); state.bubble.dataset.raw = ""; }
        state.bubble.dataset.raw += m.text; renderText(state.bubble, state.bubble.dataset.raw); scroll(); break;
      case "assistant_message": if (!state.bubble && m.text) renderText(add(el("div", "msg assistant")), m.text); state.bubble = null; break;
      case "tool_started": state.bubble = null; toolCard(m); break;
      case "command_output": {
        const c = state.cards.get(m.id); if (!c) break;
        c.body.textContent += m.text; if (c.body.textContent.length > 20000) c.body.textContent = "…" + c.body.textContent.slice(-20000);
        c.body.scrollTop = c.body.scrollHeight; break;
      }
      case "tool_finished": {
        const c = state.cards.get(m.id); if (!c) break;
        c.card.dataset.state = m.ok ? "ok" : "fail";
        if (m.meta && m.meta.diff) renderDiff(c.body, m.meta.diff);
        else if (m.tool === "run_command" || m.tool === "run_tests") { if (!c.body.textContent) c.body.textContent = m.content; }
        else if (!m.ok) c.body.textContent = m.content;
        scroll(); break;
      }
      case "tool_denied": note("Blocked: " + (m.reason || ""), "warn"); break;
      case "approval_required": approvalCard(m); break;
      case "approval_resolved": closeApproval(m.id, pending.has(m.id) ? "Approval was resolved: " + (m.approved ? "approved" : "denied or timed out") : "", "warn"); break;
      case "todos_updated": renderList("todos", m.todos, (t) => el("li", t.status, t.content), "No plan yet"); break;
      case "verification": checks.push(m); renderList("checks", checks.slice(-6), (c) => el("li", c.ok ? "pass" : "fail", (c.ok ? "✓ " : "✗ ") + (c.command.length > 100 ? c.command.slice(0, 100) + "…" : c.command)), "Not run"); break;
      case "usage": {
        state.prompt += m.prompt_tokens || 0; state.output += m.completion_tokens || 0;
        const total = state.prompt + state.output, cap = state.limits.max_run_tokens;
        $("usage").textContent = total.toLocaleString() + " tokens" + (cap ? " of " + cap.toLocaleString() + " budget" : "") +
          "\nprompt " + state.prompt.toLocaleString() + " · output " + state.output.toLocaleString();
        break;
      }
      case "context_compacted": note("Context compacted (" + m.method + "): " + m.before_tokens + " → " + m.after_tokens + " tokens"); break;
      case "llm_retry": note("Model request failed (" + m.error.slice(0, 80) + "). Retrying in " + m.delay.toFixed(1) + "s…", "warn"); break;
      case "warning": note(m.message, "warn"); break;
      case "run_finished": {
        setRunning(false); state.bubble = null; [...pending.keys()].forEach((id) => closeApproval(id));
        const r = m.result; if (r.session_id) state.sessionId = r.session_id;
        if (r.files_modified) renderList("files", r.files_modified, (f) => el("li", "", f), "None");
        if (r.error) { const box = note("Run failed: " + r.error, "bad"); box.style.whiteSpace = "pre-wrap"; }
        else if (r.status === "error") note("Run failed with no error details. Check the terminal running `rx serve`.", "bad");
        const waited = r.approval_wait ? " (" + Math.round(r.approval_wait) + "s waiting for you)" : "";
        note(r.status + (r.iterations ? " · " + r.iterations + " steps · " + (r.duration || 0) + "s" + waited : ""), r.status === "completed" ? "" : "warn");
        if (r.status === "budget_exceeded") note("The run hit its token/time budget and stopped with a report. Continue in the same session to carry on, or raise RX_MAX_RUN_TOKENS / RX_MAX_RUN_SECONDS.", "warn");
        if (r.verification && r.files_modified && r.files_modified.length && !r.verification.ran) note("Changes were not verified (no tests/checks were run).", "warn");
        break;
      }
      case "undo_result": note(m.ok ? "Restored " + m.restored.length + " file(s); removed " + m.deleted.length + " new file(s)." : "Undo failed: " + m.error, m.ok ? "" : "bad"); break;
      case "error":
        if (m.code === "unauthorized") { sessionStorage.removeItem("rx.token"); state.retry = -1; $("tokenDialog").showModal(); }
        else { note(m.message, "bad"); if (m.code !== "busy") setRunning(false); }
        break;
      default: break;
    }
  }

  // ---- UI wiring ------------------------------------------------------------------------------------
  function run() {
    const task = $("task").value.trim(); if (!task || !state.ready || state.running) return;
    add(el("div", "msg user", task)); $("task").value = ""; checks.length = 0; state.cards.clear();
    send({ type: "run", task, workspace: $("workspace").value.trim() || undefined, mode: $("mode").value, session_id: state.sessionId || undefined });
  }
  $("composer").addEventListener("submit", (e) => { e.preventDefault(); run(); });
  $("task").addEventListener("keydown", (e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); run(); } });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape" && state.running) send({ type: "cancel" }); });
  $("stop").onclick = () => send({ type: "cancel" });
  $("undo").onclick = () => { if (state.running) return; if (confirm("Restore the workspace to how it was before the last run?")) send({ type: "undo", workspace: $("workspace").value.trim() || undefined }); };
  $("newSession").onclick = () => { if (state.running) return; state.sessionId = null; log.textContent = ""; log.appendChild(el("div", "note", "New session")); renderList("todos", [], () => null, "No plan yet"); renderList("files", [], () => null, "None"); };
  $("tokenForm").addEventListener("submit", () => { const v = $("tokenInput").value.trim(); if (v) { sessionStorage.setItem("rx.token", v); state.retry = 0; connect(); } });
  connect();
})();
