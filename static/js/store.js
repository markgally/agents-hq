/* AGENTS HQ - API client and the single front-end store.
 *
 * All real state lives on the server. The store holds the last snapshot (GET /api/state) and applies
 * the live event stream (GET /api/events, Server-Sent Events) on top of it. Views subscribe to topics
 * and redraw only their own part. Cosmetic state (office animation, card positions) is kept elsewhere.
 *
 * The browser talks only to this local server. It never talks to Codex.
 */
(function () {
  "use strict";
  var AHQ = window.AHQ = window.AHQ || {};
  var U = AHQ.util;

  /* ------------------------------------------------------------------ API */
  var token = null;
  function ApiError(status, code, message, details) {
    this.name = "ApiError"; this.status = status; this.code = code; this.message = message; this.details = details || null;
  }
  ApiError.prototype = Object.create(Error.prototype);

  function request(method, path, body) {
    var opts = { method: method, headers: {}, cache: "no-store", credentials: "same-origin" };
    if (method !== "GET") {
      opts.headers["Content-Type"] = "application/json";
      if (token) opts.headers["X-AHQ-Token"] = token;
      opts.body = JSON.stringify(body == null ? {} : body);
    }
    return fetch(path, opts).then(function (res) {
      return res.text().then(function (text) {
        var data = null;
        try { data = text ? JSON.parse(text) : null; } catch (e) { data = null; }
        if (!res.ok) {
          var err = (data && data.error) || {};
          throw new ApiError(res.status, err.code || "error", err.message || ("The server answered with status " + res.status + "."), err.details);
        }
        return data;
      });
    }, function () {
      throw new ApiError(0, "offline", "AGENTS HQ is not answering. Check that its window is still open, then try again.");
    });
  }
  var api = {
    get: function (p) { return request("GET", p); },
    post: function (p, b) { return request("POST", p, b); },
    patch: function (p, b) { return request("PATCH", p, b); },
    del: function (p) { return request("DELETE", p); },
    Error: ApiError
  };
  /* Runs an action and shows the server's own error text if it fails. Returns a promise of the result or null. */
  function attempt(promise, okText) {
    return promise.then(function (r) { if (okText) U.toast(okText); return r; },
      function (e) { U.toast(e && e.message ? e.message : "Something went wrong.", true); return null; });
  }

  /* ------------------------------------------------------------------ store */
  var S = {
    ready: false, app: "AGENTS HQ", version: "", mock: false, settings: {}, connection: { state: "connecting", detail: "" },
    agents: [], byId: {}, dependencies: [], approvals: [], batch: null, eligible: [], skipped: [], summary: {},
    link: "connecting",            /* browser <-> AGENTS HQ server: connecting | live | lost */
    lastEventId: 0
  };
  var subs = {};
  function on(topic, fn) { (subs[topic] = subs[topic] || []).push(fn); }
  function emit(topic, a, b) {
    (subs[topic] || []).forEach(function (fn) {
      try { fn(a, b); } catch (e) { if (window.console) console.error("view error in", topic, e); }
    });
  }

  function index() { S.byId = {}; S.agents.forEach(function (a) { S.byId[a.id] = a; }); }
  function agent(id) { return S.byId[id] || null; }

  function applySnapshot(snap) {
    token = snap.token;
    S.app = snap.app; S.version = snap.version; S.mock = !!snap.mock;
    S.settings = snap.settings || {};
    S.connection = snap.connection || S.connection;
    S.agents = snap.agents || [];
    S.dependencies = snap.dependencies || [];
    S.approvals = snap.approvals || [];
    S.batch = snap.batch || null;
    S.eligible = snap.eligible || [];
    S.skipped = snap.skipped || [];
    S.summary = snap.summary || {};
    if (snap.last_event_id > S.lastEventId) S.lastEventId = snap.last_event_id;
    U.setTimezone(S.settings.timezone);
    index();
    S.ready = true;
    emit("state", S);
  }

  var loading = null, again = false;
  function refresh() {
    if (loading) { again = true; return loading; }
    loading = api.get("/api/state").then(function (snap) {
      loading = null;
      applySnapshot(snap);
      if (again) { again = false; refresh(); }
      return S;
    }, function (e) { loading = null; again = false; throw e; });
    return loading;
  }
  var refreshSoon = U.debounce(function () { refresh().catch(function () {}); }, 180);

  /* ------------------------------------------------------------------ events */
  var STRUCTURAL = { "agent.updated": 1, "task.created": 1, "task.updated": 1, "task.cleared": 1, "task.completed": 1, "task.failed": 1,
    "task.cancelled": 1, "task.queued": 1, "dependency.changed": 1, "settings.changed": 1, "preset.applied": 1, "history.cleared": 1,
    "connection.changed": 1, "batch.changed": 1, "approval.requested": 1, "approval.resolved": 1, "thread.updated": 1,
    "schedule.triggered": 1, "schedule.skipped": 1, "output.created": 1 };

  function applyEvent(ev) {
    var p = ev.payload || {}, a = ev.agent_id ? agent(ev.agent_id) : null;
    if (typeof ev.id === "number" && ev.id > S.lastEventId) S.lastEventId = ev.id;

    /* Every event that carries payload.runtime carries that agent's current state. */
    if (a && p.runtime) { a.runtime = p.runtime; emit("runtime", a, ev); }
    if (ev.type === "agent.updated" && p.agent && a) {
      Object.keys(p.agent).forEach(function (k) { a[k] = p.agent[k]; });
      emit("agent", a, ev);
    }
    if (ev.type === "connection.changed" && p.connection) { S.connection = p.connection; emit("connection", S.connection); }
    if (ev.type === "approval.requested" && p.approval) {
      if (!S.approvals.some(function (x) { return x.id === p.approval.id; })) S.approvals.push(p.approval);
      emit("approvals", S.approvals, ev);
    }
    if (ev.type === "approval.resolved" && p.approval) {
      S.approvals = S.approvals.filter(function (x) { return x.id !== p.approval.id; });
      emit("approvals", S.approvals, ev);
    }
    if (ev.type === "thread.updated" && p.thread && a) { a.thread = p.thread; emit("agent", a, ev); }
    if (ev.type === "dependency.changed" && p.dependencies) { S.dependencies = p.dependencies; emit("dependencies", S.dependencies); }

    emit("event", ev);
    emit(ev.type, ev);
    if (ev.log) emit("log", ev);
    if (STRUCTURAL[ev.type]) refreshSoon();
  }

  var EVENT_TYPES = ["hello", "resync", "agent.updated", "agent.status.changed", "task.created", "task.updated", "task.cleared",
    "task.queued", "task.started", "task.progress", "task.completed", "task.failed", "task.cancelled", "message.started",
    "message.delta", "message.completed", "approval.requested", "approval.resolved", "output.created", "schedule.triggered",
    "schedule.skipped", "thread.updated", "connection.changed", "batch.changed", "dependency.changed", "settings.changed",
    "preset.applied", "history.cleared", "handoff.started", "handoff.skipped"];
  var source = null, retryTimer = 0, everLive = false;
  function setLink(v) { if (S.link !== v) { S.link = v; emit("link", v); } }

  function connectEvents() {
    if (source) { try { source.close(); } catch (e) { /* already closed */ } }
    clearTimeout(retryTimer);
    setLink(everLive ? "lost" : "connecting");
    source = new EventSource("/api/events?last_id=" + encodeURIComponent(S.lastEventId || 0));
    /* The server names every event ("event: task.started"), so each type needs its own listener;
       onmessage only receives unnamed events. */
    var handle = function (m) {
      var ev;
      try { ev = JSON.parse(m.data); } catch (e) { return; }
      if (ev.type === "hello") {
        var wasLost = S.link !== "live" && everLive;
        everLive = true;
        setLink("live");
        /* After a reconnect, take a fresh snapshot: missed events were replayed, but views that only
           hold derived data (open chat, log) reload themselves on "resync". */
        if (wasLost) { refresh().then(function () { emit("resync"); }, function () {}); }
        return;
      }
      if (ev.type === "resync") { refresh().then(function () { emit("resync"); }, function () {}); return; }
      applyEvent(ev);
    };
    EVENT_TYPES.forEach(function (t) { source.addEventListener(t, handle); });
    source.onmessage = handle;
    source.onerror = function () {
      /* The browser retries by itself while readyState is CONNECTING. If it gave up, start again. */
      setLink(everLive ? "lost" : "connecting");
      if (source && source.readyState === 2) {
        clearTimeout(retryTimer);
        retryTimer = setTimeout(function () {
          /* The server may have restarted: its write token and event numbering are new. */
          refresh().then(function () { emit("resync"); connectEvents(); }, function () { connectEvents(); });
        }, 2000);
      }
    };
  }

  function start() {
    return refresh().then(function () { connectEvents(); return S; });
  }

  /* Names for display */
  function name(id) { var a = agent(id); return a ? a.display_name : id; }

  AHQ.api = api;
  AHQ.attempt = attempt;
  AHQ.store = { state: S, on: on, emit: emit, agent: agent, name: name, refresh: refresh, refreshSoon: refreshSoon, start: start,
    applyEvent: applyEvent };
})();
