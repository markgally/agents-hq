/* AGENTS HQ - safe Markdown.
 *
 * Model output, tool output and file previews are untrusted text. This renderer never builds HTML
 * strings from them: it parses a small Markdown subset and creates DOM nodes with textContent only.
 * Raw HTML in the source is shown as text. Links are limited to http(s) and mailto, open in a new
 * tab with rel="noopener noreferrer"; images are not loaded (shown as a link instead).
 */
(function () {
  "use strict";
  var AHQ = window.AHQ = window.AHQ || {};
  var U = AHQ.util, el = U.el;

  function safeUrl(url) {
    url = String(url || "").trim();
    return /^(https?:\/\/|mailto:)/i.test(url) ? url : null;
  }

  /* Inline: `code`, **bold**, *italic*, ~~strike~~, [text](url), <https://autolink>, bare URLs. */
  function inline(parent, text) {
    var re = /(`+)([\s\S]+?)\1|\*\*([^\n]+?)\*\*|__([^\n]+?)__|\*([^\s*][^*\n]*?)\*|(^|[^\w])_([^\s_][^_\n]*?)_(?!\w)|~~([^\n]+?)~~|!?\[([^\]\n]+)\]\(([^)\s]+)(?:\s+"[^"]*")?\)|<(https?:\/\/[^>\s]+)>|(https?:\/\/[^\s<>()\[\]]+[^\s<>()\[\].,;:!?'"])/g;
    var last = 0, m;
    while ((m = re.exec(text))) {
      if (m.index > last) parent.appendChild(document.createTextNode(text.slice(last, m.index)));
      if (m[2] != null) parent.appendChild(el("code", { text: m[2] }));
      else if (m[3] != null || m[4] != null) inline(parent.appendChild(el("strong")), m[3] != null ? m[3] : m[4]);
      else if (m[5] != null) inline(parent.appendChild(el("em")), m[5]);
      else if (m[7] != null) { if (m[6]) parent.appendChild(document.createTextNode(m[6])); inline(parent.appendChild(el("em")), m[7]); }
      else if (m[8] != null) inline(parent.appendChild(el("del")), m[8]);
      else if (m[9] != null) link(parent, m[9], m[10]);
      else if (m[11] != null) link(parent, m[11], m[11]);
      else if (m[12] != null) link(parent, m[12], m[12]);
      last = re.lastIndex;
    }
    if (last < text.length) parent.appendChild(document.createTextNode(text.slice(last)));
  }
  function link(parent, label, url) {
    var href = safeUrl(url);
    if (!href) { parent.appendChild(document.createTextNode(label + (label === url ? "" : " (" + url + ")"))); return; }
    parent.appendChild(el("a", { href: href, target: "_blank", rel: "noopener noreferrer", text: label }));
  }

  function codeBlock(code, lang) {
    var pre = el("pre", null, el("code", { text: code }));
    var head = el("div", { class: "codehead" }, el("span", { text: lang || "text" }),
      el("button", { type: "button", class: "mini", text: "Copy", onclick: function () { U.copy(code); } }));
    return el("div", { class: "codeblock" }, head, pre);
  }

  function splitRow(line) {
    line = line.trim().replace(/^\|/, "").replace(/\|$/, "");
    return line.split(/(?<!\\)\|/).map(function (c) { return c.trim().replace(/\\\|/g, "|"); });
  }

  function render(source) {
    var root = el("div", { class: "md" });
    var lines = String(source == null ? "" : source).replace(/\r\n?/g, "\n").split("\n");
    var i = 0, para = [];

    function flush() {
      if (!para.length) return;
      var p = el("p");
      para.forEach(function (ln, n) { if (n) p.appendChild(el("br")); inline(p, ln); });
      root.appendChild(p);
      para = [];
    }
    function listItems(ordered, indent) {
      var list = el(ordered ? "ol" : "ul"), re = ordered ? /^(\s*)\d+[.)]\s+(.*)$/ : /^(\s*)[-*+]\s+(.*)$/;
      while (i < lines.length) {
        var m = re.exec(lines[i]);
        if (!m || m[1].length < indent) break;
        if (m[1].length > indent + 1) {            /* nested list belongs to the previous item */
          var sub = listItems(/^\s*\d+[.)]\s/.test(lines[i]), m[1].length);
          (list.lastChild || list.appendChild(el("li"))).appendChild(sub);
          continue;
        }
        var li = el("li"), body = m[2], box = /^\[([ xX])\]\s+(.*)$/.exec(body);
        if (box) { li.className = "task"; li.appendChild(el("input", { type: "checkbox", disabled: true, checked: box[1] !== " " })); body = box[2]; }
        inline(li, body);
        list.appendChild(li);
        i++;
        /* continuation lines and nested lists */
        while (i < lines.length && lines[i].trim() && !re.test(lines[i]) && /^\s{2,}/.test(lines[i])) {
          if (/^\s*([-*+]|\d+[.)])\s+/.test(lines[i])) {
            var ind = /^(\s*)/.exec(lines[i])[1].length;
            li.appendChild(listItems(/^\s*\d+[.)]\s/.test(lines[i]), ind));
          } else { li.appendChild(document.createTextNode(" ")); inline(li, lines[i].trim()); i++; }
        }
      }
      return list;
    }

    while (i < lines.length) {
      var line = lines[i], m;
      if ((m = /^\s*(```+|~~~+)\s*([\w+#.-]*)\s*$/.exec(line))) {
        flush();
        var fence = m[1], lang = m[2], buf = [];
        i++;
        while (i < lines.length && lines[i].trim().indexOf(fence) !== 0) { buf.push(lines[i]); i++; }
        i++;
        root.appendChild(codeBlock(buf.join("\n"), lang));
        continue;
      }
      if (!line.trim()) { flush(); i++; continue; }
      if ((m = /^(#{1,6})\s+(.*?)\s*#*\s*$/.exec(line))) {
        flush();
        inline(root.appendChild(el("h" + Math.min(6, m[1].length + 2))), m[2]);
        i++; continue;
      }
      if (/^\s*([-*_])(\s*\1){2,}\s*$/.test(line)) { flush(); root.appendChild(el("hr")); i++; continue; }
      if (/^\s*>/.test(line)) {
        flush();
        var q = [];
        while (i < lines.length && /^\s*>/.test(lines[i])) { q.push(lines[i].replace(/^\s*>\s?/, "")); i++; }
        var bq = el("blockquote");
        bq.appendChild(render(q.join("\n")));
        root.appendChild(bq);
        continue;
      }
      if (/\|/.test(line) && i + 1 < lines.length && /^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$/.test(lines[i + 1])) {
        flush();
        var head = splitRow(line), table = el("table"), tr = el("tr");
        head.forEach(function (c) { inline(tr.appendChild(el("th")), c); });
        table.appendChild(el("thead", null, tr));
        var tb = el("tbody");
        i += 2;
        while (i < lines.length && /\|/.test(lines[i]) && lines[i].trim()) {
          var row = el("tr");
          splitRow(lines[i]).slice(0, head.length).forEach(function (c) { inline(row.appendChild(el("td")), c); });
          tb.appendChild(row);
          i++;
        }
        table.appendChild(tb);
        root.appendChild(el("div", { class: "tablewrap" }, table));
        continue;
      }
      if (/^\s*[-*+]\s+/.test(line) || /^\s*\d+[.)]\s+/.test(line)) {
        flush();
        root.appendChild(listItems(/^\s*\d+[.)]\s/.test(line), /^(\s*)/.exec(line)[1].length));
        continue;
      }
      para.push(line);
      i++;
    }
    flush();
    return root;
  }

  /* Plain text as a node (used while a reply is still streaming, and for user messages). */
  function plain(text) { return el("div", { class: "md plain", text: text == null ? "" : String(text) }); }

  AHQ.markdown = { render: render, plain: plain, safeUrl: safeUrl, codeBlock: codeBlock };
})();
