---
name: fdx-sync
description: Re-convert a Final Draft .fdx to the project's Fountain text_mirror after the writer edits the .fdx. Wraps scripts/fdx_to_fountain.py — reads source.fdx + source.text_mirror from PROJECT_PROFILE §0, regenerates the .fountain the engine reads, and reports the delta. Use after every .fdx edit on a Final Draft project (the FD analogue of :reconcile's text-mirror refresh).
---

# Re-sync the Fountain from the .fdx

You are re-deriving the Fountain `text_mirror` from a Final Draft `.fdx` for the project in `${CLAUDE_PROJECT_DIR}`. On a Final Draft project the `.fdx` is the source the writer edits; the engine reads a converted `.fountain`, which does **not** regenerate itself — so after every `.fdx` edit this must run, the same way `:reconcile` refreshes a Highland project's text mirror from the bundle.

## Preflight

1. Read `${CLAUDE_PROJECT_DIR}/Claude Docs/PROJECT_PROFILE.md` §0. You need `source.fdx` and `source.text_mirror`.
2. **If `source.fdx` is null/absent, STOP** — this isn't a Final Draft project (it's Highland or bare-Fountain); point the writer at `:reconcile` instead. Only proceed when `source.fdx` names a real `.fdx`.

## Run

3. Convert: `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/fdx_to_fountain.py" --input "${CLAUDE_PROJECT_DIR}/<source.fdx>" --out "${CLAUDE_PROJECT_DIR}/<source.text_mirror>"` (resolve both paths from §0; they're project-relative). The converter maps the body faithfully — sluglines (with `Number=` → `#N#` markers), cues, dialogue, dual dialogue (`^`), and inline emphasis (`**`/`*`/`_`).
   - Add **`--notes`** only if the writer wants FDX script notes appended as a trailing `[[ ... ]]` block. Default off — notes are kept out of the body so cue/slug parsing stays clean.
4. `git diff` the `text_mirror` and **sanity-check** the delta: it should be exactly the writer's `.fdx` edits carried into Fountain, nothing more. A first-time conversion (large diff) is expected; a routine edit should be small.

## Report & next steps

5. Summarize what changed in the `.fountain`. Then surface — don't auto-run — the downstream steps the edit implies:
   - the body-only `.fountain` + paged HTML re-derive automatically via the fountain-mode pre-commit hook when the writer commits (the hook watches `text_mirror`);
   - if cues/scenes changed, `extract_characters.py` and the audit suite read the refreshed mirror on their next run;
   - `:reconcile` applies only if this project also keeps a scene-CSV / Runtime-Model baseline.

Do **not** commit. Show the writer the diff and let them commit the `.fdx` + the regenerated `.fountain` + the re-exported PDF together (the hook enforces the source↔PDF lock-step).
