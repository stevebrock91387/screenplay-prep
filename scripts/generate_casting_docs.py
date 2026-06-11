#!/usr/bin/env python3
"""
generate_casting_docs.py — casting / table-read document generator.

Project-parameterized: reads the project name, canonical scene count, and casting
CSV from PROJECT_PROFILE §0 (load_profile()). Falls back to neutral defaults only when
no profile is present.

Reads two inputs:
  (a) Claude Docs/character_scene_index.json  — the extractor dataset (mechanical
      cue->scene truth, from extract_characters.py). NEVER edited here.
  (b) Claude Docs/casting_editorial.json      — writer-maintained editorial fields
      (descriptions, age/ethnicity/gender/size, tier, category, notes, alias
      group, and static prose sections). Code NEVER invents its contents.

Emits 4 file formats per run into Claude Docs/generated/:
  .md   authored from dataset + editorial
  .html generated FROM the .md via Conversion Tools/md2html.js
  .pdf  rendered FROM the .html via Conversion Tools/html2pdf.swift (WebKit)
  .csv  generated from the SAME dataset+editorial (not scraped from a doc)

Modes (prompt defines 4; the prompt intro says "five purposes" but lists four —
flagged, not invented):
  --mode breakdown                 Breakdown Services: role, age, ethnicity,
                                   gender, size/category, description.
  --mode fulltableread             Every speaking character, all 149 scenes.
  --mode fractional --start N [--end M]
                                   Only characters speaking in scenes N..M
                                   (M defaults to 149). Range validated.
  --mode full-breakdown            Rich per-character doc (tier / alias group /
                                   per-character blocks); scene counts+lists
                                   auto-filled from the dataset, ALL prose from
                                   the editorial file. Does NOT overwrite the
                                   canonical CASTING_BREAKDOWN.md.
  --mode wmm-request               We Make Movies read-request, CSV ONLY:
                                   Role | Brief description | empty "Actor request"
                                   column for WMM to fill in the reader. One row
                                   per role (one-actor systems sharing a display,
                                   e.g. an alter system, collapse to one row).

Bootstrap (run once so the editorial file exists, pre-filled from the existing
casting CSV — existing-doc data, not invented; blanks left as explicit TODO):
  --bootstrap-editorial

Read-only on the screenplay, CANONICAL_FACTS, and the canonical casting docs.
"""
from __future__ import annotations
import argparse
import csv
import json
import os
import re
import subprocess
import sys
from pathlib import Path

# Project root: $CLAUDE_PROJECT_DIR when set (bundled in the screenplay-prep plugin,
# run against another project), else the repo this script lives in (direct runs).
REPO = Path(os.environ["CLAUDE_PROJECT_DIR"]) if os.environ.get("CLAUDE_PROJECT_DIR") \
    else Path(__file__).resolve().parent.parent
DOCS = REPO / "Claude Docs"
DATASET = DOCS / "character_scene_index.json"
EDITORIAL = DOCS / "casting_editorial.json"
PROFILE = DOCS / "PROJECT_PROFILE.md"
OUT_DIR = DOCS / "generated"
MD2HTML = REPO / "Conversion Tools" / "md2html.js"
HTML2PDF = REPO / "Conversion Tools" / "html2pdf.swift"

# Per-screenplay parameters. Neutral defaults; load_profile() overrides them from
# PROJECT_PROFILE §0 at startup (project name → doc titles, canonical.scene_count →
# LAST_SCENE, the *_Casting_Breakdown.csv in cast_registry → SOURCE_CSV). Module
# globals so the title helpers and the tableread default bound read the resolved
# values. A repo with no PROJECT_PROFILE keeps these neutral defaults.
PROJECT_NAME = "Untitled Screenplay"
TITLE_CAPS = "UNTITLED SCREENPLAY"
LAST_SCENE = None
SOURCE_CSV = None


