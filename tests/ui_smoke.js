const fs = require("fs"), vm = require("vm");
function mkEl(tag) {
  const e = { tag, children: [], dataset: {}, style: {}, _text: "", className: "", hidden: false, disabled: false, value: "",
    classList: { add(c) { e.className += " " + c; } }, attrs: {}, handlers: {},
    appendChild(c) { c.parent = e; e.children.push(c); return c; }, append(...c) { c.forEach((x) => { x.parent = e; e.children.push(x); }); },
    remove() { e.removed = true; if (e.parent) e.parent.children = e.parent.children.filter((x) => x !== e); }, setAttribute(k, v) { e.attrs[k] = v; }, focus() {}, showModal() { e.modal = true; },
    addEventListener(t, f) { e.handlers[t] = f; }, querySelector(sel) { const want = sel.slice(1); const find = (n) => { for (const c of n.children) { if ((c.className || "").split(" ").includes(want)) return c; const r = find(c); if (r) return r; } }; return find(e); },
    scrollHeight: 0, scrollTop: 0, clientHeight: 0, options: [] };
  Object.defineProperty(e, "textContent", { get() { return e._text + e.children.map((c) => c.textContent || "").join(""); }, set(v) { e._text = v; e.children = []; } });
  return e;
}
const ids = {};
const document = { getElementById: (id) => (ids[id] ||= mkEl(id)), createElement: mkEl, createTextNode: (t) => ({ textContent: t, children: [] }), addEventListener() {} };
ids.mode = Object.assign(mkEl("select"), { value: "ask", options: [{ value: "plan" }, { value: "ask" }, { value: "auto_edit" }, { value: "auto" }] });
const sent = []; let ws;
class WS { constructor(u) { ws = this; this.url = u; this.readyState = 1; setTimeout(() => this.onopen && this.onopen(), 0); } send(s) { sent.push(JSON.parse(s)); } }
const store = { "rx.token": "tok" };
const ctx = { document, WebSocket: WS, location: { hash: "", pathname: "/ui", protocol: "http:", host: "127.0.0.1:8000" }, history: { replaceState() {} },
  sessionStorage: { getItem: (k) => store[k] || null, setItem: (k, v) => (store[k] = v), removeItem: (k) => delete store[k] },
  URLSearchParams, setTimeout, setInterval, clearInterval, console, confirm: () => true };
ctx.window = ctx; vm.createContext(ctx);
vm.runInContext(fs.readFileSync(require("path").join(__dirname, "../src/rx_agent/web/app.js"), "utf8"), ctx);
const feed = (m) => ws.onmessage({ data: JSON.stringify(m) });
setTimeout(() => {
  const assert = require("assert");
  assert.deepStrictEqual(sent[0], { type: "auth", token: "tok" });
  feed({ type: "ready", modes: ["plan", "ask"], roots: ["/proj"], model: "m", version: "1", limits: { max_run_tokens: 400000 } });
  assert.strictEqual(ids.workspace.value, "/proj");
  assert.strictEqual(ids.conn.dataset.state, "on");
  ids.task.value = "fix it"; ids.composer.handlers.submit({ preventDefault() {} });
  assert.strictEqual(sent[1].type, "run"); assert.strictEqual(sent[1].mode, "ask");
  feed({ type: "task_started", mode: "ask" }); assert.strictEqual(ids.go.hidden, true); assert.strictEqual(ids.stop.hidden, false);
  feed({ type: "assistant_delta", text: "Looking " }); feed({ type: "assistant_delta", text: "at it ```py\nx=1\n```" });
  feed({ type: "tool_started", id: "c1", tool: "edit_file", summary: "edit a.py" });
  feed({ type: "approval_required", id: "ap1", tool: "edit_file", summary: "edit a.py", reason: "Modify files", risk: "normal", preview: "--- a/a.py\n+++ b/a.py\n@@ -1 +1 @@\n-x\n+y\n", can_remember: true });
  // approvals must be pinned in the dock (outside the scrolling log), never inside it
  assert.strictEqual(ids.log.children.some((c) => (c.className || "").includes("approval")), false);
  assert.strictEqual(ids.dock.children.length, 1);
  assert.ok(ctx.document.title.includes("Approval needed"));
  const card = ids.dock.children[0];
  const buttons = card.children.find((c) => c.className === "actions").children;
  buttons[0].onclick(); // Approve
  assert.strictEqual(ids.dock.children.length, 0);
  assert.ok(!ctx.document.title.includes("Approval needed"));
  assert.deepStrictEqual(sent[2], { type: "approval_response", id: "ap1", approved: true, remember: false });
  feed({ type: "approval_resolved", id: "ap1", approved: true });   // late echo from the server is harmless
  feed({ type: "tool_finished", id: "c1", tool: "edit_file", ok: true, content: "Edited", meta: { diff: "-x\n+y" } });
  // server-side timeout: the card must disappear and the user must be told
  feed({ type: "approval_required", id: "ap2", tool: "run_command", summary: "$ make", reason: "r", risk: "normal", preview: null, can_remember: false, timeout: 600 });
  assert.strictEqual(ids.dock.children.length, 1);
  assert.ok(ids.dock.children[0].textContent.includes("auto-denies in 10:00"));
  feed({ type: "approval_resolved", id: "ap2", approved: false });
  assert.strictEqual(ids.dock.children.length, 0);
  assert.ok(ids.log.textContent.includes("timed out"));
  assert.strictEqual(ids.mode.disabled, true);   // mode is locked while a run is active
  feed({ type: "todos_updated", todos: [{ content: "step", status: "in_progress" }] });
  feed({ type: "verification", command: "pytest", ok: true, exit_code: 0 });
  feed({ type: "usage", prompt_tokens: 1000, completion_tokens: 234, total: 1234 });
  assert.ok(ids.usage.textContent.includes("1,234 tokens"), ids.usage.textContent);
  assert.ok(ids.usage.textContent.includes("prompt 1,000 · output 234"));
  feed({ type: "run_finished", result: { status: "completed", session_id: "s1", files_modified: ["a.py"], iterations: 3, duration: 1.2, verification: { ran: true } } });
  assert.strictEqual(ids.go.hidden, false); assert.strictEqual(ids.mode.disabled, false);
  ids.task.value = "again"; ids.composer.handlers.submit({ preventDefault() {} });
  assert.strictEqual(sent[3].session_id, "s1");
  // a failed run must show WHY (v1.0.2 showed only "error · 1 steps")
  feed({ type: "run_finished", result: { status: "error", error: "HTTP 402 from model API: Insufficient credits", session_id: "s1", files_modified: [], iterations: 1, duration: 0.3 } });
  assert.ok(ids.log.textContent.includes("Run failed: HTTP 402 from model API: Insufficient credits"));
  feed({ type: "run_finished", result: { status: "error", session_id: "s1", files_modified: [], iterations: 1, duration: 0.3 } });
  assert.ok(ids.log.textContent.includes("no error details"));
  feed({ type: "error", code: "unauthorized", message: "x" }); assert.ok(ids.tokenDialog.modal);
  // hostile model output must stay inert text
  feed({ type: "assistant_delta", text: "<img src=x onerror=alert(1)>" });
  console.log("UI smoke test passed:", sent.length, "messages sent");
  process.exit(0);
}, 20);
