#!/usr/bin/env python3
"""fdx_to_fountain.py — convert a Final Draft .fdx (XML) to Fountain text.

Lets a Final Draft user feed the screenplay-prep engine WITHOUT manually exporting
Fountain, and without any companion app. Self-contained — Python standard library
only (xml.etree). Maps FDX paragraph types to Fountain, carries each Scene Heading's
`Number=` attribute through as the engine's trailing `#N#` scene marker (so a numbered
FD script gets `scene_markers.expected: true` for free), and emits a Fountain title
page from <TitlePage><Content> when present.

Handles (verified against real FD exports):
  • Dual / simultaneous dialogue — an outer <Paragraph> wrapping a <DualDialogue>
    container of alternating Character/Dialogue/Parenthetical paragraphs. The 2nd
    (and later) Character cue gets Fountain's trailing ` ^` dual marker.
  • Inline styling — a <Text> run's `Style="Bold+Italic+Underline"` attribute
    (`+`-separated) becomes Fountain emphasis (`**bold**`, `*italic*`, `_underline_`,
    `***bold-italic***`). Applied to prose only (Action/Dialogue/General); cues,
    sluglines, and transitions stay PLAIN so downstream cue/slug parsing is clean.
    `AllCaps` / `HiddenText` have no Fountain inline equivalent and are ignored.
  • Script notes (opt-in, --notes) — <ScriptNote> blocks live OUTSIDE <Content>,
    anchored by an FD-internal `Range` char offset that doesn't reproduce reliably
    against the flattened body, so notes are emitted as a trailing `[[ ... ]]` block
    rather than re-anchored inline. Off by default to keep the body clean.

Usage:
    python3 fdx_to_fountain.py --input Script.fdx --out Script.fountain
    python3 fdx_to_fountain.py --input Script.fdx --notes      # also append notes
    python3 fdx_to_fountain.py --input Script.fdx              # prints to stdout

Notes / limits (MVP): non-numeric FD scene numbers (e.g. "A1") are emitted as
`#A1#` but the engine's `#(\\d+)#` regex only reads numeric ones; script-note
re-anchoring is not attempted (see above). The screenplay BODY converts faithfully
— that's what the agents and scripts read.
"""
import argparse
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

# Paragraph types that continue the current dialogue block (NO blank line before).
CONTINUES = {"Parenthetical", "Dialogue"}

# Structural types kept PLAIN — never inject inline emphasis markup, so cue / slug /
# transition parsing downstream stays clean. Everything else can carry emphasis.
PLAIN_TYPES = {"Scene Heading", "Character", "Transition"}


def _style_wrap(s, style):
    """Wrap one <Text> run in Fountain emphasis per its FDX `Style` attribute
    (`Bold+Italic+Underline`, '+'-separated). Leading/trailing whitespace is kept
    OUTSIDE the markers (Fountain emphasis can't hug a space). `AllCaps` /
    `HiddenText` carry no Fountain inline equivalent and are ignored."""
    if not style or not s.strip():
        return s
    tokens = set(style.split("+"))
    bold = "Bold" in tokens
    italic = "Italic" in tokens
    underline = "Underline" in tokens
    if not (bold or italic or underline):
        return s
    lead = s[:len(s) - len(s.lstrip())]
    trail = s[len(s.rstrip()):]
    core = s.strip()
    if bold and italic:
        core = f"***{core}***"
    elif bold:
        core = f"**{core}**"
    elif italic:
        core = f"*{core}*"
    if underline:
        core = f"_{core}_"
    return f"{lead}{core}{trail}"


def _text(para, styled=False):
    """Concatenate the DIRECT <Text> children of a Paragraph, ignoring nested
    metadata (SceneProperties, SceneArcBeats, …). With styled=True each run is
    wrapped per its Style attr; otherwise runs join raw (historical behavior —
    used for cues, slugs, the title page, and notes)."""
    parts = []
    for t in para.findall("Text"):
        s = t.text or ""
        parts.append(_style_wrap(s, t.get("Style", "")) if styled else s)
    return "".join(parts).strip()


def _para_text(para, ptype=None):
    """Text for a paragraph — styled unless it's a structural (PLAIN) type."""
    if ptype is None:
        ptype = para.get("Type", "Action")
    return _text(para, styled=ptype not in PLAIN_TYPES)


