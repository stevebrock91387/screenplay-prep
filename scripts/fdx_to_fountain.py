#!/usr/bin/env python3
"""fdx_to_fountain.py — convert a Final Draft .fdx (XML) to Fountain text.

Lets a Final Draft user feed the screenplay-prep engine WITHOUT manually exporting
Fountain, and without any companion app. Self-contained — Python standard library
only (xml.etree). Maps FDX paragraph types to Fountain, carries each Scene Heading's
`Number=` attribute through as the engine's trailing `#N#` scene marker (so a numbered
FD script gets `scene_markers.expected: true` for free), and emits a Fountain title
page from <TitlePage><Content> when present.

Usage:
    python3 fdx_to_fountain.py --input Script.fdx --out Script.fountain
    python3 fdx_to_fountain.py --input Script.fdx              # prints to stdout

Notes / limits (MVP): inline styling (bold/italic/underline) is flattened to plain
text; dual dialogue and script notes are not yet mapped; non-numeric FD scene numbers
(e.g. "A1") are emitted as `#A1#` but the engine's `#(\\d+)#` regex only reads numeric
ones. The screenplay BODY (sluglines, cues, dialogue, action, transitions) converts
faithfully — that's what the agents and scripts read.
"""
import argparse
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

# Paragraph types that continue the current dialogue block (NO blank line before).
CONTINUES = {"Parenthetical", "Dialogue"}


def _text(para):
    """Concatenate the DIRECT <Text> children of a Paragraph, flattening styled runs
    and ignoring nested metadata (SceneProperties, SceneArcBeats, …)."""
    return "".join((t.text or "") for t in para.findall("Text")).strip()


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


def convert(fdx_path):
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
        ptype = para.get("Type", "Action")
        text = _text(para)
        if not text:
            continue
        # Blank line before each new block — but not before the very first element,
        # and not before a dialogue continuation (Parenthetical / Dialogue).
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
    return "\n".join(out) + "\n"


def main():
    ap = argparse.ArgumentParser(description="Convert a Final Draft .fdx to Fountain.")
    ap.add_argument("--input", required=True, type=Path)
    ap.add_argument("--out", type=Path, help="output .fountain (default: stdout)")
    a = ap.parse_args()
    if not a.input.exists():
        sys.exit(f"ERROR: input not found: {a.input}")
    try:
        fountain = convert(a.input)
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
