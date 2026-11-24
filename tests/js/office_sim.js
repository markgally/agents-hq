/* Runs the office engine (static/js/office.js) in Node with a stand-in page and a virtual clock.
 *
 * What it checks:
 *   - the engine loads and draws in painted mode and in the procedural / box-robot fallback
 *   - all seven agents exist and keep doing idle activities
 *   - idle life makes no network request of any kind (fetch, XMLHttpRequest, EventSource, WebSocket, beacon)
 *   - an agent that gets work goes to its desk; the others keep playing
 *   - an agent pulled out of a group activity leaves alone
 *   - queued agents are not drawn as working; approval and error states show the right hologram
 *
 * Usage: node tests/js/office_sim.js            (prints one JSON line; exit code 1 on failure)
 */
"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const SRC = fs.readFileSync(path.join(__dirname, "..", "..", "static", "js", "office.js"), "utf8");

function makeWorld(search, imagesLoad) {
  let now = 1000;
  let seq = 0;
  let timers = [];
  let raf = null;
  const net = { fetch: 0, xhr: 0, es: 0, ws: 0, beacon: 0 };
  const drawn = { calls: 0, text: [] };
  const elements = {};
  const store = {};

  function ctx() {
    const target = {
      measureText: (t) => ({ width: String(t).length * 3 }),
      getImageData: (x, y, w, h) => ({ data: new Uint8ClampedArray(Math.max(1, w * h * 4)), width: w, height: h }),
      fillText: (t) => { drawn.text.push(String(t)); },
    };
    return new Proxy(target, {
      get(t, k) {
        if (k in t) return t[k];
        return function () { drawn.calls++; };
      },
      set(t, k, v) { t[k] = v; return true; },
    });
  }
  function classList() {
    const set = new Set();
    return {
      add: (...a) => a.forEach((x) => set.add(x)),
      remove: (...a) => a.forEach((x) => set.delete(x)),
      toggle: (x, on) => { if (on === undefined ? !set.has(x) : on) set.add(x); else set.delete(x); },
      contains: (x) => set.has(x),
    };
  }
  function element(id) {
    const el = {
      id, style: {}, classList: classList(), textContent: "", title: "", width: 0, height: 0,
      clientWidth: 960, clientHeight: 640, offsetWidth: 80, _html: "",
      addEventListener() {}, getContext: () => ctx(),
      getBoundingClientRect: () => ({ left: 0, top: 0, width: 960, height: 640 }),
    };
    Object.defineProperty(el, "innerHTML", {
      get() { return el._html; },
      set(v) {
        el._html = v;
        el.textContent = "";
        const re = /id="([^"]+)"/g;
        let m;
        while ((m = re.exec(v))) if (!elements[m[1]]) elements[m[1]] = element(m[1]);
      },
    });
    return el;
  }
  elements.board = element("board");
  elements.office = element("office");

  function Image() {
    const im = { width: 400, height: 320 };
    Object.defineProperty(im, "src", {
      set() {
        setTimeoutV(() => { if (imagesLoad) { if (im.onload) im.onload(); } else if (im.onerror) im.onerror(); }, 5);
      },
    });
    return im;
  }
  function setTimeoutV(fn, ms) { const id = ++seq; timers.push({ id, at: now + (ms || 0), fn }); return id; }
  function clearTimeoutV(id) { timers = timers.filter((t) => t.id !== id); }
  function setIntervalV(fn, ms) {
    const id = ++seq;
    const again = () => { timers.push({ id, at: now + ms, fn: () => { again(); fn(); } }); };
    again();
    return id;
  }

  const document = {
    hidden: false,
    getElementById: (id) => elements[id] || null,
    createElement: () => element(""),
    addEventListener() {},
  };
  const window = {
    AHQ: { util: { ls: (k, v) => { if (v === undefined) return store[k] === undefined ? null : store[k]; store[k] = String(v); return v; } } },
    addEventListener() {},
    matchMedia: () => ({ matches: false }),
    devicePixelRatio: 1,
  };
  const sandbox = {
    window, document, Image, console, Math, Date: { now: () => now }, JSON, Array, Object, String, Number, Uint8Array, Uint8ClampedArray,
    location: { search: search || "" },
    performance: { now: () => now },
    setTimeout: setTimeoutV, clearTimeout: clearTimeoutV, setInterval: setIntervalV, clearInterval: clearTimeoutV,
    requestAnimationFrame: (fn) => { raf = fn; return ++seq; },
    cancelAnimationFrame: () => { raf = null; },
    matchMedia: () => ({ matches: false }),
    fetch: () => { net.fetch++; throw new Error("network call from the office engine"); },
    XMLHttpRequest: function () { net.xhr++; },
    EventSource: function () { net.es++; },
    WebSocket: function () { net.ws++; },
    navigator: { sendBeacon: () => { net.beacon++; } },
  };
  sandbox.globalThis = sandbox;
  vm.createContext(sandbox);
  vm.runInContext(SRC, sandbox, { filename: "office.js" });

  function advance(ms) {
    const end = now + ms;
    while (now < end) {
      now += 50;
      const due = timers.filter((t) => t.at <= now).sort((a, b) => a.at - b.at);
      timers = timers.filter((t) => t.at > now);
      due.forEach((t) => t.fn());
      if (raf) { const f = raf; raf = null; f(now); }
    }
  }
  return { office: window.AHQ.office, advance, net, drawn, elements, sandbox };
}

