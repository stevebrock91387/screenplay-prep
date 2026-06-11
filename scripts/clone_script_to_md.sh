#!/usr/bin/env bash
# clone_script_to_md.sh
#
# Refresh the body-only .fountain from the .highland bundle's text.md (which IS the
# Fountain content). Run any time to bring it current without a commit; the pre-commit
# hook does the same automatically on every screenplay commit. The .fountain is BODY
# ONLY (Fountain title page stripped) so the cue extractor doesn't read TITLE:/AUTHOR:/
# NOTES: as character cues.
#
# Project-parameterized: resolves the .highland + .fountain filenames from
# PROJECT_PROFILE §0 (source.highland / source.fountain), and the project root from
# $CLAUDE_PROJECT_DIR when set (so it works bundled in the screenplay-prep plugin).
# Falls back to the first *.highland in the project root if there's no profile.
#
# Why not a background "on save" agent? macOS TCC denies launchd agents access to
# iCloud Drive (~/Library/Mobile Documents), so a WatchPaths daemon can't read/write
# these files. This script runs as you (full access).
set -euo pipefail

REPO="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
PROFILE="$REPO/Claude Docs/PROJECT_PROFILE.md"

# Pull a quoted §0 value for a key (e.g. highland, fountain); empty if absent/null.
profile_val() { [ -f "$PROFILE" ] && grep -m1 -E "^[[:space:]]*$1:[[:space:]]*\"" "$PROFILE" 2>/dev/null | sed -E "s/^[^\"]*\"([^\"]+)\".*/\1/"; }

HL_NAME="$(profile_val highland)"; [ -z "$HL_NAME" ] && HL_NAME="$(cd "$REPO" && ls -1 *.highland 2>/dev/null | head -1)"
FT_NAME="$(profile_val fountain)"; [ -z "$FT_NAME" ] && FT_NAME="${HL_NAME%.highland}.fountain"
HL="$REPO/$HL_NAME"
FOUNTAIN="$REPO/$FT_NAME"

[ -f "$HL" ] || { echo "ERROR: .highland not found: $HL" >&2; exit 1; }
TEXT_PATH="$(unzip -Z1 "$HL" 2>/dev/null | grep -E '\.textbundle/text\.md$' | head -n 1)"
[ -n "$TEXT_PATH" ] || { echo "ERROR: text.md not found inside the .highland bundle" >&2; exit 1; }

TMP="$(mktemp)"; trap 'rm -f "$TMP"' EXIT
unzip -p "$HL" "$TEXT_PATH" > "$TMP"
[ -s "$TMP" ] || { echo "ERROR: extracted text.md is empty" >&2; exit 1; }

awk 'f || /^(INT|EXT|EST|I\/E)[.\/ ]/ {f=1} f' "$TMP" > "$FOUNTAIN"

echo "refreshed from the screenplay:"
echo "  $(basename "$FOUNTAIN")  ($(wc -l < "$FOUNTAIN" | tr -d ' ') lines, body only)"
