/* AGENTS HQ - dashboard bootstrap: header controls, view toggle, Run Everything, first-run tutorial. */
(function () {
  "use strict";
  var AHQ = window.AHQ = window.AHQ || {};
  var U = AHQ.util, $ = U.$, store = AHQ.store, S = store.state, api = AHQ.api, attempt = AHQ.attempt;

  var view = U.ls("view") || "office"; /* office | canvas */

  function setView(v) {
    view = v === "canvas" ? "canvas" : "office";
    U.ls("view", view);
    var board = $("board");
    board.classList.toggle("office", view === "office");
    $("viewBtn").textContent = view === "office" ? "Canvas View" : "Office View";
    $("boardLabel").textContent = view === "office" ? "Office" : "Canvas";
    AHQ.office.setOn(view === "office");
    if (view === "canvas") AHQ.board.place();
  }

  function connLabel(state) {
    return ({
      connected: "Connected",
      connecting: "Connecting",
      auth_required: "Authentication required",
      disconnected: "Disconnected",
      rate_limited: "Rate limited",
      error: "Error"
    })[state] || (state || "Unknown");
  }

  function renderConn() {
    var c = S.connection || {};
    var state = c.state || "disconnected";
    if (S.link === "lost") state = "error";
    else if (S.link === "connecting" && state === "disconnected") state = "connecting";
    var pill = $("connPill");
    pill.className = "conn " + state;
    $("connText").textContent = connLabel(state);
    pill.title = c.detail || c.error || "Codex connection. Click for details.";
    $("testMode").hidden = !S.mock;
  }

  function renderGo() {
    var btn = $("goBtn");
    var stop = $("stopBatchBtn");
    var batch = S.batch;
    var eligible = (S.eligible || []).length;
    var approvals = (S.approvals || []).length;
    btn.classList.remove("busy", "need", "done");
    stop.hidden = true;
    if (batch && batch.active) {
      btn.textContent = "Working…";
      btn.classList.add("busy");
      btn.disabled = true;
      stop.hidden = false;
    } else if (approvals) {
      btn.textContent = "Approval Required";
      btn.classList.add("need");
      btn.disabled = false;
    } else if (batch && batch.just_finished) {
      btn.textContent = "View Results";
      btn.classList.add("done");
      btn.disabled = false;
    } else {
      btn.textContent = "▶ Run Everything";
      btn.disabled = eligible === 0;
    }
  }

  function tickClock() {
    var el = $("tzClock");
    if (!el) return;
    try {
      el.textContent = new Intl.DateTimeFormat("en-GB", {
        timeZone: (S.settings && S.settings.timezone) || "Asia/Manila",
        hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false
      }).format(new Date());
    } catch (e) {
      el.textContent = new Date().toLocaleTimeString();
    }
    $("tzName").textContent = (S.settings && S.settings.timezone) || "Asia/Manila";
  }

  function bindHeader() {
    $("viewBtn").addEventListener("click", function () { setView(view === "office" ? "canvas" : "office"); });
    $("howBtn").addEventListener("click", function () { AHQ.dialogs.how(); });
    $("setupBtn").addEventListener("click", function () { AHQ.dialogs.setup(); });
    $("codexBtn").addEventListener("click", function () { AHQ.dialogs.codex(); });
    $("connPill").addEventListener("click", function () { AHQ.dialogs.codex(); });
    $("teamBtn").addEventListener("click", function () { AHQ.dialogs.team(); });
    $("collabBtn").addEventListener("click", function () { AHQ.dialogs.collab(); });
    $("goBtn").addEventListener("click", function () {
      var btn = $("goBtn");
      if (btn.classList.contains("need")) {
        var ap = (S.approvals || [])[0];
        if (ap) AHQ.panel.open(ap.agent_id, "chat");
        return;
      }
      if (btn.classList.contains("done")) {
        AHQ.dialogs.outputs();
        return;
      }
      attempt(api.post("/api/run-everything", { idempotency_key: U.uid() }), "Batch started.")
        .then(function () { store.refresh(); });
    });
    $("stopBatchBtn").addEventListener("click", function () {
      U.confirm({ title: "Stop this batch?", text: "Only tasks started by Run Everything are stopped. Scheduled work that has not started is left alone.", ok: "Stop Batch", danger: true })
        .then(function (yes) {
          if (yes) attempt(api.post("/api/run-everything/stop"), "Batch stop requested.").then(function () { store.refresh(); });
        });
    });
  }

  function banner() {
    var b = $("linkBanner");
    if (S.link === "lost") {
      b.hidden = false;
      b.className = "banner bad";
      b.textContent = "Lost connection to AGENTS HQ. Reconnecting…";
    } else if ((S.connection || {}).state === "auth_required") {
      b.hidden = false;
      b.className = "banner";
      b.textContent = "Codex needs authentication. Open Codex Integration to connect, or finish the Setup Guide.";
    } else {
      b.hidden = true;
    }
  }

  function boot() {
    U.initConfirm();
    AHQ.panel.init();
    AHQ.board.init();
    AHQ.log.init();
    bindHeader();
    store.on("state", function () { renderConn(); renderGo(); banner(); tickClock(); });
    store.on("connection", function () { renderConn(); banner(); });
    store.on("link", function () { renderConn(); banner(); });
    store.on("approvals", renderGo);
    store.on("event", function (ev) {
      if (ev && (ev.type === "batch.changed" || /^task\./.test(ev.type))) renderGo();
    });

    AHQ.office.onPick(function (id) { AHQ.panel.open(id); });
    AHQ.office.ready(function () { setView(view); });

    store.start().then(function () {
      document.title = "AGENTS HQ";
      renderConn(); renderGo(); banner(); tickClock();
      setInterval(tickClock, 1000);
      var seen = U.ls("howto") === "1" || (S.settings && S.settings.tutorial_seen);
      if (!seen) setTimeout(function () { AHQ.dialogs.how(); }, 400);
      if (!(S.settings && S.settings.setup_complete) && (S.connection || {}).state !== "connected") {
        /* Explore is allowed; only AI execution is blocked. Soft hint once. */
        if (!U.ls("setup-hint")) {
          U.ls("setup-hint", "1");
          setTimeout(function () { U.toast("Open Setup Guide when you are ready to connect Codex."); }, 1200);
        }
      }
    }, function (e) {
      U.toast(e && e.message ? e.message : "AGENTS HQ did not start.", true);
      $("connPill").className = "conn error";
      $("connText").textContent = "Error";
    });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
