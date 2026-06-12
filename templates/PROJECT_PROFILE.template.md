# PROJECT_PROFILE — «Title»

> **The single per-screenplay parameter file.** Everything the reusable engine (screenplay-prep plugin: agents + scripts) needs to operate on *this* screenplay lives here or is pointed to from here. Copy this template into `<project>/Claude Docs/PROJECT_PROFILE.md` and refill every field marked **`«per-project»`**. Numbers themselves live in `CANONICAL_FACTS.md` (the fact arbiter); this file holds the *non-numeric* parameters and points at the rest.

---

## 0. Engine parameters (machine-readable — agents/scripts read THIS block)

```yaml
source:
  # The git hook dispatches on which container you commit:
  #   • Highland users: set `highland` to the bundle; commit it + the PDF.
  #   • Final Draft / WriterDuet / Fathom / any tool: set `highland: null` and EXPORT
  #     a full Fountain file + a PDF, commit both, and point `text_mirror` at that
  #     .fountain. The engine reads Fountain text + the PDF — no companion app needed.
  highland: null                        # the .highland bundle, OR null for a Fountain-export workflow
  pdf: "«Title».pdf"                    # the rendered PDF (pagination authority); commit it with the source
  text_mirror: "«Title».fountain"       # the FULL screenplay text the agents read — for a Fountain-export
                                        # workflow this IS your committed .fountain; for Highland, "Claude Docs/«Title»_text.md"
  fountain: "Claude Docs/«Title»_body.fountain"   # DERIVED body-only fountain for the cue extractor (must differ from text_mirror)
  format: fountain                      # content type: fountain | text | fdx(needs-convert)

scene_markers:
  expected: true                        # FALSE for unlocked drafts (no #N#) — else "missing markers" is a false defect
  regex: '#(\d+)#'                      # trailing slug scene markers

canonical:
  facts_doc: "Claude Docs/CANONICAL_FACTS.md"   # authoritative for all numbers; null if none yet
  scene_count: null                     # fountain slug count; null until locked
  body_pages: null

quote_standard: null                    # straight | smart | null (detection is generic; the canonical glyph is a project choice)
separator_standard: " - "               # slug element separator

locations:
  master_set: null                      # line→logical scene CSV; "unreconciled slug = finding" only if this exists
  scout_doc: null
  approx_count: null

transition_policy: {}                   # project law, NOT screenplay law — leave empty for scripts with no house rule

reference_docs:
  handoff: "Claude Docs/HANDOFF.md"
  revision_notes: "Claude Docs/SCRIPT_REVISION_NOTES.md"
  scene_csv: null                       # reconcile.py parse baseline; null until a derived CSV exists
  runtime_model: null                   # reconcile.py target doc; null if no Runtime Model

cast_registry: []                       # cue↔roster reconciliation files; [] until a registry exists

reconcile_anchors: []                   # Runtime-Model sections held against auto-re-anchoring; [] if none
```

---

## 5. Cast & alias systems (for `cast-cue-linter` — prose inventory)

*List each character whose cues legitimately vary, and the canonical form. Mark suspected continuity slips to flag (not silently unify). Empty until the cast is set.* `«per-project»`

## 6. Motif inventory (for `motif-tracker` — verify each fires across ALL instances)

*List each recurring motif/patterned setup and its full instance set (scene + line + the signature form). `motif-tracker` reports "nothing to verify" if this is empty.* `«per-project»`

## 9. Reconcile anchors (for `scripts/reconcile.py` — auto-held from §0)

*If any Runtime-Model section must keep a logical scene the line-position heuristic would eject, list it in §0 `reconcile_anchors` as `{ section, includes_logical_scene }`. `reconcile.py` then pins it automatically. Empty for most scripts.* `«per-project»`
