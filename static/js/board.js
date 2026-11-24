/* AGENTS HQ - Canvas view: seven draggable agent cards on the dotted board, optional hand-off wires,
 * and the bridge that feeds the same server state to the Office view.
 *
 * Card positions are cosmetic and stored in the browser only. "Tidy up" resets positions and nothing else.
 */
(function () {
  "use strict";
  var AHQ = window.AHQ = window.AHQ || {};
  var U = AHQ.util, el = U.el, $ = U.$, store = AHQ.store, S = store.state;
  var POS_KEY = "pos-v1", CARD_W = 215;
  var board, nodesBox, cards = {}, POS = {}, selected = null;
  var said = {};          /* agent id -> {text, bad, until}: short real-event notes shown in the card bubble */
  var wireState = {};     /* dependency id -> {state: live|done|fail, run} from server events only */

  function defaults() {
    var w = Math.max(960, board.clientWidth), gap = Math.max(16, Math.min(40, (w - 4 * CARD_W - 40) / 3)), out = {};
    var row1 = (w - (4 * CARD_W + 3 * gap)) / 2, row2 = (w - (3 * CARD_W + 2 * gap)) / 2;
    S.agents.forEach(function (a, i) {
      out[a.id] = i < 4 ? [Math.round(row1 + i * (CARD_W + gap)), 96] : [Math.round(row2 + (i - 4) * (CARD_W + gap)), 356];
    });
    return out;
  }
  function loadPos() {
    POS = defaults();
    try {
      var saved = JSON.parse(U.ls(POS_KEY) || "null");
      if (saved) Object.keys(saved).forEach(function (k) {
        if (POS[k] && Array.isArray(saved[k]) && isFinite(saved[k][0]) && isFinite(saved[k][1])) POS[k] = [saved[k][0], saved[k][1]];
      });
    } catch (e) { /* damaged preference: fall back to the default layout */ }
  }
  function place() {
    Object.keys(cards).forEach(function (id) {
      var n = cards[id].node, p = POS[id];
      n.style.left = Math.max(0, Math.min(board.clientWidth - CARD_W, p[0])) + "px";
      n.style.top = Math.max(34, Math.min(board.clientHeight - 60, p[1])) + "px";
    });
    wires();
  }
  function tidy() {
    POS = defaults();
    U.ls(POS_KEY, null);
    board.classList.add("anim");
    place();
    var t0 = Date.now();
    (function follow() { wires(); if (Date.now() - t0 < 700) requestAnimationFrame(follow); })();
    setTimeout(function () { board.classList.remove("anim"); wires(); }, 720);
    U.toast("All tidy. Only the card positions changed.");
  }

  /* ---------- cards ---------- */
  function build() {
    U.clear(nodesBox);
    cards = {};
    S.agents.forEach(function (a) {
      var c = { bub: el("div", { class: "bub" }), face: el("span"), name: el("b"), role: el("span", { class: "s" }),
        st: el("div", { class: "st" }), task: el("div", { class: "task" }), next: el("span"), last: el("span") };
      c.node = el("div", { class: "node", id: "n-" + a.id, tabindex: "0", role: "button", dataset: { id: a.id } },
        c.bub,
        el("div", { class: "nh" }, c.face, el("div", { class: "bd" }, c.name, c.role)),
        c.st, c.task, el("div", { class: "ft" }, c.next, c.last));
      cards[a.id] = c;
      nodesBox.appendChild(c.node);
    });
    loadPos();
    place();
    S.agents.forEach(render);
  }

  function visual(status) {
    if (status === "starting" || status === "running" || status === "tool" || status === "cancelling") return "working";
    if (status === "awaiting_approval" || status === "unknown") return "waiting";
    return "idle";
  }

  function render(a) {
    var c = cards[a.id];
    if (!c) return;
    var rt = a.runtime || {}, vis = visual(rt.status), last = rt.last_run, task = a.task;
    var lastBad = last && (last.status === "failed" || last.status === "rate_limited" || last.status === "interrupted") && vis === "idle" && rt.status !== "queued";
    c.node.className = "node " + vis + (selected === a.id ? " sel" : "") + (lastBad && last.status !== "interrupted" ? " bad" : "") + (a.enabled ? "" : " off");
    c.node.setAttribute("aria-label", a.display_name + ", " + (a.role || "Unassigned") + ", " + U.statusLabel(rt.status));
    U.clear(c.face).appendChild(U.face(a.sprite_key, vis, a.display_name));
    c.name.textContent = a.display_name;
    c.role.textContent = a.role || "Unassigned";

    U.clear(c.st);
    c.st.appendChild(U.pill(rt.status));
    if (rt.pending_approvals) c.st.appendChild(el("span", { class: "flag ap", text: rt.pending_approvals === 1 ? "Approval pending" : rt.pending_approvals + " approvals pending" }));
    if (rt.queued && rt.status !== "queued") c.st.appendChild(el("span", { class: "pill queued", text: rt.queued + " queued" }));
    if (lastBad && last.status !== "interrupted") c.st.appendChild(el("span", { class: "flag er", title: last.error_message || "", text: "Last run " + U.statusLabel(last.status).toLowerCase() }));
    if (a.thread && a.thread.status === "unavailable") c.st.appendChild(el("span", { class: "flag er", title: a.thread.detail || "", text: "Thread unavailable" }));
    if (!a.enabled) c.st.appendChild(el("span", { class: "pill", text: "Disabled" }));

    var running = rt.run && rt.status !== "idle";
    if (running && rt.run.kind === "chat") { c.task.textContent = rt.activity_label || rt.detail || "Answering your message"; c.task.className = "task"; }
    else if (running) { c.task.textContent = rt.run.title || "Task"; c.task.className = "task"; }
    else if (task) { c.task.textContent = task.title; c.task.className = "task"; }
    else { c.task.textContent = "Available for work."; c.task.className = "task free"; }
    c.task.title = running && rt.detail ? rt.detail : "";

    var sch = task && task.schedule && task.schedule.enabled && task.schedule.next_run_at;
    c.next.textContent = sch ? "Next run: " + U.dateTime(task.schedule.next_run_at) : "Next run: not scheduled";
    c.next.title = sch ? task.schedule.description : "";
    var lastDone = last && last.status === "completed" ? last : null;
    c.last.textContent = lastDone ? "Last completed: " + (lastDone.title || "chat reply") + ", " + U.dateTime(lastDone.finished_at)
      : last ? "Last run: " + U.statusLabel(last.status).toLowerCase() + ", " + U.dateTime(last.finished_at) : "Last completed: nothing yet";
    bubble(a);
  }

  /* The bubble shows what is really happening: dots while working, a prompt when approval is needed,
     or a short note taken from a real server event. Idle agents show nothing here. */
  function bubble(a) {
    var c = cards[a.id];
    if (!c) return;
    var rt = a.runtime || {}, vis = visual(rt.status), note = said[a.id], b = c.bub;
    U.clear(b);
    b.className = "bub";
    if (note && note.until < Date.now()) { note = null; delete said[a.id]; }
    if (rt.status === "awaiting_approval") { b.textContent = "I need your approval to continue."; b.classList.add("on", "bad"); }
    else if (rt.status === "unknown") { b.textContent = "Please review my last task."; b.classList.add("on", "bad"); }
    else if (vis === "working") {
      b.appendChild(el("span", { class: "dots" }, el("i"), el("i"), el("i")));
      b.appendChild(document.createTextNode(" " + (rt.status === "cancelling" ? "stopping" : (rt.activity_label || "thinking").toLowerCase())));
      b.classList.add("on");
    }
    else if (rt.status === "queued") { b.textContent = "Waiting in the queue."; b.classList.add("on"); }
    else if (note) { b.textContent = note.text; b.classList.add("on"); if (note.bad) b.classList.add("bad"); }
    var top = parseFloat(c.node.style.top) || 0;
    b.classList.toggle("below", top < 80);
  }
  function say(id, text, bad, ms) {
    text = U.clip(String(text).replace(/\S{26,}/g, function (w) { return w.slice(0, 14) + "\u2026" + w.slice(-8); }), 110);
    said[id] = { text: text, bad: !!bad, until: Date.now() + (ms || 6000) };
    var a = store.agent(id);
    if (a) bubble(a);
    setTimeout(function () { var x = store.agent(id); if (x) bubble(x); }, (ms || 6000) + 50);
    AHQ.office.say(id, text, Math.min(ms || 6000, 5200), bad);
  }

  /* ---------- wires: only configured hand-offs; colours only from server events ---------- */
  function wires() {
    var svg = $("wires");
    while (svg.firstChild) svg.removeChild(svg.firstChild);
    if (!S.settings.collaboration_enabled || !S.dependencies.length) return;
    var ns = "http://www.w3.org/2000/svg";
    var defs = document.createElementNS(ns, "defs"), mk = document.createElementNS(ns, "marker"), arrow = document.createElementNS(ns, "path");
    mk.setAttribute("id", "ah"); mk.setAttribute("viewBox", "0 0 10 10"); mk.setAttribute("refX", "8"); mk.setAttribute("refY", "5");
    mk.setAttribute("markerWidth", "8"); mk.setAttribute("markerHeight", "8"); mk.setAttribute("orient", "auto");
    arrow.setAttribute("d", "M1 1 L9 5 L1 9"); arrow.setAttribute("fill", "none"); arrow.setAttribute("stroke", "#8a8d93"); arrow.setAttribute("stroke-width", "1.6");
    mk.appendChild(arrow); defs.appendChild(mk); svg.appendChild(defs);
    S.dependencies.forEach(function (d) {
      var A = cards[d.source_agent_id], B = cards[d.destination_agent_id];
      if (!A || !B) return;
      var a = A.node, b = B.node, al = a.offsetLeft, ar = al + a.offsetWidth, at = a.offsetTop, ab = at + a.offsetHeight,
        bl = b.offsetLeft, br = bl + b.offsetWidth, bt = b.offsetTop, bb = bt + b.offsetHeight, path, y1, y2, x1, x2, dx, dy;
      if (bl >= ar - 20) { y1 = at + a.offsetHeight / 2; y2 = bt + b.offsetHeight / 2; dx = Math.max(40, (bl - ar) / 2); path = "M" + ar + " " + y1 + " C" + (ar + dx) + " " + y1 + " " + (bl - dx) + " " + y2 + " " + bl + " " + y2; }
      else if (br <= al + 20) { y1 = at + a.offsetHeight / 2; y2 = bt + b.offsetHeight / 2; dx = Math.max(40, (al - br) / 2); path = "M" + al + " " + y1 + " C" + (al - dx) + " " + y1 + " " + (br + dx) + " " + y2 + " " + br + " " + y2; }
      else if (bt >= ab) { x1 = al + a.offsetWidth / 2; x2 = bl + b.offsetWidth / 2; dy = Math.max(30, (bt - ab) / 2); path = "M" + x1 + " " + ab + " C" + x1 + " " + (ab + dy) + " " + x2 + " " + (bt - dy) + " " + x2 + " " + bt; }
      else { x1 = al + a.offsetWidth / 2; x2 = bl + b.offsetWidth / 2; dy = Math.max(30, (at - bb) / 2); path = "M" + x1 + " " + at + " C" + x1 + " " + (at - dy) + " " + x2 + " " + (bb + dy) + " " + x2 + " " + bb; }
      var p = document.createElementNS(ns, "path"), ws = wireState[d.id];
      p.setAttribute("d", path);
      p.setAttribute("class", "w" + (ws ? " " + ws.state : "") + (d.enabled ? "" : " off"));
      p.setAttribute("marker-end", "url(#ah)");
      p.setAttribute("data-dep", d.id);
      svg.appendChild(p);
    });
  }
  function depBetween(src, dst) {
    return S.dependencies.filter(function (d) { return d.source_agent_id === src && d.destination_agent_id === dst; })[0];
  }
  function setWire(dep, state, run) { if (!dep) return; wireState[dep.id] = { state: state, run: run || null }; wires(); }
  function wireForRun(runId) {
    var id = Object.keys(wireState).filter(function (k) { return wireState[k].run === runId; })[0];
    return id ? S.dependencies.filter(function (d) { return d.id === id; })[0] : null;
  }

  /* ---------- selection, drag, click ---------- */
  function select(id) {
    selected = id || null;
    Object.keys(cards).forEach(function (k) { cards[k].node.classList.toggle("sel", k === selected); });
    AHQ.office.select(selected);
  }
  function anchor(id) {
    /* Where the workspace panel should attach, in board coordinates. */
    var r = board.getBoundingClientRect();
    if (board.classList.contains("office")) {
      var p = AHQ.office.screenPos(id);
      if (p) return { x: p[0] - r.left, y: p[1] - r.top, w: 0, h: 0, office: true };
    }
    var n = cards[id] && cards[id].node;
    return n ? { x: n.offsetLeft, y: n.offsetTop, w: n.offsetWidth, h: n.offsetHeight } : { x: 20, y: 60, w: 0, h: 0 };
  }

  var drag = null;
  function initDrag() {
    board.addEventListener("pointerdown", function (e) {
      var n = e.target.closest && e.target.closest(".node");
      if (!n || e.button > 0) return;
      drag = { n: n, x: e.clientX, y: e.clientY, l: n.offsetLeft, t: n.offsetTop, moved: false, id: e.pointerId };
      try { n.setPointerCapture(e.pointerId); } catch (_) { /* older browsers */ }
    });
    board.addEventListener("pointermove", function (e) {
      if (!drag) return;
      var dx = e.clientX - drag.x, dy = e.clientY - drag.y;
      if (!drag.moved && Math.abs(dx) + Math.abs(dy) < 5) return;
      drag.moved = true;
      drag.n.classList.add("drag");
      var l = Math.max(0, Math.min(board.clientWidth - drag.n.offsetWidth, drag.l + dx)),
        t = Math.max(34, Math.min(board.clientHeight - drag.n.offsetHeight, drag.t + dy));
      drag.n.style.left = l + "px"; drag.n.style.top = t + "px";
      POS[drag.n.dataset.id] = [l, t];
      wires();
    });
    var end = function () {
      if (!drag) return;
      var n = drag.n, moved = drag.moved;
      n.classList.remove("drag");
      drag = null;
      if (moved) { U.ls(POS_KEY, JSON.stringify(POS)); var a = store.agent(n.dataset.id); if (a) bubble(a); }
      else AHQ.panel.toggle(n.dataset.id);
    };
    board.addEventListener("pointerup", end);
    board.addEventListener("pointercancel", function () { if (drag) { drag.n.classList.remove("drag"); drag = null; } });
    nodesBox.addEventListener("keydown", function (e) {
      var n = e.target.closest && e.target.closest(".node");
      if (n && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); AHQ.panel.toggle(n.dataset.id); }
    });
    window.addEventListener("resize", U.debounce(function () { place(); AHQ.office.layout(); }, 80));
  }

  /* ---------- office bridge: the office gets exactly the same server state as the cards ---------- */
  function officeSync() {
    AHQ.office.sync(S.agents.map(function (a) {
      var rt = a.runtime || {};
      return { id: a.id, name: a.display_name, sprite: a.sprite_key, status: a.enabled ? rt.status : "idle", activity: rt.activity || "" };
    }));
  }

  function init() {
    board = $("board"); nodesBox = $("nodes");
    initDrag();
    $("tidyBtn").addEventListener("click", tidy);

    store.on("state", function () {
      if (Object.keys(cards).length !== S.agents.length) build();
      else S.agents.forEach(render);
      wires();
      officeSync();
    });
    store.on("runtime", function (a) { render(a); officeSync(); });
    store.on("agent", function (a) { render(a); officeSync(); });
    store.on("dependencies", wires);

    /* Notes and effects that come from real events only. */
    store.on("task.completed", function (ev) {
      var run = (ev.payload || {}).run || {};
      say(ev.agent_id, run.kind === "task" ? "Done: " + (run.title || "task") : "Reply ready.", false, 6000);
      AHQ.office.flash(ev.agent_id, "done", 3500);
      setWire(wireForRun(ev.run_id), "done", ev.run_id);
    });
    store.on("task.failed", function (ev) {
      var run = (ev.payload || {}).run || {};
      say(ev.agent_id, run.status === "rate_limited" ? "Codex usage limit reached." : run.status === "unknown" ? "I lost the connection mid-task. Please review." : "That did not work. See the error in my workspace.", true, 9000);
      AHQ.office.flash(ev.agent_id, "error", 5000);
      setWire(wireForRun(ev.run_id), "fail", ev.run_id);
    });
    store.on("task.cancelled", function (ev) {
      var run = (ev.payload || {}).run || {};
      say(ev.agent_id, "Stopped.", false, 4000);
      setWire(wireForRun(ev.run_id), "fail", ev.run_id);
      if (/did not finish successfully|declined/.test(run.status_detail || "")) {
        S.dependencies.forEach(function (d) { if (d.destination_agent_id === ev.agent_id) setWire(d, "fail", ev.run_id); });
      }
    });
    store.on("approval.requested", function (ev) { AHQ.office.flash(ev.agent_id, "approval", 2500); });
    store.on("handoff.started", function (ev) {
      var p = ev.payload || {}, dep = depBetween(p.source_agent_id, p.destination_agent_id);
      setWire(dep, "live", p.run && p.run.id);
      AHQ.office.handoff(p.source_agent_id, p.destination_agent_id, "Handing my result over\u2026", "All yours, " + store.name(p.destination_agent_id) + "!");
    });
    store.on("handoff.skipped", function (ev) {
      var p = ev.payload || {};
      setWire(depBetween(p.source_agent_id, p.destination_agent_id), "fail");
    });
  }

  AHQ.board = { init: init, select: select, anchor: anchor, say: say, place: place, wires: wires, visual: visual, officeSync: officeSync,
    stats: function () { return { cards: Object.keys(cards).length, positions: POS, wires: wireState }; } };
})();
