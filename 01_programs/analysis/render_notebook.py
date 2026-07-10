#!/usr/bin/env python3
"""Render the jupytext pipeline (stage1_pipeline.py, `# %%` cells) into the
self-contained 01_notebook.html. Auto-stamps the render date+time so the
notebook regenerates in sync with each pipeline run (wired into serve.py's re-run).

Cell types: `# %% [markdown]`, `# %% [shell]`, `# %%` (code). In a code cell the
trailing run of `#`-comment lines is the captured output (interspersed comments
stay in the code). Markdown lines are joined into flowing paragraphs (blank lines
break paragraphs) so text wraps to the page, not to the .py's 72-char source wrap.
"""
import re, html, sys
from datetime import datetime

SRC = sys.argv[1] if len(sys.argv) > 1 else "stage1_pipeline.py"
OUT = sys.argv[2] if len(sys.argv) > 2 else "01_notebook.html"

CSS = """:root{--bg:#FAF9F7;--surface:#fff;--ink:#1E1B16;--ink2:#4A443B;--muted:#8A8172;--line:#E7E2D9;--sunken:#F0ECE4;--treg:#9A3E9C;--code:#F6F3EC}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font-family:'Inter Tight',system-ui,-apple-system,Segoe UI,sans-serif;font-size:14px;line-height:1.5}
.wrap{max-width:900px;margin:0 auto;padding:40px 24px 90px}
.hd{border-bottom:1px solid var(--line);padding-bottom:20px;margin-bottom:8px}
.hd h1{font-size:22px;margin:0 0 6px}
.hd .sub{color:var(--muted);font-size:13px;line-height:1.55} .hd a{color:var(--treg);text-decoration:none}
.md{margin:26px 0 10px}
.md h2,.md h3,.md h4{margin:12px 0 6px;font-weight:600;line-height:1.25}
.md h2{font-size:19px} .md h3{font-size:15.5px;padding-top:14px;border-top:1px solid var(--sunken)} .md h4{font-size:13.5px;color:var(--ink2)}
.md p{margin:5px 0;color:var(--ink2)} .md code{background:var(--sunken);border-radius:4px;padding:1px 5px;font-family:ui-monospace,Menlo,monospace;font-size:12px}
.md ul{margin:5px 0;padding-left:20px;color:var(--ink2)} .md li{margin:2px 0}
.cell{margin:12px 0}
.ci{font-family:ui-monospace,Menlo,monospace;font-size:10.5px;color:var(--treg);font-weight:600;margin-bottom:3px}
.ci.sh{color:var(--muted);text-transform:uppercase;letter-spacing:.08em;font-size:9px}
pre.code{background:var(--code);border:1px solid var(--line);border-left:3px solid var(--treg);border-radius:8px;padding:12px 14px;overflow-x:auto;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12px;line-height:1.55;color:#2B2620;margin:0;white-space:pre}
pre.code.sh{border-left-color:#3E7A5A;color:#2b3a30}
.md pre.code.sh{margin:8px 0}
pre.out{background:transparent;border-left:2px solid var(--line);padding:2px 0 2px 12px;margin:6px 0 0 2px;overflow-x:auto;font-family:ui-monospace,Menlo,monospace;font-size:11.5px;line-height:1.5;color:var(--ink2);white-space:pre-wrap;word-break:break-word}
pre.out .ol{color:var(--muted);font-size:9px;letter-spacing:.08em;text-transform:uppercase;font-weight:700}
@media(prefers-color-scheme:dark){:root{--bg:#1a1714;--surface:#221e1a;--ink:#efe9df;--ink2:#c9c1b4;--muted:#8f8779;--line:#332d26;--sunken:#2a251f;--code:#201c18}pre.code{color:#d9d2c6}pre.code.sh{color:#a9d3ba}}"""


def esc(s):
    return html.escape(s, quote=False)


def md_inline(s):
    s = esc(s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"\*(.+?)\*", r"<i>\1</i>", s)
    s = re.sub(r"`(.+?)`", r"<code>\1</code>", s)
    return s


def parse_cells(src):
    cells, cur, kind = [], [], "code"
    for line in src.splitlines():
        m = re.match(r"^# %%(.*)$", line)
        if m:
            if cur or cells:
                cells.append((kind, cur))
            tag = m.group(1).strip()
            kind = "markdown" if "markdown" in tag else "shell" if "shell" in tag else "code"
            cur = []
        else:
            cur.append(line)
    cells.append((kind, cur))
    return [(k, c) for k, c in cells if any(x.strip() for x in c)]


def strip_hash(lines):                       # "# text" -> "text", "#" -> ""
    out = []
    for ln in lines:
        if ln.strip() == "#":
            out.append("")
        elif ln.startswith("# "):
            out.append(ln[2:])
        elif ln.startswith("#"):
            out.append(ln[1:])
        else:
            out.append(ln)
    return out


