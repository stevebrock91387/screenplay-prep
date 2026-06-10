#!/usr/bin/env python3
"""
scripts/reconcile.py — Reconcile pagination-dependent facts to the current Highland PDF.

Run after committing a new .highland + PDF pair. The script:
  1. Verifies the .highland and committed PDF are in sync (same check as pre-commit hook).
  2. Derives CANONICAL_PAGES from the PDF (script-body, title page excluded).
  3. Recomputes Runtime Model section headers, scene CSV, runtime estimates.
  4. Audits CANONICAL_FACTS.md row-by-row against the documents it governs.
  5. Greps the repo for stale page-count references.
  6. Reports everything. Applies only with --apply, and only after human gates are resolved.

Usage:
  scripts/reconcile.py                       # report mode (no writes)
  scripts/reconcile.py --apply               # apply derived changes (no manual gates blocking)
  scripts/reconcile.py --categories FILE     # provide user-decided categories for uncertain scenes
  scripts/reconcile.py --approve-stale FILE  # provide approved stale-ref fixes

Hard rules:
  - Cannot render the PDF (Highland is GUI-only). Stops if .highland != PDF baseline.
  - Two human gates are mandatory stops, not optional:
      Gate 1 — Scene categorization for genuinely uncertain scenes.
      Gate 2 — Stale-reference approval before applying corrections.
  - Never commits. Presents diffs and waits for you.
  - Idempotent: a clean repo reports "nothing to reconcile" and exits 0.

Dependencies: python3, pypdf, plus stdlib + git.
"""

import argparse
import csv
import hashlib
import json
import os
import re
import subprocess
import sys
import zipfile
from pathlib import Path

# -------------------- Paths --------------------
# Project root: $CLAUDE_PROJECT_DIR when set (so this script works when bundled in
# the screenplay-prep plugin and run against another project), else the repo this
# script lives in (direct in-repo runs).
REPO_ROOT = Path(os.environ["CLAUDE_PROJECT_DIR"]) if os.environ.get("CLAUDE_PROJECT_DIR") \
    else Path(__file__).resolve().parent.parent

P = {
    "highland":       REPO_ROOT / "Blank Slate Full Script.highland",
    "pdf":            REPO_ROOT / "Blank Slate Full Script.pdf",
    # script_text is this script's PARSE BASELINE — the scene_csv keys every scene
    # to its line_start/line_end, so its line numbers must stay stable. It is NOT a
    # verbatim copy of the live screenplay: the pre-commit hook intentionally does
    # NOT refresh it (that hook maintains the body-only .fountain).
    # Refreshing this file means re-running reconcile.py --apply so scene_csv's line
    # numbers are recomputed in lock-step. Do NOT hand-edit it or auto-copy text.md
    # into it — either silently desyncs the 82-scene CSV. For an always-current
    # plain-text copy of the script, use the tracked .fountain instead.
    "script_text":    REPO_ROOT / "Claude Docs" / "Blank_Slate_Full_Script_text.md",
    "scene_csv":      REPO_ROOT / "Claude Docs" / "blank_slate_scenes.csv",
    "runtime_model":  REPO_ROOT / "Claude Docs" / "Blank_Slate_Runtime_Model.md",
    "runtime_py":     REPO_ROOT / "Claude Docs" / "runtime_model.py",
    "runtime_config": REPO_ROOT / "Claude Docs" / "runtime_config.json",
    "canonical":      REPO_ROOT / "Claude Docs" / "CANONICAL_FACTS.md",
    "script_state":   REPO_ROOT / ".script-state",
}

TABLE_READ_RATIO = 1.25

# -------------------- Output helpers --------------------
USE_COLOR = sys.stdout.isatty()
def c(s, code): return f"\033[{code}m{s}\033[0m" if USE_COLOR else s
def red(s):    return c(s, "31")
def green(s):  return c(s, "32")
def yellow(s): return c(s, "33")
def bold(s):   return c(s, "1")

def heading(s):
    print()
    print(bold(s))
    print(bold("-" * len(s)))

# -------------------- Text normalization --------------------
FOUNTAIN_SCENE_NUM_RE = re.compile(r"\s*#\d+#\s*$")

def normalize(s):
    """Normalize slug text for matching. Strips Fountain scene-number markers (#N#)
    since they exist in the source but not in the rendered PDF text."""
    s = s.replace("’", "'").replace("‘", "'")
    s = s.replace("–", "-").replace("—", "-")
    s = FOUNTAIN_SCENE_NUM_RE.sub("", s)
    return re.sub(r"\s+", " ", s).strip().upper()

def word_set(s):
    head = re.split(r"[(]", s)[0]
    return {w for w in re.split(r"[^A-Z]+", normalize(head)) if len(w) > 2}

def fmt_min(total_min):
    """Format total minutes as H:MM (e.g. 155.9 → '2:36'). For sub-hour, returns '0:NN'."""
    m = int(round(total_min))
    return f"{m // 60}:{m % 60:02d}"

def fmt_mmss(total_min):
    """Format total minutes as M:SS (e.g. 27.33 → '27:20'). For per-section subtotals."""
    s = int(round(total_min * 60))
    return f"{s // 60}:{s % 60:02d}"

