---
name: new
description: Onboard a new screenplay project to the screenplay-prep engine. Stamps the PROJECT_PROFILE template into the current project's Claude Docs/, scaffolds the expected folders, and walks the writer through filling the «per-project» parameters. Use once per screenplay, before any audit/reconcile skill can operate.
---

# New screenplay onboarding

You are onboarding the screenplay in the current working directory (`${CLAUDE_PROJECT_DIR}`) so the screenplay-prep engine can operate on it. `$ARGUMENTS` is the project title (e.g. `Family Business`); if empty, ask for it.

## Verify first (do not overwrite)

1. Check whether `${CLAUDE_PROJECT_DIR}/Claude Docs/PROJECT_PROFILE.md` already exists. **If it does, STOP** — report that the project is already onboarded and show its `# PROJECT_PROFILE — <name>` header. Do not overwrite it. Offer to open it for editing instead.
2. Confirm the screenplay source is present (a `.highland` bundle, `.fountain`, `.fdx`, or a text export). Note what you found; the profile's `source.*` block must point at the real filenames. Resolve the source per format:
   - **`.highland`** → `source.highland` = the bundle; `source.text_mirror` = `Claude Docs/<name>_text.md` (the hook + reconcile manage it).
   - **`.fountain`** (a full export from any tool) → `source.highland: null`, `source.fdx: null`; `source.text_mirror` = that committed `.fountain`.
   - **`.fdx` (Final Draft)** → **convert it now**: run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/fdx_to_fountain.py" --input "<name>.fdx" --out "${CLAUDE_PROJECT_DIR}/Claude Docs/<name>.fountain"`. Set `source.fdx` = the `.fdx`, `source.format: fdx`, `source.text_mirror` = the converted `Claude Docs/<name>.fountain`. Tell the writer to **re-run that conversion whenever they edit the `.fdx`** — the `/screenplay-prep:fdx-sync` skill wraps it (the FD analogue of `:reconcile`'s mirror refresh). FD scene numbers come through as `#N#` markers, so `scene_markers.expected` can be `true`.
   - In all cases `source.fountain` (the body-only file the cue extractor reads) is a **derived** path under `Claude Docs/` (e.g. `<name>_body.fountain`), distinct from `text_mirror`; the git hook derives it.

## Stamp the template

3. Create `${CLAUDE_PROJECT_DIR}/Claude Docs/` if absent.
4. Copy `${CLAUDE_PLUGIN_ROOT}/templates/PROJECT_PROFILE.template.md` to `${CLAUDE_PROJECT_DIR}/Claude Docs/PROJECT_PROFILE.md`, replacing the `«Title»` tokens in the header and `source.*` paths with the real title/filenames you found (and the format you resolved in step 2). Leave every other `«per-project»` field as a placeholder — **do not invent** scene counts, motifs, alias systems, or cast. Those are the writer's to fill (and the agents read them).
5. Tell the writer exactly which fields still need filling and in what order: `source.*` (done if you could resolve them), `scene_markers.expected`, `canonical.*` (once a draft is locked), then §5 alias systems and §6 motif inventory as the script matures.

## Next steps to surface (don't run them unasked)

- `/screenplay-prep:init` — install the `.highland`↔PDF git pre-commit hook.
- `/screenplay-prep:audit` — once §0 is filled, the audit suite can run (absent capabilities simply scope the run).
- The engine reads everything from this profile; nothing else is screenplay-specific.

Do not commit anything. Onboarding creates files in the writer's project repo; let them review and commit.
