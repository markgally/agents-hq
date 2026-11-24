/* AGENTS HQ - Bot Log + Command Center. Persisted activity from the server; never invents events. */
(function () {
  "use strict";
  var AHQ = window.AHQ = window.AHQ || {};
  var U = AHQ.util, el = U.el, $ = U.$, store = AHQ.store, S = store.state;
  var FILTERS = [
    { id: "all", label: "All Activity" },
    { id: "working", label: "Working" },
    { id: "completed", label: "Completed" },
    { id: "errors", label: "Errors" },
    { id: "approvals", label: "Approvals" }
  ];
  var filter = "all", entries = [], loading = false, facesBox, dockTiles, feed, filtersEl, ccEl;
  var SPRITE_TONE = { mgr: "green", cap: "blue", "in": "grey", sch: "purple", pack: "pink", ved: "orange", rvs: "lime" };

  function catMatch(entry) {
    var c = entry.category || "";
    if (filter === "all") return true;
    if (filter === "working") return c === "working" || (c === "info" && /queued|started|progress/i.test(entry.type || ""));
    if (filter === "completed") return c === "completed";
    if (filter === "errors") return c === "error" || entry.severity === "error";
    if (filter === "approvals") return c === "approval" || /approval/i.test(entry.type || "");
    return true;
  }

  function agentVisual(rt) {
    return AHQ.board && AHQ.board.visual ? AHQ.board.visual((rt || {}).status) : "idle";
  }

  function meterLevel(rt) {
    var st = (rt && rt.status) || "idle";
    if (st === "running" || st === "tool" || st === "starting" || st === "cancelling") return 3;
    if (st === "queued" || st === "awaiting_approval" || st === "unknown" || st === "recovering") return 2;
    if (st === "failed" || st === "rate_limited" || st === "blocked" || st === "interrupted") return 1;
    if (st === "completed") return 2;
    return 0;
  }

  function renderFaces() {
    U.clear(facesBox);
    (S.agents || []).forEach(function (a) {
      var rt = a.runtime || {};
      var face = U.face(a.sprite_key, agentVisual(rt), a.display_name);
      face.style.cursor = "pointer";
      if (rt.status === "awaiting_approval" || rt.status === "failed") face.classList.add("alert");
      face.addEventListener("click", function () { AHQ.panel.open(a.id, "chat"); });
      facesBox.appendChild(face);
    });
  }

  function renderDock() {
    if (!dockTiles) return;
    U.clear(dockTiles);
    var openId = AHQ.panel && AHQ.panel.current ? AHQ.panel.current() : null;
    var agents = S.agents || [];
    if (!agents.length) {
      dockTiles.appendChild(el("div", { class: "dock-empty", text: "Agents appear here once the office loads." }));
      return;
    }
    agents.forEach(function (a) {
      var rt = a.runtime || {};
      var vis = agentVisual(rt);
      var tone = SPRITE_TONE[a.sprite_key] || "blue";
      var st = rt.status || "idle";
      var level = meterLevel(rt);
      var active = openId === a.id;
      var alert = st === "awaiting_approval" || st === "failed" || st === "unknown";
      var blurb = rt.activity_label || rt.detail || (a.enabled === false ? "Disabled" : (a.role || "Unassigned"));
      var tile = el("button", {
        type: "button",
        class: "dock-tile tone-" + tone + (active ? " on" : "") + (alert ? " alert" : "") + (a.enabled === false ? " off" : ""),
        "aria-label": "Open chat with " + a.display_name,
        "aria-pressed": active ? "true" : "false",
        title: "Chat with " + a.display_name,
        onclick: function () { AHQ.panel.open(a.id, "chat"); }
      },
        U.face(a.sprite_key, vis, a.display_name),
        el("div", { class: "dock-meta" },
          el("b", { class: "dock-name", text: a.display_name }),
          el("span", { class: "dock-role", text: U.clip(blurb, 36) }),
          el("div", { class: "dock-stats" },
            U.pill(st),
            el("span", {
              class: "dock-meter l" + level + " " + U.statusClass(st),
              "aria-hidden": "true",
              title: U.statusLabel(st)
            },
              el("i"), el("i"), el("i")))));
      dockTiles.appendChild(tile);
    });
  }

  function metric(label, value, cls) {
    return el("div", { class: cls || "" }, el("b", { text: String(value == null ? "—" : value) }), el("span", { text: label }));
  }

  function renderCC() {
    var s = S.summary || {};
    U.clear(ccEl);
    ccEl.appendChild(metric("Agents", s.total_agents || 0));
    ccEl.appendChild(metric("Idle", s.idle_agents || 0, "good"));
    ccEl.appendChild(metric("Working", s.working_agents || 0));
    ccEl.appendChild(metric("Queued", s.queued_tasks || 0));
    ccEl.appendChild(metric("Approvals", s.pending_approvals || 0, s.pending_approvals ? "warn" : ""));
    ccEl.appendChild(metric("Done", s.completed_tasks || 0, "good"));
    ccEl.appendChild(metric("Failed", s.failed_tasks || 0, s.failed_tasks ? "bad" : ""));
    var next = s.next_scheduled_execution;
    ccEl.appendChild(el("div", { class: "wide" },
      el("span", { text: "Next schedule: " }),
      el("b", { text: next ? U.dateTime(next) : "none" })));
  }

  function renderFilters() {
    U.clear(filtersEl);
    FILTERS.forEach(function (f) {
      filtersEl.appendChild(el("button", {
        type: "button", role: "tab", "aria-selected": f.id === filter,
        text: f.label,
        onclick: function () { filter = f.id; renderFilters(); renderFeed({ forceStick: true }); }
      }));
    });
  }

  function row(entry) {
    var a = entry.agent_id ? store.agent(entry.agent_id) : null;
    var cat = entry.category || "";
    var cls = "ev";
    if (entry.severity === "error" || cat === "error") cls += " error";
    else if (cat === "approval") cls += " approval";
    else if (cat === "completed") cls += " completed";
    var face = a
      ? U.face(a.sprite_key, "idle", a.display_name)
      : el("div", { class: "sysi", text: "·" });
    var who = a ? a.display_name : "AGENTS HQ";
    var text = entry.log || entry.message || entry.type || "";
    return el("button", {
      type: "button",
      class: cls,
      onclick: function () {
        if (!entry.agent_id) return;
        if (cat === "approval") AHQ.panel.open(entry.agent_id, "chat");
        else if (cat === "completed") AHQ.panel.open(entry.agent_id, "outputs");
        else AHQ.panel.open(entry.agent_id);
      }
    },
      face,
      el("div", null,
        el("div", null,
          el("span", { class: "who", text: who }),
          el("span", { class: "tm", text: U.time(entry.ts || entry.created_at) })),
        el("div", { class: "tx", text: text }))
    );
  }

  function nearBottom() {
    if (!feed) return true;
    return feed.scrollHeight - feed.scrollTop - feed.clientHeight < 80;
  }
  function stickBottom(force) {
    if (!feed) return;
    if (force || nearBottom()) feed.scrollTop = feed.scrollHeight;
  }

  function renderFeed(opts) {
    opts = opts || {};
    var stick = opts.forceStick || nearBottom();
    U.clear(feed);
    var shown = entries.filter(catMatch);
    if (!shown.length) {
      feed.appendChild(el("div", { class: "empty", text: loading ? "Loading…" : "No activity yet." }));
      return;
    }
    /* Oldest at the top, newest at the bottom — the feed sits in the bottom-right log area. */
    shown.forEach(function (e) { feed.appendChild(row(e)); });
    if (stick) requestAnimationFrame(function () { stickBottom(true); });
  }

  function load() {
    loading = true;
    return AHQ.api.get("/api/log?limit=200").then(function (r) {
      entries = (r && r.entries) || [];
      loading = false;
      renderFeed({ forceStick: true });
    }, function () { loading = false; });
  }

  function onLog(ev) {
    if (!ev || !ev.log) return;
    entries.push({
      id: ev.id, type: ev.type, agent_id: ev.agent_id, run_id: ev.run_id,
      category: ev.category, severity: ev.severity, log: ev.log,
      ts: ev.ts, created_at: ev.ts
    });
    if (entries.length > 500) entries = entries.slice(-500);
    renderFeed();
    renderCC();
    renderFaces();
    renderDock();
  }

  function refreshChrome() {
    renderFaces();
    renderDock();
    renderCC();
  }

  function init() {
    facesBox = $("faces"); dockTiles = $("dockTiles"); feed = $("feed"); filtersEl = $("logFilters"); ccEl = $("cc");
    renderFilters();
    renderDock();
    store.on("state", refreshChrome);
    store.on("runtime", refreshChrome);
    store.on("panel", renderDock);
    store.on("log", onLog);
    store.on("event", function (ev) {
      if (ev && ev.log) onLog(ev);
      else refreshChrome();
    });
    store.on("resync", load);
    $("outputsBtn").addEventListener("click", function () { AHQ.dialogs.outputs(); });
    $("connectorsBtn").addEventListener("click", function () { AHQ.dialogs.connectors(); });
    $("settingsBtn").addEventListener("click", function () { AHQ.dialogs.settings(); });
    load();
  }

  AHQ.log = { init: init, reload: load };
})();
