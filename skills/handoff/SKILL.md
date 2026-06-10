---
name: handoff
description: Refresh the project's HANDOFF.md against actual repo state using the verify-then-update discipline — read the real git log, derived-doc state, and open worklist items FIRST, then update the one named handoff document to match, showing the assembled result before it's saved. Use at the end of a working session or before handing the project to another tool/person.
---

# Refresh HANDOFF

You are refreshing `${CLAUDE_PROJECT_DIR}/Claude Docs/HANDOFF.md` (or the path in `§0 reference_docs.handoff`) for the screenplay project. Follow the project's **verify-then-update** discipline: establish actual state before writing, update one named target, show the result before committing.

## Verify (state FIRST — never write from memory)

1. Read the current `HANDOFF.md` and note its "last updated to commit X" anchor.
2. Establish actual repo state: recent `git log --oneline` since that anchor, `git status`, and whether the derived corpus is current (scene CSV / Runtime Model / text mirror vs. the latest script commit). Note any uncommitted work and any open items in `SCRIPT_REVISION_NOTES.md` (`§0 reference_docs.revision_notes`).
3. List the gaps between what HANDOFF.md claims and what the repo actually shows. These are what the update fixes.

## Update (one target, shown before saved)

4. Update HANDOFF.md to match reality: bump the commit anchor, fold in what changed since, refresh the open-worklist and "creative decisions / locked" sections, and correct anything now stale. Preserve the document's existing structure and any standing-constraint notes verbatim.
5. **Show the assembled result** (the diff, or the rewritten sections) before it is final. Do not invent status — if something is uncertain, say so in the doc as an open item rather than asserting completion.

## Don't

Don't commit unless the writer asks. Don't touch any document other than HANDOFF.md in this skill — if the verify step surfaced drift elsewhere (a stale number, an unreconciled CSV), report it as a finding and point at `/screenplay-prep:reconcile` or `/screenplay-prep:audit`; fixing it is a separate, deliberate step.
