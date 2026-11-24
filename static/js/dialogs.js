/* AGENTS HQ - How to Use, Setup Guide, Codex Integration, presets, collaboration, settings. */
(function () {
  "use strict";
  var AHQ = window.AHQ = window.AHQ || {};
  var U = AHQ.util, el = U.el, $ = U.$, store = AHQ.store, S = store.state, api = AHQ.api, attempt = AHQ.attempt;
  var dlg = $("dlg"), title = $("dlgTitle"), sub = $("dlgSub"), body = $("dlgBody"), foot = $("dlgFoot");
  var onClose = null;

  function open(opts) {
    title.textContent = opts.title || "";
    sub.textContent = opts.sub || "";
    $("dlgCard").className = "gcard" + (opts.size ? " " + opts.size : "");
    U.clear(body); U.clear(foot);
    if (opts.body) U.append(body, opts.body);
    if (opts.foot) U.append(foot, opts.foot);
    onClose = opts.onClose || null;
    dlg.hidden = false;
  }
  function close() {
    dlg.hidden = true;
    $("dlgCard").className = "gcard";
    if (onClose) { var fn = onClose; onClose = null; fn(); }
  }
  $("dlgClose").addEventListener("click", close);
  dlg.addEventListener("mousedown", function (e) { if (e.target === dlg) close(); });

  var AGENT_PIPS = ["#3fb27f", "#5b8def", "#8a93a5", "#8e7cf0", "#d9758f", "#f59632", "#96cd3c"];

  function pips() {
    return el("div", { class: "how-pips" }, AGENT_PIPS.map(function (c) {
      return el("i", { style: "background:" + c });
    }));
  }

  /* Tiny inline SVG scenes — decorative only, no network. */
  function howIcon(kind) {
    var svgs = {
      connect: '<svg viewBox="0 0 64 48" aria-hidden="true"><rect x="6" y="10" width="24" height="28" rx="4" fill="#1e1f21"/><rect x="10" y="14" width="16" height="10" rx="2" fill="#3fb27f"/><circle cx="14" cy="32" r="2" fill="#58c47e"/><circle cx="22" cy="32" r="2" fill="#e5b24a"/><path d="M30 24h8" stroke="#f5a300" stroke-width="2.5" stroke-linecap="round"/><circle cx="46" cy="24" r="12" fill="#fff4d6" stroke="#f5a300" stroke-width="2"/><path d="M42 24l3 3 6-7" fill="none" stroke="#1f9d63" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/></svg>',
      customize: '<svg viewBox="0 0 64 48" aria-hidden="true"><rect x="8" y="14" width="18" height="16" rx="4" fill="#3fb27f"/><rect x="12" y="17" width="10" height="7" rx="1.5" fill="#163528"/><circle cx="14" cy="20" r="1.2" fill="#9be7b9"/><circle cx="18" cy="20" r="1.2" fill="#9be7b9"/><rect x="24" y="10" width="18" height="16" rx="4" fill="#5b8def"/><rect x="28" y="13" width="10" height="7" rx="1.5" fill="#1a2a4a"/><circle cx="30" cy="16" r="1.2" fill="#b8d0ff"/><circle cx="34" cy="16" r="1.2" fill="#b8d0ff"/><rect x="40" y="18" width="18" height="16" rx="4" fill="#d9758f"/><rect x="44" y="21" width="10" height="7" rx="1.5" fill="#4a1f2c"/><circle cx="46" cy="24" r="1.2" fill="#ffd0dc"/><circle cx="50" cy="24" r="1.2" fill="#ffd0dc"/><path d="M14 38h36" stroke="#e3e8f2" stroke-width="3" stroke-linecap="round"/></svg>',
      assign: '<svg viewBox="0 0 64 48" aria-hidden="true"><rect x="10" y="8" width="44" height="32" rx="6" fill="#eef4ff" stroke="#4a8df0" stroke-width="2"/><rect x="16" y="14" width="22" height="3" rx="1.5" fill="#4a8df0"/><rect x="16" y="21" width="32" height="2.5" rx="1.2" fill="#c5d6f5"/><rect x="16" y="27" width="28" height="2.5" rx="1.2" fill="#c5d6f5"/><circle cx="48" cy="34" r="9" fill="#2bb878"/><path d="M44.5 34l2.5 2.5 5-5" fill="none" stroke="#fff" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg>',
      run: '<svg viewBox="0 0 64 48" aria-hidden="true"><circle cx="32" cy="24" r="16" fill="#1f9d63"/><path d="M27 16l16 8-16 8z" fill="#fff"/><circle cx="50" cy="12" r="3" fill="#f5a300"/><circle cx="14" cy="36" r="2.5" fill="#e5b24a"/><circle cx="52" cy="34" r="2" fill="#8fe3b3"/></svg>',
      office: '<svg viewBox="0 0 64 48" aria-hidden="true"><path d="M8 34 L32 20 L56 34 L32 48 Z" fill="#c4a574"/><path d="M20 28 L32 21 L44 28 L32 35 Z" fill="#8a93a5"/><rect x="28" y="12" width="8" height="10" rx="1" fill="#5b8def"/><circle cx="18" cy="22" r="3.5" fill="#3fb27f"/><circle cx="46" cy="22" r="3.5" fill="#d9758f"/><path d="M14 16c2-4 6-4 8 0" fill="none" stroke="#f5a300" stroke-width="1.5"/><circle cx="50" cy="14" r="2" fill="#96cd3c"/></svg>',
      results: '<svg viewBox="0 0 64 48" aria-hidden="true"><rect x="12" y="8" width="28" height="34" rx="4" fill="#fff8e6" stroke="#f5a300" stroke-width="2"/><rect x="18" y="14" width="16" height="2.5" rx="1" fill="#e5b24a"/><rect x="18" y="20" width="12" height="2.5" rx="1" fill="#f1d58a"/><rect x="18" y="26" width="14" height="2.5" rx="1" fill="#f1d58a"/><path d="M36 28l8 4v10l-8 4-8-4V32z" fill="#4a8df0"/><path d="M36 28l8 4-8 4-8-4z" fill="#6ba3f5"/><path d="M28 32v10l8 4V36z" fill="#2f6fd6"/></svg>',
      folders: '<svg viewBox="0 0 64 48" aria-hidden="true"><path d="M8 18h18l4 4h26v18a4 4 0 0 1-4 4H12a4 4 0 0 1-4-4V18z" fill="#f5a300"/><path d="M8 18V14a3 3 0 0 1 3-3h12l3 3H8z" fill="#e5b24a"/><rect x="34" y="10" width="22" height="16" rx="3" fill="#4a8df0"/><path d="M38 18h14M38 22h10" stroke="#fff" stroke-width="2" stroke-linecap="round"/></svg>',
      threads: '<svg viewBox="0 0 64 48" aria-hidden="true"><circle cx="16" cy="18" r="7" fill="#3fb27f"/><circle cx="32" cy="14" r="7" fill="#5b8def"/><circle cx="48" cy="18" r="7" fill="#d9758f"/><circle cx="24" cy="34" r="7" fill="#8e7cf0"/><circle cx="40" cy="34" r="7" fill="#f59632"/><path d="M22 22l6-4M38 20l6 2M28 28l-4-6M36 28l4-6" stroke="#c5d0e0" stroke-width="2" stroke-linecap="round"/></svg>',
      knobs: '<svg viewBox="0 0 64 48" aria-hidden="true"><rect x="8" y="10" width="48" height="28" rx="8" fill="#eef4ff" stroke="#4a8df0" stroke-width="2"/><circle cx="22" cy="24" r="8" fill="#1f9d63"/><circle cx="22" cy="24" r="3" fill="#fff"/><rect x="34" y="16" width="16" height="4" rx="2" fill="#c5d6f5"/><rect x="34" y="24" width="12" height="4" rx="2" fill="#c5d6f5"/><rect x="34" y="32" width="14" height="4" rx="2" fill="#f5a300"/></svg>',
      pulse: '<svg viewBox="0 0 64 48" aria-hidden="true"><circle cx="32" cy="24" r="14" fill="#e3f6ec" stroke="#1f9d63" stroke-width="2"/><circle cx="32" cy="24" r="6" fill="#1f9d63"/><path d="M8 24h10M46 24h10M32 8v6M32 34v6" stroke="#8fe3b3" stroke-width="2.5" stroke-linecap="round"/><circle cx="52" cy="12" r="3" fill="#f5a300"/></svg>',
      docs: '<svg viewBox="0 0 64 48" aria-hidden="true"><rect x="14" y="8" width="26" height="32" rx="3" fill="#fff" stroke="#4a8df0" stroke-width="2"/><rect x="20" y="14" width="14" height="2.5" rx="1" fill="#4a8df0"/><rect x="20" y="20" width="12" height="2" rx="1" fill="#c5d6f5"/><rect x="20" y="26" width="14" height="2" rx="1" fill="#c5d6f5"/><circle cx="48" cy="34" r="10" fill="#f5a300"/><path d="M48 28v8M44 34h8" stroke="#fff" stroke-width="2.2" stroke-linecap="round"/></svg>',
      handoff: '<svg viewBox="0 0 64 48" aria-hidden="true"><circle cx="16" cy="24" r="10" fill="#3fb27f"/><circle cx="48" cy="24" r="10" fill="#5b8def"/><path d="M26 18h8l-2-3M34 30h-8l2 3" fill="none" stroke="#f5a300" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/><path d="M26 24h12" stroke="#f5a300" stroke-width="2.4" stroke-linecap="round"/><circle cx="16" cy="22" r="1.4" fill="#9be7b9"/><circle cx="20" cy="22" r="1.4" fill="#9be7b9"/><circle cx="44" cy="22" r="1.4" fill="#b8d0ff"/><circle cx="48" cy="22" r="1.4" fill="#b8d0ff"/></svg>'
    };
    var wrap = el("div", { class: "how-art" });
    wrap.innerHTML = svgs[kind] || "";
    return wrap;
  }

  function statusTone(state) {
    var s = String(state || "").toLowerCase();
    if (s === "connected" || s === "ok" || s === "ready" || s === "active") return "green";
    if (s === "connecting" || s === "rate_limited" || s === "auth_required") return "gold";
    if (s === "error" || s === "failed" || s === "disconnected") return "pink";
    return "blue";
  }

  function how() {
    var steps = [
      { tone: "green", icon: "connect", title: "Connect Codex", blurb: "Plug in your signed-in Codex. One connection powers the whole office." },
      { tone: "blue", icon: "customize", title: "Customize your agents", blurb: "Click any of the seven cute characters. Name them, pick a role, write standing instructions." },
      { tone: "pink", icon: "assign", title: "Assign tasks", blurb: "Chat for quick asks, or save an assignment in the Tasks tab for bigger work." },
      { tone: "gold", icon: "run", title: "Run Everything", blurb: "Hit the green button. Eligible jobs queue up and run for real — idle agents keep playing." },
      { tone: "orange", icon: "office", title: "Explore the office", blurb: "Flip between Canvas and Office. Coffee, arcade, jokes, and group antics when work is quiet." },
      { tone: "lime", icon: "results", title: "Collect your results", blurb: "Grab outputs, reopen chats, and open verified files when the team is done." }
    ];
    var grid = el("div", { class: "how-grid" }, steps.map(function (s, i) {
      return el("article", { class: "how-card tone-" + s.tone },
        el("div", { class: "how-top" },
          el("span", { class: "how-num", text: String(i + 1) }),
          howIcon(s.icon)),
        el("b", { text: s.title }),
        el("p", { text: s.blurb }));
    }));
    var banner = el("div", { class: "how-banner" },
      pips(),
      el("p", { text: "Your office. Your agents. Your rules. Six quick moves and you are running a tiny AI workforce." }));
    open({
      title: "How to Use AGENTS HQ",
      sub: "Seven Agents. Endless Possibilities.",
      size: "mid",
      body: el("div", { class: "how" }, banner, grid),
      foot: el("button", { type: "button", class: "pri", text: "Let's go!", onclick: function () {
        attempt(api.patch("/api/settings", { tutorial_seen: true }));
        U.ls("howto", "1");
        close();
      }})
    });
  }

  /* ---------- Setup Guide ---------- */
  function setup() {
    var step = 0;
    var state = { setup: null };
    var meta = [
      { tone: "green", icon: "connect", title: "Codex Connection", blurb: "Detect Codex, check sign-in, and prove the wire is live." },
      { tone: "gold", icon: "folders", title: "Workspace", blurb: "Pick where agents work and where finished files land." },
      { tone: "pink", icon: "threads", title: "Agent Threads", blurb: "Seven seats ready. Threads wake lazily — zero idle tokens." },
      { tone: "blue", icon: "knobs", title: "Execution Settings", blurb: "Dial concurrency and timeouts, then open the office." }
    ];

    function load() {
      return api.get("/api/setup").then(function (r) { state.setup = r; paint(); return r; },
        function (e) { U.toast(e.message || "Could not load setup.", true); });
    }
    function paint() {
      var s = state.setup || {};
      var m = meta[step];
      U.clear(body); U.clear(foot);

      var wrap = el("div", { class: "how setup-guide" });
      wrap.appendChild(el("div", { class: "how-banner" },
        pips(),
        el("p", { text: "Four colorful stops. Connect Codex, plant your folders, meet the crew, then set the dials." })));

      var rail = el("div", { class: "setup-rail" });
      meta.forEach(function (item, i) {
        var cls = "setup-stop tone-" + item.tone + (i === step ? " on" : "") + (i < step ? " done" : "");
        rail.appendChild(el("button", {
          type: "button",
          class: cls,
          onclick: function () { step = i; paint(); }
        },
          el("span", { class: "how-num", text: String(i + 1) }),
          el("span", { class: "setup-stop-label" },
            el("b", { text: item.title }),
            el("small", { text: i < step ? "Done" : (i === step ? "You are here" : "Up next") }))
        ));
        if (i < meta.length - 1) rail.appendChild(el("i", { class: "setup-link" + (i < step ? " on" : "") }));
      });
      wrap.appendChild(rail);

      var panel = el("article", { class: "how-card setup-panel tone-" + m.tone });
      panel.appendChild(el("div", { class: "how-top" },
        el("span", { class: "how-num", text: String(step + 1) }),
        howIcon(m.icon)));
      panel.appendChild(el("b", { text: m.title }));
      panel.appendChild(el("p", { text: m.blurb }));

      if (step === 0) {
        var checks = (s.checks || []).filter(function (c) { return c.step === 1; });
        if (!checks.length) {
          var live = (S.connection || {});
          checks = [
            { label: "Codex connection", ok: live.state === "connected", detail: live.detail || live.state || "Not checked yet" }
          ];
        }
        var list = el("ul", { class: "checks" });
        checks.forEach(function (c) {
          list.appendChild(el("li", { class: c.ok ? "ok" : "no" },
            el("i", { text: c.ok ? "✓" : "!" }),
            el("div", null,
              el("b", { text: c.label || c.id || "Check" }),
              el("small", { text: c.detail || "" }))));
        });
        panel.appendChild(list);
        foot.appendChild(el("button", { type: "button", class: "pri", text: "Test / Connect", onclick: function () {
          attempt(api.post("/api/codex/connect"), "Connection checked.")
            .then(function () { return store.refresh(); })
            .then(load);
        }}));
      } else if (step === 1) {
        var ws = (S.settings || {}).default_workspace || "";
        var od = (S.settings || {}).default_output_dir || "";
        var wIn = el("input", { value: ws, style: "width:100%", placeholder: "e.g. C:\\Users\\you\\Projects" });
        var oIn = el("input", { value: od, style: "width:100%", placeholder: "e.g. C:\\Users\\you\\AGENT-HQ-outputs" });
        var fields = el("div", { class: "setup-fields" },
          el("label", null, el("span", { text: "Working folder" }), wIn),
          el("label", null, el("span", { text: "Output folder" }), oIn));
        panel.appendChild(fields);
        panel.appendChild(el("div", { class: "info-chip tone-gold" },
          el("span", { class: "info-chip-kicker", text: "Tip" }),
          el("strong", { text: "Keep both folders local" }),
          el("small", { text: "Agents only touch paths you allow. Saving also updates the allowed roots list." })));
        foot.appendChild(el("button", { type: "button", text: "Save folders", onclick: function () {
          attempt(api.patch("/api/settings", {
            default_workspace: wIn.value.trim(),
            default_output_dir: oIn.value.trim(),
            allowed_roots: [wIn.value.trim(), oIn.value.trim()].filter(Boolean)
          }), "Folders saved.").then(function () { store.refresh(); load(); });
        }}));
      } else if (step === 2) {
        var agents = S.agents || [];
        var grid = el("div", { class: "agent-chip-grid" });
        if (!agents.length) {
          panel.appendChild(el("p", { class: "mute", text: "Agent seats will appear once the office state loads." }));
        } else {
          agents.forEach(function (a, i) {
            var st2 = (a.thread && a.thread.status) || "uninitialized";
            grid.appendChild(el("div", { class: "agent-chip tone-" + (["green", "blue", "pink", "gold", "orange", "lime", "blue"][i % 7]) },
              U.face(a.sprite_key, "idle", a.display_name),
              el("div", null,
                el("b", { text: a.display_name }),
                el("small", { text: st2 }))));
          });
          panel.appendChild(grid);
        }
        panel.appendChild(el("div", { class: "info-chip tone-pink" },
          el("span", { class: "info-chip-kicker", text: "Idle policy" }),
          el("strong", { text: "No idle Codex calls" }),
          el("small", { text: "Coffee, arcade, and office antics are local animation only." })));
      } else {
        var conc = el("input", { type: "number", min: "1", max: "7", value: String((S.settings || {}).concurrency || 2) });
        var to = el("input", { type: "number", min: "60", value: String((S.settings || {}).default_timeout_sec || 1800) });
        panel.appendChild(el("div", { class: "setup-fields dual" },
          el("label", null, el("span", { text: "Max concurrent agents (1–7)" }), conc),
          el("label", null, el("span", { text: "Default task timeout (seconds)" }), to)));
        panel.appendChild(el("div", { class: "info-chip tone-blue" },
          el("span", { class: "info-chip-kicker", text: "Timezone" }),
          el("strong", { text: (S.settings || {}).timezone || "Asia/Manila" }),
          el("small", { text: "Schedules store in UTC and display in this zone." })));
        foot.appendChild(el("button", { type: "button", text: "Save settings", onclick: function () {
          attempt(api.patch("/api/settings", {
            concurrency: Number(conc.value),
            default_timeout_sec: Number(to.value)
          }), "Settings saved.").then(function () { store.refresh(); });
        }}));
        foot.appendChild(el("button", { type: "button", class: "pri", text: "Finish Setup", onclick: function () {
          attempt(api.post("/api/setup/finish"), "Setup complete.").then(function (r) {
            if (r) { close(); store.refresh(); }
          });
        }}));
      }

      wrap.appendChild(panel);
      body.appendChild(wrap);

      if (step > 0) foot.appendChild(el("button", { type: "button", text: "Back", onclick: function () { step--; paint(); } }));
      if (step < 3) foot.appendChild(el("button", { type: "button", class: "pri", text: "Next", onclick: function () { step++; paint(); } }));
    }
    open({ title: "Setup Guide", sub: "Four colorful stops to open the office", size: "mid", body: el("div"), foot: el("div") });
    load();
  }

  /* ---------- Codex Integration ---------- */
  function codex() {
    var box = el("div", { class: "how codex-panel", text: "Loading…" });
    var tones = ["green", "blue", "pink", "gold", "orange", "lime", "blue"];

    function connFrom(st) {
      return (st && (st.codex || st.connection)) || st || {};
    }
    function accountLine(conn) {
      var acc = conn.account || {};
      if (conn.signed_in || conn.logged_in) {
        return "Signed in via " + (acc.type || conn.login_method || "ChatGPT")
          + (acc.plan ? (" · " + acc.plan + " plan") : "");
      }
      return conn.detail || conn.error || "Authorize with the supported sign-in method, then hit Connect.";
    }
    function paintAgents(threadBox) {
      U.clear(threadBox);
      var agents = S.agents || [];
      if (!agents.length) {
        threadBox.appendChild(el("div", { class: "info-chip tone-blue" },
          el("span", { class: "info-chip-kicker", text: "Waiting" }),
          el("strong", { text: "Office state still loading" }),
          el("small", { text: "Refresh once agents appear on the board." })));
        return;
      }
      agents.forEach(function (a, i) {
        var t = a.thread || {};
        var has = !!t.provider_thread_id;
        var stLabel = t.status || "uninitialized";
        var detail = has
          ? (stLabel + " · " + U.clip(t.provider_thread_id, 28))
          : (t.detail || "No thread yet — created on first chat or Run Now");
        var resumeBtn = el("button", {
          type: "button", class: "mini", text: "Resume",
          disabled: !has || stLabel === "uninitialized",
          title: has ? "Reopen this agent's saved Codex thread" : "No thread to resume yet",
          onclick: function () {
            attempt(api.post("/api/agents/" + a.id + "/thread/resume"), "Resumed.")
              .then(function () { return store.refresh(); })
              .then(reload);
          }
        });
        var resetBtn = el("button", {
          type: "button", class: "mini", text: "Reset",
          disabled: !has,
          title: has ? "Clear the local link. Codex keeps the conversation." : "Nothing to reset",
          onclick: function () {
            U.confirm({
              title: "Reset " + a.display_name + "'s thread?",
              text: "The local association is cleared. Conversation history in Codex is not deleted. A new thread is created the next time this agent runs.",
              ok: "Reset", danger: true
            }).then(function (yes) {
              if (!yes) return;
              attempt(api.post("/api/agents/" + a.id + "/thread/reset", { confirm: true }), "Thread reset.")
                .then(function () { return store.refresh(); })
                .then(reload);
            });
          }
        });
        threadBox.appendChild(el("div", { class: "agent-chip wide tone-" + tones[i % tones.length] },
          U.face(a.sprite_key, "idle", a.display_name),
          el("div", { class: "grow" },
            el("b", { text: a.display_name }),
            el("small", { text: detail }),
            t.status === "unavailable" && t.detail ? el("small", { class: "err", text: t.detail }) : null),
          el("div", { class: "row" }, resumeBtn, resetBtn)));
      });
    }
    function paintDiscover(holder) {
      U.clear(holder);
      holder.appendChild(el("p", { class: "mute", text: "Loading Codex threads…" }));
      api.get("/api/codex/threads").then(function (r) {
        U.clear(holder);
        var list = (r && r.threads) || [];
        if (!list.length) {
          holder.appendChild(el("div", { class: "info-chip tone-blue" },
            el("span", { class: "info-chip-kicker", text: "Codex list" }),
            el("strong", { text: "No threads returned" }),
            el("small", { text: "Codex had nothing to list for this account right now." })));
          return;
        }
        var grid = el("div", { class: "discover-grid" });
        list.slice(0, 12).forEach(function (t) {
          var claimed = t.claimed_by ? store.name(t.claimed_by) : null;
          grid.appendChild(el("div", { class: "discover-card" + (t.from_agent_hq ? " hq" : "") },
            el("b", { text: t.name || "(untitled thread)" }),
            el("small", { text: U.clip(t.preview || "", 90) || "No preview" }),
            el("div", { class: "discover-meta" },
              el("span", { class: "stat " + (claimed ? "connected" : ""), text: claimed ? ("Linked to " + claimed) : "Unclaimed" }),
              t.from_agent_hq ? el("span", { class: "cap", text: "AGENTS HQ" }) : null)));
        });
        holder.appendChild(grid);
        if (list.length > 12) {
          holder.appendChild(el("p", { class: "mute mt", text: "Showing 12 of " + list.length + " Codex threads." }));
        }
      }, function (e) {
        U.clear(holder);
        holder.appendChild(el("div", { class: "info-chip tone-gold" },
          el("span", { class: "info-chip-kicker", text: "Codex list" }),
          el("strong", { text: "Could not list remote threads" }),
          el("small", { text: (e && e.message) || "thread/list may be unavailable. Agent seats above still work from local state." })));
      });
    }

    function reload() {
      return api.get("/api/codex/status").then(function (st) {
        U.clear(box);
        var conn = connFrom(st);
        var stName = conn.state || conn.status || "—";
        var tone = statusTone(stName);
        var caps = conn.capabilities || null;

        box.appendChild(el("div", { class: "how-banner" },
          pips(),
          el("p", { text: "One Codex pipe powers all seven agents. Connect, poke the wire, then manage threads." })));

        var hero = el("article", { class: "how-card tone-" + tone });
        hero.appendChild(el("div", { class: "how-top" },
          el("span", { class: "stat " + (stName === "connected" ? "connected" : ""), text: stName }),
          howIcon(stName === "connected" ? "pulse" : "connect")));
        hero.appendChild(el("b", { text: conn.provider || "Codex App Server" }));
        hero.appendChild(el("p", { text: accountLine(conn) }));
        if (conn.detail && (conn.signed_in || conn.logged_in)) {
          hero.appendChild(el("p", { class: "mute", text: conn.detail }));
        }

        var facts = el("div", { class: "fact-row" });
        [
          { k: "Version", v: conn.version || "—" },
          { k: "Executable", v: conn.executable || conn.path || "Not detected" },
          { k: "Model", v: conn.default_model || "—" }
        ].forEach(function (f) {
          facts.appendChild(el("div", { class: "fact" },
            el("span", { text: f.k }),
            el("strong", { text: f.v })));
        });
        hero.appendChild(facts);
        box.appendChild(hero);

        var actions = el("div", { class: "row mt codex-actions" });
        actions.appendChild(el("button", { type: "button", class: "pri", text: "Connect", onclick: function () {
          attempt(api.post("/api/codex/connect"), "Connected.").then(function () { return store.refresh(); }).then(reload);
        }}));
        actions.appendChild(el("button", { type: "button", text: "Disconnect", onclick: function () {
          U.confirm({ title: "Disconnect Codex?", text: "Active turns will be interrupted safely where possible.", ok: "Disconnect", danger: true })
            .then(function (yes) {
              if (yes) attempt(api.post("/api/codex/disconnect"), "Disconnected.")
                .then(function () { return store.refresh(); }).then(reload);
            });
        }}));
        actions.appendChild(el("button", { type: "button", text: "Test", onclick: function () {
          attempt(api.post("/api/codex/test"), "Test OK.").then(function () { return store.refresh(); }).then(reload);
        }}));
        actions.appendChild(el("button", { type: "button", text: "Refresh", onclick: function () {
          store.refresh().then(reload);
        }}));
        box.appendChild(actions);

        if (caps && typeof caps === "object") {
          var keys = Object.keys(caps).filter(function (k) { return caps[k]; }).slice(0, 12);
          if (keys.length) {
            box.appendChild(el("div", { class: "caps mt" }, keys.map(function (k) {
              return el("span", { class: "cap", text: k });
            })));
          }
        }

        box.appendChild(el("div", { class: "section-head mt" },
          el("div", null,
            el("b", { text: "Agent threads" }),
            el("p", { class: "mute", text: "Local seat for each of the seven agents. Resume reopens a saved Codex thread; Reset only clears AGENTS HQ's link." })),
          howIcon("threads")));

        var threadBox = el("div", { class: "agent-chip-grid" });
        box.appendChild(threadBox);
        paintAgents(threadBox);

        box.appendChild(el("div", { class: "section-head mt" },
          el("div", null,
            el("b", { text: "Codex thread browser" }),
            el("p", { class: "mute", text: "What Codex itself lists for this account. Linked seats show who claimed them." })),
          howIcon("docs")));
        var discover = el("div", { class: "discover-wrap" });
        box.appendChild(discover);
        paintDiscover(discover);

        box.appendChild(el("div", { class: "docs-link mt" },
          howIcon("docs"),
          el("a", { href: "https://developers.openai.com/blog/codex-as-a-platform", target: "_blank", rel: "noopener", text: "Official Codex documentation" })));
      }, function (e) {
        U.clear(box);
        box.appendChild(el("p", { class: "err", text: e.message || "Could not load Codex status." }));
      });
    }
    open({ title: "Codex Integration", sub: "Connection, pulse check, and thread registry", size: "mid", body: box });
    store.refresh().then(reload, reload);
  }

  /* ---------- Team presets ---------- */
  function team() {
    var box = el("div", { text: "Loading presets…" });
    var selected = null;
    var tones = ["green", "blue", "pink", "gold", "orange", "lime", "blue"];

    function applySelected() {
      if (!selected) return;
      U.confirm({
        title: "Apply " + selected.name + "?",
        text: "Only names, roles, and instructions change.\n\nThreads, conversation history, permissions, and assignments stay as they are. No agent starts working.",
        ok: "Apply preset"
      }).then(function (yes) {
        if (!yes) return;
        attempt(api.post("/api/presets/apply", { preset_id: selected.id, confirm: true }), "Preset applied.")
          .then(function (r) {
            if (!r) return;
            close();
            store.refresh();
          });
      });
    }

    function paintPreview(holder, preset) {
      U.clear(holder);
      if (!preset) {
        holder.appendChild(el("p", { class: "mute", text: "Pick a preset on the left to preview the seven roles." }));
        return;
      }
      holder.appendChild(el("b", { class: "preset-title", text: preset.name }));
      holder.appendChild(el("p", { class: "mute", text: preset.summary || "" }));
      var list = el("div", { class: "preset-agents" });
      (preset.agents || []).forEach(function (spec, i) {
        var live = store.agent(spec.agent_id);
        var sprite = (live && live.sprite_key) || "cap";
        list.appendChild(el("div", { class: "agent-chip tone-" + tones[i % tones.length] },
          U.face(sprite, "idle", spec.display_name || spec.role),
          el("div", null,
            el("b", { text: spec.display_name || spec.role || spec.agent_id }),
            el("small", { text: spec.role || "" }),
            spec.instructions ? el("small", { text: U.clip(spec.instructions, 110) }) : null)));
      });
      holder.appendChild(list);
    }

    function paint(presets) {
      U.clear(box);
      if (!presets.length) {
        box.appendChild(el("p", { class: "mute", text: "No team presets are available." }));
        return;
      }
      if (!selected) selected = presets[0];

      var list = el("div", { class: "pl" });
      var preview = el("div", { class: "pr" });
      presets.forEach(function (p) {
        list.appendChild(el("button", {
          type: "button",
          "aria-selected": selected && selected.id === p.id ? "true" : "false",
          onclick: function () {
            selected = p;
            paint(presets);
          }
        },
          p.name,
          el("small", { text: p.summary || (p.agents || []).length + " agents" })));
      });
      paintPreview(preview, selected);
      box.appendChild(el("div", { class: "presets" }, list, preview));
    }

    open({
      title: "Team presets",
      sub: "Preview a roster, then apply. Threads and history stay intact.",
      size: "mid",
      body: box,
      foot: el("button", {
        type: "button", class: "pri", text: "Apply selected preset",
        onclick: applySelected
      })
    });

    api.get("/api/presets").then(function (r) {
      paint(r.presets || []);
    }, function (e) {
      U.clear(box);
      box.appendChild(el("p", { class: "err", text: e.message || "Could not load presets." }));
    });
  }

  /* ---------- Collaboration ---------- */
  function collab() {
    var box = el("div", { class: "how collab-panel" });
    var tones = ["green", "blue", "pink", "gold", "orange", "lime", "blue"];

    function agentOptions(selectedId, skipId) {
      return (S.agents || []).filter(function (a) { return a.id !== skipId; }).map(function (a) {
        return el("option", { value: a.id, selected: a.id === selectedId, text: a.display_name });
      });
    }
    function condLabel(c) {
      return c === "on_finish" ? "When finished (any outcome)" : "When successful";
    }
    function xferLabel(t) {
      return t === "none" ? "Signal only" : "Pass the result";
    }

    function paint() {
      U.clear(box);
      var enabled = !!(S.settings || {}).collaboration_enabled;
      var deps = S.dependencies || [];

      box.appendChild(el("div", { class: "how-banner" },
        pips(),
        el("p", { text: "Real hand-offs between agents. Office jokes and coffee chats stay cosmetic — they never move work." })));

      var power = el("article", { class: "how-card tone-" + (enabled ? "green" : "gold") });
      power.appendChild(el("div", { class: "how-top" },
        el("span", { class: "stat " + (enabled ? "connected" : "configuration_required"), text: enabled ? "ON" : "OFF" }),
        howIcon("handoff")));
      power.appendChild(el("b", { text: enabled ? "Collaboration is live" : "Collaboration is paused" }));
      power.appendChild(el("p", { text: enabled
        ? "Canvas wires light up for configured routes. A finished run can pass work to the next agent."
        : "Turn this on to draw routes between agents. Nothing runs until you add a hand-off and a real task finishes." }));
      power.appendChild(el("div", { class: "row mt" },
        el("button", {
          type: "button",
          class: enabled ? "" : "pri",
          text: enabled ? "Turn collaboration off" : "Enable collaboration",
          onclick: function () {
            attempt(api.patch("/api/settings", { collaboration_enabled: !enabled }),
              enabled ? "Collaboration off." : "Collaboration on.")
              .then(function () { return store.refresh(); })
              .then(paint);
          }
        })));
      box.appendChild(power);

      if (!enabled) {
        box.appendChild(el("div", { class: "info-chip tone-gold" },
          el("span", { class: "info-chip-kicker", text: "How it works" }),
          el("strong", { text: "Opt-in routes, not automatic chatter" }),
          el("small", { text: "1) Enable collaboration  2) Add From → To hand-offs  3) Run a task — on success (or finish), the next agent can pick up the result." })));
        return;
      }

      var srcDefault = (S.agents[0] && S.agents[0].id) || "";
      var dstDefault = (S.agents[1] && S.agents[1].id) || srcDefault;
      var src = el("select", { "aria-label": "From agent" }, agentOptions(srcDefault));
      var dst = el("select", { "aria-label": "To agent" }, agentOptions(dstDefault, srcDefault));
      var cond = el("select", { "aria-label": "When to hand off" },
        el("option", { value: "on_success", selected: true, text: "When successful" }),
        el("option", { value: "on_finish", text: "When finished (any outcome)" }));
      var xfer = el("select", { "aria-label": "What to transfer" },
        el("option", { value: "result", selected: true, text: "Pass the result" }),
        el("option", { value: "none", text: "Signal only" }));
      var needApproval = el("input", { type: "checkbox", id: "collabApprove" });

      src.addEventListener("change", function () {
        var keep = dst.value;
        U.clear(dst);
        agentOptions(keep === src.value ? "" : keep, src.value).forEach(function (o) { dst.appendChild(o); });
        if (!dst.value && dst.options.length) dst.selectedIndex = 0;
      });

      var composer = el("article", { class: "how-card tone-blue collab-composer" });
      composer.appendChild(el("div", { class: "how-top" },
        el("span", { class: "how-num", text: "+" }),
        howIcon("threads")));
      composer.appendChild(el("b", { text: "Add a hand-off" }));
      composer.appendChild(el("p", { text: "Pick who finishes work and who receives it next. Loops are blocked." }));
      composer.appendChild(el("div", { class: "collab-flow" },
        el("label", { class: "collab-field" }, el("span", { text: "From" }), src),
        el("div", { class: "collab-arrow", "aria-hidden": "true", text: "→" }),
        el("label", { class: "collab-field" }, el("span", { text: "To" }), dst)));
      composer.appendChild(el("div", { class: "collab-options" },
        el("label", { class: "collab-field" }, el("span", { text: "Trigger" }), cond),
        el("label", { class: "collab-field" }, el("span", { text: "Transfer" }), xfer),
        el("label", { class: "collab-check" }, needApproval, el("span", { text: "Ask me before the hand-off runs" }))));
      composer.appendChild(el("div", { class: "row mt" },
        el("button", {
          type: "button", class: "pri", text: "Add hand-off",
          onclick: function () {
            if (src.value === dst.value) {
              U.toast("Pick two different agents.", true);
              return;
            }
            attempt(api.post("/api/dependencies", {
              source_agent_id: src.value,
              destination_agent_id: dst.value,
              condition: cond.value,
              transfer: xfer.value,
              require_approval: !!needApproval.checked
            }), "Hand-off added.").then(function () { return store.refresh(); }).then(paint);
          }
        })));
      box.appendChild(composer);

      box.appendChild(el("div", { class: "section-head mt" },
        el("div", null,
          el("b", { text: "Active routes" }),
          el("p", { class: "mute", text: deps.length
            ? (deps.length + " hand-off" + (deps.length === 1 ? "" : "s") + " on the canvas.")
            : "No routes yet — add one above. Wires appear on Canvas View." })),
        howIcon("office")));

      if (!deps.length) {
        box.appendChild(el("div", { class: "info-chip tone-blue" },
          el("span", { class: "info-chip-kicker", text: "Empty map" }),
          el("strong", { text: "Waiting for the first route" }),
          el("small", { text: "Example: Researcher → Content Writer when successful, passing the result." })));
        return;
      }

      var list = el("div", { class: "collab-routes" });
      deps.forEach(function (d, i) {
        var from = store.agent(d.source_agent_id);
        var to = store.agent(d.destination_agent_id);
        var card = el("div", { class: "collab-route tone-" + tones[i % tones.length] + (d.enabled === false ? " off" : "") },
          el("div", { class: "collab-route-agents" },
            from ? U.face(from.sprite_key, "idle", from.display_name) : el("div", { class: "sysi", text: "?" }),
            el("div", { class: "collab-route-names" },
              el("b", { text: store.name(d.source_agent_id) }),
              el("span", { class: "collab-arrow", text: "→" }),
              el("b", { text: store.name(d.destination_agent_id) })),
            to ? U.face(to.sprite_key, "idle", to.display_name) : null),
          el("div", { class: "collab-route-meta" },
            el("span", { class: "cap", text: condLabel(d.condition) }),
            el("span", { class: "cap", text: xferLabel(d.transfer) }),
            d.require_approval ? el("span", { class: "cap", text: "Needs approval" }) : null,
            d.enabled === false ? el("span", { class: "cap no", text: "Paused" }) : null),
          el("div", { class: "row" },
            el("button", {
              type: "button", class: "mini",
              text: d.enabled === false ? "Enable" : "Pause",
              onclick: function () {
                attempt(api.patch("/api/dependencies/" + d.id, { enabled: d.enabled === false }),
                  d.enabled === false ? "Hand-off enabled." : "Hand-off paused.")
                  .then(function () { return store.refresh(); }).then(paint);
              }
            }),
            el("button", {
              type: "button", class: "mini", text: "Remove",
              onclick: function () {
                U.confirm({
                  title: "Remove this hand-off?",
                  text: store.name(d.source_agent_id) + " will no longer pass work to " + store.name(d.destination_agent_id) + ".",
                  ok: "Remove", danger: true
                }).then(function (yes) {
                  if (!yes) return;
                  attempt(api.del("/api/dependencies/" + d.id), "Removed.")
                    .then(function () { return store.refresh(); }).then(paint);
                });
              }
            })));
        list.appendChild(card);
      });
      box.appendChild(list);
    }

    open({
      title: "Collaboration",
      sub: "Optional hand-offs — wires on the canvas, work on success",
      size: "mid",
      body: box
    });
    paint();
  }

  /* ---------- Outputs aggregate ---------- */
  function outputs() {
    var box = el("div", { text: "Loading…" });
    open({ title: "All outputs", sub: "Verified results only", body: box });
    api.get("/api/outputs").then(function (r) {
      U.clear(box);
      var list = (r && r.outputs) || [];
      if (!list.length) { box.appendChild(el("div", { class: "empty", text: "No outputs yet." })); return; }
      list.forEach(function (o) {
        box.appendChild(el("div", { class: "box", onclick: function () {
          close();
          AHQ.panel.openOutput(o.agent_id, o.id);
        }},
          el("b", { text: o.title || "Output" }),
          el("div", { class: "mute", text: store.name(o.agent_id) + " · " + U.dateTime(o.created_at) })
        ));
      });
    }, function (e) { U.clear(box); box.appendChild(el("p", { class: "err", text: e.message })); });
  }

  /* ---------- Connectors ---------- */
  function connectors() {
    var box = el("div", { text: "Loading…" });
    open({ title: "Integrations", sub: "Only real Codex / MCP capabilities are listed", body: box });
    api.get("/api/connectors").then(function (r) {
      U.clear(box);
      var items = (r && r.connectors) || [];
      if (!items.length) {
        box.appendChild(el("p", { class: "mute", text: "No optional integrations are available in the connected Codex yet. AGENTS HQ works without them." }));
        return;
      }
      items.forEach(function (c) {
        box.appendChild(el("div", { class: "box row between" },
          el("div", null, el("b", { text: c.name || c.id }), el("div", { class: "mute", text: c.detail || "" })),
          el("span", { class: "stat " + (c.status || "unsupported"), text: c.status || "unsupported" })));
      });
    }, function (e) {
      U.clear(box);
      box.appendChild(el("p", { class: "mute", text: "Integrations are unavailable until Codex is connected." }));
    });
  }

  /* ---------- Settings ---------- */
  function settings() {
    var box = el("div");
    var s = S.settings || {};
    var conc = el("input", { type: "number", min: "1", max: "7", value: String(s.concurrency || 2) });
    var tz = el("input", { value: s.timezone || "Asia/Manila" });
    box.appendChild(el("label", { text: "Concurrency" }));
    box.appendChild(conc);
    box.appendChild(el("label", { class: "mt", text: "Timezone" }));
    box.appendChild(tz);
    open({
      title: "Settings",
      body: box,
      foot: el("button", { type: "button", class: "pri", text: "Save", onclick: function () {
        attempt(api.patch("/api/settings", {
          concurrency: Number(conc.value),
          timezone: tz.value.trim()
        }), "Saved.").then(function () { close(); store.refresh(); });
      }})
    });
  }

  AHQ.dialogs = {
    open: open, close: close, how: how, setup: setup, codex: codex,
    team: team, collab: collab, outputs: outputs, connectors: connectors, settings: settings
  };
})();
