---
name: cast-report
description: Build a polished, send-ready cast report (landscape PDF + full-width DOCX) from a cast CSV — e.g. a scene-scoped cast list headed to a casting service. Wraps scripts/make_cast_report.py: 10pt, bold headers, each role's row kept whole across pages, descriptions backfilled from casting_editorial.json. Use when the writer needs a formatted casting submission/handout, not the raw CSV.
---

# Cast report (landscape PDF + DOCX)

You are turning a cast CSV into a formatted, send-ready report for the screenplay in `${CLAUDE_PROJECT_DIR}`. The CSV is a per-role list — `Role, Description, Performer` — typically a scene-scoped export from the writer's app (Fathom/Highland/etc.) or a derived doc. The output is a **letter-landscape, 10pt, bold-header** report as both **PDF** (for sending) and **DOCX** (editable), with each role's row kept whole across page breaks.

## Preflight

1. Get the **cast CSV** path from the writer (or find the scene-scoped cast CSV they exported). It needs `Role` / `Description` / `Performer` columns (case-insensitive; extra columns ignored).
2. Note two optional sources the script uses if present: `Claude Docs/casting_editorial.json` (to backfill blank descriptions) and the project's `Conversion Tools/md2docx.js` (for the DOCX). The **PDF needs Google Chrome** (headless render so page-breaks / repeating headers / landscape are honored); if Chrome is absent it falls back to `Conversion Tools/html2pdf.swift` with a warning (that path can split long rows).

## Run

3. `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/make_cast_report.py" --csv "<the CSV>" --title "<Project> — Cast …" --subtitle "<scope, e.g. Scenes 1–30>"` with `CLAUDE_PROJECT_DIR` set to the project. Add:
   - `--blank-performer` for an outbound-to-casting sheet (empties the Performer column);
   - `--no-fill` to leave blank descriptions blank instead of pulling from `casting_editorial.json`;
   - `--out-stem "<name>"` to set the output filename (default: `<csv> - Report` beside the CSV).
4. The script writes `<stem>.pdf`, `<stem>.docx`, and the `.html`/`.md` sources. It never invents data — a blank field with no editorial fallback stays blank.

## Report

State the output paths, the role count, and whether the PDF used Chrome or the Swift fallback (so the writer knows if rows could split). Do **not** commit — these are deliverables the writer reviews and sends; leave them for the writer to keep or discard.
