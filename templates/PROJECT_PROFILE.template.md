# PROJECT_PROFILE — «Title»

> **The single per-screenplay parameter file.** Everything the reusable engine (screenplay-prep plugin: agents + scripts) needs to operate on *this* screenplay lives here or is pointed to from here. Copy this template into `<project>/Claude Docs/PROJECT_PROFILE.md` and refill every field marked **`«per-project»`**. Numbers themselves live in `CANONICAL_FACTS.md` (the fact arbiter); this file holds the *non-numeric* parameters and points at the rest.

---

## 0. Engine parameters (machine-readable — agents/scripts read THIS block)

```yaml
source:
  # Three onboarding paths, depending on your writing app:
  #   • Highland: set `highland` to the bundle; commit it + the PDF.
  #   • Final Draft (.fdx): set `fdx` to the file; run scripts/fdx_to_fountain.py to
  #     produce the .fountain `text_mirror`, then commit the .fdx + that .fountain + PDF.
  #     (/screenplay-prep:new does the conversion for you. FD scene numbers carry through
  #     as `#N#` markers, so scene_markers.expected can be true.)
  #   • WriterDuet / Fathom / anything else: EXPORT a full Fountain file + a PDF; set
  #     `highland: null`, `fdx: null`, and point `text_mirror` at that .fountain.
  # The engine always reads Fountain text + the PDF — no companion app required.
  highland: null                        # the .highland bundle (Highland), else null
  fdx: null                             # the Final Draft .fdx (converted to text_mirror), else null
  pdf: "«Title».pdf"                    # the rendered PDF (pagination authority); commit it with the source
  text_mirror: "«Title».fountain"       # the FULL screenplay text the agents read. Bare-Fountain: your committed
                                        # .fountain. Highland: "Claude Docs/«Title»_text.md". FDX: the CONVERTED
                                        # "Claude Docs/«Title».fountain" (output of fdx_to_fountain.py).
  fountain: "Claude Docs/«Title»_body.fountain"   # DERIVED body-only fountain for the cue extractor (must differ from text_mirror)
  format: fountain                      # content type: fountain | fdx

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
