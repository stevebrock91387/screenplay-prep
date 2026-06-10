#!/usr/bin/env python3
"""
extract_characters.py — deterministic character-cue extractor for *Blank Slate*.

Builds a 1..149 scene index from the EXPLICIT `#N#` slug-line markers in the
authoritative Fountain source (NOT document-order counting), parses character
cues per the Fountain spec, and emits a committed dataset (JSON) plus a stdout
table. READ-ONLY on the script.

Design rules (see Claude Docs/CASTING_TOOL_BRIEF.md):
- Authoritative source: "Blank Slate Full Script.fountain" (repo root).
- Scene index comes from `#(\\d+)#` markers on slug lines (1..149).
- Aliases are NOT merged. Every distinct cue is emitted literally; alias
  grouping is an editorial decision. A SUGGESTED grouping is reported for
  convenience only and never applied.
- Flags (not filters): V.O./O.S.-only cues, group/collective cues, single-scene cues.

Usage:
    python3 scripts/extract_characters.py            # write dataset + print table
    python3 scripts/extract_characters.py --check     # print table only, no write
"""
from __future__ import annotations
import json
import os
import re
import sys
from pathlib import Path

# Project root: $CLAUDE_PROJECT_DIR when set (bundled in the screenplay-prep plugin,
# run against another project), else the repo this script lives in (direct runs).
REPO = Path(os.environ["CLAUDE_PROJECT_DIR"]) if os.environ.get("CLAUDE_PROJECT_DIR") \
    else Path(__file__).resolve().parent.parent
# NOTE: the source filename is still Blank Slate-specific; parameterizing this from
# PROJECT_PROFILE §0 source.fountain + scene_markers.regex is the remaining coupling
# (see PLUGIN_PLAN). Until then this script is the one engine piece not yet generic.
FOUNTAIN = REPO / "Blank Slate Full Script.fountain"
OUT_JSON = REPO / "Claude Docs" / "character_scene_index.json"

# A slug line ends with an explicit scene-number marker: ... #N#
SLUG_MARKER = re.compile(r"#(\d+)#\s*$")
# Defensive: also recognize an unmarked slug by its prefix, so we never treat one as a cue.
SLUG_PREFIX = re.compile(r"^(INT|EXT|EST|INT\.?/EXT\.?|I/E)[.\s/]", re.IGNORECASE)
# Character-cue extensions to strip down to the base name.
EXTENSION = re.compile(
    r"\s*\((?:V\.?O\.?|O\.?S\.?|O\.?C\.?|CONT'?D|CONT’D|PRE-?LAP|FILTERED|"
    r"TEXT|TEXT MESSAGE|TEXTING|INTO PHONE|ON PHONE|ON TV|ON RADIO|V\.O|O\.S)\.?\)\s*$",
    re.IGNORECASE,
)
# Transition lines that are uppercase but are NOT character cues.
TRANSITION = re.compile(
    r"(\bTO:\s*$|^FADE\b|^SMASH\b|^MATCH CUT\b|^CUT\b|^INTERCUT\b|^INSERT\b|"
    r"^DISSOLVE\b|^BACK TO\b|^TITLE\b|^SUPER\b|^OMITTED\b)",
    re.IGNORECASE,
)
# Tokens that mark a cue as a group / collective speaker (flag only).
GROUP_TOKENS = ("GROUP", "PARTICIPANTS", "MEMBERS", "COHORT", "STUDENTS",
                "CROWD", "EVERYONE", "ALL", "BOTH", "CLASS", "TOGETHER", "AGENTS")

# Convenience only — reported, never applied. Editorial merge is the writer's call.
SUGGESTED_ALIASES = {
    "RYAN SYSTEM (one actor)": ["RYAN", "RYAN KING", "JAMES", "MR. BLANK", "BLANK",
                                 "SIOBHAN", "YOUNG RYAN", "JAMES/BLANK"],
    "ROBERTO (staged-reveal aliases)": ["ROBERTO", "ARMANI", "TORCIDO"],
    "MARGARET (watch for 'MEGHAN' continuity slip)": ["MARGARET", "MEG", "MEGHAN"],
}


def is_uppercase_cue(text: str) -> bool:
    """True if text has letters and no lowercase letters (Fountain cue rule)."""
    if not re.search(r"[A-Z]", text):
        return False
    if re.search(r"[a-z]", text):
        return False
    return True