def load_profile():
    """Resolve per-screenplay parameters from PROJECT_PROFILE §0 into the module
    globals. Tolerant per key:
      - project name: from the H1 header; falls back to the neutral default.
      - scene_count: `canonical.scene_count` if a number; None if null/absent (a
        fresh/unlocked draft) — main() then derives it from the dataset.
      - SOURCE_CSV: the first *_Casting_Breakdown.csv in §0 cast_registry; None if
        the registry has none (no CSV to prefill from).
    Returns the resolved values (scene_count/source_csv may be None)."""
    global PROJECT_NAME, TITLE_CAPS, LAST_SCENE, SOURCE_CSV
    scene_count = None
    if PROFILE.exists():
        txt = PROFILE.read_text(encoding="utf-8")
        m = re.search(r'^#\s*PROJECT_PROFILE\s*[—–-]\s*(.+?)\s*$', txt, re.M)
        if m:
            PROJECT_NAME = m.group(1).strip()
            TITLE_CAPS = PROJECT_NAME.upper()
        m = re.search(r'scene_count:\s*(\d+)', txt)   # a bare number; 'null' won't match
        if m:
            scene_count = int(m.group(1))
            LAST_SCENE = scene_count
        # the casting CSV listed in §0 cast_registry (first *_Casting_Breakdown.csv)
        m = re.search(r'"([^"]*[Cc]asting_[Bb]reakdown\.csv)"', txt)
        SOURCE_CSV = REPO / m.group(1) if m else None
    return {"name": PROJECT_NAME, "title_caps": TITLE_CAPS,
            "scene_count": scene_count, "source_csv": SOURCE_CSV}

EDITORIAL_FIELDS = ["display", "tier", "category", "age", "ethnicity",
                    "gender", "size", "alias_group", "description", "notes"]
STATIC_SECTIONS = ["storyline", "casting_strategy", "casting_timeline",
                   "casting_budget", "tax_credit", "deia"]


# --------------------------------------------------------------------------- IO
def load_dataset():
    if not DATASET.exists():
        sys.exit(f"ERROR: {DATASET.relative_to(REPO)} missing. Run extract_characters.py first.")
    return json.loads(DATASET.read_text(encoding="utf-8"))


def load_editorial():
    if not EDITORIAL.exists():
        sys.exit(f"ERROR: {EDITORIAL.relative_to(REPO)} missing. "
                 f"Run: python3 scripts/generate_casting_docs.py --bootstrap-editorial")
    return json.loads(EDITORIAL.read_text(encoding="utf-8"))


