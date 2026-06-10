#!/usr/bin/env bash
# clone_script_to_md.sh
#
# Refresh the plain-text screenplay copies from the .highland bundle's text.md
# (which IS the Fountain content). Run any time to bring them current without a
# commit; the pre-commit hook does the same automatically on every screenplay commit.
#
#   - Blank Slate Full Script.fountain   tracked source the casting extractor + agents
#                                        parse. BODY ONLY (Fountain title page stripped)
#                                        so the cue extractor doesn't read
#                                        TITLE:/AUTHOR:/NOTES: as character cues.
#
# Why not a background "on save" agent? macOS TCC denies launchd agents access to
# iCloud Drive (~/Library/Mobile Documents), so a WatchPaths daemon can't read/write
# these files. This script runs as you (full access).
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HL="$REPO/Blank Slate Full Script.highland"
FOUNTAIN="$REPO/Blank Slate Full Script.fountain"

[ -f "$HL" ] || { echo "ERROR: .highland not found: $HL" >&2; exit 1; }
TEXT_PATH="$(unzip -Z1 "$HL" 2>/dev/null | grep -E '\.textbundle/text\.md$' | head -n 1)"
[ -n "$TEXT_PATH" ] || { echo "ERROR: text.md not found inside the .highland bundle" >&2; exit 1; }

TMP="$(mktemp)"; trap 'rm -f "$TMP"' EXIT
unzip -p "$HL" "$TEXT_PATH" > "$TMP"
[ -s "$TMP" ] || { echo "ERROR: extracted text.md is empty" >&2; exit 1; }

awk 'f || /^(INT|EXT|EST|I\/E)[.\/ ]/ {f=1} f' "$TMP" > "$FOUNTAIN"

echo "refreshed from the screenplay:"
echo "  $(basename "$FOUNTAIN")  ($(wc -l < "$FOUNTAIN" | tr -d ' ') lines, body only)"
