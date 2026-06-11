#!/usr/bin/env python3
"""
extract_characters.py — deterministic character-cue extractor.

Project-parameterized: reads the Fountain source, the scene-marker regex, whether
markers are expected, and the locked scene count from PROJECT_PROFILE §0 (neutral
defaults when no profile is present). Builds a scene index from the EXPLICIT scene
markers when the project has them (NOT document-order counting), or numbers scenes by
slug order for a markerless/unlocked draft. Parses character cues per the Fountain
spec and emits a committed dataset (JSON) plus a stdout table. READ-ONLY.

Design rules (see Claude Docs/CASTING_TOOL_BRIEF.md):
- Source / marker regex / markers_expected / scene_count come from PROJECT_PROFILE §0.
- When markers are expected, the scene index comes from those markers (e.g. a
  trailing `#(\\d+)#` token); the locked `canonical.scene_count` drives the
  completeness check. A markerless project is numbered by slug order instead.
- Aliases are NOT merged. Every distinct cue is emitted literally; alias grouping is
  an editorial decision. A SUGGESTED grouping is reported for convenience only,
  filtered to cues that actually appear, and never applied.
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
OUT_JSON = REPO / "Claude Docs" / "character_scene_index.json"


def load_profile():
    """Resolve §0 source/scene parameters from PROJECT_PROFILE.md:
      - source.fountain → the cue-parsing source,
      - scene_markers.expected → True if the script carries `#N#` markers (else
        scenes are numbered by slug order — a markerless/unlocked draft),
      - scene_markers.regex → the marker pattern (capture group 1 = the number),
      - canonical.scene_count → the locked count for the completeness check (None
        if not locked yet).
    Falls back to neutral defaults so the script still runs standalone."""
    prof = REPO / "Claude Docs" / "PROJECT_PROFILE.md"
    # Neutral defaults (used only with NO profile): the first *.fountain in the repo
    # root, markers expected, trailing #N# pattern.
    out = {"fountain": next(iter(sorted(REPO.glob("*.fountain"))), REPO / "script.fountain"),
           "markers_expected": True,
           "marker_regex": r"#(\d+)#",
           "scene_count": None}
    if prof.exists():
        txt = prof.read_text(encoding="utf-8")
        m = re.search(r'\bfountain:\s*"([^"]+)"', txt)
        if m:
            out["fountain"] = REPO / m.group(1)
        m = re.search(r'\bexpected:\s*(true|false)\b', txt, re.IGNORECASE)
        if m:
            out["markers_expected"] = (m.group(1).lower() == "true")
        m = re.search(r"\bregex:\s*'([^']+)'", txt) or re.search(r'\bregex:\s*"([^"]+)"', txt)
        if m:
            out["marker_regex"] = m.group(1)
        m = re.search(r'\bscene_count:\s*(\d+)', txt)
        if m:
            out["scene_count"] = int(m.group(1))
    return out


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
# Empty by default: alias systems are per-screenplay and live in PROJECT_PROFILE §5
# (read by cast-cue-linter) + the casting editorial JSON, not hardcoded here. A project
# may add local hints in this shape if useful:
#   SUGGESTED_ALIASES = {"<group label>": ["CUE_A", "CUE_B", ...]}
SUGGESTED_ALIASES = {}


def is_uppercase_cue(text: str) -> bool:
    """True if text has letters and no lowercase letters (Fountain cue rule)."""
    if not re.search(r"[A-Z]", text):
        return False
    if re.search(r"[a-z]", text):
        return False
    return True


def parse(fountain_path, marker_re, markers_expected):
    lines = fountain_path.read_text(encoding="utf-8").splitlines()
    n = len(lines)
    current_scene = 0
    scene_markers = []  # ordered list of scene numbers as encountered (may repeat)
    cues = {}           # base name -> record

    def blank(i):
        return i < 0 or i >= n or lines[i].strip() == ""

    for i, raw_line in enumerate(lines):
        line = raw_line.strip()
        if line == "":
            continue

        if markers_expected:
            m = marker_re.search(line)
            if m and line[m.end():].strip() == "":
                # slug line ending with an explicit scene-number marker
                current_scene = int(m.group(1))
                scene_markers.append(current_scene)
                continue
            if SLUG_PREFIX.match(line):
                # Slug without a marker — never a cue.
                continue
        else:
            # No markers in this project (unlocked draft): number scenes by slug order.
            if SLUG_PREFIX.match(line):
                current_scene += 1
                scene_markers.append(current_scene)
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

    return records, scene_markers


def build_dataset(records, scene_markers, profile):
    scene_index = sorted(set(scene_markers))
    dupes = sorted({s for s in scene_markers if scene_markers.count(s) > 1})
    expected_count = profile["scene_count"]
    if expected_count:
        expected = list(range(1, expected_count + 1))
        gaps = [s for s in expected if s not in scene_index]
        complete = (not gaps and not dupes and scene_index == expected)
    else:
        gaps, complete = [], None      # no locked count → no completeness claim
    # Suggested alias groups: convenience only, never applied. Filtered to members
    # that actually appear as cues, so a different project gets none of these.
    suggested = {}
    for group, members in SUGGESTED_ALIASES.items():
        present = [c for c in members if any(r["cue"] == c for r in records)]
        if present:
            suggested[group] = present
    return {
        "_meta": {
            "source": Path(profile["fountain"]).name,
            "scene_index_method": ("explicit scene markers" if profile["markers_expected"]
                                   else "document-order slug lines (no markers)"),
            "scene_count": len(scene_index),
            "expected_scene_count": expected_count,
            "scene_index_complete": complete,
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
    ec = meta.get("expected_scene_count")
    print(f"\nSCENE INDEX: {meta['scene_count']} scenes"
          + (f", contiguous 1..{ec} = {meta['scene_index_complete']}" if ec
             else " (no locked scene count)")
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
    profile = load_profile()
    fountain = profile["fountain"]
    if not fountain.exists():
        sys.exit(f"ERROR: Fountain source not found at {fountain}")
    marker_re = re.compile(profile["marker_regex"])
    records, scene_markers = parse(fountain, marker_re, profile["markers_expected"])
    dataset = build_dataset(records, scene_markers, profile)
    print_table(dataset)
    if check_only:
        print("\n--check: dataset NOT written.")
        return
    OUT_JSON.write_text(json.dumps(dataset, indent=2, ensure_ascii=False) + "\n",
                        encoding="utf-8")
    print(f"\nDataset written: {OUT_JSON.relative_to(REPO)}")


if __name__ == "__main__":
    main()
