"""Developer aid: structural map of a large single-file page.

  py tools/html_map.py FILE stats            line count, longest lines, <style>/<script> positions
  py tools/html_map.py FILE funcs [A B]      top-level-ish `function name(` declarations with line numbers (range A..B)
  py tools/html_map.py FILE grep REGEX [N]   matching lines, clipped to N characters (default 160)
  py tools/html_map.py FILE ids              element ids in the markup part
"""
import re
import sys


def main():
    path, mode = sys.argv[1], sys.argv[2]
    with open(path, encoding="utf-8") as fh:
        lines = fh.read().split("\n")
    if mode == "stats":
        print("lines:", len(lines), "chars:", sum(len(l) for l in lines))
        longest = sorted(((len(l), i + 1) for i, l in enumerate(lines)), reverse=True)[:8]
        print("longest lines (len, line):", longest)
        for i, l in enumerate(lines):
            if re.search(r"</?(style|script|body|head|main|header|aside|section)\b", l) and len(l) < 300:
                print("%6d  %s" % (i + 1, l.strip()[:140]))
    elif mode == "funcs":
        a = int(sys.argv[3]) if len(sys.argv) > 3 else 1
        b = int(sys.argv[4]) if len(sys.argv) > 4 else len(lines)
        for i in range(a - 1, min(b, len(lines))):
            m = re.match(r"^(\s*)(?:async\s+)?function\s+([A-Za-z0-9_$]+)\s*\(([^)]*)\)", lines[i])
            if m and len(m.group(1)) <= 4:
                print("%6d  %s(%s)" % (i + 1, m.group(2), m.group(3)[:50]))
            else:
                m = re.match(r"^(\s{0,4})(?:const|let|var)\s+([A-Za-z0-9_$]+)\s*=", lines[i])
                if m:
                    print("%6d  %s %s" % (i + 1, "var", lines[i].strip()[:110]))
                elif re.match(r"^\s{0,4}//\s*[=\-]{3,}", lines[i]) or re.match(r"^\s{0,4}/\*", lines[i]):
                    print("%6d  %s" % (i + 1, lines[i].strip()[:120]))
    elif mode == "grep":
        rx = re.compile(sys.argv[3])
        clip = int(sys.argv[4]) if len(sys.argv) > 4 else 160
        for i, l in enumerate(lines):
            if rx.search(l):
                print("%6d  %s" % (i + 1, l.strip()[:clip]))
    elif mode == "ids":
        for i, l in enumerate(lines):
            for m in re.finditer(r'\bid="([^"]+)"', l):
                print("%6d  #%s" % (i + 1, m.group(1)))


if __name__ == "__main__":
    main()