# -------------------- Preflight --------------------
def preflight():
    for k in ("highland", "pdf", "script_state"):
        if not P[k].exists():
            return False, f"missing: {P[k].name}"
    with zipfile.ZipFile(P["highland"]) as z:
        name = next((n for n in z.namelist() if n.endswith(".textbundle/text.md")), None)
        if not name:
            return False, "no <textbundle>/text.md inside .highland"
        cur_hash = hashlib.sha256(z.read(name)).hexdigest()
    recorded = None
    for line in P["script_state"].read_text().splitlines():
        if line.startswith("text_md_sha256="):
            recorded = line.split("=", 1)[1].strip()
            break
    if cur_hash != recorded:
        msg = (
            "BLOCKED — .highland and PDF are out of sync.\n\n"
            f"  current text.md sha256: {cur_hash}\n"
            f"  .script-state recorded:  {recorded or '<none>'}\n\n"
            "Re-export the PDF from Highland (File > Export > PDF), save over\n"
            f"  {P['pdf'].name}\n"
            "then stage and commit both. The pre-commit hook will update .script-state.\n"
            "This script cannot render the PDF — Highland's export is GUI-only."
        )
        return False, msg
    return True, "in sync"

# -------------------- PDF + script loaders --------------------
def derive_canonical_pages():
    from pypdf import PdfReader
    r = PdfReader(str(P["pdf"]))
    total = len(r.pages)
    pagenum_re = re.compile(r"^(\d+)\.$")
    body = None
    for line in (r.pages[-1].extract_text() or "").splitlines():
        m = pagenum_re.match(line.strip())
        if m:
            body = int(m.group(1))
            break
    if body is None:
        raise RuntimeError("could not parse script-body page number from PDF last page")
    return body, total

def load_pdf_pages():
    from pypdf import PdfReader
    r = PdfReader(str(P["pdf"]))
    pagenum_re = re.compile(r"^(\d+)\.$")
    out = []
    for i, p in enumerate(r.pages):
        text = p.extract_text() or ""
        body = None
        for line in text.splitlines():
            m = pagenum_re.match(line.strip())
            if m:
                body = int(m.group(1))
                break
        out.append({"idx": i, "body": body, "text": text, "norm_text": normalize(text)})
    return out

SLUG_RE = re.compile(r"^(?:INT\.|EXT\.|I/E\.|INT/EXT)", re.IGNORECASE)

def load_script_lines_and_sluglines():
    """Return (lines, sluglines, total_line_count).
    total_line_count matches `wc -l` (counts newlines, not splitlines entries).
    """
    text = P["script_text"].read_text()
    lines = text.splitlines(keepends=False)
    sluglines = [(i + 1, ln) for i, ln in enumerate(lines) if SLUG_RE.match(ln)]
    total_lines = text.count("\n")  # wc -l convention
    return lines, sluglines, total_lines

# -------------------- Slug positioning --------------------
def position_slug_in_pdf(slug_text, pdf_pages, cur_idx, cur_off):
    """Forward-only search; returns (body_page, frac, new_idx, new_off)."""
    target = normalize(slug_text)
    page = pdf_pages[cur_idx]
    if page["body"] is not None:
        idx = page["norm_text"].find(target, cur_off)
        if idx >= 0:
            frac = idx / max(len(page["norm_text"]), 1)
            return page["body"], frac, cur_idx, idx + 1
    for j in range(cur_idx + 1, len(pdf_pages)):
        pg = pdf_pages[j]
        if pg["body"] is None:
            continue
        idx = pg["norm_text"].find(target)
        if idx >= 0:
            frac = idx / max(len(pg["norm_text"]), 1)
            return pg["body"], frac, j, idx + 1
    return None, None, cur_idx, cur_off

# -------------------- Part A: section headers --------------------
HEADER_RE = re.compile(r"^(### .+?)\s*\(lines (\d+)-(\d+)\)\s*—\s*pages?\s+([0-9-]+)\s*$")

def parse_section_headers(rm_text):
    out = []
    for i, line in enumerate(rm_text.splitlines(), start=1):
        m = HEADER_RE.match(line)
        if m:
            out.append({
                "line_num":   i,
                "label":      m.group(1).strip(),
                "line_start": int(m.group(2)),
                "line_end":   int(m.group(3)),
                "page_range": m.group(4),
                "raw":        line,
            })
    return out

