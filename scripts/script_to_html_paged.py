#!/usr/bin/env python3
"""Fountain to PAGINATED screenplay HTML.
Faithful FNPaginator.m port for monospace Courier (deterministic heights).
Responsive via CSS container queries with em-based sizing — whole layout scales together, no JS."""
import argparse, re, html, math
from pathlib import Path

SCENE_RE = re.compile(r'^(INT\.?|EXT\.?|EST\.?|INT\.?/EXT\.?|INT/EXT|I/E|EXT\.?/INT\.?)\b', re.I)
SCENE_NUM_RE = re.compile(r'\s*#([^#]+)#\s*$')
CUE_RE = re.compile(r"^[A-Z][A-Z0-9 '\.\-]*(\([^)]+\))?\s*$")
PAREN_RE = re.compile(r'^\s*\([^)]+\)\s*$')
TRANS_RE = re.compile(r'^(.*TO:|FADE (IN|OUT|TO BLACK)\.?|CUT TO:|DISSOLVE TO:|SMASH CUT TO:|MATCH CUT TO:)\s*$', re.I)
DIRECTIVE_RE = re.compile(r'^([A-Za-z][A-Za-z ()]*?):\s*(.*)$')
# Author-private / outline-only Fountain content — excluded from pagination AND rendering
# (Fountain spec: notes are "for the writer's eyes"; sections/synopses are outline-only).
NOTE_RE = re.compile(r'^\[\[.*\]\]$')          # standalone [[ writer's note ]]
SECTION_RE = re.compile(r'^#[^#]')              # # Section heading (NOT a #N# scene marker, which is line-end)
SYNOPSIS_RE = re.compile(r'^=[^=]')             # = synopsis (NOT === page break)

PAGE_HEIGHT = 792
TOP_BOTTOM_BUFFER = 72
# Convention-correct usable height = pageHeight - topMargin - bottomMargin = 792-72-72 = 648 (54 lines/page).
# The old `* 2.01` form (=647, 53 lines/page) carried forward a V1 FNPaginator floating-point fudge
# that no longer guards anything and cost one line per page — the primary source of Highland page drift.
# (See Fathom PAGINATION_AUDIT_2026-05-16, Category 3.)
MAX_PAGE_HEIGHT = PAGE_HEIGHT - TOP_BOTTOM_BUFFER * 2
LINE_HEIGHT = 12
CHAR_WIDTH = 7.2
WIDTH = {"Scene Heading":430,"Action":430,"General":430,"Transition":430,"Character":250,"Dialogue":250,"Parenthetical":212}
# Scene heading: 1 blank line before (matches Highland). The old value 2 (the "double space between
# scenes" convention) inflated the page count by ~1 blank line per slug. (Fathom audit Cat 1.)
SPACE_BEFORE = {"Scene Heading":1,"Action":1,"General":1,"Character":1,"Transition":1,"Dialogue":0,"Parenthetical":0}

def strip_markup(s):
    s = re.sub(r'_([^_]+)_', r'\1', s); s = re.sub(r'\*\*([^*]+)\*\*', r'\1', s); s = re.sub(r'\*([^*]+)\*', r'\1', s)
    return s.strip()
def esc(s): return html.escape(strip_markup(s))

def split_title_page(lines):
    body_start = None
    for i, l in enumerate(lines):
        s = l.strip()
        if SCENE_RE.match(s) or (s.startswith('.') and len(s)>1 and s[1].isalpha()):
            body_start = i; break
    if body_start is None: return {}, lines
    fields, cur = {}, None
    for l in lines[:body_start]:
        if not l.strip(): continue
        m = DIRECTIVE_RE.match(l)
        if m and not l.startswith((' ','\t')):
            cur = m.group(1).strip().lower(); fields[cur] = []
            if m.group(2).strip(): fields[cur].append(m.group(2).strip())
        elif cur is not None:
            if l.strip(): fields[cur].append(l.strip())
    fields = {k:v for k,v in fields.items() if v}
    return fields, lines[body_start:]

def render_title_page(f):
    if not f or "title" not in f: return ""
    def g(*ks):
        for k in ks:
            if k in f: return [esc(x) for x in f[k] if x.strip()]
        return []
    p = ['<div class="page titlepage"><div class="tp-main">']
    p.append('<div class="tp-title">' + "<br>".join(g("title")) + '</div>')
    if g("credit"): p.append('<div class="tp-credit">' + "<br>".join(g("credit")) + '</div>')
    if g("author","authors"): p.append('<div class="tp-author">' + "<br>".join(g("author","authors")) + '</div>')
    p.append('</div><div class="tp-foot">')
    if g("draft date","draft"): p.append('<div>' + "<br>".join(g("draft date","draft")) + '</div>')
    if g("contact info","contact"): p.append('<div class="tp-contact">' + "<br>".join(g("contact info","contact")) + '</div>')
    if g("revision"): p.append('<div class="tp-rev">' + "<br>".join(g("revision")) + '</div>')
    if g("notes"): p.append('<div class="tp-notes">' + " ".join(g("notes")) + '</div>')
    p.append('</div></div>')
    return "\n".join(p)

