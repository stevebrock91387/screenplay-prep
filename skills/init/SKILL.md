---
name: init
description: Install the source↔PDF lock-step git pre-commit hook into the current screenplay project. The hook is a git hook (not a Claude Code plugin hook) because the screenplay is edited outside Claude Code in a writing app, so only a git commit-time check can catch it. Format-aware (Highland bundle OR a Fountain export from any tool); reads filenames from PROJECT_PROFILE §0. Use once per project clone, after onboarding.
---

# Install the git hook

You are wiring the source↔PDF pre-commit hook into the screenplay project at `${CLAUDE_PROJECT_DIR}`. This is a **git** hook, not a Claude Code plugin hook — plugin hooks fire on tool/session events, but the screenplay is edited in a writing app (outside Claude Code), so the only reliable enforcement point is `git commit`. The hook blocks a commit that changes the screenplay text unless the re-exported PDF is staged too, then re-derives the body-only `.fountain` + the paged HTML. It is **project-parameterized** — it reads the source/PDF/derived filenames from `PROJECT_PROFILE §0`, and dispatches on the container: if `source.highland` is set it watches the `.highland` bundle; otherwise it watches the committed Fountain file named in `source.text_mirror` (the Final Draft / WriterDuet / Fathom / any-tool path). No companion app required.

## Verify first

1. Confirm `${CLAUDE_PROJECT_DIR}` is a git repo (`git rev-parse --show-toplevel`). If not, tell the writer to `git init` first (or offer to) — the hook has nothing to attach to otherwise.
2. Check whether a pre-commit hook is already installed (an active `core.hooksPath`, or `.git/hooks/pre-commit`, or a tracked `.githooks/pre-commit`). **If one exists, show it and STOP** — don't clobber a hook you didn't write; report what's there and let the writer decide.

## Install

3. Recommended (tracked, shareable): create `${CLAUDE_PROJECT_DIR}/.githooks/` if absent, copy `${CLAUDE_PLUGIN_ROOT}/bin/pre-commit` to `.githooks/pre-commit`, `chmod +x` it, and set `git config core.hooksPath .githooks`. This keeps the hook in the repo so a fresh clone just needs the one `git config` line.
4. The hook reads its filenames from `PROJECT_PROFILE §0` (`source.highland` / `source.pdf` / `source.text_mirror` / `source.fountain`), so nothing is hardcoded — just confirm §0 is filled. **Final Draft / bare-Fountain projects:** make sure `source.highland: null` and `source.text_mirror` points at the committed full `.fountain` export (the hook watches that file); `source.fountain` should be a *different*, derived body-only path (e.g. `Claude Docs/<name>_body.fountain`). If `§0` isn't filled yet, the hook installs but stays a silent no-op until it is.
5. Verify it's live: `git config --get core.hooksPath` returns `.githooks`, and the file is executable.

## Report

State what you installed and the one command a future clone needs (`git config core.hooksPath .githooks`). Do not commit the hook install unless the writer asks. Note that the hook also re-derives the `.fountain` and regenerates the paged HTML on every screenplay commit — so those stay current automatically once it's wired.
