# screenplay-prep

A reusable Claude Code **plugin** that packages the screenplay production-prep engine — read-only audit agents plus the reconcile / casting-doc / paged-HTML scripts — so it works turnkey across every screenplay you own. The reference instance it was extracted from is *Blank Slate*.

## The split

- **This plugin = the engine** (agents, scripts, the git hook, templates). Install once.
- **Each screenplay = a project repo** holding its own *content*: the `.highland`/PDF, `CANONICAL_FACTS.md`, the derived scene CSV, the production docs, and — the keystone — **`Claude Docs/PROJECT_PROFILE.md`**, the per-script parameter file every agent and script reads.
- No profile → the generic engine has nothing project-specific to read. Onboarding a new screenplay = copying `templates/PROJECT_PROFILE.template.md` and filling the `«per-project»` fields.

## What's inside

| Path | What |
|---|---|
| `agents/` | 15 read-only auditors (continuity, motif, slugline, cast-cue, fact-drift, fidelity, structure, dialogue-voice, rights, pitch, proofreader, revision-impact, derived-number, commit-gate, verify-then-update). Invocable as `screenplay-prep:<name>`. |
| `scripts/` | `reconcile.py` (PDF↔derived-doc reconcile, auto-holds `§0 reconcile_anchors`), `generate_casting_docs.py` + `extract_characters.py` (casting/table-read docs), `script_to_html_paged.py` (Fountain→paged HTML), `clone_script_to_md.sh` (text-mirror/​fountain refresh). Call via `${CLAUDE_PLUGIN_ROOT}/scripts/…`. |
| `skills/screenplay-audit/` | `/screenplay-prep:screenplay-audit [scope]` — runs the audit suite and consolidates findings. |
| `bin/pre-commit` | the `.highland`↔PDF lock-step git hook. **Not a plugin hook** (those fire on tool events; the `.highland` is edited outside Claude Code in Highland). Install per-project: `git config core.hooksPath` pointed at a dir containing it, or copy it into `.githooks/`. |
| `templates/` | `PROJECT_PROFILE.template.md` — the onboarding keystone. |

## Local-dev test

```bash
claude --plugin-dir "/path/to/screenplay-prep"
# then, inside a screenplay project that has Claude Docs/PROJECT_PROFILE.md:
#   /screenplay-prep:screenplay-audit
#   /screenplay-prep:screenplay-audit all
```

## Status (v0.1.0)

Skeleton. Agents + scripts are the parameterized versions proven on Blank Slate (no-regression) and a Family Business smoke test (adapts cleanly — absent capabilities scope the run instead of failing). **Known bootstrap duplication:** the agents/scripts here are copies of the Blank Slate repo's `.claude/agents/` + `scripts/`; once this plugin is installed, that repo's local copies become redundant and can be retired. Not yet wired to a marketplace (`marketplace.json` + `/plugin install`) — that's the next step, along with the `/screenplay-prep:new`, `:reconcile`, `:html`, `:handoff`, `:init` skills. See the originating `PLUGIN_PLAN.md`.