def parse_elements(lines):
    els, i = [], 0
    while i < len(lines):
        line = lines[i].strip()
        if not line: i += 1; continue
        # Sections (# …) and synopses (= …) are outline-only — never paginated or rendered.
        # Boneyard /* … */ is not present in this script; add if introduced.
        if SECTION_RE.match(line) or SYNOPSIS_RE.match(line): i += 1; continue
        # [[ writer's notes ]] are INTENTIONAL narrator notes (exported in the Highland PDF too), so they
        # ARE rendered + paginated — but as a DISTINCT note element, not as plain script action (which is
        # how the original buggy converter showed them, indistinguishable from the screenplay).
        mnote = NOTE_RE.match(line)
        if mnote:
            els.append({"type":"Note","text":line[2:-2].strip()}); i += 1; continue
        if SCENE_RE.match(line) or (line.startswith('.') and len(line)>1 and line[1].isalpha()):
            num = ''
            m = SCENE_NUM_RE.search(line)
            if m: num = m.group(1); line = SCENE_NUM_RE.sub('', line)
            els.append({"type":"Scene Heading","text":line.lstrip('.'),"num":num}); i += 1; continue
        if TRANS_RE.match(line): els.append({"type":"Transition","text":line}); i += 1; continue
        nxt = lines[i+1].strip() if i+1 < len(lines) else ''
        if CUE_RE.match(line) and not SCENE_RE.match(line) and nxt:
            els.append({"type":"Character","text":line}); i += 1
            while i < len(lines):
                d = lines[i].strip()
                if not d: break
                if SCENE_RE.match(d) or TRANS_RE.match(d) or (d.startswith('.') and len(d)>1 and d[1].isalpha()): break
                els.append({"type":"Parenthetical" if PAREN_RE.match(d) else "Dialogue","text":d}); i += 1
            continue
        buf=[line]; i+=1
        while i < len(lines):
            a = lines[i].strip()
            if not a: break
            nx = lines[i+1].strip() if i+1<len(lines) else ''
            if (SCENE_RE.match(a) or TRANS_RE.match(a) or (a.startswith('.') and len(a)>1 and a[1].isalpha())
                or (CUE_RE.match(a) and not SCENE_RE.match(a) and nx)): break
            buf.append(a); i+=1
        els.append({"type":"Action","text":" ".join(buf)})
    return els