def derive_new_headers(headers, sluglines, pdf_pages, total_script_lines):
    # 1. For each header, find the slug closest to its recorded line_start.
    #    Forward search first (to handle scripts that grew); fall back to backward
    #    search (for scripts that shrank). This keeps each section anchored to its
    #    actual content rather than collapsing to a stale line number that no
    #    longer maps to any slug.
    for h in headers:
        first = None
        # forward search
        for ln, slug in sluglines:
            if ln >= h["line_start"]:
                first = (ln, slug)
                break
        # fall back to nearest preceding slug (script shrank past this anchor)
        if first is None:
            for ln, slug in reversed(sluglines):
                if ln < h["line_start"]:
                    first = (ln, slug)
                    break
        if first is None:
            first = (h["line_start"], "")
        h["new_line_start"] = first[0]
        h["matched_slug"]   = first[1]
    # 2. line_end = next header's new_line_start - 1; last = total_script_lines
    for i in range(len(headers) - 1):
        headers[i]["new_line_end"] = headers[i + 1]["new_line_start"] - 1
    headers[-1]["new_line_end"] = total_script_lines
    # 3. PDF body page for each opening slug
    cur_idx, cur_off = 0, 0
    for h in headers:
        body, _, cur_idx, cur_off = position_slug_in_pdf(h["matched_slug"], pdf_pages, cur_idx, cur_off)
        h["new_body_page"] = body
    # 4. Page ranges: overlap-by-one convention (this section's end = next section's start)
    max_body = max((p["body"] or 0) for p in pdf_pages)
    for i in range(len(headers) - 1):
        h, nxt = headers[i], headers[i + 1]
        if h["new_body_page"] is not None and nxt["new_body_page"] is not None:
            h["new_page_range"] = f"{h['new_body_page']}-{nxt['new_body_page']}"
        else:
            h["new_page_range"] = h["page_range"]
    last = headers[-1]
    if last["new_body_page"] is not None:
        if last["new_body_page"] >= max_body:
            last["new_page_range"] = f"{last['new_body_page']}"
        else:
            last["new_page_range"] = f"{last['new_body_page']}-{max_body}"
    else:
        last["new_page_range"] = last["page_range"]
    # 5. Format the new header line
    for h in headers:
        page_kw = "page" if "-" not in h["new_page_range"] else "pages"
        h["new_raw"] = f"{h['label']} (lines {h['new_line_start']}-{h['new_line_end']}) — {page_kw} {h['new_page_range']}"
    return headers

# -------------------- Reconcile anchors (PROJECT_PROFILE §0) --------------------
# Some Runtime Model section boundaries are anchored to dramatic content, not to the
# line-position heuristic. derive_new_headers() always wants to re-anchor them to the
# nearest slug, which ejects the anchored scene into the neighbouring section (e.g.
# HQ Raid must keep logical scene 46, whose line_start sits one line below the curated
# header start; Bishop must keep scene 72). Historically the writer hand-restored these
# after every --apply. These helpers read the anchors from PROJECT_PROFILE §0 and hold
# them automatically — see PROJECT_PROFILE §9. A script with no anchors (fresh project)
# gets an empty list and all of this is a no-op.
def load_reconcile_anchors():
    """Read §0 reconcile_anchors from PROJECT_PROFILE.md. Returns a list of
    {"section": str, "scene": str}; [] if the profile or the key is absent (not an
    error — a fresh script simply has nothing to hold). The 'includes_logical_scene'
    token is unique to this block, so a global scan is safe."""
    prof = REPO_ROOT / "Claude Docs" / "PROJECT_PROFILE.md"
    if not prof.exists():
        return []
    txt = prof.read_text()
    return [{"section": m.group(1), "scene": m.group(2)}
            for m in re.finditer(
                r'section:\s*"([^"]+)"\s*,?\s*includes_logical_scene:\s*(\d+)', txt)]

def _rebuild_header_raw(h):
    page_kw = "page" if "-" not in h["new_page_range"] else "pages"
    return f"{h['label']} (lines {h['new_line_start']}-{h['new_line_end']}) — {page_kw} {h['new_page_range']}"

def pin_anchored_headers(headers, anchors):
    """Pin each anchored Runtime Model section's line range + page range to its
    committed value (reject the heuristic's re-anchoring), and repair the neighbour
    boundaries that shared an edge. Idempotent: on an already-correct repo it produces
    no change. Returns [(section, status, detail)] notes for the report."""
    notes = []
    if not anchors:
        return notes
    anchored_idx = set()
    for anc in anchors:
        idx = next((i for i, h in enumerate(headers) if anc["section"] in h["label"]), None)
        if idx is not None:
            anchored_idx.add(idx)
    for anc in anchors:
        idx = next((i for i, h in enumerate(headers) if anc["section"] in h["label"]), None)
        if idx is None:
            notes.append((anc["section"], "UNRESOLVED", "no matching Runtime Model section header"))
            continue
        h = headers[idx]
        was = h["new_raw"]
        moved = was != h["raw"]
        # Pin this section to its committed value.
        h["new_line_start"], h["new_line_end"] = h["line_start"], h["line_end"]
        h["new_page_range"] = h["page_range"]
        h["new_raw"] = h["raw"]
        # Repair the neighbour edges that abut this pinned section (skip anchored ones).
        if idx - 1 >= 0 and (idx - 1) not in anchored_idx:
            hn = headers[idx - 1]
            hn["new_line_end"] = h["line_start"] - 1
            if (hn["new_line_start"], hn["new_line_end"]) == (hn["line_start"], hn["line_end"]):
                hn["new_page_range"], hn["new_raw"] = hn["page_range"], hn["raw"]
            else:
                hn["new_raw"] = _rebuild_header_raw(hn)
        if idx + 1 < len(headers) and (idx + 1) not in anchored_idx:
            hn = headers[idx + 1]
            if hn["new_line_start"] <= h["line_end"]:
                hn["new_line_start"] = h["line_end"] + 1
                if (hn["new_line_start"], hn["new_line_end"]) == (hn["line_start"], hn["line_end"]):
                    hn["new_page_range"], hn["new_raw"] = hn["page_range"], hn["raw"]
                else:
                    hn["new_raw"] = _rebuild_header_raw(hn)
        detail = (f"re-anchor rejected (engine wanted '{was}'); pinned to committed "
                  f"lines {h['line_start']}-{h['line_end']} to keep logical scene {anc['scene']}"
                  if moved else
                  f"stable at committed lines {h['line_start']}-{h['line_end']} (keeps logical scene {anc['scene']})")
        notes.append((anc["section"], "HELD" if moved else "OK", detail))
    return notes

