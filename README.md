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
| `skills/` | Six slash commands: `/screenplay-prep:new <Title>` (onboard a project — stamp the profile template), `:init` (install the git hook), `:reconcile` (reconcile-baseline after an edit), `:audit [scope]` (run the auditor suite, consolidated by severity), `:html` (regenerate the paged web reader), `:handoff` (refresh HANDOFF via verify-then-update). |
| `bin/pre-commit` | the `.highland`↔PDF lock-step git hook. **Not a plugin hook** (those fire on tool events; the `.highland` is edited outside Claude Code in Highland). Install per-project: `git config core.hooksPath` pointed at a dir containing it, or copy it into `.githooks/`. |
| `templates/` | `PROJECT_PROFILE.template.md` — the onboarding keystone. |

## Install (private marketplace)

This repo is also its own marketplace (`brock-screenplays`, declared in `.claude-plugin/marketplace.json`):

```bash
claude plugin marketplace add "/path/to/screenplay-prep"   # local path, GitHub repo, or git URL
claude plugin install screenplay-prep@brock-screenplays
claude plugin list                                          # verify: enabled, v0.2.0
```

Or from inside a session: `/plugin marketplace add <path>` then `/plugin install screenplay-prep@brock-screenplays`. Choose scope at install (`--scope user` for every project, `--scope project` to commit per-repo). Inventory: 6 skills + 15 agents, ~2.1k always-on tokens.

## Local-dev test (no install)

```bash
claude --plugin-dir "/path/to/screenplay-prep"
# then, inside a screenplay project that has Claude Docs/PROJECT_PROFILE.md:
#   /screenplay-prep:audit
#   /screenplay-prep:audit all
```

## Status (v0.2.0)

Skeleton + the six skills (`new` / `init` / `reconcile` / `audit` / `html` / `handoff`) + a private marketplace (`brock-screenplays`). Agents + scripts are the parameterized versions proven on Blank Slate (no-regression) and a Family Business smoke test (adapts cleanly — absent capabilities scope the run instead of failing). Verified: headless `--plugin-dir` load (15 agents + 6 skills register under `screenplay-prep:`), and the full `marketplace add → install screenplay-prep@brock-screenplays → list` cycle (in an isolated config). **Known bootstrap duplication:** the agents/scripts here are copies of the Blank Slate repo's `.claude/agents/` + `scripts/`; once this plugin is installed, that repo's local copies become redundant and can be retired. The one remaining hardcoding is `extract_characters.py` (the `#(\d+)#` marker regex + fountain source). See the originating `PLUGIN_PLAN.md`.