def render_markdown(lines):
    lines = strip_hash(lines)
    out, para, lst, code = [], [], [], []
    in_code = False

    def flush_para():
        if para:
            out.append("<p>" + md_inline(" ".join(para)) + "</p>"); para.clear()

    def flush_list():
        if lst:
            out.append("<ul>" + "".join("<li>" + md_inline(x) + "</li>" for x in lst) + "</ul>"); lst.clear()

    def flush_code():
        if code:
            out.append('<pre class="code sh">' + esc("\n".join(code)) + "</pre>"); code.clear()

    for ln in lines:
        ln = ln.rstrip()
        fence = ln.lstrip().startswith("```")
        if in_code:                     # inside a ``` fence: accumulate verbatim, no parsing
            if fence:
                flush_code(); in_code = False
            else:
                code.append(ln)
            continue
        if fence:                       # opening fence
            flush_para(); flush_list(); in_code = True
            continue
        h = re.match(r"^(#{1,4})\s+(.*)$", ln)
        li = re.match(r"^[-*]\s+(.*)$", ln)
        cont = re.match(r"^\s+\S", ln)  # indented (hanging-indent) continuation line
        if not ln:
            flush_para(); flush_list()
        elif h:
            flush_para(); flush_list()
            lvl = min(len(h.group(1)) + 1, 4)  # page already has <h1>; # title -> h2, ## section -> h3
            out.append(f"<h{lvl}>{md_inline(h.group(2))}</h{lvl}>")
        elif li:
            flush_para(); lst.append(li.group(1))
        elif lst and cont:              # wrapped continuation folds into the open bullet
            lst[-1] += " " + ln.strip()
        elif para and cont:             # ...or into the open paragraph
            para.append(ln.strip())
        else:
            flush_list(); para.append(ln)
    flush_para(); flush_list(); flush_code()
    return '<div class="md">' + "".join(out) + "</div>"


def split_code_output(lines):
    # trailing run of comment lines (after the last code line) = captured output
    while lines and not lines[-1].strip():
        lines = lines[:-1]
    out = []
    while lines and lines[-1].lstrip().startswith("#"):
        out.insert(0, lines.pop())
    while lines and not lines[-1].strip():
        lines = lines[:-1]
    return lines, strip_hash(out)


def render_code(lines, n):
    code, output = split_code_output(lines)
    while code and not code[0].strip():
        code = code[1:]
    h = f'<div class="cell"><div class="ci">[{n}]</div><pre class="code">{esc(chr(10).join(code))}</pre>'
    if output:
        h += '<pre class="out"><span class="ol">result ▸</span>\n' + esc("\n".join(output)) + "</pre>"
    return h + "</div>"


def render_shell(lines):
    cmds = ["$ " + c for c in strip_hash(lines) if c.strip()]
    return f'<div class="cell"><div class="ci sh">shell</div><pre class="code sh">{esc(chr(10).join(cmds))}</pre></div>'


src = open(SRC).read()
now = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %Z")
body, n = [], 0
for kind, lines in parse_cells(src):
    if kind == "markdown":
        body.append(render_markdown(lines))
    elif kind == "shell":
        body.append(render_shell(lines))
    else:
        n += 1; body.append(render_code(lines, n))

header = (
    '<div class="hd"><h1>How this map was built — provenance notebook</h1>'
    '<div class="sub">A single clean pass reproducing the '
    '<a href="/01_page.html">spot · Stage-1 CD4 workbench</a> overlay end to end — '
    'data fetched from the <a href="https://virtualcellmodels.cziscience.com/dataset/genome-scale-tcell-perturb-seq" '
    'target="_blank" rel="noopener">CZI Virtual Cell Platform</a> via the <code>vcp</code> CLI, then scVI/Leiden '
    'clusters → a reproducible label rule → Masopust et al. per-cell calls → the permutation-FDR floor → two '
    'validation checks. Deterministic (fixed seed): a re-run reproduces every value below.</div>'
    f'<div class="sub" style="margin-top:9px;font-size:11.5px">Analysis built &amp; validated with '
    f'<b style="color:var(--treg)">Claude Science</b> (Anthropic\'s science workbench, on the compute host) · '
    f'auto-rendered from <code>stage1_pipeline.py</code> on <b>{now}</b>.</div></div>'
)
doc = ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
       '<meta name="viewport" content="width=device-width,initial-scale=1">'
       '<title>spot · Stage-1 provenance notebook</title><style>' + CSS + '</style></head>'
       '<body><div class="wrap">' + header + "".join(body) + "</div></body></html>")
open(OUT, "w").write(doc)
print(f"rendered {OUT} ({n} code cells) at {now}")