# -------------------- Part B: scene CSV --------------------
def load_existing_csv():
    rows = []
    with P["scene_csv"].open() as f:
        for r in csv.DictReader(f):
            rows.append({
                "scene_id":     r["scene_id"],
                "line_start":   int(float(r["line_start"])),
                "line_end":     int(float(r["line_end"])),
                "scene_name":   r["scene_name"],
                "category":     r["category"],
                "pages":        float(r["pages"]),
            })
    return rows

def assign_scenes_to_slugs(scenes, sluglines):
    assignments = []
    last_idx = -1
    for row in scenes:
        old_start  = row["line_start"]
        name_words = word_set(row["scene_name"])
        drift = (assignments[-1]["new_line_start"] - assignments[-1]["old_line_start"]) if assignments else 0
        expected = old_start + drift
        candidates = []
        for i in range(last_idx + 1, len(sluglines)):
            ln, slug = sluglines[i]
            if ln > expected + 200:
                break
            overlap = len(name_words & word_set(slug))
            candidates.append((overlap, -abs(ln - expected), i, ln, slug))
        if not candidates and last_idx + 1 < len(sluglines):
            i = last_idx + 1
            ln, slug = sluglines[i]
            candidates = [(0, -abs(ln - expected), i, ln, slug)]
        if not candidates:
            break
        candidates.sort(reverse=True)
        overlap, _, idx, ln, slug = candidates[0]
        assignments.append({
            "scene_id":       row["scene_id"],
            "scene_name":     row["scene_name"],
            "old_line_start": old_start,
            "old_line_end":   row["line_end"],
            "old_pages":      row["pages"],
            "category":       row["category"],
            "new_line_start": ln,
            "matched_slug":   slug,
            "slug_idx":       idx,
            "name_overlap":   overlap,
            "boundary_shift": abs(ln - old_start),
        })
        last_idx = idx
    return assignments

def fill_new_csv_fields(assignments, pdf_pages, canonical_pages, total_script_lines):
    # line_end
    for i in range(len(assignments) - 1):
        assignments[i]["new_line_end"] = assignments[i + 1]["new_line_start"] - 1
    assignments[-1]["new_line_end"] = total_script_lines
    # PDF positions
    cur_idx, cur_off = 0, 0
    for a in assignments:
        body, frac, cur_idx, cur_off = position_slug_in_pdf(a["matched_slug"], pdf_pages, cur_idx, cur_off)
        a["pdf_body_page"] = body
        a["pdf_frac"]      = frac
        a["abs_pos"]       = (body + frac) if body is not None else None
    # pages from PDF positions
    N = len(assignments)
    for i in range(N - 1):
        pa, pb = assignments[i]["abs_pos"], assignments[i + 1]["abs_pos"]
        if pa is None or pb is None:
            assignments[i]["new_pages"] = None
        else:
            assignments[i]["new_pages"] = round(pb - pa, 1)
    last = assignments[-1]
    last["new_pages"] = round((canonical_pages + 1) - last["abs_pos"], 1) if last["abs_pos"] is not None else None
    for a in assignments:
        if a.get("new_pages") is not None and a["new_pages"] < 0.1:
            a["new_pages"] = 0.1
    return assignments

def detect_uncertain_categories(assignments):
    """Heuristic: low name overlap AND large boundary shift.

    KNOWN LIMITATION — this gate is a safety net with a hole, not a guarantee.
    It catches scenes where the slug name changed OR the line range moved
    significantly. It does NOT catch a scene whose content was rewritten
    in place — same slug name, same approximate line range, but the
    dramatic register shifted (e.g., an action sequence rewritten as
    interior body-language work, or vice versa). Such re-categorization
    leaves the boundary and name fingerprints intact and slips past this
    check entirely.

    Mitigation: category correctness still warrants periodic human review
    of the scene CSV independent of whether this gate fires. Treat a
    clean reconcile as "no boundary-or-rename drift detected" — not as
    "categories are confirmed correct."
    """
    return [a for a in assignments
            if a["name_overlap"] < 1 and a["boundary_shift"] > 100]

def csv_row_changed(a):
    return (a["new_line_start"] != a["old_line_start"] or
            a["new_line_end"]   != a["old_line_end"]   or
            round(a.get("new_pages") or 0, 1) != round(a["old_pages"], 1))

# -------------------- Runtime computation --------------------
def compute_runtime_minutes(assignments):
    cfg = json.loads(P["runtime_config"].read_text())
    ratios = {k: v["ratio"] for k, v in cfg["categories"].items()}
    return sum((a["new_pages"] or 0) * ratios.get(a["category"], 1.0) for a in assignments)

