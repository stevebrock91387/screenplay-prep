---
name: reconcile
description: Run the reconcile-baseline flow after a screenplay edit — refresh the plain-text mirror from the .highland, then run reconcile.py to recompute the scene CSV + Runtime Model against the committed PDF, holding the §0 reconcile_anchors automatically. Reports the derived delta for the writer to review and commit. Use as part of every committed script edit.
---

# Reconcile baseline

You are running the reconcile-baseline for the screenplay in `${CLAUDE_PROJECT_DIR}` after a script edit. This keeps the derived corpus (text mirror, scene CSV, Runtime Model, CANONICAL_FACTS render-derived numbers) in lock-step with the screenplay — the project's standing rule is that this happens as part of *every* committed script edit, not deferred.

## Preflight

1. Read `${CLAUDE_PROJECT_DIR}/Claude Docs/PROJECT_PROFILE.md` §0. You need `source.highland`, `source.text_mirror`, and `reference_docs.scene_csv`. If there is no `reconcile.py`-style derived corpus for this project (no scene CSV / Runtime Model), tell the writer this project doesn't use the reconcile engine and stop.
2. `reconcile.py` reads the **committed** PDF and compares the live `.highland` text hash to `.script-state`. If they're out of sync it will block — that means the PDF needs re-exporting from Highland (a GUI step the writer does) and the change committing first. Surface that clearly; don't try to render the PDF.

## Run

3. **Refresh the text mirror** from the `.highland` (the mirror is a verbatim copy of the bundle's `text.md`; nothing auto-regenerates it). Extract `*/text.md` from the bundle and write it over `source.text_mirror`. Confirm the diff is only the expected edited lines.
4. **Report mode first:** run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/reconcile.py"` (no `--apply`) with `CLAUDE_PROJECT_DIR` set to the project. Read the output:
   - Part A header changes + the **anchor `HELD`/`OK` lines** — confirm each `§0 reconcile_anchors` entry shows `HELD` (engine re-anchor rejected) or `OK` (stable). The engine now holds these automatically; you do **not** hand-restore.
   - Part B CSV row changes, Part 5 runtime, Part 6 CANONICAL_FACTS audit, Part 7 stale-page-count grep.
5. If the delta looks right, run with `--apply`. Then `git diff` the derived docs and **sanity-check**: legitimate changes (a scene whose edited text nudged its page weight, and the roll-up) vs. anything unexpected. The anchored sections should be untouched.

## Report

Summarize: what changed in the scene CSV, the Runtime Model totals, and whether any CANONICAL_FACTS number actually moved (dialogue/slug edits are usually count-neutral). List the anchor `HELD`/`OK` status. Do **not** commit — show the writer the diff and let them commit the script + derived docs together (the pre-commit hook enforces the `.highland`↔PDF lock-step).
