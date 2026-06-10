---
name: screenplay-audit
description: Run the read-only screenplay audit suite against the current project. Reads PROJECT_PROFILE.md §0 for the per-screenplay parameters, then dispatches the relevant auditor agents (continuity, motif, slugline, cast-cue, fact-drift, fidelity, structure, dialogue) and summarizes findings by severity. Use after a script revision, before circulating a draft, or to spot-check the derived production-doc corpus.
---

# Screenplay audit

You are orchestrating the **screenplay-prep** audit suite for the screenplay project in the current working directory. The agents are project-parameterized: they read `${CLAUDE_PROJECT_DIR}/Claude Docs/PROJECT_PROFILE.md` §0 for the per-screenplay configuration and otherwise behave generically.

## Preflight

1. Confirm `${CLAUDE_PROJECT_DIR}/Claude Docs/PROJECT_PROFILE.md` exists. If it does not, tell the user this project has not been onboarded yet — they need a `PROJECT_PROFILE.md` (copy `${CLAUDE_PLUGIN_ROOT}/templates/PROJECT_PROFILE.template.md` and fill the `«per-project»` fields). Do not fabricate parameters; stop here.
2. Read §0. Note which capabilities are available for *this* project: `scene_markers.expected`, `canonical.facts_doc` (null → fact-drift has nothing to audit), `locations.master_set` (null → no location reconcile), `cast_registry` (empty → cast-cue skips roster reconciliation), and the §6 motif inventory (empty → motif-tracker reports "nothing to verify"). An absent capability is **not** a failure — it scopes the run.

## Scope

`$ARGUMENTS` selects the run. With no argument, run the **default set**: `slugline-location-linter`, `cast-cue-linter`, `continuity-checker`, `motif-tracker`, `fact-drift-auditor`, `screenplay-fidelity-auditor`. Recognized argument tokens (space- or comma-separated): the agent names above, plus `dialogue` (`dialogue-voice-auditor`), `structure` (`structure-beat-mapper`), `rights` (`rights-clearance-scanner`), `pitch` (`pitch-consistency-auditor`), `proof` (`proofreader`), or `all` (every auditor).

## Run

Dispatch each selected agent (they are read-only — safe to run in parallel). Each returns a structured report. Then **synthesize one consolidated summary**:

- Group findings by severity the agents assign (P1/P2/P3 or CONTRADICTED / DRIFT / UNSUPPORTED, etc.).
- Lead with the single highest-risk finding and the agent that found it.
- For each agent, give a one-line verdict (clean, or N findings) so coverage is visible — never let a skipped/empty-capability agent read as "passed."
- Note any capability that was absent in §0 (and therefore not checked), explicitly.

Do **not** edit any file. These are flag-only audits; the writer decides and fixes. If asked for fix routes, point at `SCRIPT_REVISION_NOTES.md` conventions, but the edits are the human's call.