def _iter_items(para):
    """Yield (ptype, text) for one <Content> paragraph. A <DualDialogue> wrapper
    expands into its inner cues in order, with the 2nd-and-later Character cue
    marked by a trailing ' ^' (Fountain's dual-dialogue marker)."""
    dd = para.find("DualDialogue")
    if dd is not None:
        chars = 0
        for inner in dd.findall("Paragraph"):
            itype = inner.get("Type", "Action")
            itext = _para_text(inner, itype)
            if not itext:
                continue
            if itype == "Character":
                chars += 1
                if chars >= 2:
                    itext = f"{itext} ^"
            yield itype, itext
        return
    yield para.get("Type", "Action"), _para_text(para)


def _title_page(root):
    """Best-effort Fountain title page from <TitlePage><Content> only (never Header/
    Footer). Returns a list of lines, or [] if there's no usable title content."""
    tp = root.find("TitlePage")
    content = tp.find("Content") if tp is not None else None
    if content is None:
        return []
    texts = [t for t in (_text(p) for p in content.findall("Paragraph")) if t]
    if not texts:
        return []
    lines = [f"Title: {texts[0]}"]
    for t in texts[1:]:
        if t.lower() in ("written by", "by", "screenplay by"):
            continue
        lines.append(f"Author: {t}")
        break
    return lines


def _script_notes(root):
    """Collect anchored + unanchored FDX script notes as plain strings. Their FD
    `Range` char-offset anchors are not reliably reproducible against the flattened
    body, so callers emit these as a trailing block, not re-anchored inline."""
    notes = []
    for block_name in ("ScriptNotes", "UnanchoredScriptNotes"):
        block = root.find(block_name)
        if block is None:
            continue
        for sn in block.findall("ScriptNote"):
            text = " ".join(p for p in (_text(x) for x in sn.findall("Paragraph")) if p).strip()
            if text:
                notes.append(text)
    return notes


def convert(fdx_path, include_notes=False):
    """Parse a .fdx and return Fountain text."""
    root = ET.parse(fdx_path).getroot()
    content = root.find("Content")
    if content is None:
        raise ValueError("no <Content> element — is this a Final Draft script .fdx?")
    out = []
    title = _title_page(root)
    if title:
        out.extend(title)
        out.append("")  # blank line closes the title page
    first = True
    for para in content.findall("Paragraph"):
        for ptype, text in _iter_items(para):
            if not text:
                continue
            # Blank line before each new block — but not before the very first
            # element, and not before a dialogue continuation (Parenthetical /
            # Dialogue).
            if not first and ptype not in CONTINUES:
                out.append("")
            first = False
            if ptype == "Scene Heading":
                num = para.get("Number")
                out.append(f"{text} #{num}#" if num else text)
            elif ptype == "Character":
                out.append(text if text.isupper() else text.upper())
            elif ptype == "Parenthetical":
                out.append(text if text.startswith("(") else f"({text})")
            elif ptype == "Transition":
                out.append(text if text.isupper() else text.upper())
            else:  # Dialogue, Action, Shot, General, and anything else → as-is
                out.append(text)
    if include_notes:
        for n in _script_notes(root):
            out.append("")
            out.append(f"[[{n}]]")
    return "\n".join(out) + "\n"


def main():
    ap = argparse.ArgumentParser(description="Convert a Final Draft .fdx to Fountain.")
    ap.add_argument("--input", required=True, type=Path)
    ap.add_argument("--out", type=Path, help="output .fountain (default: stdout)")
    ap.add_argument("--notes", action="store_true",
                    help="append FDX script notes as a trailing [[ ... ]] block")
    a = ap.parse_args()
    if not a.input.exists():
        sys.exit(f"ERROR: input not found: {a.input}")
    try:
        fountain = convert(a.input, include_notes=a.notes)
    except ET.ParseError as e:
        sys.exit(f"ERROR: could not parse .fdx XML: {e}")
    except ValueError as e:
        sys.exit(f"ERROR: {e}")
    if a.out:
        a.out.write_text(fountain, encoding="utf-8")
        print(f"wrote {a.out}  ({fountain.count(chr(10))} lines)")
    else:
        sys.stdout.write(fountain)


if __name__ == "__main__":
    main()