def norm(s: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", (s or "").upper())


def flat(s) -> str:
    """Collapse any whitespace (incl. newlines from wrapped CSV cells) to single spaces."""
    return re.sub(r"\s+", " ", str(s)).strip()


GENERIC_FIRSTWORD = {"GROUP", "PARTICIPANTS", "MEMBERS", "ALL", "BOTH", "CROWD",
                     "EVERYONE", "CLASS", "STUDENTS", "COHORT", "AGENTS", "TOGETHER"}
# Honorifics that prefix a role so the cue is a non-first word (DETECTIVE EUGENE PHLAT).
TITLES = {"DETECTIVE", "DR", "DOCTOR", "AGENT", "OFFICER", "MR", "MRS", "MS",
          "CAPTAIN", "SERGEANT", "LIEUTENANT", "CHIEF", "PROFESSOR", "NURSE", "SPECIAL"}


def csv_match(cue, csv_rows):
    """CSV->cue match, precision-first:
      1. exact role / role-minus-parenthetical / exact slash-segment, then
      2. cue == first word of a slash-segment (catches 'LEAD' -> 'LEAD /
         ALIAS / ...'), EXCEPT generic group tokens (so 'GROUP' never grabs
         'Group Leader')."""
    n = norm(cue)
    for row in csv_rows:
        role = row.get("Role", "")
        if norm(role) == n or norm(role.split("(")[0]) == n:
            return row
        for seg in role.replace("(", "/").split("/"):
            if norm(seg) == n:
                return row
    if cue.strip().split()[0].upper() not in GENERIC_FIRSTWORD:
        for row in csv_rows:
            role = row.get("Role", "")
            for seg in role.replace("(", "/").split("/"):
                words = seg.strip().split()
                if words and norm(words[0]) == n:
                    return row
        # title-prefixed single roles: cue is a non-title word (EUGENE in
        # 'DETECTIVE EUGENE PHLAT'). Gated on a known honorific to stay precise.
        for row in csv_rows:
            role = row.get("Role", "")
            if "/" in role:
                continue
            words = role.replace("(", " ").split()
            if words and norm(words[0]) in TITLES and any(norm(w) == n for w in words[1:]):
                return row
    return None


# ------------------------------------------------------------------ bootstrap
def bootstrap_editorial(dataset):
    """Create the editorial skeleton, pre-filled from the existing casting CSV.
    Pulls only from an existing doc; never invents. Blanks are explicit TODOs."""
    csv_rows = []
    if SOURCE_CSV and SOURCE_CSV.exists():
        with SOURCE_CSV.open(encoding="utf-8") as fh:
            csv_rows = list(csv.DictReader(fh))

    roles = {}
    prefilled = 0
    for rec in dataset["characters"]:
        cue = rec["cue"]
        match = csv_match(cue, csv_rows)
        entry = {k: "" for k in EDITORIAL_FIELDS}
        entry["display"] = cue.title()
        if match:
            entry["display"] = flat(match.get("Role", "")) or cue.title()
            entry["age"] = flat(match.get("Age", ""))
            entry["ethnicity"] = flat(match.get("Ethnicity", ""))
            entry["gender"] = flat(match.get("Gender", ""))
            entry["size"] = flat(match.get("Size", ""))
            entry["description"] = flat(match.get("Description", ""))
            prefilled += 1
        roles[cue] = entry

    # Non-destructive MERGE: never clobber writer edits. Existing non-empty
    # fields win; empty fields get the CSV prefill; newly-appeared cues are added.
    existing_roles, existing_static, had_prev = {}, {}, EDITORIAL.exists()
    if had_prev:
        try:
            prev = json.loads(EDITORIAL.read_text(encoding="utf-8"))
            existing_roles = prev.get("roles", {})
            existing_static = prev.get("static_sections", {})
        except Exception:  # noqa: BLE001
            existing_roles, existing_static = {}, {}

    def nonempty(v):
        return v.strip() if isinstance(v, str) else v

    merged, preserved, added = {}, 0, 0
    for cue, prefill in roles.items():
        prev_entry = existing_roles.get(cue, {})
        if not prev_entry:
            added += 1 if had_prev else 0
        kept = False
        entry = {}
        for k in EDITORIAL_FIELDS:
            pv = nonempty(prev_entry.get(k, ""))
            if pv:
                entry[k] = prev_entry[k]
                if k != "display":
                    kept = True
            else:
                entry[k] = prefill[k]
        if kept:
            preserved += 1
        merged[cue] = entry

    static = {k: existing_static.get(k, "") or "" for k in STATIC_SECTIONS}
    dropped = [c for c in existing_roles if c not in roles]
    for cue in dropped:  # preserve writer-added roles that aren't current cues
        merged[cue] = existing_roles[cue]

    out = {
        "_meta": {
            "note": ("Writer-maintained editorial fields for casting docs. Code never "
                     "invents content; empty strings are intentional TODOs to fill. "
                     "Keys under 'roles' MUST match extractor cues exactly. "
                     "--bootstrap-editorial MERGES: existing non-empty values are preserved."),
            "prefilled_from": (str(SOURCE_CSV.relative_to(REPO))
                               if SOURCE_CSV and SOURCE_CSV.exists() else None),
            "prefilled_roles": prefilled,
            "total_roles": len(merged),
            "skeleton": not had_prev,
        },
        "roles": merged,
        "static_sections": static,
    }
    EDITORIAL.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    verb = "merged into existing" if had_prev else "skeleton written"
    print(f"Editorial {verb}: {EDITORIAL.relative_to(REPO)}")
    print(f"  roles: {len(merged)}   CSV-prefilled: {prefilled}   "
          f"writer-edits preserved: {preserved}   new roles added: {added}")
    if dropped:
        print(f"  WARN: {len(dropped)} editorial role(s) no longer a cue in the script "
              f"(left intact, review): {', '.join(dropped)}")


# ------------------------------------------------------------------- helpers
def ed_role(editorial, cue):
    return editorial.get("roles", {}).get(cue, {k: "" for k in EDITORIAL_FIELDS})


def scenes_str(scenes):
    return ", ".join(str(s) for s in scenes)


def in_range(scenes, start, end):
    return any(start <= s <= end for s in scenes)


def md_table(headers, rows):
    out = ["| " + " | ".join(headers) + " |",
           "| " + " | ".join("---" for _ in headers) + " |"]
    for r in rows:
        out.append("| " + " | ".join(flat(c).replace("|", "\\|") for c in r) + " |")
    return "\n".join(out)


def collapse_by_display(dataset, editorial):
    """One entry per unique editorial display, merging the scene data of cues
    that share it (e.g. two cues for one actor's alter, or a cover-name + real-name
    pair, collapse to one row). Keeps the first cue's editorial fields."""
    by_disp, order = {}, []
    for rec in dataset["characters"]:
        e = ed_role(editorial, rec["cue"])
        disp = e["display"] or rec["cue"]
        g = by_disp.get(disp)
        if not g:
            g = {"display": disp, "cues": [], "scenes": set(),
                 "editorial": e, "alias_group": e.get("alias_group", "")}
            by_disp[disp] = g
            order.append(disp)
        g["cues"].append(rec["cue"])
        g["scenes"].update(rec["scenes"])
    roles = []
    for disp in order:
        g = by_disp[disp]
        sc = sorted(g["scenes"])
        g["scenes"], g["scene_count"] = sc, len(sc)
        g["first_scene"] = sc[0] if sc else None
        g["last_scene"] = sc[-1] if sc else None
        roles.append(g)
    return roles


def cluster_sort(roles, by="first"):
    """Order roles so members sharing a non-empty alias_group sit together,
    clustered at the group's best position; solo roles keep their own slot.
    by='first' → earliest scene; by='count' → scene count descending."""
    def gkey(r):
        return r["alias_group"] or ("\x00solo\x00" + r["display"])
    anchor = {}
    for r in roles:
        k = gkey(r)
        if by == "first":
            anchor[k] = min(anchor.get(k, 10**9), r["first_scene"] or 9999)
        else:
            anchor[k] = max(anchor.get(k, -1), r["scene_count"])
    if by == "first":
        roles.sort(key=lambda r: (anchor[gkey(r)], gkey(r), -r["scene_count"], r["display"]))
    else:
        roles.sort(key=lambda r: (-anchor[gkey(r)], gkey(r), -r["scene_count"], r["display"]))
    return roles


# --------------------------------------------------------------------- modes
def _arc_with_size(e):
    """Personality & Character Arc text with role size appended (BD convention)."""
    size = (e["size"] or e["category"] or "").strip()
    arc = flat(e["description"])
    return (arc + (f"  [{size}]" if size else "")).strip()


def gen_breakdown(dataset, editorial):
    """Field-by-field reference for posting on Breakdown Express / Actors Access.
    Roles are entered one at a time in the form; the per-role blocks below mirror
    its fields (Gender / Age / Ethnic Appearance auto-fill Physical Characteristics;
    the text goes in Personality & Character Arc with role size at the end)."""
    title = f"{TITLE_CAPS} — Breakdown Services Posting"
    roles = cluster_sort(collapse_by_display(dataset, editorial), by="count")
    storyline = flat(editorial.get("static_sections", {}).get("storyline", ""))
    parts = [f"# {title}", "",
             "*Field-by-field reference for posting on Breakdown Express / Actors Access "
             "(\"Add a New Role,\" one role at a time). In the form, **Physical "
             "Characteristics** auto-fills from Gender / Age / Ethnic Appearance; the text "
             "below goes in **Personality & Character Arc**, with role size at the end. "
             "Paying-role defaults to Yes — confirm per role.*", ""]
    if storyline:
        parts += [f"**Storyline:** {storyline}", ""]
    parts += ["---", ""]
    age_flags = []
    for g in roles:
        e = g["editorial"]
        age = e["age"] or "—"
        parts += [f"## {g['display']}",
                  f"- **Gender:** {e['gender'] or '—'}",
                  f"- **Age:** {age}",
                  f"- **Ethnic Appearance:** {e['ethnicity'] or '—'}",
                  f"- **Personality & Character Arc:** {_arc_with_size(e) or '_(TODO)_'}",
                  "- **Paying role:** Yes",
                  ""]
        m = re.match(r"\s*(\d+)\s*[-–]\s*(\d+)", age)
        if m and int(m.group(2)) - int(m.group(1)) > 20:
            age_flags.append(f"{g['display']} ({age})")
    if age_flags:
        parts += ["---", "",
                  "**⚠ Age ranges over BD's 20-year adult limit — tighten before "
                  "posting:** " + "; ".join(age_flags), ""]
    md = "\n".join(parts)
    csv_headers = ["Role Name", "Gender", "Age", "Ethnic Appearance",
                   "Personality & Character Arc", "Paying role"]
    csv_rows = [[g["display"], g["editorial"]["gender"], g["editorial"]["age"],
                 g["editorial"]["ethnicity"], _arc_with_size(g["editorial"]), "Yes"]
                for g in roles]
    return md, (csv_headers, csv_rows)


def gen_tableread(dataset, editorial, start=1, end=None, fractional=False):
    """Table read by role. Cues that are one actor (e.g. an alter system, or a
    villain's staged-reveal aliases) are merged per their alias_group; grouped
    alter systems stay distinct (each may be read by a different actor pre-casting).
    First-appearance order."""
    if end is None:
        end = LAST_SCENE
    roles = cluster_sort(collapse_by_display(dataset, editorial), by="first")
    if fractional:
        title = f"{TITLE_CAPS} — Table Read (scenes {start}–{end})"
        sub = "roles speaking in this range"
    else:
        title = f"{TITLE_CAPS} — Full Table Read (all {LAST_SCENE} scenes)"
        sub = "every speaking role"
    headers = ["Role", "Scenes (count)", "First", "Last", "Scene numbers"]
    rows = []
    for g in roles:
        sc = [s for s in g["scenes"] if start <= s <= end] if fractional else g["scenes"]
        if fractional and not sc:
            continue
        rows.append([g["display"], len(sc),
                     sc[0] if sc else "", sc[-1] if sc else "", scenes_str(sc)])
    md = (f"# {title}\n\n*{len(rows)} {sub}. Cues that are one actor (per their "
          f"alias_group) are merged; grouped identity systems stay distinct. "
          f"Scene data from the extractor.*\n\n"
          + md_table(headers, rows) + "\n")
    csv_headers = ["Role", "SceneCount", "FirstScene", "LastScene", "Scenes"]
    csv_rows = [[r[0], r[1], r[2], r[3], r[4]] for r in rows]
    return md, (csv_headers, csv_rows)


def gen_full_breakdown(dataset, editorial):
    title = f"{TITLE_CAPS} — Full Casting Breakdown"
    roles = collapse_by_display(dataset, editorial)
    # group by tier if present else alias_group else 'Unassigned'
    groups = {}
    for g in roles:
        e = g["editorial"]
        key = e["tier"] or e["alias_group"] or "Unassigned (set tier/alias_group in editorial)"
        groups.setdefault(key, []).append(g)
    parts = [f"# {title}", "",
             "*Per-character blocks. Scene counts/lists auto-filled from the extractor; "
             "all prose from the editorial file (blanks = TODO, never invented). Cues that "
             "are one actor (per their alias_group) are merged.*", ""]
    for key in sorted(groups):
        parts.append(f"## {key}")
        parts.append("")
        for g in sorted(groups[key], key=lambda x: (-x["scene_count"], x["first_scene"] or 9999)):
            e = g["editorial"]
            parts.append(f"### {g['display']}  ({' / '.join(g['cues'])})")
            meta = []
            if e["age"]: meta.append(f"Age {e['age']}")
            if e["ethnicity"]: meta.append(e["ethnicity"])
            if e["gender"]: meta.append(e["gender"])
            if e["size"] or e["category"]: meta.append(e["size"] or e["category"])
            if meta:
                parts.append("**" + " · ".join(meta) + "**")
            parts.append(f"- **Scenes ({g['scene_count']}):** {scenes_str(g['scenes']) or '—'}")
            parts.append(f"- **Description:** {e['description'] or '_(TODO)_'}")
            if e["notes"]:
                parts.append(f"- **Notes:** {e['notes']}")
            parts.append("")
    # static sections
    for key in STATIC_SECTIONS:
        val = editorial.get("static_sections", {}).get(key, "")
        parts.append(f"## {key.replace('_', ' ').title()}")
        parts.append("")
        parts.append(val if val else "_(TODO — supply in editorial static_sections)_")
        parts.append("")
    md = "\n".join(parts)
    # CSV
    csv_headers = ["Role", "Cues", "Tier", "AliasGroup", "SceneCount", "Scenes",
                   "Age", "Ethnicity", "Gender", "Size", "Description", "Notes"]
    csv_rows = []
    for g in roles:
        e = g["editorial"]
        csv_rows.append([g["display"], " / ".join(g["cues"]), e["tier"],
                         e["alias_group"], g["scene_count"], scenes_str(g["scenes"]),
                         e["age"], e["ethnicity"], e["gender"], e["size"],
                         e["description"], e["notes"]])
    return md, (csv_headers, csv_rows)


# ------------------------------------------------------------------- emit
def gen_wmm_request(dataset, editorial):
    """We Make Movies read-request (CSV only): Role | Description (full paragraph) |
    Actor request (empty column for WMM to fill in the reader). One row per role —
    cues that are one actor (per their alias_group) merge — and grouped identity
    systems are clustered together (each alter may be read by a different actor
    pre-casting). Leads first by scene count."""
    roles = cluster_sort(collapse_by_display(dataset, editorial), by="count")
    headers = ["Role", "Description", "Actor request"]
    rows = [[g["display"], flat(g["editorial"]["description"]), ""] for g in roles]
    return headers, rows


COMPACT_CSS = """<style>
  /* casting-doc overrides layered on the shared md2html.js prose styling */
  html, body { font-size: 10pt; padding: 0 32pt; }
  h1, h1.doc-title, h2, h3 { font-size: 12pt; margin: 6pt 0 4pt 0; }
  p.doc-subtitle { font-size: 10pt; }
  table { font-size: 10pt; width: 100%; }
  th, td { padding: 3pt 6pt; vertical-align: top; }
</style>"""


def write_outputs(stem, md, csv_pack, orientation="portrait"):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    md_path = OUT_DIR / f"{stem}.md"
    html_path = OUT_DIR / f"{stem}.html"
    pdf_path = OUT_DIR / f"{stem}.pdf"
    csv_path = OUT_DIR / f"{stem}.csv"

    md_path.write_text(md + "\n", encoding="utf-8")
    headers, rows = csv_pack
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(headers)
        w.writerows(rows)

    produced = [md_path.name, csv_path.name]
    # HTML from MD
    try:
        subprocess.run(["node", str(MD2HTML), str(md_path), str(html_path)],
                       check=True, capture_output=True, text=True)
        html = html_path.read_text(encoding="utf-8")
        if "</head>" in html:  # inject compact overrides without touching md2html.js
            html = html.replace("</head>", COMPACT_CSS + "\n</head>", 1)
            html_path.write_text(html, encoding="utf-8")
        produced.append(html_path.name)
    except Exception as e:  # noqa: BLE001
        print(f"  WARN: HTML step skipped ({e}). Run manually: "
              f'node "{MD2HTML}" "{md_path}" "{html_path}"')
        return produced
    # PDF from HTML (orientation: portrait|landscape)
    try:
        subprocess.run(["swift", str(HTML2PDF), str(html_path), str(pdf_path), orientation],
                       check=True, capture_output=True, text=True)
        produced.append(pdf_path.name)
    except Exception as e:  # noqa: BLE001
        print(f"  WARN: PDF step skipped ({e}). Run manually: "
              f'swift "{HTML2PDF}" "{html_path}" "{pdf_path}" {orientation}')
    return produced


def main():
    global LAST_SCENE
    prof = load_profile()  # resolve PROJECT_NAME / TITLE_CAPS / LAST_SCENE / SOURCE_CSV from §0
    ap = argparse.ArgumentParser(description=f"{PROJECT_NAME} casting/table-read generator")
    ap.add_argument("--mode", choices=["breakdown", "fulltableread", "fractional",
                                       "full-breakdown", "wmm-request"])
    ap.add_argument("--start", type=int)
    ap.add_argument("--end", type=int)
    ap.add_argument("--bootstrap-editorial", action="store_true")
    args = ap.parse_args()

    dataset = load_dataset()
    # Authoritative scene count: profile canonical.scene_count, else the extractor's
    # own _meta.scene_count (derived from the project's own dataset, never guessed).
    LAST_SCENE = prof["scene_count"] or dataset.get("_meta", {}).get("scene_count") or LAST_SCENE

    if args.bootstrap_editorial:
        bootstrap_editorial(dataset)
        return
    if not args.mode:
        ap.error("--mode is required (unless --bootstrap-editorial)")

    editorial = load_editorial()

    orientation = "portrait"
    if args.mode == "breakdown":
        md, csvp = gen_breakdown(dataset, editorial)
        stem = "casting_breakdown_services"
        orientation = "portrait"  # per-role blocks, not a wide table
    elif args.mode == "fulltableread":
        md, csvp = gen_tableread(dataset, editorial)
        stem = "tableread_full"
        orientation = "landscape"
    elif args.mode == "fractional":
        start = args.start if args.start is not None else 1
        end = args.end if args.end is not None else LAST_SCENE
        if not (1 <= start <= end <= LAST_SCENE):
            ap.error(f"--start/--end must satisfy 1 <= start <= end <= {LAST_SCENE} "
                     f"(got start={start}, end={end})")
        md, csvp = gen_tableread(dataset, editorial, start, end, fractional=True)
        stem = f"tableread_scenes_{start}-{end}"
        orientation = "landscape"
    elif args.mode == "full-breakdown":
        md, csvp = gen_full_breakdown(dataset, editorial)
        stem = "full_breakdown"
    elif args.mode == "wmm-request":
        headers, rows = gen_wmm_request(dataset, editorial)
        stem = "wmm_read_request"
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        csv_path = OUT_DIR / f"{stem}.csv"
        with csv_path.open("w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(headers)
            w.writerows(rows)
        print(f"\nMODE: wmm-request  ->  {OUT_DIR.relative_to(REPO)}/{stem}.csv (CSV only)")
        print(f"  produced: {csv_path.name}  ({len(rows)} roles)")
        return

    produced = write_outputs(stem, md, csvp, orientation)
    print(f"\nMODE: {args.mode}  ->  {OUT_DIR.relative_to(REPO)}/{stem}.*")
    print("  produced: " + ", ".join(produced))


if __name__ == "__main__":
    main()
