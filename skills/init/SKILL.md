---
name: init
description: Install the .highland↔PDF lock-step git pre-commit hook into the current screenplay project. The hook is a git hook (not a Claude Code plugin hook) because the .highland is edited outside Claude Code in Highland, so only a git commit-time check can catch it. Use once per project clone, after onboarding.
---

# Install the git hook

You are wiring the `.highland`↔PDF pre-commit hook into the screenplay project at `${CLAUDE_PROJECT_DIR}`. This is a **git** hook, not a Claude Code plugin hook — plugin hooks fire on tool/session events, but the screenplay is edited in Highland (outside Claude Code), so the only reliable enforcement point is `git commit`. The hook blocks a commit that changes the screenplay text inside the `.highland` unless the PDF was re-exported, and it re-derives the body-only `.fountain` + the paged HTML.

## Verify first

1. Confirm `${CLAUDE_PROJECT_DIR}` is a git repo (`git rev-parse --show-toplevel`). If not, tell the writer to `git init` first (or offer to) — the hook has nothing to attach to otherwise.
2. Check whether a pre-commit hook is already installed (an active `core.hooksPath`, or `.git/hooks/pre-commit`, or a tracked `.githooks/pre-commit`). **If one exists, show it and STOP** — don't clobber a hook you didn't write; report what's there and let the writer decide.

## Install

3. Recommended (tracked, shareable): create `${CLAUDE_PROJECT_DIR}/.githooks/` if absent, copy `${CLAUDE_PLUGIN_ROOT}/bin/pre-commit` to `.githooks/pre-commit`, `chmod +x` it, and set `git config core.hooksPath .githooks`. This keeps the hook in the repo so a fresh clone just needs the one `git config` line.
4. The hook expects the screenplay filenames; if this project's `.highland`/PDF names differ from the defaults baked into the hook, point that out — the hook may need its `PDF_PATH`/glob adjusted for this project (a known remaining generalization: the hook reads some hardcoded filenames).
5. Verify it's live: `git config --get core.hooksPath` returns `.githooks`, and the file is executable.

## Report

State what you installed and the one command a future clone needs (`git config core.hooksPath .githooks`). Do not commit the hook install unless the writer asks. Note that the hook also re-derives the `.fountain` and regenerates the paged HTML on every screenplay commit — so those stay current automatically once it's wired.