def compute_section_totals(assignments, headers, anchors=None):
    cfg = json.loads(P["runtime_config"].read_text())
    ratios = {k: v["ratio"] for k, v in cfg["categories"].items()}
    short = {
        "### Act One Setup":                       "Act One Setup",
        "### Act One Mid":                         "Act One Mid",
        "### Act One Late":                        "Act One Late",
        "### Act Two Glass Ceiling":               "Glass Ceiling",
        "### Act Two Sierra Reveal":               "Sierra Reveal",
        "### Act Two HQ Raid":                     "HQ Raid",
        "### Act Three Berkeley Flashback":        "Berkeley",
        "### Act Three Bishop / S2 Investigation": "Bishop / S2 Investigation",
        "### Act Three Tahoe Finale":              "Tahoe Finale",
        "### Post-Credit":                         "Post-Credit",
    }
    # PROJECT_PROFILE §0 reconcile_anchors: force the named logical scene into its
    # section's total regardless of line-boundary math. (HQ Raid's curated total
    # counts scene 46 even though its line_start falls one line below the header
    # start; without this the bucketer would mis-assign it — see §9.)
    forced = {}  # scene_id -> section short-label
    if anchors:
        labels = {short.get(h["label"], h["label"]) for h in headers}
        for anc in anchors:
            tgt = next((lbl for lbl in labels if anc["section"] in lbl or lbl in anc["section"]), anc["section"])
            forced[str(anc["scene"])] = tgt
    out = []
    for h in headers:
        label = short.get(h["label"], h["label"])
        ls, le = h["new_line_start"], h["new_line_end"]
        scenes = [a for a in assignments
                  if forced.get(a["scene_id"]) == label
                  or (a["scene_id"] not in forced and ls <= a["new_line_start"] <= le)]
        pages = round(sum((a["new_pages"] or 0) for a in scenes), 1)
        mins  = sum((a["new_pages"] or 0) * ratios.get(a["category"], 1.0) for a in scenes)
        out.append({"label": label, "pages": pages, "mins": mins})
    return out

# -------------------- CANONICAL_FACTS audit --------------------
CANONICAL_ROW_RE = re.compile(r"^\|\s*([^|]+?)\s*\|\s*([^|]*?)\s*\|\s*([^|]*?)\s*\|\s*$")

def parse_canonical_facts():
    rows = {}
    in_table = False
    for i, line in enumerate(P["canonical"].read_text().splitlines(), start=1):
        if line.strip().startswith("| Fact"):
            in_table = True
            continue
        if line.strip().startswith("|---"):
            continue
        if in_table:
            if not line.strip().startswith("|"):
                in_table = False
                continue
            m = CANONICAL_ROW_RE.match(line)
            if m:
                fact = m.group(1).strip()
                val  = m.group(2).strip().replace("**", "")
                rows[fact] = {"line_num": i, "value": val, "raw_line": line}
    return rows

def audit_canonical_facts(rows, canonical_pages, model_runtime_min,
                          slugline_count, csv_main_scene_count):
    expected = {
        "Page count":                       str(canonical_pages),
        "Scene count (slug lines)":         str(slugline_count),
        "Consolidated logical scenes":      str(csv_main_scene_count),
        "Runtime — model estimate":         fmt_min(model_runtime_min),
        "Runtime — table-read projection":  fmt_min(canonical_pages * TABLE_READ_RATIO),
    }
    drift = []
    for fact, exp in expected.items():
        if fact not in rows:
            drift.append({"fact": fact, "registry": None, "expected": exp, "missing_row": True})
            continue
        if rows[fact]["value"] != exp:
            drift.append({
                "fact":     fact,
                "line_num": rows[fact]["line_num"],
                "registry": rows[fact]["value"],
                "expected": exp,
            })
    return drift

# -------------------- Stale page-count grep --------------------
def git_ls_files():
    res = subprocess.run(["git", "-C", str(REPO_ROOT), "ls-files"],
                         capture_output=True, text=True, check=True)
    return res.stdout.splitlines()

EXCLUDE_FROM_GREP = {
    ".script-state",
    "Blank Slate Full Script.highland",
    "Blank Slate Full Script.pdf",
    "scripts/reconcile.py",
    "Claude Docs/CANONICAL_FACTS.md",  # registry itself; audited separately
    "Claude Docs/HANDOFF.md",           # historical narrative deliberately contains old values
}

TEXT_EXTS = {".md", ".txt", ".csv", ".json", ".py", ".sh", ".js", ".swift"}