const IDS = [1, 2, 3, 4, 5, 6, 7].map((n) => "agent-0" + n);
function agents(over) {
  return IDS.map((id, i) => Object.assign({ id, name: "Agent " + (i + 1), status: "idle", activity: "" }, (over || {})[id] || {}));
}
const fail = [];
function check(ok, what) { if (!ok) fail.push(what); }
function bot(w, id) { return w.office.stats().bots.filter((b) => b.id === id)[0]; }

function start(search, imagesLoad) {
  const w = makeWorld(search, imagesLoad);
  let readyCalled = false;
  w.office.ready(() => { readyCalled = true; });
  w.advance(200);
  check(readyCalled, "ready callback fired (" + (search || "default") + ")");
  w.office.sync(agents());
  w.office.setOn(true);
  w.advance(300);
  return w;
}

const report = {};

/* 1. Painted office, own sprite sheets. */
(function painted() {
  const w = start("", true);
  let s = w.office.stats();
  check(s.mode === "painted", "painted mode when the plate image loads");
  check(s.bots.length === 7, "seven characters");
  check(s.bots.every((b) => b.source === "individual"), "own sprite sheets in use");
  check(s.bots.every((b) => b.atDesk), "everyone starts at a desk");

  /* Ten minutes with nobody working: idle life only. */
  let away = 0;
  for (let i = 0; i < 600; i++) { w.advance(1000); if (w.office.stats().bots.some((b) => !b.atDesk)) away++; }
  s = w.office.stats();
  check(s.idleStarts >= 20, "idle activities keep starting (" + s.idleStarts + ")");
  check(away > 100, "agents leave their desks to play (" + away + " of 600 samples)");
  check(Object.values(w.net).every((n) => n === 0), "no network request during idle life");
  check(w.drawn.calls > 1000, "the canvas is being drawn");
  report.painted = { idleStarts: s.idleStarts, awaySamples: away, net: Object.assign({}, w.net) };

  /* Agent 1 gets real work: it goes to its desk; the rest stay free. */
  w.office.sync(agents({ "agent-01": { status: "running", activity: "terminal", name: "JARVIS" } }));
  w.advance(20000);
  let a1 = bot(w, "agent-01");
  check(a1.st === "working" && a1.atDesk && !a1.moving, "working agent is at its desk");
  check(a1.holo === "terminal", "hologram follows the reported activity (" + a1.holo + ")");
  check(a1.name === "JARVIS", "renamed agent keeps its slot");
  const before = w.office.stats().idleStarts;
  let othersAway = 0;
  for (let i = 0; i < 120; i++) { w.advance(1000); const st = w.office.stats(); check(bot(w, "agent-01").atDesk, "working agent stays at its desk"); if (st.bots.some((b) => b.id !== "agent-01" && !b.atDesk)) othersAway++; if (fail.length > 12) break; }
  check(w.office.stats().idleStarts > before, "the others keep starting idle activities while one agent works");
  check(othersAway > 20, "the others keep leaving their desks while one agent works (" + othersAway + ")");

  /* Pull one member out of a group activity: only that one leaves. */
  w.office.sync(agents());
  w.advance(30000);
  let started = false;
  for (let tries = 0; tries < 40 && !started; tries++) {
    w.advance(3000);
    const free = w.office.stats().bots.filter((b) => b.atDesk && !b.moving && !b.activity);
    if (free.length >= 3) started = w.office.debug.fun(free[0].id, "train");
  }
  check(started, "a group activity can be started");
  if (started) {
    w.advance(4000);
    const members = w.office.stats().bots.filter((b) => b.activity).map((b) => b.id);
    check(members.length >= 3, "group has at least three members (" + members.length + ")");
    const pulled = members[1];
    const over = {}; over[pulled] = { status: "running", activity: "thinking" };
    w.office.sync(agents(over));
    w.advance(1500);
    const st = w.office.stats();
    const still = members.filter((id) => id !== pulled && bot(w, id).activity);
    check(still.length === members.length - 1, "the other members stay in the activity (" + still.length + " of " + (members.length - 1) + ")");
    check(!bot(w, pulled).activity, "the agent with work left the activity");
    w.advance(20000);
    check(bot(w, pulled).atDesk, "the agent with work reached its desk");
    report.group = { members: members.length, pulled, stillPlaying: still.length, mode: st.mode };
  }

  /* Queued is not working; approval and unknown ask for attention; flash kinds are shown. */
  w.office.sync(agents({ "agent-02": { status: "queued" }, "agent-03": { status: "awaiting_approval" }, "agent-04": { status: "unknown" } }));
  w.advance(25000);
  const q = bot(w, "agent-02"), ap = bot(w, "agent-03"), un = bot(w, "agent-04");
  check(q.st === "queued" && q.holo === "" && q.atDesk, "queued agent waits at its desk without a work hologram");
  check(/queue/i.test(q.bubble), "queued agent says it is queued (" + q.bubble + ")");
  check(ap.st === "waiting" && ap.holo === "approval", "approval hologram");
  check(un.st === "waiting", "unknown state asks for attention");
  w.office.sync(agents());
  w.office.flash("agent-02", "error", 3000);
  w.advance(200);
  check(bot(w, "agent-02").holo === "error", "error hologram after a reported failure");
  w.advance(4000);
  check(bot(w, "agent-02").holo === "", "error hologram clears");
  w.office.flash("agent-02", "done", 3000);
  w.advance(200);
  check(bot(w, "agent-02").holo === "done", "completion hologram after a reported completion");

  /* Every activity kind draws without an error. */
  ["thinking", "typing", "scroll", "terminal", "file_read", "document", "coding", "database", "research", "test", "tool", "something_new"].forEach((kind) => {
    const over = {}; IDS.forEach((id) => { over[id] = { status: "running", activity: kind }; });
    w.office.sync(agents(over));
    w.advance(kind === "thinking" ? 30000 : 400);
    const b = bot(w, "agent-05");
    check(b.holo === (kind === "something_new" ? "thinking" : kind), "hologram kind " + kind + " (" + b.holo + ")");
  });
  check(w.office.stats().bots.every((b) => b.atDesk), "all seven at their desks when all seven work");
  check(Object.values(w.net).every((n) => n === 0), "no network request at any point (painted)");
})();