def element_height(el):
    w = WIDTH.get(el["type"], 430); cpl = max(1, int(w // CHAR_WIDTH))
    text = strip_markup(el["text"]) or " "
    return max(1, math.ceil(len(text)/cpl)) * LINE_HEIGHT
def space_before(el, top): return 0 if top else SPACE_BEFORE.get(el["type"],1)*LINE_HEIGHT

def paginate(els):
    pages, cur, y = [], [], 0
    n = len(els); idx = 0
    while idx < n:
        el = els[idx]; sb = space_before(el, len(cur)==0); h = element_height(el)
        if el["type"] == "Character":
            block=[el]; bh=h; j=idx+1
            while j<n and els[j]["type"] in ("Dialogue","Parenthetical"):
                block.append(els[j]); bh += element_height(els[j])+space_before(els[j],False); j+=1
            if y+sb+bh <= MAX_PAGE_HEIGHT:
                if sb: y+=sb
                for b in block: cur.append(b)
                y+=bh; idx=j
            else:
                pages.append(cur); cur=[]; y=0
                if bh <= MAX_PAGE_HEIGHT:
                    for b in block: cur.append(b)
                    y=bh; idx=j
                else:
                    placed=[dict(block[0])]; ph=element_height(block[0]); k=1
                    while k<len(block):
                        bh2=element_height(block[k])+space_before(block[k],False)
                        if ph+bh2 > MAX_PAGE_HEIGHT-LINE_HEIGHT: break
                        placed.append(block[k]); ph+=bh2; k+=1
                    placed.append({"type":"More","text":"(MORE)"})
                    for b in placed: cur.append(b)
                    pages.append(cur); cur=[]; y=0
                    cont=dict(block[0]); cont["text"]=block[0]["text"]+" (CONT'D)"
                    cur.append(cont); y=element_height(cont)
                    for b in block[k:]: cur.append(b); y+=element_height(b)+space_before(b,False)
                    idx=j
            continue
        if y+sb+h > MAX_PAGE_HEIGHT and len(cur)>0:
            pages.append(cur); cur=[]; y=0; sb=0
        if sb: y+=sb
        cur.append(el); y+=h; idx+=1
    if cur: pages.append(cur)
    return pages

def render_element(el):
    t = el["type"]
    if t=="Scene Heading":
        s=f'<div class="slug">{esc(el["text"])}'
        if el.get("num"): s+=f'<span class="snum">{esc(el["num"])}</span>'
        return s+'</div>'
    if t=="Transition": return f'<div class="trans">{esc(el["text"])}</div>'
    if t=="Character": return f'<div class="cue">{esc(el["text"])}</div>'
    if t=="Parenthetical": return f'<div class="paren">{esc(el["text"])}</div>'
    if t=="Dialogue": return f'<div class="dlg">{esc(el["text"])}</div>'
    if t=="More": return '<div class="more">(MORE)</div>'
    if t=="Note": return f'<div class="note">{esc(el["text"])}</div>'
    return f'<div class="action">{esc(el["text"])}</div>'

def render_pages(pages):
    out=[]
    for pno, page in enumerate(pages,1):
        out.append(f'<div class="page"><div class="pageno">{pno}.</div>')
        for el in page: out.append(render_element(el))
        out.append('</div>')
    return "\n".join(out)

CSS = """<style>
.screenplay-wrap{container-type:inline-size}
.screenplay{font-family:'Courier New',Courier,monospace;line-height:1;color:#111;
  height:80vh;overflow-y:auto;border:1px solid #ccc;background:#e8e8e8;padding:1.5em 0;
  font-size:12pt}
.screenplay .page{background:#fff;width:51em;min-height:66em;margin:0 auto 2em;padding:6em;
  box-shadow:0 1px 6px rgba(0,0,0,.25);position:relative;box-sizing:border-box}
.screenplay .pageno{position:absolute;top:3em;right:6em;font-size:1em}
.screenplay .titlepage{display:flex;flex-direction:column;justify-content:space-between;text-align:center}
.screenplay .tp-main{margin-top:18em}
.screenplay .tp-title{font-size:1.5em;font-weight:bold;text-transform:uppercase;margin-bottom:9em}
.screenplay .tp-author{margin-top:1.8em}
.screenplay .tp-foot{font-size:.83em;line-height:1.5;margin-bottom:3em}
.screenplay .tp-notes{font-size:.67em;color:#555;margin-top:2.4em}
.screenplay .slug{font-weight:bold;text-transform:uppercase;margin:2em 0 1em;position:relative}
.screenplay .snum{position:absolute;right:0;font-weight:normal}
.screenplay .action{margin:0 0 1em}
.screenplay .cue{text-transform:uppercase;margin:1em 0 0;margin-left:12em;font-weight:bold}
.screenplay .paren{margin-left:8.4em;margin-right:9.6em}
.screenplay .dlg{margin-left:6em;margin-right:9em}
.screenplay .more{margin-left:12em}
.screenplay .trans{text-align:right;text-transform:uppercase;margin:1em 0}
.screenplay .note{margin:1em 0;padding:.5em 1em;background:#fff8dc;border-left:3px solid #c9a227;
  font-style:italic;color:#555}

@container (max-width: 850px){ .screenplay-wrap .screenplay{font-size:10pt} }
@container (max-width: 700px){ .screenplay-wrap .screenplay{font-size:8.5pt} }
@container (max-width: 550px){ .screenplay-wrap .screenplay{font-size:7pt} }
@container (max-width: 420px){ .screenplay-wrap .screenplay{font-size:5.5pt} }
</style>"""

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--out", default="script_paged.html")
    ap.add_argument("--page-height", type=int, default=None)
    args = ap.parse_args()
    global MAX_PAGE_HEIGHT
    if args.page_height: MAX_PAGE_HEIGHT = args.page_height
    lines = Path(args.input).read_text(encoding="utf-8").splitlines()
    fields, body = split_title_page(lines)
    els = parse_elements(body); pages = paginate(els)
    full = CSS + '\n<div class="screenplay-wrap"><div class="screenplay">\n' + render_title_page(fields) + '\n' + render_pages(pages) + '\n</div></div>'
    Path(args.out).write_text(full, encoding="utf-8")
    print(f"Wrote {args.out} — {len(pages)} body pages (MAX_PAGE_HEIGHT={MAX_PAGE_HEIGHT})")

if __name__ == "__main__":
    main()
