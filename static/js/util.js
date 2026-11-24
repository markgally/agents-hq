/* AGENTS HQ - small shared helpers. No network access here. */
(function () {
  "use strict";
  var AHQ = window.AHQ = window.AHQ || {};
  var PREFIX = "ahq-";

  function $(id) { return document.getElementById(id); }

  /* Local storage for cosmetic preferences only (card positions, view, sound, dismissed tips). */
  function ls(key, value) {
    try {
      if (value === undefined) return localStorage.getItem(PREFIX + key);
      if (value === null) { localStorage.removeItem(PREFIX + key); return null; }
      localStorage.setItem(PREFIX + key, String(value));
    } catch (e) { /* private mode or blocked storage: preferences simply do not persist */ }
    return value;
  }

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  /* el("div", {class: "x", text: "hi", onclick: fn, dataset: {id: 1}}, child, child...)
     Text always goes in through textContent, so nothing a model or a file says can become markup. */
  function el(tag, attrs) {
    var node = document.createElement(tag), i, key;
    attrs = attrs || {};
    for (key in attrs) {
      if (!Object.prototype.hasOwnProperty.call(attrs, key)) continue;
      var v = attrs[key];
      if (v == null || v === false) continue;
      if (key === "class") node.className = v;
      else if (key === "text") node.textContent = v;
      else if (key === "dataset") { for (var d in v) node.dataset[d] = v[d]; }
      else if (key === "style") node.style.cssText = v;
      else if (key.slice(0, 2) === "on" && typeof v === "function") node.addEventListener(key.slice(2), v);
      else if (key === "value") node.value = v;
      else if (key === "checked" || key === "disabled" || key === "selected" || key === "hidden" || key === "readOnly" || key === "open") node[key] = !!v;
      else node.setAttribute(key, v === true ? "" : v);
    }
    for (i = 2; i < arguments.length; i++) append(node, arguments[i]);
    return node;
  }
  function append(node, child) {
    if (child == null || child === false) return;
    if (Array.isArray(child)) { child.forEach(function (c) { append(node, c); }); return; }
    node.appendChild(typeof child === "string" || typeof child === "number" ? document.createTextNode(String(child)) : child);
  }
  function clear(node) { while (node.firstChild) node.removeChild(node.firstChild); return node; }

  /* ---- time ---- */
  var tz = "Asia/Manila";
  function setTimezone(name) { if (name) tz = name; }
  function fmt(iso, opts) {
    if (!iso) return "";
    var d = typeof iso === "number" ? new Date(iso * 1000) : new Date(iso);
    if (isNaN(d)) return "";
    try { return new Intl.DateTimeFormat("en-GB", Object.assign({ timeZone: tz }, opts)).format(d); }
    catch (e) { return new Intl.DateTimeFormat("en-GB", opts).format(d); }
  }
  function time(iso) { return fmt(iso, { hour: "2-digit", minute: "2-digit", hour12: false }); }
  function dayKey(iso) { return fmt(iso, { year: "numeric", month: "2-digit", day: "2-digit" }); }
  function dateTime(iso) {
    if (!iso) return "";
    var today = dayKey(new Date().toISOString());
    return dayKey(iso) === today ? "today " + time(iso)
      : fmt(iso, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", hour12: false });
  }
  function fullDateTime(iso) {
    return fmt(iso, { year: "numeric", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false });
  }
  function duration(a, b) {
    if (!a || !b) return "";
    var s = Math.max(0, Math.round((new Date(b) - new Date(a)) / 1000));
    if (s < 60) return s + " s";
    if (s < 3600) return Math.floor(s / 60) + " min " + (s % 60) + " s";
    return Math.floor(s / 3600) + " h " + Math.floor((s % 3600) / 60) + " min";
  }
  function bytes(n) {
    if (n == null) return "";
    if (n < 1024) return n + " B";
    if (n < 1048576) return (n / 1024).toFixed(1) + " KB";
    return (n / 1048576).toFixed(1) + " MB";
  }
  function clip(s, n) { s = String(s == null ? "" : s); return s.length > n ? s.slice(0, n - 1) + "\u2026" : s; }

  /* ---- robot face used on cards, in the log and in the workspace header ---- */
  var FACE = { mgr: ["green", "\u02d8 \u02d8"], cap: ["blue", "\u2022 \u2022"], "in": ["grey", "\u2013 \u2013"], sch: ["purple", "^ ^"],
               pack: ["pink", "o o"], ved: ["orange", "\u2022 \u2022"], rvs: ["lime", "\u2022 \u2022"] };
  var SPRITE_NAME = { mgr: "Green", cap: "Blue", "in": "Grey", sch: "Purple", pack: "Pink", ved: "Orange", rvs: "Lime" };
  function face(sprite, state, title) {
    var f = FACE[sprite] || FACE.cap;
    return el("div", { class: "bot " + f[0] + " " + (state || "idle"), title: title || null }, el("div", { class: "scr", text: f[1] }));
  }

  /* ---- status words shown to the user ---- */
  var STATUS = {
    idle: ["Idle", ""], scheduled: ["Scheduled", "sched"], assigned: ["Assigned", "sched"], queued: ["Queued", "queued"],
    starting: ["Starting", "working"], running: ["Working", "working"], tool: ["Using a tool", "working"],
    awaiting_approval: ["Approval needed", "waiting"], cancelling: ["Stopping", "working"], unknown: ["Needs review", "waiting"],
    completed: ["Completed", "done"], failed: ["Failed", "bad"], interrupted: ["Stopped", "bad"], cancelled: ["Cancelled", ""],
    rate_limited: ["Rate limited", "bad"], blocked: ["Blocked", "bad"], recovering: ["Recovering", "queued"], pending: ["Pending", ""],
    draft: ["Draft", ""], disabled: ["Disabled", ""]
  };
  function statusLabel(s) { return (STATUS[s] || [s || "", ""])[0]; }
  function statusClass(s) { return (STATUS[s] || ["", ""])[1]; }
  function pill(status, text) { return el("span", { class: "pill " + statusClass(status), text: text || statusLabel(status) }); }

  /* ---- toast and confirmation ---- */
  var toastTimer = 0;
  function toast(text, bad) {
    var t = $("toast");
    if (!t) return;
    t.textContent = text;
    t.classList.toggle("bad", !!bad);
    t.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { t.hidden = true; }, bad ? 5200 : 2800);
  }
  /* confirm({title, text, ok, danger, detail}) -> Promise<boolean> */
  var confirmDone = null;
  function confirm(o) {
    return new Promise(function (resolve) {
      if (confirmDone) confirmDone(false);
      $("cfmT").textContent = o.title;
      $("cfmP").textContent = o.text || "";
      var extra = $("cfmX");
      clear(extra);
      if (o.detail) append(extra, o.detail);
      $("cfmYes").textContent = o.ok || "Confirm";
      $("cfmYes").className = o.danger ? "pri danger" : "pri";
      $("cfmNo").textContent = o.cancel || "Cancel";
      $("cfm").hidden = false;
      $("cfmYes").focus();
      confirmDone = function (v) { confirmDone = null; $("cfm").hidden = true; resolve(v); };
    });
  }
  function initConfirm() {
    $("cfmYes").addEventListener("click", function () { if (confirmDone) confirmDone(true); });
    $("cfmNo").addEventListener("click", function () { if (confirmDone) confirmDone(false); });
    $("cfm").addEventListener("mousedown", function (e) { if (e.target === $("cfm") && confirmDone) confirmDone(false); });
  }
  function confirmOpen() { return !!confirmDone; }
  function confirmCancel() { if (confirmDone) confirmDone(false); }

  function copy(text) {
    var done = function () { toast("Copied."); };
    if (navigator.clipboard && navigator.clipboard.writeText) {
      return navigator.clipboard.writeText(text).then(done, function () { fallbackCopy(text); done(); });
    }
    fallbackCopy(text); done();
    return Promise.resolve();
  }
  function fallbackCopy(text) {
    var ta = el("textarea", { style: "position:fixed;left:-9999px;top:0" });
    ta.value = text;
    document.body.appendChild(ta);
    ta.select();
    try { document.execCommand("copy"); } catch (e) { /* nothing else to try */ }
    ta.remove();
  }
  function uid() {
    if (window.crypto && crypto.randomUUID) return crypto.randomUUID();
    return "k" + Date.now().toString(36) + Math.random().toString(36).slice(2, 12);
  }
  function debounce(fn, ms) {
    var t = 0;
    return function () { var a = arguments, self = this; clearTimeout(t); t = setTimeout(function () { fn.apply(self, a); }, ms); };
  }
  function reducedMotion() { return !!(window.matchMedia && matchMedia("(prefers-reduced-motion:reduce)").matches); }

  AHQ.util = {
    $: $, ls: ls, esc: esc, el: el, append: append, clear: clear, setTimezone: setTimezone, timezone: function () { return tz; },
    time: time, dateTime: dateTime, fullDateTime: fullDateTime, dayKey: dayKey, duration: duration, bytes: bytes, clip: clip,
    face: face, FACE: FACE, SPRITE_NAME: SPRITE_NAME, statusLabel: statusLabel, statusClass: statusClass, pill: pill,
    toast: toast, confirm: confirm, initConfirm: initConfirm, confirmOpen: confirmOpen, confirmCancel: confirmCancel,
    copy: copy, uid: uid, debounce: debounce, reducedMotion: reducedMotion
  };
})();
