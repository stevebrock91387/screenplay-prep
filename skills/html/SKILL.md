---
name: html
description: Generate the paged, Squarespace-ready HTML reader from the screenplay's text mirror via script_to_html_paged.py (Highland-calibrated pagination, renders [[ notes ]] as styled note boxes). Use to refresh the embeddable web reader after a script change.
---

# Paged HTML reader

You are generating the paged HTML reader for the screenplay in `${CLAUDE_PROJECT_DIR}` — the standalone web version (e.g. for embedding in Squarespace), an alternative to a sketchy PDF embed.

## Inputs

1. Read `${CLAUDE_PROJECT_DIR}/Claude Docs/PROJECT_PROFILE.md` §0 for `source.text_mirror` (the title-page + body text the converter takes; NOT the body-only `.fountain`, so the title page renders). If the mirror is stale, run `/screenplay-prep:reconcile` first (or refresh it) so the HTML reflects the current script.
2. The converter is `${CLAUDE_PLUGIN_ROOT}/scripts/script_to_html_paged.py`. It is fully arg-driven (`--input`, `--out`, `--page-height`) and Highland-calibrated (parenthetical width 212 for Highland page parity — deliberately NOT the Fathom app's 137; don't "fix" it). `[[ … ]]` notes render as distinct `.note` boxes — these are intentional narrator notes the writer exports in the Highland PDF, kept visible, not hidden.

## Run

3. Run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/script_to_html_paged.py" --input "<text_mirror>" --out "<project>/Claude Docs/generated/script_paged.html"`. The `generated/` tree is conventionally gitignored.
4. Report the output path and the page count the converter landed (it should match the canonical body-page count in §0 `canonical.body_pages` if one is set). If it diverges by more than a page, flag it — usually a pagination-calibration or notes-handling issue, not a content one.

## Note

The project's git pre-commit hook may already regenerate this HTML on every screenplay commit; this skill is for an on-demand refresh or a first generation. Do not commit the generated file unless the writer asks — it's a derived artifact.