/* 2. Shared sheet fallback: own sheets missing. */
(function sheet() {
  const w = start("?assets=nosprites", true);
  const s = w.office.stats();
  check(s.mode === "painted", "painted mode with missing own sheets");
  check(s.bots.every((b) => b.source === "sheet"), "shared sheet used when own sheets are missing (" + s.bots[0].source + ")");
  w.advance(60000);
  report.sheet = { source: s.bots[0].source };
})();

/* 3. Everything missing: procedural office with box robots. */
(function procedural() {
  const w = start("?assets=none", false);
  let s = w.office.stats();
  check(s.mode === "procedural", "procedural mode when the plate is missing");
  check(s.bots.length === 7, "seven characters in the fallback office");
  check(s.bots.every((b) => b.source === "box"), "box robots when no sprite image is available (" + s.bots[0].source + ")");
  w.office.sync(agents({ "agent-06": { status: "running", activity: "coding" }, "agent-07": { status: "awaiting_approval" } }));
  w.advance(60000);
  s = w.office.stats();
  check(bot(w, "agent-06").holo === "coding" && bot(w, "agent-07").holo === "approval", "holograms in the fallback office");
  check(w.drawn.text.indexOf("AGENT 6") > -1, "room signs carry the agent names");
  check(Object.values(w.net).every((n) => n === 0), "no network request at any point (procedural)");
  report.procedural = { mode: s.mode, source: s.bots[0].source };
})();

report.ok = fail.length === 0;
report.failures = fail;
console.log(JSON.stringify(report));
process.exit(fail.length ? 1 : 0);