def parse(fountain_path: Path):
    lines = fountain_path.read_text(encoding="utf-8").splitlines()
    n = len(lines)
    current_scene = 0
    scene_markers = []  # ordered list of scene numbers as encountered
    cues = {}           # base name -> record

    def blank(i):
        return i < 0 or i >= n or lines[i].strip() == ""

    for i, raw_line in enumerate(lines):
        line = raw_line.strip()
        if line == "":
            continue

        m = SLUG_MARKER.search(line)
        if m:
            current_scene = int(m.group(1))
            scene_markers.append(current_scene)
            continue
        if SLUG_PREFIX.match(line):
            # Slug without a marker (shouldn't happen here) — never a cue.
            continue

        # Candidate character cue: blank line before, non-blank (dialogue) after.
        if not blank(i - 1):
            continue
        if blank(i + 1):
            continue

        candidate = line
        forced = candidate.startswith("@")
        if forced:
            candidate = candidate[1:].strip()
        dual = candidate.endswith("^")
        if dual:
            candidate = candidate[:-1].strip()

        if TRANSITION.search(candidate):
            continue

        # The portion before any extension must be all-uppercase, and short.
        base = EXTENSION.sub("", candidate).strip()
        had_ext = base != candidate
        ext_is_vo_os = bool(re.search(r"\(\s*(V\.?O|O\.?S)", candidate, re.IGNORECASE))
        if not base or len(base) > 40:
            continue
        if not is_uppercase_cue(base):
            continue
        # Reject bare numbers / pure punctuation.
        if not re.search(r"[A-Z]", base):
            continue

        rec = cues.setdefault(base, {
            "cue": base,
            "raw_variants": set(),
            "scenes": set(),
            "vo_os_appearances": 0,
            "total_appearances": 0,
            "forced": False,
            "dual_dialogue": False,
        })
        rec["raw_variants"].add(candidate)
        if current_scene > 0:
            rec["scenes"].add(current_scene)
        rec["total_appearances"] += 1
        if ext_is_vo_os:
            rec["vo_os_appearances"] += 1
        rec["forced"] = rec["forced"] or forced
        rec["dual_dialogue"] = rec["dual_dialogue"] or dual

    # Finalize records.
    records = []
    for base, rec in cues.items():
        scenes = sorted(rec["scenes"])
        is_group = any(tok in base.split() or tok in base for tok in GROUP_TOKENS)
        records.append({
            "cue": base,
            "raw_variants": sorted(rec["raw_variants"]),
            "scenes": scenes,
            "scene_count": len(scenes),
            "first_scene": scenes[0] if scenes else None,
            "last_scene": scenes[-1] if scenes else None,
            "total_cue_appearances": rec["total_appearances"],
            "flags": {
                "vo_os_only": rec["vo_os_appearances"] > 0
                              and rec["vo_os_appearances"] == rec["total_appearances"],
                "has_vo_os": rec["vo_os_appearances"] > 0,
                "group_cue": is_group,
                "single_scene": len(scenes) == 1,
                "forced_cue": rec["forced"],
                "dual_dialogue": rec["dual_dialogue"],
            },
        })
    records.sort(key=lambda r: (r["first_scene"] if r["first_scene"] else 9999, r["cue"]))

    scene_index = sorted(set(scene_markers))
    return records, scene_index


def build_dataset(records, scene_index):
    expected = list(range(1, 150))
    gaps = [s for s in expected if s not in scene_index]
    dupes = sorted({s for s in scene_index if scene_index.count(s) > 1})
    suggested = {
        group: [c for c in members if any(r["cue"] == c for r in records)]
        for group, members in SUGGESTED_ALIASES.items()
    }
    return {
        "_meta": {
            "source": "Blank Slate Full Script.fountain",
            "scene_index_method": "explicit #N# slug markers",
            "scene_count": len(scene_index),
            "scene_index_complete_1_149": (not gaps and not dupes
                                           and scene_index == expected),
            "missing_scene_numbers": gaps,
            "duplicate_scene_numbers": dupes,
            "distinct_cues": len(records),
            "note": ("Cues are literal and UNMERGED. Alias grouping is editorial. "
                     "suggested_alias_groups is a convenience only and is NOT applied."),
        },
        "suggested_alias_groups": suggested,
        "characters": records,
    }


def print_table(dataset):
    recs = dataset["characters"]
    meta = dataset["_meta"]
    print(f"\nSCENE INDEX: {meta['scene_count']} scenes, "
          f"contiguous 1..149 = {meta['scene_index_complete_1_149']}"
          + (f"  MISSING={meta['missing_scene_numbers']}" if meta["missing_scene_numbers"] else "")
          + (f"  DUPES={meta['duplicate_scene_numbers']}" if meta["duplicate_scene_numbers"] else ""))
    print(f"DISTINCT CUES: {meta['distinct_cues']}\n")
    print(f"{'CUE':<26}{'#sc':>4}  {'first':>5}  {'last':>5}  flags")
    print("-" * 78)
    for r in recs:
        f = r["flags"]
        flags = ",".join(k for k, v in (
            ("VO/OS-only", f["vo_os_only"]),
            ("group", f["group_cue"]),
            ("single", f["single_scene"]),
            ("dual", f["dual_dialogue"]),
        ) if v)
        print(f"{r['cue']:<26}{r['scene_count']:>4}  "
              f"{str(r['first_scene']):>5}  {str(r['last_scene']):>5}  {flags}")
    # Summary counts.
    g = sum(1 for r in recs if r["flags"]["group_cue"])
    v = sum(1 for r in recs if r["flags"]["vo_os_only"])
    s = sum(1 for r in recs if r["flags"]["single_scene"])
    print("-" * 78)
    print(f"group cues: {g}   V.O./O.S.-only: {v}   single-scene: {s}")
    print("\nSUGGESTED alias groups (convenience only — NOT applied):")
    for grp, members in dataset["suggested_alias_groups"].items():
        if members:
            print(f"  {grp}: {', '.join(members)}")


def main():
    check_only = "--check" in sys.argv
    if not FOUNTAIN.exists():
        sys.exit(f"ERROR: Fountain source not found at {FOUNTAIN}")
    records, scene_index = parse(FOUNTAIN)
    dataset = build_dataset(records, scene_index)
    print_table(dataset)
    if check_only:
        print("\n--check: dataset NOT written.")
        return
    OUT_JSON.write_text(json.dumps(dataset, indent=2, ensure_ascii=False) + "\n",
                        encoding="utf-8")
    print(f"\nDataset written: {OUT_JSON.relative_to(REPO)}")


if __name__ == "__main__":
    main()
