#!/usr/bin/env python3
"""sync_embedded.py — release packaging step for the Control Room.

The app embeds copies of the three studio tools as JS string variables
(SCRIPT_GEN, SCRIPT_EXP, SCRIPT_RES) so owners can download them from the
Data Vault. Those copies once drifted from the tools on disk (audit issue
#1). This tool removes the drift permanently: it replaces the embedded
strings in an exported Control Room HTML file with the EXACT bytes of the
canonical files in tools/, escaped the same way the app stores them.

Usage: python3 sync_embedded.py <exported-control-room.html>
The file is rewritten in place; a .bak copy is kept beside it.
Exit 0 = all three scripts synced and verified identical after re-reading.
"""
import sys, os

HERE = os.path.dirname(os.path.abspath(__file__))
CANON = {"SCRIPT_GEN": "generate_data.py",
         "SCRIPT_EXP": "export_studio.py",
         "SCRIPT_RES": "restore_studio.py"}

def js_escape(text):
    return (text.replace("\\", "\\\\")
                .replace('"', '\\"')
                .replace("'", "\\'")
                .replace("\r\n", "\n")
                .replace("\n", "\\n"))

def js_unescape(s):
    out, i = [], 0
    while i < len(s):
        if s[i] == "\\" and i + 1 < len(s):
            n = s[i + 1]
            out.append("\n" if n == "n" else n)
            i += 2
        else:
            out.append(s[i])
            i += 1
    return "".join(out)

def find_var_span(html, var):
    """Return (start, end) of the string CONTENT of `var NAME = "..."`."""
    marker = f"var {var} = \""
    i = html.find(marker)
    if i < 0:
        raise SystemExit(f"{var} not found in the HTML")
    start = i + len(marker)
    j = start
    while True:
        j = html.find('"', j)
        if j < 0:
            raise SystemExit(f"{var}: unterminated string")
        # a quote ends the string only when preceded by an even number of backslashes
        bs, k = 0, j - 1
        while k >= start and html[k] == "\\":
            bs += 1
            k -= 1
        if bs % 2 == 0:
            return start, j
        j += 1

def main():
    path = sys.argv[1]
    with open(path, encoding="utf-8") as f:
        html = f.read()
    with open(path + ".bak", "w", encoding="utf-8") as f:
        f.write(html)
    for var, fname in CANON.items():
        with open(os.path.join(HERE, fname), encoding="utf-8") as f:
            canonical = f.read()
        start, end = find_var_span(html, var)
        html = html[:start] + js_escape(canonical) + html[end:]
        print(f"{var} <- tools/{fname} ({len(canonical)} chars)")
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    # verify: re-read and unescape, demand byte equality with disk
    with open(path, encoding="utf-8") as f:
        html = f.read()
    for var, fname in CANON.items():
        with open(os.path.join(HERE, fname), encoding="utf-8") as f:
            canonical = f.read()
        start, end = find_var_span(html, var)
        if js_unescape(html[start:end]) != canonical:
            print(f"VERIFY FAILED for {var}")
            return 1
        print(f"{var} verified byte-identical to tools/{fname}")
    print("SYNC COMPLETE — embedded scripts are byte-identical to the canonical tools.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