# Strict patterns for "this is the script's total page count" — fewer false positives
# than the generic `(\d+) page` match. Each pattern is checked against full lines.
STRONG_TOTAL_PAGE_PATTERNS = [
    # "X pages Highland Pro" or "Highland Pro X pages"
    re.compile(r"\b(\d{2,3})\s+pages?\s+Highland\b", re.IGNORECASE),
    re.compile(r"Highland Pro\s+(\d{2,3})\s+pages?\b", re.IGNORECASE),
    # "X-page script/draft/feature"
    re.compile(r"\b(\d{2,3})-page\s+(?:script|draft|feature)\b", re.IGNORECASE),
    # "X pages, MONTH YEAR draft"
    re.compile(r"\b(\d{2,3})\s+pages?,\s+\w+\s+\d{4}\s+draft\b", re.IGNORECASE),
    # "Page count[:|] X"  or "Page count | **X**"
    re.compile(r"\bPage count[:\s|]+\*?\*?(\d{2,3})\b", re.IGNORECASE),
    # "X pages / NN scenes"  (one-liner project specs)
    re.compile(r"\b(\d{2,3})\s+pages?\s*/\s*\d+\s+scenes?\b", re.IGNORECASE),
    # "X pages ÷ N pages/day"
    re.compile(r"\b(\d{2,3})\s+pages?\s*[÷/]\s*[\d.]+\s+pp?(?:ages?)?[/]day", re.IGNORECASE),
    # "X pages at N pages/day"
    re.compile(r"\b(\d{2,3})\s+pages?\s+at\s+[\d.\s-]+\s+pages?[/ ]?day", re.IGNORECASE),
    # "Feature. X pages"
    re.compile(r"\bFeature\.?\s+(\d{2,3})\s+pages?\b", re.IGNORECASE),
    # "Source script: ... (X pages, ...)" with parens
    re.compile(r"\(\s*(\d{2,3})\s+pages?[,)]", re.IGNORECASE),
]

# Patterns that DEFINITELY match but are NOT total page counts (deny-list)
SUPPRESS_PATTERNS = [
    re.compile(r"~\s*\d{1,3}\s+pages?", re.IGNORECASE),         # "~17 pages" approximations
    re.compile(r"\d{1,3}\s+pages?\s+of\s+\w+", re.IGNORECASE),  # "53 pages of content"
    re.compile(r"FAA\s+Part\s+107", re.IGNORECASE),
    re.compile(r"1\.25:1\s+at\s+95\s+pages?", re.IGNORECASE),   # calibration baseline
]

def grep_stale_page_refs(canonical_pages):
    hits = []
    for rel in git_ls_files():
        if rel in EXCLUDE_FROM_GREP or rel.startswith("Claude Docs/PROMPT_"):
            continue
        path = REPO_ROOT / rel
        if path.suffix.lower() not in TEXT_EXTS:
            continue
        try:
            text = path.read_text(errors="replace")
        except Exception:
            continue
        for line_no, line in enumerate(text.splitlines(), start=1):
            # Skip if line matches a suppress pattern
            if any(p.search(line) for p in SUPPRESS_PATTERNS):
                continue
            for pat in STRONG_TOTAL_PAGE_PATTERNS:
                m = pat.search(line)
                if not m:
                    continue
                n = int(m.group(1))
                if n == canonical_pages:
                    continue
                hits.append({
                    "file":           rel,
                    "line":           line_no,
                    "value":          n,
                    "text":           line.strip(),
                    "classification": "total page-count reference",
                    "pattern":        pat.pattern,
                })
                break  # one hit per line
    return hits

# -------------------- Writers (apply mode) --------------------
def write_new_csv(assignments):
    with P["scene_csv"].open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["scene_id", "line_start", "line_end",
                                          "scene_name", "category", "pages"])
        w.writeheader()
        for a in assignments:
            w.writerow({
                "scene_id":   a["scene_id"],
                "line_start": a["new_line_start"],
                "line_end":   a["new_line_end"],
                "scene_name": a["scene_name"],
                "category":   a["category"],
                "pages":      a["new_pages"],
            })

def write_runtime_model_updates(headers, section_totals, total_min, total_pages,
                                 canonical_pages, model_runtime_min):
    """Rewrite section headers, TOTALS table, reconciliation note, model figure prose."""
    text = P["runtime_model"].read_text()
    lines = text.splitlines()
    # 1. Section headers
    for h in headers:
        if h["raw"] != h["new_raw"]:
            lines[h["line_num"] - 1] = h["new_raw"]
    # 2. TOTALS table — find the table rows by section label and replace.
    #    Convention: per-section "Estimated Minutes" column is M:SS
    #    (e.g. "27:20"); TOTAL row shows "M:SS (H:MM)" (e.g. "155:56 (2:36)").
    for idx, ln in enumerate(lines):
        for st in section_totals:
            if ln.startswith(f"| {st['label']} |"):
                lines[idx] = f"| {st['label']} | {st['pages']:.1f} | {fmt_mmss(st['mins'])} |"
                break
        if ln.startswith("| **TOTAL**"):
            lines[idx] = (
                f"| **TOTAL** | **{total_pages:.1f}** | "
                f"**{fmt_mmss(total_min)} ({fmt_min(model_runtime_min)})** |"
            )
    # 3. Reconciliation note — replace the line beginning *(Note: page totals
    for idx, ln in enumerate(lines):
        if ln.startswith("*(Note: page totals") or ln.startswith("*Page totals in this model"):
            diff = abs(total_pages - canonical_pages)
            if diff <= 1.0:
                lines[idx] = (
                    f"*(Note: page totals are scene-block estimates derived from each scene's "
                    f"PDF position; total scene-block sum is {total_pages:.1f}, within rounding "
                    f"tolerance of Highland Pro's canonical {canonical_pages}.)*"
                )
            else:
                lines[idx] = (
                    f"*Page totals in this model are scene-block estimates summing to "
                    f"~{round(total_pages)}. Highland Pro's canonical script count is "
                    f"{canonical_pages} — a ~{round(diff)}-page divergence. Per-scene values "
                    f"derive from PDF position honestly; the sum is whatever it is.*"
                )
            break
    # 4. Model figure prose
    h_mm = fmt_h_mm(model_runtime_min)
    for idx, ln in enumerate(lines):
        if "model estimates approximately" in ln and "hours" in ln:
            lines[idx] = re.sub(
                r"approximately \d+ hours? and \d+ minutes",
                f"approximately {h_mm['h']} hours and {h_mm['m']} minutes",
                ln,
            )
            # Restore as plain string version
            lines[idx] = re.sub(
                r"approximately \d+ hours? and \d+ minutes",
                f"approximately {h_mm['h']} hours and {h_mm['m']} minutes",
                ln,
            )
            break
    P["runtime_model"].write_text("\n".join(lines) + "\n")

