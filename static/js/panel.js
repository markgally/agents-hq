/* AGENTS HQ - agent workspace panel: Chat, Configure, Tasks, Outputs, History.
 *
 * One panel, opened from a canvas card, an office character, a Bot Log entry or a result. Everything shown
 * here comes from the server; nothing is simulated. Text from models, tools and files is rendered through
 * AHQ.markdown or textContent only.
 */
(function () {
  "use strict";
  var AHQ = window.AHQ = window.AHQ || {};
  var U = AHQ.util, el = U.el, $ = U.$, api = AHQ.api, attempt = AHQ.attempt, store = AHQ.store, S = store.state, MD = AHQ.markdown;

  var TABS = [["chat", "Chat"], ["configure", "Configure"], ["tasks", "Tasks"], ["outputs", "Outputs"], ["history", "History"]];
  var panel, openId = null, tab = "chat", big = false;
  var head = {}, body = null, tabBtns = {};
  var chat = null;       /* state of the open chat view */
  var drafts = {};       /* agent id -> unsent text, kept while the page is open */
  var view = {};         /* per-tab transient state */

  function agent() { return openId ? store.agent(openId) : null; }
  function active(rt) { return rt && ["starting", "running", "tool", "awaiting_approval", "cancelling"].indexOf(rt.status) > -1; }
  function codexReady() { return S.connection.state === "connected" || S.connection.state === "rate_limited"; }

  /* ------------------------------------------------------------ frame */
  function buildFrame() {
    panel = $("panel");
    head.ic = el("div", { class: "ic" });
    head.name = el("b");
    head.role = el("span");
    head.pill = el("span", { class: "pill" });
    head.big = el("button", { type: "button", class: "rb", title: "Expand", "aria-label": "Expand or shrink the workspace", text: "\u2922", onclick: function () { setBig(!big); } });
    head.close = el("button", { type: "button", class: "rb", title: "Close", "aria-label": "Close", text: "\u2715", onclick: close });
    var tabs = el("div", { class: "tabs", role: "tablist" });
    TABS.forEach(function (t) {
      tabBtns[t[0]] = el("button", { type: "button", role: "tab", dataset: { tab: t[0] }, onclick: function () { show(t[0]); } }, t[1]);
      tabs.appendChild(tabBtns[t[0]]);
    });
    body = el("div", { class: "pbody" });
    U.append(panel, [el("div", { class: "phx" }, head.ic, el("div", { class: "ti" }, head.name, head.role), head.pill, head.big, head.close), tabs, body]);
    $("panelShade").addEventListener("click", function () { setBig(false); });
  }

  function renderHead() {
    var a = agent();
    if (!a) return;
    var rt = a.runtime || {};
    U.clear(head.ic).appendChild(U.face(a.sprite_key, AHQ.board.visual(rt.status), a.display_name));
    head.name.textContent = a.display_name;
    head.role.textContent = (a.role || "Unassigned") + (rt.detail ? " \u00b7 " + rt.detail : rt.activity_label ? " \u00b7 " + rt.activity_label : "");
    head.pill.className = "pill " + U.statusClass(rt.status);
    head.pill.textContent = U.statusLabel(rt.status);
    panel.classList.toggle("busy", active(rt));
    var n = rt.pending_approvals || 0;
    U.clear(tabBtns.chat).appendChild(document.createTextNode("Chat"));
    if (n) tabBtns.chat.appendChild(el("span", { class: "n", text: String(n) }));
  }

  function position() {
    if (!openId || big) return;
    var board = $("board"), a = AHQ.board.anchor(openId), bw = board.clientWidth, bh = board.clientHeight;
    var w = Math.min(500, bw - 16), h = Math.min(580, bh - 16);
    var left = Math.max(8, Math.min(a.x + a.w / 2 - w / 2, bw - w - 8));
    var top = a.office ? a.y - h / 2 : a.y + a.h + 12;
    if (a.office) left = a.x > bw / 2 ? Math.max(8, a.x - w - 40) : Math.min(bw - w - 8, a.x + 40);
    top = Math.max(8, Math.min(top, bh - h - 8));
    panel.style.left = left + "px"; panel.style.top = top + "px"; panel.style.height = h + "px";
  }
  function setBig(on) {
    big = !!on;
    panel.classList.toggle("big", big);
    $("panelShade").hidden = !big;
    head.big.textContent = big ? "\u2921" : "\u2922";
    head.big.title = big ? "Shrink" : "Expand";
    if (!big) position();
    if (chat) scrollDown(true);
  }

  function open(id, which) {
    if (!store.agent(id)) return;
    if (openId !== id) { saveDraft(); openId = id; chat = null; view = {}; }
    panel.classList.add("on");
    AHQ.board.select(id);
    renderHead();
    position();
    show(which || (openId === id && panel.dataset.tab) || "chat", true);
    AHQ.store.emit("panel", openId);
  }
  function close() {
    if (!openId) return;
    saveDraft();
    panel.classList.remove("on", "busy");
    setBig(false);
    openId = null; chat = null;
    AHQ.board.select(null);
    AHQ.store.emit("panel", null);
  }
  function toggle(id) { if (openId === id) close(); else open(id, "chat"); }

  function show(which, force) {
    if (!openId) return;
    if (tab === "chat" && which !== "chat") saveDraft();
    if (tab === which && !force && body.firstChild) return;
    tab = which;
    panel.dataset.tab = which;
    TABS.forEach(function (t) { tabBtns[t[0]].setAttribute("aria-selected", t[0] === which ? "true" : "false"); });
    U.clear(body);
    body.className = "pbody" + (which === "chat" ? " chat" : "");
    if (which !== "chat") chat = null;
    ({ chat: showChat, configure: showConfigure, tasks: showTasks, outputs: showOutputs, history: showHistory })[which]();
  }
  function loading(text) { return el("div", { class: "mute", text: text || "Loading\u2026" }); }
  function failed(e, retry) {
    return el("div", { class: "note bad" }, (e && e.message) || "Could not load this.", " ",
      retry ? el("button", { type: "button", class: "mini", text: "Try again", onclick: retry }) : null);
  }

  /* ============================================================ Chat */
  function saveDraft() { if (chat && chat.input && openId) drafts[openId] = chat.input.value; }

  function showChat() {
    var id = openId, a = agent();
    var c = chat = { id: id, els: {}, msgs: {}, attachments: [], approvals: el("div"), unknown: el("div"), oldest: null };
    c.thread = el("div", { class: "thr" });
    c.list = el("div", { id: "msgs", "aria-live": "polite" });
    c.more = el("button", { type: "button", class: "mini", style: "align-self:center", hidden: true, text: "Load earlier messages", onclick: loadEarlier });
    c.input = el("textarea", { id: "chatInput", rows: "2", placeholder: "Message " + a.display_name + "\u2026  (Enter to send, Shift+Enter for a new line)", "aria-label": "Message" });
    c.input.value = drafts[id] || "";
    c.send = el("button", { type: "button", class: "pri", id: "chatSend", text: "Send", onclick: function () { send(false); } });
    c.steer = el("button", { type: "button", id: "chatSteer", hidden: true, title: "Send this text into the task that is running now, instead of queueing it", text: "Steer Current Task", onclick: function () { send(true); } });
    c.stop = el("button", { type: "button", class: "danger", id: "chatStop", hidden: true, text: "Stop", onclick: stop });
    c.attach = el("button", { type: "button", id: "chatAttach", title: "Refer to a file in this agent's working folder", text: "Attach file", onclick: togglePicker });
    c.chips = el("div", { class: "chips" });
    c.picker = el("div", { class: "picker", hidden: true });
    c.status = el("div", { class: "statusline", id: "chatStatus" });
    c.input.addEventListener("keydown", function (e) {
      if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); send(false); }
    });
    c.input.addEventListener("input", grow);
    U.append(body, el("div", { class: "chatwrap" }, c.thread, c.list,
      el("div", { class: "composer" }, c.picker, c.chips, c.input,
        el("div", { class: "cbar2" }, c.send, c.steer, c.stop, c.attach, el("span", { class: "grow" }), c.status))));
    c.list.appendChild(loading("Loading the conversation\u2026"));
    renderThread();
    renderComposer();
    loadMessages();
    setTimeout(function () { if (chat === c) { grow(); c.input.focus(); } }, 30);
  }
  function grow() {
    if (!chat) return;
    chat.input.style.height = "auto";
    chat.input.style.height = Math.min(180, chat.input.scrollHeight + 2) + "px";
  }

  function loadMessages() {
    var c = chat, id = openId;
    api.get("/api/agents/" + id + "/messages?limit=200").then(function (r) {
      if (chat !== c) return;
      var a = agent();
      if (a) { a.thread = r.thread; a.runtime = r.runtime; }
      U.clear(c.list);
      c.els = {}; c.msgs = {};
      c.list.appendChild(c.more);
      c.more.hidden = r.messages.length < 200;
      c.oldest = r.messages.length ? r.messages[0].seq : null;
      if (!r.messages.length) c.list.appendChild(c.emptyNote = el("div", { class: "mute", style: "margin:auto;text-align:center;max-width:300px",
        text: "No messages yet. Say hello, or give " + (a ? a.display_name : "this agent") + " something to do." }));
      r.messages.forEach(function (m) { upsert(m, true); });
      c.list.appendChild(c.unknown);
      c.list.appendChild(c.approvals);
      renderApprovals();
      renderUnknown();
      renderThread(); renderComposer(); renderHead();
      scrollDown(true);
    }, function (e) {
      if (chat !== c) return;
      U.clear(c.list).appendChild(failed(e, loadMessages));
    });
  }
  function loadEarlier() {
    var c = chat;
    if (!c || !c.oldest) return;
    api.get("/api/agents/" + c.id + "/messages?limit=200&before=" + c.oldest).then(function (r) {
      if (chat !== c) return;
      var anchorEl = c.more.nextSibling, h0 = c.list.scrollHeight;
      r.messages.forEach(function (m) {
        if (c.els[m.id]) return;
        c.msgs[m.id] = m;
        c.els[m.id] = messageEl(m);
        c.list.insertBefore(c.els[m.id], anchorEl);
      });
      c.oldest = r.messages.length ? r.messages[0].seq : c.oldest;
      c.more.hidden = r.messages.length < 200;
      c.list.scrollTop += c.list.scrollHeight - h0;
    }, function (e) { U.toast(e.message, true); });
  }

  function nearBottom() { var l = chat.list; return l.scrollHeight - l.scrollTop - l.clientHeight < 90; }
  function scrollDown(force) { if (chat && (force || chat.stick)) chat.list.scrollTop = chat.list.scrollHeight; }

  function upsert(m, initial) {
    var c = chat;
    if (!c || m.agent_id !== c.id) return;
    c.stick = initial || nearBottom();
    if (c.emptyNote) { c.emptyNote.remove(); c.emptyNote = null; }
    var old = c.els[m.id], node = messageEl(m);
    if (old && old.tagName === "DIV" && old.querySelector("details[open]")) { var d = node.querySelector("details"); if (d) d.open = true; }
    c.msgs[m.id] = m;
    c.els[m.id] = node;
    if (old) c.list.replaceChild(node, old);
    else c.list.insertBefore(node, c.unknown.parentNode === c.list ? c.unknown : null);
    if (!initial) scrollDown();
  }

  function metaLine(m, extra) {
    var line = el("div", { class: "meta" }, el("span", { title: U.fullDateTime(m.created_at), text: U.time(m.created_at) }));
    U.append(line, extra);
    return line;
  }
  function tstat(status) {
    var map = { completed: ["done", "ok"], inProgress: ["running", "run"], failed: ["failed", "bad"], declined: ["declined", "bad"], interrupted: ["stopped", "bad"] };
    var s = map[status] || [status || "", ""];
    return s[0] ? el("span", { class: "tstat " + s[1], text: s[0] }) : null;
  }

  function messageEl(m) {
    var meta = m.meta || {}, node;
    if (m.role === "user") {
      var tags = [];
      if (m.status === "queued") tags.push(el("span", { class: "tag", text: "Queued" }));
      if (m.status === "cancelled") tags.push(el("span", { class: "tag c", text: "Not sent (cancelled)" }));
      if (meta.steer) tags.push(el("span", { class: "tag c", text: "Steered into the running task" }));
      (meta.attachments || []).forEach(function (f) { tags.push(el("span", { class: "tag c", text: "\uD83D\uDCCE " + (f.name || f) })); });
      if (meta.kind === "task" || meta.task_title) tags.push(el("span", { class: "tag c", text: "Assignment" }));
      node = el("div", { class: "m user", dataset: { id: m.id } }, MD.plain(m.content), metaLine(m, tags));
    } else if (m.role === "assistant") {
      var streaming = m.status === "streaming";
      node = el("div", { class: "m assistant" + (streaming ? " streaming" : ""), dataset: { id: m.id } });
      node.appendChild(streaming ? MD.plain(m.content) : MD.render(m.content));
      if (!streaming) {
        var text = m.content;
        node.appendChild(metaLine(m, [meta.phase === "commentary" ? el("span", { class: "tag c", text: "Progress note" }) : null,
          m.status === "interrupted" ? el("span", { class: "tag c", text: "Stopped before finishing" }) : null,
          el("button", { type: "button", class: "mini", text: "Copy", onclick: function () { U.copy(text); } })]));
      }
    } else if (m.role === "tool") {
      node = toolEl(m);
    } else if (m.role === "error") {
      node = el("div", { class: "m error", dataset: { id: m.id } }, el("b", { text: "Error: " }), m.content, metaLine(m));
    } else {
      node = el("div", { class: "m notice", dataset: { id: m.id }, text: m.content });
    }
    return node;
  }

  function toolEl(m) {
    var meta = m.meta || {}, title, detail, bodyNodes = [];
    if (m.kind === "command") {
      title = "Command"; detail = meta.command || "";
      if (meta.cwd) bodyNodes.push(el("div", { class: "mute", text: "In: " + meta.cwd }));
      bodyNodes.push(el("pre", { class: "out", text: m.content || (m.status === "streaming" ? "" : "(no output)") }));
      if (meta.exit_code != null) bodyNodes.push(el("div", { class: "mute", text: "Exit code " + meta.exit_code + (meta.duration_ms != null ? " \u00b7 " + meta.duration_ms + " ms" : "") }));
    } else if (m.kind === "file_change") {
      var files = meta.files || [];
      title = "File changes"; detail = files.length === 1 ? files[0].path : files.length + " files";
      bodyNodes.push(el("ul", null, files.map(function (f) { return el("li", null, el("code", { text: f.path || "" }), f.kind ? " (" + f.kind + ")" : ""); })));
      if (m.content) bodyNodes.push(el("pre", { class: "out", text: m.content }));
    } else if (m.kind === "search") {
      title = "Web search"; detail = meta.query || "";
    } else {
      title = meta.server ? "Integration" : "Tool"; detail = meta.server ? meta.server + " \u00b7 " + (meta.tool || "") : (meta.tool || "");
      if (meta.error) bodyNodes.push(el("div", { class: "err", text: meta.error }));
      if (m.content) bodyNodes.push(el("pre", { class: "out", text: m.content }));
    }
    var summary = el("summary", null, el("b", { text: title }), el("code", { text: detail, title: detail }), tstat(m.status === "streaming" ? "inProgress" : meta.status));
    return el("div", { class: "m tool", dataset: { id: m.id } }, el("details", null, summary, bodyNodes.length ? bodyNodes : el("div", { class: "mute", text: "No further details." })));
  }

  function onDelta(ev) {
    var c = chat, p = ev.payload || {};
    if (!c || ev.agent_id !== c.id) return;
    var node = c.els[p.message_id], m = c.msgs[p.message_id];
    if (!node || !m) return;
    c.stick = nearBottom();
    m.content = (m.content || "") + p.delta;
    var target = p.output ? node.querySelector("pre.out") : node.querySelector(".md");
    if (target) target.textContent = m.content;
    scrollDown();
  }

  /* ---- approvals shown inside the chat ---- */
  function approvalCard(ap) {
    var d = ap.request_details || {}, a = store.agent(ap.agent_id), who = a ? a.display_name : "The agent";
    var titles = { command: who + " wants to run a command", command_legacy: who + " wants to run a command", file_change: who + " wants to change files",
      file_change_legacy: who + " wants to change files", permissions: who + " asks for extra permissions", question: who + " has a question for you",
      tool: who + " wants to use an integration", handoff: "Hand work to " + who + "?" };
    var card = el("div", { class: "apc", dataset: { approval: ap.id } }, el("b", { text: titles[ap.approval_type] || who + " needs your approval" }));
    if (d.reason) card.appendChild(el("p", { text: d.reason }));
    if (d.command) card.appendChild(el("pre", { text: d.command }));
    var facts = [];
    if (d.cwd) facts.push(["Folder", d.cwd]);
    if (d.network && d.network !== true) facts.push(["Network", String(d.network)]);
    if (d.network === true) facts.push(["Network", "access requested"]);
    if (d.grant_root) facts.push(["Write access to", d.grant_root]);
    if (d.files && d.files.length) facts.push(["Files", d.files.join(", ")]);
    if (d.read && d.read.length) facts.push(["Read", d.read.join(", ")]);
    if (d.write && d.write.length) facts.push(["Write", d.write.join(", ")]);
    if (d.server) facts.push(["Integration", d.server]);
    if (d.message) facts.push(["Message", d.message]);
    if (d.url) facts.push(["Link (not opened)", d.url]);
    if (d.source) facts.push(["From", d.source]);
    if (facts.length) card.appendChild(el("dl", { class: "kv", style: "margin-bottom:10px" }, facts.map(function (f) { return [el("dt", { text: f[0] }), el("dd", { text: f[1] })]; })));

    var answers = {};
    (d.questions || []).forEach(function (q) {
      var box = el("div", { class: "f" }, el("span", { text: q.header || "Question" }), el("small", { text: q.question || "" }));
      if (q.options && q.options.length) {
        var sel = el("select", null, el("option", { value: "", text: "Choose\u2026" }), q.options.map(function (o) { return el("option", { value: o.label, text: o.label + (o.description ? " - " + o.description : "") }); }));
        sel.addEventListener("change", function () { answers[q.id] = sel.value; });
        box.appendChild(sel);
      }
      if (!q.options || !q.options.length || q.allow_other) {
        var inp = el("input", { type: q.secret ? "password" : "text", autocomplete: "off", placeholder: q.options && q.options.length ? "Or type another answer" : "Your answer" });
        inp.addEventListener("input", function () { if (inp.value) answers[q.id] = inp.value; });
        box.appendChild(inp);
      }
      card.appendChild(box);
    });

    var row = el("div", { class: "row" });
    var respond = function (decision) {
      [].forEach.call(row.querySelectorAll("button"), function (b) { b.disabled = true; });
      api.post("/api/approvals/" + ap.id + "/respond", { decision: decision, answers: answers }).then(function () {
        U.toast({ accept: "Approved.", accept_session: "Approved for this session.", decline: "Declined.", cancel: "Task cancelled." }[decision]);
      }, function (e) {
        U.toast(e.message, true);
        [].forEach.call(row.querySelectorAll("button"), function (b) { b.disabled = false; });
        store.refreshSoon();
      });
    };
    var isQuestion = ap.approval_type === "question";
    row.appendChild(el("button", { type: "button", class: "pri", dataset: { decision: "accept" }, text: isQuestion ? "Send answer" : "Approve once", onclick: function () { respond("accept"); } }));
    if (["command", "command_legacy", "file_change"].indexOf(ap.approval_type) > -1)
      row.appendChild(el("button", { type: "button", dataset: { decision: "accept_session" }, title: "Allow the same kind of action for the rest of this Codex session", text: "Approve for this session", onclick: function () { respond("accept_session"); } }));
    row.appendChild(el("button", { type: "button", dataset: { decision: "decline" }, text: "Decline", onclick: function () { respond("decline"); } }));
    if (ap.approval_type !== "handoff")
      row.appendChild(el("button", { type: "button", class: "danger", dataset: { decision: "cancel" }, text: "Decline and stop the task", onclick: function () { respond("cancel"); } }));
    card.appendChild(row);
    card.appendChild(el("div", { class: "mute", style: "margin-top:6px", text: "Asked " + U.dateTime(ap.requested_at) + ". Nothing happens until you choose." }));
    return card;
  }
  function renderApprovals() {
    if (!chat) return;
    var mine = S.approvals.filter(function (x) { return x.agent_id === chat.id; });
    var stick = nearBottom();
    U.clear(chat.approvals);
    chat.approvals.style.cssText = mine.length ? "display:grid;gap:10px" : "display:none";
    mine.forEach(function (ap) { chat.approvals.appendChild(approvalCard(ap)); });
    if (stick) scrollDown(true);
  }
  function renderUnknown() {
    if (!chat) return;
    var a = agent(), rt = a && a.runtime;
    U.clear(chat.unknown);
    if (!rt || rt.status !== "unknown") return;
    chat.unknown.appendChild(el("div", { class: "note warn" },
      el("b", { text: "The outcome of the last task is unknown. " }),
      (rt.detail || "The connection to Codex was lost while it was running.") + " AGENTS HQ did not re-run it, because it may already have made changes. Check the result, then choose.",
      el("div", { class: "bar" },
        el("button", { type: "button", text: "Mark as reviewed", onclick: function () { attempt(api.post("/api/agents/" + chat.id + "/acknowledge"), "Marked as reviewed."); } }),
        el("button", { type: "button", text: "Check the Codex thread", onclick: function () { attempt(api.post("/api/agents/" + chat.id + "/thread/sync"), "Thread checked."); } }),
        rt.run && rt.run.kind === "task" || (rt.last_run && rt.last_run.kind === "task") ? el("button", { type: "button", class: "warn", text: "Retry the task", onclick: retryTask }) : null)));
  }

  function renderThread() {
    if (!chat) return;
    var a = agent(), t = (a && a.thread) || {}, bar = chat.thread;
    U.clear(bar);
    bar.className = "thr" + (t.status === "unavailable" ? " bad" : "");
    if (t.provider_thread_id) {
      bar.appendChild(el("span", { text: t.status === "unavailable" ? "Thread unavailable:" : "Codex thread:" }));
      bar.appendChild(el("div", { class: "idline grow" }, el("code", { id: "threadId", title: t.provider_thread_id, text: t.provider_thread_id })));
      bar.appendChild(el("button", { type: "button", class: "mini", text: "Copy", onclick: function () { U.copy(t.provider_thread_id); } }));
      if (t.status === "unavailable") bar.appendChild(el("button", { type: "button", class: "mini", title: t.detail || "", text: "Fix in Codex Integration", onclick: function () { AHQ.dialogs.codex(); } }));
    } else {
      bar.appendChild(el("span", { id: "threadId", text: t.status === "archived" ? "No active thread. A new one is created with the next message."
        : "No Codex thread yet. One is created with the first message and then reused." }));
    }
  }

  function renderComposer() {
    var c = chat;
    if (!c) return;
    var a = agent(), rt = (a && a.runtime) || {}, working = active(rt), busy = working || rt.status === "queued";
    var canSteer = !!(S.connection.capabilities && S.connection.capabilities["turn/steer"]) && (rt.status === "running" || rt.status === "tool");
    c.stop.hidden = !busy;
    c.stop.textContent = working ? "Stop" : "Cancel queued";
    c.stop.disabled = rt.status === "cancelling";
    c.steer.hidden = !canSteer;
    c.send.textContent = busy ? "Queue follow-up" : "Send";
    var msg = "";
    if (!codexReady()) {
      msg = S.connection.state === "auth_required" ? "Codex needs you to sign in. Open Codex Integration." : S.connection.state === "connecting" ? "Connecting to Codex\u2026" : "Codex is not connected. Open Codex Integration to connect.";
    } else if (!a.enabled) msg = "This agent is disabled in Configure.";
    else if (rt.status === "awaiting_approval") msg = "Waiting for your approval above.";
    else if (rt.status === "cancelling") msg = "Stopping\u2026";
    else if (working) msg = (rt.activity_label || rt.detail || "Working") + (rt.queued ? " \u00b7 " + rt.queued + " queued" : "");
    else if (rt.status === "queued") msg = rt.detail || "Waiting for a free slot.";
    else if (S.connection.state === "rate_limited") msg = "Codex reports a usage limit. A message may fail until it resets.";
    c.status.textContent = msg;
    c.send.disabled = !codexReady() || !a.enabled || c.sending;
    U.clear(c.chips);
    c.attachments.forEach(function (f, i) {
      c.chips.appendChild(el("span", { class: "chip" }, el("span", { text: "\uD83D\uDCCE " + f }),
        el("button", { type: "button", "aria-label": "Remove " + f, text: "\u2715", onclick: function () { c.attachments.splice(i, 1); renderComposer(); } })));
    });
  }

  function send(steer) {
    var c = chat;
    if (!c || c.sending) return;
    var text = c.input.value.trim();
    if (!text) { c.input.focus(); return; }
    if (!codexReady()) { U.toast("Codex is not connected yet. Open Codex Integration.", true); return; }
    c.sending = true;
    c.key = c.key || U.uid();      /* the same key is reused if this exact send is retried, so it cannot run twice */
    renderComposer();
    var bodyData = steer ? { text: text, mode: "steer" } : { text: text, idempotency_key: c.key, attachments: c.attachments.slice() };
    api.post("/api/agents/" + c.id + "/messages", bodyData).then(function (r) {
      c.sending = false; c.key = null;
      if (chat !== c) return;
      c.input.value = ""; drafts[c.id] = ""; c.attachments = []; grow();
      if (r.runtime) { var a = agent(); if (a) a.runtime = r.runtime; }
      if (r.message) upsert(r.message);
      renderComposer(); renderHead();
      c.input.focus();
    }, function (e) {
      c.sending = false;
      if (e.status && e.status < 500 && e.code !== "offline") c.key = null;
      if (chat === c) renderComposer();
      U.toast(e.message, true);
    });
  }
  function stop() {
    var c = chat; if (!c) return;
    c.stop.disabled = true;
    api.post("/api/agents/" + c.id + "/interrupt", {}).then(function () { U.toast("Stop requested."); },
      function (e) { U.toast(e.message, true); if (chat === c) renderComposer(); });
  }

  function togglePicker() {
    var c = chat; if (!c) return;
    c.picker.hidden = !c.picker.hidden;
    if (c.picker.hidden) return;
    U.clear(c.picker);
    var q = el("input", { type: "text", placeholder: "Search files in the working folder", style: "width:100%", "aria-label": "Search files" });
    var list = el("ul"), base = el("div", { class: "mute" });
    var load = U.debounce(function () {
      api.get("/api/agents/" + c.id + "/files?q=" + encodeURIComponent(q.value)).then(function (r) {
        if (chat !== c) return;
        base.textContent = r.base + (r.truncated ? " (first 300 matches)" : "");
        U.clear(list);
        if (!r.files.length) list.appendChild(el("li", { class: "mute", text: "No files found." }));
        r.files.forEach(function (f) {
          list.appendChild(el("li", null, el("button", { type: "button", text: f, onclick: function () {
            if (c.attachments.indexOf(f) < 0 && c.attachments.length < 8) c.attachments.push(f);
            else if (c.attachments.length >= 8) U.toast("Attach at most 8 files.", true);
            c.picker.hidden = true; renderComposer(); c.input.focus();
          } })));
        });
      }, function (e) { U.clear(list).appendChild(el("li", { class: "err", text: e.message })); });
    }, 200);
    q.addEventListener("input", load);
    U.append(c.picker, [q, base, list, el("div", { class: "mute", text: "The file is not uploaded anywhere. Codex reads it from this folder." })]);
    load(); q.focus();
  }

  /* ============================================================ Configure */
  function field(label, control, help) { return el("label", { class: "f" }, el("span", { text: label }), control, help ? el("small", { text: help }) : null); }
  function input(value, attrs) { var i = el("input", Object.assign({ type: "text" }, attrs || {})); i.value = value == null ? "" : value; return i; }
  function area(value, rows) { var t = el("textarea", { rows: String(rows || 3) }); t.value = value == null ? "" : value; return t; }
  function select(options, value) {
    var s = el("select");
    options.forEach(function (o) { s.appendChild(el("option", { value: o[0], text: o[1] })); });
    s.value = value == null ? "" : value;
    return s;
  }
  function checkFolderBtn(inputEl, out) {
    return el("button", { type: "button", class: "mini", text: "Check folder", onclick: function () {
      if (!inputEl.value.trim()) { out.textContent = "Empty: the default folder is used."; out.className = "fhelp"; return; }
      api.post("/api/settings/check-folder", { path: inputEl.value.trim() }).then(function (r) {
        var f = r.folder;
        out.className = "fhelp";
        out.textContent = !f.exists ? "This folder does not exist." : !f.inside_permitted ? "Outside the permitted folders. Add it under Settings first."
          : f.readable && f.writable ? "OK: exists, readable and writable." : f.readable ? "Readable, but not writable." : "Not readable.";
      }, function (e) { out.textContent = e.message; out.className = "err"; });
    } });
  }

  function showConfigure() {
    var id = openId, holder = body;
    holder.appendChild(loading());
    Promise.all([api.get("/api/agents/" + id), api.get("/api/connectors").catch(function () { return null; })]).then(function (res) {
      if (openId !== id || tab !== "configure") return;
      var a = res[0].agent, conn = res[1];
      U.clear(holder);
      var models = S.connection.models || [];
      var f = {
        name: input(a.display_name, { maxlength: "40", id: "cfgName" }),
        role: input(a.role === "Unassigned" ? "" : a.role, { maxlength: "80", placeholder: "Unassigned", id: "cfgRole" }),
        description: area(a.description, 2), personality: area(a.personality, 2), instructions: area(a.instructions, 6),
        model: select([["", "Codex default" + (S.connection.default_model ? " (" + S.connection.default_model + ")" : "")]].concat(models.map(function (m) { return [m.id, m.name + (m.default ? " (default)" : "")]; })), a.model || ""),
        effort: el("select"),
        workdir: input(a.working_directory, { placeholder: a.effective_working_directory || "" }),
        outdir: input(a.output_directory, { placeholder: a.effective_output_directory || "" }),
        sandbox: select([["read-only", "Read only: can read files in its folder, cannot change anything"], ["workspace-write", "Read and write inside its working folder"]], a.permissions.sandbox),
        network: el("input", { type: "checkbox", checked: a.permissions.network }),
        approval: select([["on-request", "Ask me when Codex decides approval is needed (recommended)"], ["untrusted", "Ask me before every command that is not known to be safe"], ["never", "Never ask: refuse anything that would need approval"]], a.permissions.approval),
        enabled: el("input", { type: "checkbox", checked: a.enabled })
      };
      f.instructions.id = "cfgInstructions";
      if (a.model && !models.some(function (m) { return m.id === a.model; })) { f.model.appendChild(el("option", { value: a.model, text: a.model + " (not offered now)" })); f.model.value = a.model; }
      var fillEffort = function () {
        var m = models.filter(function (x) { return x.id === (f.model.value || S.connection.default_model); })[0], opts = (m && m.efforts) || [];
        U.clear(f.effort);
        f.effort.appendChild(el("option", { value: "", text: "Model default" + (m && m.default_effort ? " (" + m.default_effort + ")" : "") }));
        opts.forEach(function (e) { f.effort.appendChild(el("option", { value: e, text: e })); });
        if (a.reasoning_effort && opts.indexOf(a.reasoning_effort) < 0) f.effort.appendChild(el("option", { value: a.reasoning_effort, text: a.reasoning_effort + " (not offered for this model)" }));
        f.effort.value = a.reasoning_effort || "";
      };
      f.model.addEventListener("change", fillEffort); fillEffort();
      var syncNet = function () { f.network.disabled = f.sandbox.value === "read-only"; if (f.network.disabled) f.network.checked = false; };
      f.sandbox.addEventListener("change", syncNet); syncNet();

      var sprite = a.sprite_key, sprites = el("div", { class: "sprites", role: "radiogroup", "aria-label": "Character" });
      Object.keys(U.FACE).forEach(function (k) {
        var radio = el("input", { type: "radio", name: "sprite", value: k, checked: k === sprite });
        var lab = el("label", { class: k === sprite ? "on" : "" }, radio, U.face(k, "idle"), U.SPRITE_NAME[k]);
        radio.addEventListener("change", function () { sprite = k; [].forEach.call(sprites.children, function (x) { x.classList.toggle("on", x === lab); }); });
        sprites.appendChild(lab);
      });

      var tools = (a.allowed_tools || []).slice(), toolBox = el("div");
      var selectable = conn && conn.available ? conn.items.filter(function (i) { return i.selectable; }) : null;
      if (selectable === null) toolBox.appendChild(el("div", { class: "fhelp", text: "Connect Codex to see the integrations (MCP servers) it has configured." + (tools.length ? " Currently allowed: " + tools.join(", ") + "." : "") }));
      else if (!selectable.length) toolBox.appendChild(el("div", { class: "fhelp", text: "Codex has no integrations (MCP servers) configured, so there is nothing to allow." }));
      else selectable.forEach(function (it) {
        var cb = el("input", { type: "checkbox", checked: tools.indexOf(it.id) > -1 });
        cb.addEventListener("change", function () { if (cb.checked) { if (tools.indexOf(it.id) < 0) tools.push(it.id); } else tools = tools.filter(function (x) { return x !== it.id; }); });
        toolBox.appendChild(el("label", { class: "check" }, cb, el("span", null, it.name + " ", el("span", { class: "stat " + it.status, text: it.status.replace(/_/g, " ") }), el("small", { class: "fhelp", style: "display:block", text: it.detail }))));
      });

      var wdHelp = el("small", { class: "fhelp", text: "Empty uses the default: " + (S.settings.default_workspace || "") }),
        odHelp = el("small", { class: "fhelp", text: "Empty uses the default: " + (S.settings.default_output_dir || "") });
      var msg = el("span", { class: "mute" });
      var save = el("button", { type: "button", class: "pri", id: "cfgSave", text: "Save changes", onclick: function () {
        var patch = {
          display_name: f.name.value.trim(), role: f.role.value.trim(), description: f.description.value, personality: f.personality.value,
          instructions: f.instructions.value, model: f.model.value || null, reasoning_effort: f.effort.value || null,
          working_directory: f.workdir.value.trim() || null, output_directory: f.outdir.value.trim() || null,
          permissions: { sandbox: f.sandbox.value, network: f.network.checked, approval: f.approval.value }, sprite_key: sprite, enabled: f.enabled.checked
        };
        if (selectable !== null && JSON.stringify(tools.slice().sort()) !== JSON.stringify((a.allowed_tools || []).slice().sort())) patch.allowed_tools = tools;
        save.disabled = true; msg.textContent = "Saving\u2026"; msg.className = "mute";
        api.patch("/api/agents/" + id, patch).then(function (r) {
          save.disabled = false; a = r.agent;
          var mine = store.agent(id);
          if (mine) Object.keys(r.agent).forEach(function (k) { mine[k] = r.agent[k]; });
          msg.textContent = "Saved. The thread, history and outputs were kept."; renderHead(); store.emit("agent", mine);
        }, function (e) { save.disabled = false; msg.textContent = e.message; msg.className = "err"; });
      } });

      U.append(holder, [
        el("div", { class: "sec", text: "Identity" }),
        el("div", { class: "f2" }, field("Name", f.name), field("Role", f.role, "For example: Researcher, Software Developer.")),
        field("Description", f.description, "What this agent is for."),
        field("Personality", f.personality),
        field("Standing instructions", f.instructions, "Sent to Codex as this agent's instructions. They guide behaviour; they are not a security boundary. Access is limited by the permissions below."),
        el("div", { class: "flabel", text: "Character" }), sprites,
        el("div", { class: "sec", text: "Model" }),
        models.length ? null : el("div", { class: "note", text: "Connect Codex to choose from the models it offers. Until then the Codex default is used." }),
        el("div", { class: "f2" }, field("Model", f.model), field("Reasoning effort", f.effort)),
        el("div", { class: "sec", text: "Folders" }),
        el("label", { class: "f" }, el("span", { text: "Working folder" }), el("div", { class: "row" }, el("span", { class: "grow" }, f.workdir), checkFolderBtn(f.workdir, wdHelp)), wdHelp),
        el("label", { class: "f" }, el("span", { text: "Output folder" }), el("div", { class: "row" }, el("span", { class: "grow" }, f.outdir), checkFolderBtn(f.outdir, odHelp)), odHelp),
        el("div", { class: "sec", text: "Permissions" }),
        field("File access", f.sandbox, "Enforced by Codex's own sandbox, not by the instructions."),
        el("label", { class: "check" }, f.network, el("span", null, "Allow network access while working", el("small", { class: "fhelp", style: "display:block", text: "Only possible together with write access. Off by default." }))),
        field("Approvals", f.approval, "Approval requests appear in this agent's Chat tab and in the Bot Log. Nothing is approved automatically."),
        el("div", { class: "flabel", text: "Allowed integrations" }), toolBox,
        el("div", { class: "fhelp", text: "If the agent starts using an integration that is not allowed here, AGENTS HQ stops the task as soon as Codex reports it." }),
        el("div", { class: "sec", text: "Availability" }),
        el("label", { class: "check" }, f.enabled, el("span", null, "Agent enabled", el("small", { class: "fhelp", style: "display:block", text: "A disabled agent keeps its thread and history but does not run tasks." }))),
        el("div", { class: "bar" }, save, msg),
        el("div", { class: "fhelp", style: "margin-top:8px", text: "Renaming or changing the role never deletes the Codex thread, the conversation or the outputs. New instructions apply from the next message." })
      ]);
    }, function (e) { if (openId === id && tab === "configure") U.clear(holder).appendChild(failed(e, function () { show("configure", true); })); });
  }

  /* ============================================================ Tasks */
  var WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
  function showTasks() {
    var id = openId, holder = body;
    holder.appendChild(loading());
    Promise.all([api.get("/api/agents/" + id), api.get("/api/settings")]).then(function (res) {
      if (openId !== id || tab !== "tasks") return;
      var a = res[0].agent, t = a.task, zones = res[1].timezones || [S.settings.timezone], rt = a.runtime || {};
      var mine = store.agent(id);
      if (mine) { mine.task = a.task; mine.runtime = a.runtime; }
      U.clear(holder);
      var sch = (t && t.schedule) || null, rec = (sch && sch.recurrence) || {};
      var f = {
        title: input(t && t.title, { maxlength: "120", id: "taskTitle", placeholder: "Short name, for example: Weekly report" }),
        prompt: area(t && t.prompt, 6),
        expected: area(t && t.expected_output, 2), criteria: area(t && t.completion_criteria, 2),
        workdir: input(t && t.working_directory, { placeholder: a.effective_working_directory || "" }),
        priority: select([["low", "Low"], ["normal", "Normal"], ["high", "High"]], (t && t.priority) || "normal"),
        mode: select([["one_time", "One time: runs once, then counts as done"], ["repeatable", "Repeatable: may run again each time"]], (t && t.execution_mode) || "one_time"),
        maxdur: input(t && t.max_duration_sec ? Math.round(t.max_duration_sec / 60) : "", { type: "number", min: "1", max: "360", placeholder: String(Math.round((S.settings.default_timeout_sec || 1800) / 60)) }),
        retries: select([["", "Default (" + (S.settings.max_retries != null ? S.settings.max_retries : 1) + ")"], ["0", "0: never retry automatically"], ["1", "1"], ["2", "2"]], t && t.max_retries != null ? String(t.max_retries) : ""),
        enabled: el("input", { type: "checkbox", checked: t ? t.enabled : true }),
        kind: select([["", "Manual only (no schedule)"], ["once", "Once, at a date and time"], ["hourly", "Every hour"], ["daily", "Every day"], ["weekly", "Every week"], ["monthly", "Every month"], ["cron", "Custom (cron expression)"]], rec.type || ""),
        runAt: input(rec.run_at || "", { type: "datetime-local" }), minute: input(rec.minute != null ? rec.minute : 0, { type: "number", min: "0", max: "59" }),
        time: input(rec.time || "09:00", { type: "time" }), day: input(rec.day || 1, { type: "number", min: "1", max: "31" }),
        cron: input(rec.cron || "", { placeholder: "minute hour day month weekday, for example: 30 8 * * 1-5", class: "mono" }),
        start: input(rec.start_date || "", { type: "date" }), end: input(rec.end_date || "", { type: "date" }),
        tz: select(zones.map(function (z) { return [z, z]; }), (sch && sch.timezone) || S.settings.timezone),
        missed: select([["skip", "Skip it (default)"], ["catch_up", "Run it once when AGENTS HQ is back"]], (sch && sch.missed_execution_policy) || S.settings.missed_policy_default || "skip"),
        overlap: select([["skip", "Do not start a second run (default)"], ["queue", "Queue it behind the running one"]], (sch && sch.overlap_policy) || S.settings.overlap_policy_default || "skip"),
        schOn: el("input", { type: "checkbox", checked: sch ? sch.enabled : true })
      };
      f.prompt.id = "taskPrompt";
      if (sch && zones.indexOf(sch.timezone) < 0) { f.tz.appendChild(el("option", { value: sch.timezone, text: sch.timezone })); f.tz.value = sch.timezone; }
      var days = (rec.weekdays || [0]).slice(), dayBox = el("div", { class: "days" });
      WEEKDAYS.forEach(function (d, i) {
        var cb = el("input", { type: "checkbox", checked: days.indexOf(i) > -1 }), lab = el("label", { class: days.indexOf(i) > -1 ? "on" : "" }, cb, d);
        cb.addEventListener("change", function () { if (cb.checked) { if (days.indexOf(i) < 0) days.push(i); } else days = days.filter(function (x) { return x !== i; }); lab.classList.toggle("on", cb.checked); });
        dayBox.appendChild(lab);
      });
      var rows = {
        once: field("Date and time", f.runAt), hourly: field("Minute of the hour", f.minute), time: field("Time of day", f.time),
        weekly: el("div", { class: "f" }, el("span", { text: "Days of the week" }), dayBox), monthly: field("Day of the month", f.day, "If the month is shorter, the last day of the month is used."),
        cron: field("Cron expression", f.cron, "Five fields: minute, hour, day of month, month, day of week (0 or 7 is Sunday)."),
        common: el("div", null, el("div", { class: "f2" }, field("Time zone", f.tz), field("If a run time is missed", f.missed)),
          el("div", { class: "f2" }, field("If the previous run is still going", f.overlap), el("div")),
          el("div", { class: "f2" }, field("Start date (optional)", f.start), field("End date (optional)", f.end)),
          el("label", { class: "check" }, f.schOn, el("span", { text: "Schedule enabled" })),
          sch && sch.next_run_at && sch.enabled ? el("div", { class: "note", text: "Next run: " + U.fullDateTime(sch.next_run_at) + " (" + U.timezone() + "). " + sch.description + "." }) : null,
          el("div", { class: "note warn", text: "Schedules run on this computer, and only while AGENTS HQ is open and Codex is connected. This is not a cloud service that works 24/7." }))
      };
      var schBox = el("div");
      var syncKind = function () {
        var k = f.kind.value;
        U.clear(schBox);
        if (!k) return;
        if (k === "once") schBox.appendChild(rows.once);
        if (k === "hourly") schBox.appendChild(rows.hourly);
        if (k === "daily" || k === "weekly" || k === "monthly") schBox.appendChild(rows.time);
        if (k === "weekly") schBox.appendChild(rows.weekly);
        if (k === "monthly") schBox.appendChild(rows.monthly);
        if (k === "cron") schBox.appendChild(rows.cron);
        schBox.appendChild(rows.common);
      };
      f.kind.addEventListener("change", syncKind); syncKind();

      var collect = function () {
        var k = f.kind.value, data = {
          title: f.title.value.trim(), prompt: f.prompt.value, expected_output: f.expected.value, completion_criteria: f.criteria.value,
          working_directory: f.workdir.value.trim() || null, priority: f.priority.value, execution_mode: f.mode.value,
          max_duration_sec: f.maxdur.value ? Math.round(Number(f.maxdur.value) * 60) : null, max_retries: f.retries.value === "" ? null : Number(f.retries.value),
          enabled: f.enabled.checked, schedule: null
        };
        if (k) {
          var r = { type: k };
          if (k === "once") r.run_at = f.runAt.value;
          if (k === "hourly") r.minute = Number(f.minute.value || 0);
          if (k === "daily" || k === "weekly" || k === "monthly") r.time = f.time.value;
          if (k === "weekly") r.weekdays = days.slice();
          if (k === "monthly") r.day = Number(f.day.value || 1);
          if (k === "cron") r.cron = f.cron.value.trim();
          if (f.start.value) r.start_date = f.start.value;
          if (f.end.value) r.end_date = f.end.value;
          data.schedule = { recurrence: r, timezone: f.tz.value, missed_execution_policy: f.missed.value, overlap_policy: f.overlap.value, enabled: f.schOn.checked };
        }
        return data;
      };

      var msg = el("span", { class: "mute", id: "taskMsg" });
      var reload = function (text) { show("tasks", true); if (text) U.toast(text); };
      var act = function (promise, okText) { return promise.then(function () { reload(okText); }, function (e) { msg.textContent = e.message; msg.className = "err"; U.toast(e.message, true); }); };
      var saveBtn = el("button", { type: "button", class: "pri", id: "taskSave", text: "Save Assignment", onclick: function () {
        saveBtn.disabled = true;
        act(api.post("/api/agents/" + id + "/tasks", collect()), "Assignment saved.").then(function () { saveBtn.disabled = false; });
      } });
      var hasOpen = rt.run && rt.run.kind === "task" && rt.status !== "idle";
      var last = rt.last_run && rt.last_run.kind === "task" ? rt.last_run : null;
      var retryable = last && ["failed", "interrupted", "cancelled", "rate_limited", "unknown"].indexOf(last.status) > -1 && !hasOpen;
      var buttons = el("div", { class: "bar" }, saveBtn,
        el("button", { type: "button", id: "taskRun", disabled: !t || hasOpen || !codexReady(), title: !t ? "Save the assignment first" : !codexReady() ? "Codex is not connected" : hasOpen ? "Already running or queued" : "Start this assignment now", text: "Run Now",
          onclick: function () { act(api.post("/api/agents/" + id + "/run", { idempotency_key: U.uid() }), "Started."); } }),
        el("button", { type: "button", id: "taskBatch", disabled: !t, title: !t ? "Save the assignment first" : "", text: t && t.in_batch ? "Remove from Run Everything" : "Add to Run Everything",
          onclick: function () { act(api.post("/api/agents/" + id + "/batch", { in_batch: !(t && t.in_batch) }), t && t.in_batch ? "Removed from Run Everything." : "Added to Run Everything."); } }),
        el("button", { type: "button", id: "taskStop", class: "danger", disabled: !hasOpen, title: hasOpen ? "" : "Nothing is running", text: "Stop Task",
          onclick: function () { act(api.post("/api/agents/" + id + "/interrupt", { run_id: rt.run.id }), "Stop requested."); } }),
        el("button", { type: "button", id: "taskRetry", disabled: !retryable || !codexReady(), title: retryable ? "Run the assignment again" : "Only work that failed or was stopped can be retried", text: "Retry", onclick: retryTask }),
        el("button", { type: "button", id: "taskClear", disabled: !t, text: "Clear Assignment", onclick: function () {
          U.confirm({ title: "Clear this assignment?", text: "The assignment and its schedule are removed from " + a.display_name + ". Past runs, outputs and the Codex thread are kept.", ok: "Clear assignment", danger: true })
            .then(function (yes) { if (yes) act(api.del("/api/agents/" + id + "/tasks"), "Assignment cleared."); });
        } }));

      var stateNote = null;
      if (t) {
        var parts = ["State: " + U.statusLabel(t.state) + "."];
        if (t.state === "completed") parts.push("This one-time assignment is done, so Run Everything will not repeat it. Run Now or changing the prompt runs it again.");
        if (t.in_batch && t.state !== "completed") parts.push("Included in Run Everything.");
        if (hasOpen) parts.push("Now: " + U.statusLabel(rt.status) + (rt.detail ? " (" + rt.detail + ")" : "") + ".");
        if (last) parts.push("Last run " + U.statusLabel(last.status).toLowerCase() + " " + U.dateTime(last.finished_at) + (last.error_message ? ": " + last.error_message : "."));
        stateNote = el("div", { class: "note" + (last && last.status !== "completed" && !hasOpen ? " warn" : ""), id: "taskState", text: parts.join(" ") });
      } else stateNote = el("div", { class: "note", id: "taskState", text: a.display_name + " has no assignment. It stays idle in the office until you save one, or you can simply chat with it." });

      U.append(holder, [stateNote,
        el("div", { class: "sec", text: "Assignment" }),
        field("Task title", f.title), field("Task prompt", f.prompt, "What the agent should do. This is sent to its Codex thread when the task runs."),
        el("div", { class: "f2" }, field("Expected output", f.expected), field("Completion criteria", f.criteria)),
        field("Working folder for this task", f.workdir, "Empty uses the agent's folder: " + (a.effective_working_directory || "")),
        el("div", { class: "f2" }, field("Priority", f.priority), field("Execution mode", f.mode)),
        el("div", { class: "f2" }, field("Maximum duration (minutes)", f.maxdur), field("Automatic retries", f.retries, "Only failures that are safe to repeat are retried, at most twice.")),
        el("label", { class: "check" }, f.enabled, el("span", { text: "Assignment enabled" })),
        el("div", { class: "sec", text: "Schedule (optional)" }),
        field("When should it run?", f.kind), schBox,
        buttons, msg]);
    }, function (e) { if (openId === id && tab === "tasks") U.clear(holder).appendChild(failed(e, function () { show("tasks", true); })); });
  }
  function retryTask() {
    var id = openId;
    attempt(api.post("/api/agents/" + id + "/retry", {}), "Retry started.").then(function (r) { if (r && openId === id && tab === "tasks") show("tasks", true); });
  }

  /* ============================================================ Outputs */
  function outputItem(o, onOpen, showAgent) {
    return el("div", { class: "it click", tabindex: "0", role: "button", dataset: { output: o.id }, onclick: function () { onOpen(o.id); },
      onkeydown: function (e) { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onOpen(o.id); } } },
      el("div", { class: "t" }, el("b", { text: o.title || o.file_name || "Result" }), U.pill(o.status)),
      el("div", { class: "d", text: [showAgent ? store.name(o.agent_id) : null, o.run_kind === "task" ? "Task: " + (o.run_title || "") : "Chat", U.dateTime(o.created_at),
        o.file_name ? o.file_name + " (" + U.bytes(o.size_bytes) + ")" : "no file"].filter(Boolean).join(" \u00b7 ") }),
      o.excerpt ? el("div", { class: "x", text: o.excerpt }) : null);
  }
  /* Detail view shared by the Outputs tab and the "All outputs" dialog. `back` returns to the list. */
  function outputDetail(holder, outputId, back) {
    U.clear(holder).appendChild(loading());
    api.get("/api/outputs/" + outputId).then(function (r) {
      var o = r.output, text = o.content != null ? o.content : o.preview;
      U.clear(holder);
      var act = el("div", { class: "bar" });
      if (text != null) act.appendChild(el("button", { type: "button", text: "Copy", onclick: function () { U.copy(text); } }));
      if (o.file_path) {
        act.appendChild(el("button", { type: "button", disabled: !o.can_open, title: o.can_open ? "Open with the default program on this computer" : "The file no longer exists or cannot be opened from here", text: "Open file",
          onclick: function () { attempt(api.post("/api/outputs/" + o.id + "/open"), "Opened on this computer."); } }));
        act.appendChild(el("button", { type: "button", disabled: !o.file_exists, title: o.file_exists ? "" : "The file no longer exists", text: "Open containing folder",
          onclick: function () { attempt(api.post("/api/outputs/" + o.id + "/reveal"), "Folder opened."); } }));
      }
      if (o.file_exists || o.has_content) act.appendChild(el("a", { href: "/api/outputs/" + encodeURIComponent(o.id) + "/download", download: "", class: "dl" }, el("button", { type: "button", tabindex: "-1", text: "Download" })));
      var facts = [["Agent", store.name(o.agent_id)], ["From", o.run_kind === "task" ? "Task: " + (o.run_title || "") : "Chat reply"], ["Status", U.statusLabel(o.status)],
        ["Created", U.fullDateTime(o.created_at)], ["Type", o.output_type + (o.mime_type ? " (" + o.mime_type + ")" : "")]];
      if (o.file_path) facts.push(["File", o.file_path + (o.file_exists === false ? "  (no longer on disk)" : "")]);
      if (o.size_bytes != null) facts.push(["Size", U.bytes(o.size_bytes)]);
      var pv = el("div", { class: "preview" });
      if (text == null) pv.appendChild(el("div", { class: "mute", text: o.file_exists === false ? "The file is no longer on disk, so there is nothing to preview." : "No preview for this file type. Use Open file or Download." }));
      else if (o.output_type === "markdown" || /\.md$/i.test(o.file_name || "")) pv.appendChild(MD.render(text));
      else pv.appendChild(el("pre", { text: text }));
      U.append(holder, [el("button", { type: "button", class: "link", text: "\u2190 Back to the list", onclick: back }),
        el("h3", { style: "margin:10px 0 8px;font-size:16px", text: o.title || o.file_name || "Result" }),
        el("dl", { class: "kv" }, facts.map(function (x) { return [el("dt", { text: x[0] }), el("dd", { text: x[1] })]; })), act, pv]);
    }, function (e) { U.clear(holder).appendChild(failed(e, back)); });
  }

  function showOutputs() {
    var id = openId, holder = body;
    var q = el("input", { type: "search", placeholder: "Search results", "aria-label": "Search results" }),
      st = select([["", "Any status"], ["completed", "Completed"], ["failed", "Failed"], ["interrupted", "Stopped"]], "");
    var list = el("div", { class: "list", id: "outList" }), detail = el("div", { hidden: true }), top = el("div", { class: "filters" }, q, st);
    var back = function () { detail.hidden = true; top.hidden = false; list.hidden = false; load(); };
    var openOne = function (oid) { top.hidden = true; list.hidden = true; detail.hidden = false; outputDetail(detail, oid, back); };
    var load = function () {
      api.get("/api/agents/" + id + "/outputs?q=" + encodeURIComponent(q.value) + "&status=" + encodeURIComponent(st.value)).then(function (r) {
        if (openId !== id || tab !== "outputs") return;
        U.clear(list);
        if (!r.outputs.length) list.appendChild(el("div", { class: "mute", text: q.value || st.value ? "Nothing matches." : "No results yet. Replies and task results appear here once the agent has really produced them." }));
        r.outputs.forEach(function (o) { list.appendChild(outputItem(o, openOne)); });
      }, function (e) { U.clear(list).appendChild(failed(e, load)); });
    };
    view.reloadOutputs = function () { if (!list.hidden) load(); };
    q.addEventListener("input", U.debounce(load, 250)); st.addEventListener("change", load);
    U.append(holder, [top, list, detail]);
    list.appendChild(loading());
    if (view.openOutput) { var o = view.openOutput; view.openOutput = null; openOne(o); } else load();
  }

  /* ============================================================ History */
  function showHistory() {
    var id = openId, holder = body;
    var q = el("input", { type: "search", placeholder: "Search runs", "aria-label": "Search runs" }),
      st = select([["", "Any result"], ["completed", "Completed"], ["failed", "Failed"], ["interrupted", "Stopped"], ["cancelled", "Cancelled"], ["rate_limited", "Rate limited"], ["unknown", "Unknown outcome"]], "");
    var list = el("div", { class: "list", id: "histList" }), threads = el("div");
    var load = function () {
      api.get("/api/agents/" + id + "/history?q=" + encodeURIComponent(q.value) + "&status=" + encodeURIComponent(st.value)).then(function (r) {
        if (openId !== id || tab !== "history") return;
        U.clear(list);
        if (!r.runs.length) list.appendChild(el("div", { class: "mute", text: q.value || st.value ? "Nothing matches." : "No runs yet." }));
        r.runs.forEach(function (run) { list.appendChild(runItem(run)); });
        U.clear(threads);
        if (r.threads.length) {
          threads.appendChild(el("div", { class: "sec", text: "Codex threads used by this agent" }));
          threads.appendChild(el("div", { class: "list" }, r.threads.map(function (t) {
            return el("div", { class: "it" }, el("div", { class: "t" }, el("div", { class: "idline" }, el("code", { text: t.provider_thread_id })), el("span", { class: "pill " + (t.status === "active" ? "done" : ""), text: t.status })),
              el("div", { class: "d", text: (t.origin === "associated" ? "Associated by you" : "Created by AGENTS HQ") + " " + U.dateTime(t.created_at) + (t.last_used_at ? " \u00b7 last used " + U.dateTime(t.last_used_at) : "") + (t.archived_at ? " \u00b7 archived " + U.dateTime(t.archived_at) : "") }));
          })));
        }
      }, function (e) { U.clear(list).appendChild(failed(e, load)); });
    };
    view.reloadHistory = load;
    q.addEventListener("input", U.debounce(load, 250)); st.addEventListener("change", load);
    var clearBtn = el("button", { type: "button", class: "mini", text: "Clear history\u2026", onclick: function () {
      var a = agent();
      U.confirm({ title: "Clear " + a.display_name + "'s history?", text: "This deletes this agent's conversation, finished runs, saved results and log entries from AGENTS HQ.\n\nFiles on disk and the Codex thread are not touched. This cannot be undone.", ok: "Clear history", danger: true })
        .then(function (yes) { if (yes) attempt(api.post("/api/history/clear", { confirm: true, agent_id: id }), "History cleared.").then(function (r) { if (r) load(); }); });
    } });
    U.append(holder, [el("div", { class: "filters" }, q, st, el("span", { class: "grow" }), clearBtn), list, threads]);
    list.appendChild(loading());
    load();
  }
  function runItem(run) {
    var trig = { chat: "Chat message", manual: "Run Now", batch: "Run Everything", schedule: "Schedule", retry: "Retry", handoff: "Hand-off", auto_retry: "Automatic retry" }[run.trigger_type] || run.trigger_type;
    var facts = [["Started by", trig], ["Queued", U.fullDateTime(run.queued_at)], ["Started", run.started_at ? U.fullDateTime(run.started_at) : "not started"],
      ["Ended", run.finished_at ? U.fullDateTime(run.finished_at) : "still open"], ["Run id", run.id]];
    if (run.retry_count) facts.push(["Retries", String(run.retry_count)]);
    if (run.provider_thread_id) facts.push(["Thread id", run.provider_thread_id]);
    if (run.provider_turn_id) facts.push(["Turn id", run.provider_turn_id]);
    if (run.occurrence_id) facts.push(["Schedule occurrence", run.occurrence_id]);
    if (run.parent_run_id) facts.push(["Handed over from run", run.parent_run_id]);
    if (run.usage && run.usage.total_tokens) facts.push(["Tokens reported by Codex", run.usage.total_tokens + " (" + (run.usage.input_tokens || 0) + " in, " + (run.usage.output_tokens || 0) + " out)"]);
    var details = el("details", null, el("summary", { text: "Details" }),
      el("dl", { class: "kv", style: "margin-top:8px" }, facts.map(function (x) { return [el("dt", { text: x[0] }), el("dd", { text: x[1] })]; })),
      run.prompt ? el("div", null, el("div", { class: "flabel", style: "margin-top:8px", text: "Prompt" }), el("div", { class: "preview", style: "max-height:160px" }, el("pre", { text: run.prompt }))) : null,
      (run.transitions || []).length ? el("ul", { class: "steps" }, run.transitions.map(function (t) {
        return el("li", null, el("time", { text: U.time(t.created_at) }), U.statusLabel(t.to_state) + (t.detail ? ": " + t.detail : ""));
      })) : null,
      (run.approvals || []).length ? el("div", { style: "margin-top:8px" }, el("div", { class: "flabel", text: "Approval decisions" }), el("ul", { class: "steps" }, run.approvals.map(function (ap) {
        return el("li", null, el("time", { text: U.time(ap.requested_at) }), ap.type.replace(/_/g, " ") + ": " + ap.status.replace(/_/g, " ") + (ap.resolved_at ? " at " + U.time(ap.resolved_at) : ""));
      }))) : null,
      (run.outputs || []).length ? el("div", { style: "margin-top:8px" }, el("div", { class: "flabel", text: "Results" }), run.outputs.map(function (o) {
        return el("div", null, el("button", { type: "button", class: "link", text: o.title || o.file_name || "Result", onclick: function () { view.openOutput = o.id; show("outputs", true); } }));
      })) : null);
    return el("div", { class: "it", dataset: { run: run.id } },
      el("div", { class: "t" }, el("b", { text: run.kind === "task" ? (run.title || "Task") : "Chat message" }), U.pill(run.status)),
      el("div", { class: "d", text: U.dateTime(run.started_at || run.queued_at) + (run.started_at && run.finished_at ? " \u00b7 took " + U.duration(run.started_at, run.finished_at) : "") + " \u00b7 " + trig }),
      run.error_message ? el("div", { class: "x", style: "color:#a4231c", text: run.error_message }) : run.status_detail && run.status !== "completed" ? el("div", { class: "x", text: run.status_detail }) : run.result_summary ? el("div", { class: "x", text: run.result_summary }) : null,
      details);
  }

  /* ============================================================ live updates */
  function init() {
    buildFrame();
    store.on("state", function () {
      if (!openId) return;
      if (!agent()) { close(); return; }
      renderHead();
      if (chat) { renderThread(); renderComposer(); renderApprovals(); renderUnknown(); }
    });
    store.on("runtime", function (a) {
      if (a.id !== openId) return;
      renderHead();
      if (chat) { renderComposer(); renderUnknown(); }
    });
    store.on("agent", function (a) { if (a && a.id === openId) { renderHead(); if (chat) renderThread(); } });
    store.on("connection", function () { if (chat) renderComposer(); });
    store.on("approvals", function () { if (openId) { renderHead(); renderApprovals(); } });
    store.on("message.started", function (ev) { if (chat && ev.payload.message) upsert(ev.payload.message); });
    store.on("message.completed", function (ev) { if (chat && ev.payload.message) upsert(ev.payload.message); });
    store.on("message.delta", onDelta);
    var afterRun = function (ev) {
      if (ev.agent_id !== openId) return;
      /* Error and stop notices are stored by the server without their own event: fetch the settled conversation. */
      if (chat && ev.type !== "task.completed") loadMessages();
      if (tab === "outputs" && view.reloadOutputs) view.reloadOutputs();
      if (tab === "history" && view.reloadHistory) view.reloadHistory();
      if (tab === "tasks") show("tasks", true);
    };
    store.on("task.completed", afterRun); store.on("task.failed", afterRun); store.on("task.cancelled", afterRun);
    store.on("output.created", function (ev) { if (ev.agent_id === openId && tab === "outputs" && view.reloadOutputs) view.reloadOutputs(); });
    store.on("history.cleared", function () { if (openId) show(tab, true); });
    store.on("resync", function () { if (openId) { if (chat) loadMessages(); else show(tab, true); } });
    window.addEventListener("resize", U.debounce(position, 80));
  }

  AHQ.panel = { init: init, open: open, close: close, toggle: toggle, current: function () { return openId; }, isBig: function () { return big; },
    setBig: setBig, outputItem: outputItem, outputDetail: outputDetail,
    openOutput: function (agentId, outputId) { open(agentId, "outputs"); view.openOutput = outputId; show("outputs", true); } };
})();