def fmt_h_mm(total_min):
    s = int(round(total_min * 60))
    return {"h": s // 3600, "m": (s % 3600) // 60, "fmt": f"{s // 3600}:{(s % 3600) // 60:02d}"}

def write_canonical_updates(canonical_pages, model_runtime_min):
    text = P["canonical"].read_text()
    new = text
    new = re.sub(
        r"(\| Page count \| \*\*)\d+(\*\*)",
        rf"\g<1>{canonical_pages}\g<2>",
        new,
    )
    new = re.sub(
        r"(\| Runtime — table-read projection \| \*\*)\d+:\d{2}(\*\* \| )\d+(\s*×)",
        rf"\g<1>{fmt_min(canonical_pages * TABLE_READ_RATIO)}\g<2>{canonical_pages}\g<3>",
        new,
    )
    new = re.sub(
        r"(\| Runtime — model estimate \| \*\*)\d+:\d{2}(\*\*)",
        rf"\g<1>{fmt_min(model_runtime_min)}\g<2>",
        new,
    )
    P["canonical"].write_text(new)

# -------------------- Main --------------------
def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--apply", action="store_true", help="Write changes to disk (default: report only)")
    p.add_argument("--categories", type=Path, help="JSON file mapping scene_id → category for uncertain scenes")
    p.add_argument("--approve-stale", type=Path, help="JSON file with approved stale-ref fixes (list of file/line dicts)")
    args = p.parse_args()

    # --- 1. Preflight ---
    heading("1. Preflight")
    ok, msg = preflight()
    if not ok:
        print(red(msg))
        sys.exit(1)
    print(green(f"  ✓ {msg}"))

    # --- 2. Canonical pages from PDF ---
    heading("2. Canonical pages (from PDF)")
    canonical_pages, total_sheets = derive_canonical_pages()
    print(f"  Script body: {canonical_pages} pages")
    print(f"  Total sheets (incl. title page): {total_sheets}")

    # --- Load inputs ---
    script_lines, sluglines, total_script_lines = load_script_lines_and_sluglines()
    pdf_pages = load_pdf_pages()

    # --- 3. Part A: Section headers (+ §0 anchor holds) ---
    heading("3. Part A — Runtime Model section headers")
    headers = parse_section_headers(P["runtime_model"].read_text())
    headers = derive_new_headers(headers, sluglines, pdf_pages, total_script_lines)
    anchors = load_reconcile_anchors()
    anchor_notes = pin_anchored_headers(headers, anchors)
    header_changes = [h for h in headers if h["raw"] != h["new_raw"]]
    print(f"  {len(headers)} headers; {len(header_changes)} need updating.")
    for h in header_changes:
        print(f"  {yellow('  before:')} {h['raw']}")
        print(f"  {green('  after: ')} {h['new_raw']}")
    if anchor_notes:
        print(f"  anchors held (PROJECT_PROFILE §0): {len(anchor_notes)}")
        for section, status, detail in anchor_notes:
            paint = {"HELD": yellow, "OK": green, "UNRESOLVED": red}.get(status, yellow)
            print(f"    {paint(status)} — {section}: {detail}")

    # --- 4. Part B: Scene CSV ---
    heading("4. Part B — Scene CSV")
    existing = load_existing_csv()
    assignments = assign_scenes_to_slugs(existing, sluglines)
    assignments = fill_new_csv_fields(assignments, pdf_pages, canonical_pages, total_script_lines)
    new_sum = sum((a.get("new_pages") or 0) for a in assignments)
    csv_changes = [a for a in assignments if csv_row_changed(a)]
    print(f"  Existing CSV pages sum: {sum(a['old_pages'] for a in assignments):.2f}")
    print(f"  Recomputed sum:          {new_sum:.2f}")
    print(f"  Canonical:               {canonical_pages}.0")
    print(f"  Rows changed:            {len(csv_changes)} of {len(assignments)}")

    # --- Gate 1: Uncertain categories ---
    uncertain = detect_uncertain_categories(assignments)
    user_categories = {}
    if args.categories and args.categories.exists():
        user_categories = json.loads(args.categories.read_text())
    if uncertain:
        heading("Gate 1: Uncertain category assignments")
        unresolved = []
        for u in uncertain:
            sid = u["scene_id"]
            if sid in user_categories:
                u["category"] = user_categories[sid]
                print(green(f"  scene {sid}: category set to '{user_categories[sid]}' (from --categories)"))
            else:
                unresolved.append(u)
                print(red(f"  scene {sid}: '{u['scene_name'][:50]}'"))
                print(f"    matched slug: {u['matched_slug'][:60]}")
                print(f"    name overlap: {u['name_overlap']}, boundary shift: {u['boundary_shift']} lines")
        if unresolved:
            print()
            print(red("  Resolve by passing --categories <file.json> with structure:"))
            print('  {"<scene_id>": "<category>", ...}')
            print(f'  unresolved: {[u["scene_id"] for u in unresolved]}')

    # --- 5. Runtime + section totals ---
    heading("5. Runtime estimate (from recomputed CSV)")
    model_runtime_min = compute_runtime_minutes(assignments)
    section_totals = compute_section_totals(assignments, headers, anchors)
    print(f"  Model runtime: {fmt_min(model_runtime_min)} ({model_runtime_min:.1f} min)")
    print(f"  Table-read:    {fmt_min(canonical_pages * TABLE_READ_RATIO)} (canonical × 1.25)")
    print(f"  Section totals sum to: {sum(s['pages'] for s in section_totals):.1f} pages")

    # --- 6. CANONICAL_FACTS audit ---
    heading("6. CANONICAL_FACTS audit")
    canonical_rows = parse_canonical_facts()
    main_scene_count = sum(1 for a in assignments if "." not in a["scene_id"])
    drift = audit_canonical_facts(canonical_rows, canonical_pages, model_runtime_min,
                                   len(sluglines), main_scene_count)
    # Drift values may be reported as raw H:MM via fmt_min; ensure consistent format
    # (fix already done — keeping audit using fmt_min which now returns H:MM)
    if drift:
        for d in drift:
            print(yellow(f"  drift: {d['fact']}: registry='{d.get('registry')}' expected='{d['expected']}'"))
    else:
        print(green("  ✓ all checked rows match their sources"))

    # --- 7. Stale page-count grep ---
    heading("7. Stale page-count references")
    stale = grep_stale_page_refs(canonical_pages)
    if stale:
        groups = {}
        for s in stale:
            groups.setdefault(s["classification"], []).append(s)
        for k in sorted(groups):
            print(f"  [{k}] — {len(groups[k])} hit(s)")
            for s in groups[k]:
                print(f"    {s['file']}:{s['line']}  ({s['value']})  {s['text'][:80]}")
    else:
        print(green("  ✓ no stale page-count references found"))

    # --- Idempotency check ---
    nothing_to_do = (
        not header_changes and not csv_changes and not drift and not stale
        and not uncertain
    )
    if nothing_to_do:
        print()
        print(green(bold("Nothing to reconcile. Repo is fully current with the committed PDF.")))
        sys.exit(0)

    # --- Apply or report ---
    if not args.apply:
        print()
        print(yellow(bold("Report-only mode.")))
        print(yellow("Re-run with --apply to write the derived changes (headers, CSV, registry rows)."))
        if uncertain and not user_categories:
            print(yellow("Gate 1 unresolved — provide --categories <file>."))
        if stale:
            print(yellow("Stale references listed above; provide --approve-stale <file> to fix them."))
            print(yellow('  approve-stale JSON: {"fixes":[{"file":"...","line":NN,"old":"NN","new":"NN"}, ...]}'))
        sys.exit(0)

    # === APPLY MODE ===
    print()
    print(bold("APPLY MODE"))
    if uncertain and any(u["scene_id"] not in user_categories for u in uncertain):
        print(red("Gate 1 unresolved. Refusing to apply."))
        sys.exit(2)

    # 1. Write CSV
    write_new_csv(assignments)
    print(green(f"  ✓ wrote {P['scene_csv'].relative_to(REPO_ROOT)} ({len(assignments)} rows, sum={new_sum:.2f})"))

    # 2. Write Runtime Model updates
    total_pages = sum(s["pages"] for s in section_totals)
    write_runtime_model_updates(headers, section_totals, model_runtime_min, total_pages,
                                 canonical_pages, model_runtime_min)
    print(green(f"  ✓ updated {P['runtime_model'].relative_to(REPO_ROOT)} (headers, TOTALS, note, model figure)"))

    # 3. Write CANONICAL_FACTS
    write_canonical_updates(canonical_pages, model_runtime_min)
    print(green(f"  ✓ updated {P['canonical'].relative_to(REPO_ROOT)} (page count, table-read, model estimate)"))

    # 4. Stale-ref fixes
    if stale and args.approve_stale and args.approve_stale.exists():
        approved = json.loads(args.approve_stale.read_text())
        fixes = approved.get("fixes", [])
        applied = 0
        for fix in fixes:
            path = REPO_ROOT / fix["file"]
            txt = path.read_text()
            lines2 = txt.splitlines()
            ln = fix["line"] - 1
            if 0 <= ln < len(lines2):
                lines2[ln] = lines2[ln].replace(str(fix["old"]), str(fix["new"]), 1)
                path.write_text("\n".join(lines2) + ("\n" if txt.endswith("\n") else ""))
                applied += 1
        print(green(f"  ✓ applied {applied} stale-ref fixes from --approve-stale"))
    elif stale:
        print(yellow(f"  {len(stale)} stale page-count references not fixed (no --approve-stale file)"))

    print()
    print(bold("Done. Review changes with `git diff`, then commit."))
    print("  (The pre-commit hook will fire — no .highland or PDF should be in the diff.)")

if __name__ == "__main__":
    main()
