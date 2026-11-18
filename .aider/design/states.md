# workflow-coda — Feature 6 ("states") — Master Handoff Specification

**Scope:** the whole remaining feature — the producer half (6a, in flight) and the
consumer half (6b, not started), plus parked items and riders. This supersedes any
earlier 6a-only handoff and folds it in; it is written to be the single document
carried into a fresh session. Where this spec conflicts with source, **the
source code is ground truth** — re-derive from source and flag the discrepancy.

---

## 1. The project in one paragraph

`workflow-coda` builds **self-contained single-file HTML reports** from pipeline
artifact bundles. A JSON **manifest** (schema version currently `"0.3.0"`) declares
artifacts (id, type, path, format, status); a YAML **layout** (layout schema version,
just flipped `"0.2.0"` → `"0.3.0"`) composes pages from plugin **components** through
tabs and `row`/`grid`/`card`/`diagnostics` composition nodes plus component placements;
**plugins** declare components gated by the manifest's schema version; the **builder**
walks the layout into a registry-free `ReportDocument` tree; the **renderer** emits one
HTML page with embedded assets (data URIs, inlined SVG logos), themes, inline
scripts, and a diagnostics ledger. Authoring mistakes **teach** (named errors with the
fix spelled out); degradation is data (notice/skip/fail policies, collapse of empty
compositions, problems vs informational diagnostic kinds). Reports are read as local
files; the page is CSP-constrained and must hold no network dependency.

**File map and held-status:**

| File | Role |
|---|---|
| `layout.py`, `layout_loader.py`, `text.py` | Layout models, loader, leaf text rules |
| `verification/expansion.py` | `for_each` placeholder engine |
| `report.py`, `builder.py` | Document models; build pipeline |
| `render.py`, `templates/*` | Document → HTML |
| `tests/` (factories, layout, layout_loader, core_notice, core_seam, tutorials, registry) | Suite, single-sourced for versions |
| Builder/renderer/verification-spec test files | — |
| `docs/` (Sphinx; `schemas.rst`, `core/*.rst`, examples `hello-report/`, `waterfall-plugin/`, `build/`) | Reference + tutorials |

---

## 2. Feature 6, whole: what "states" is

One report dimension — `batch`, `sample_id` — with an axis of values; the report
**builds every state's content** and the **reader selects** which state is shown. Two
halves, one composition law:

- **Producer half (6a):** the layout's `type: states` node; the builder expands
  children once per axis value at **build time**; the renderer emits one panel per
  state. The page carries all N states in the DOM.

    source keys	exactly one of values / samplesheet / glob per for_each; zero or multiple teach
    file:	required with values/samplesheet; forbidden with glob — the glob is the path provider, the FILE/--spec law transposed
    glob grammar	exactly one {name}, and it names the dimension
    samplesheet	{file, column, sep?} read through the tabular grammar, sep defaulting to tab; duplicate values and blank cells teach
    order	first appearance — the producer's order is the story
    sanitize	default off — silent lowercasing is the dishonest fix; raws interpolate into file:/glob:/samplesheet: (the disk's names are the truth); the slug interpolates into id:/type: when sanitize: true; with it off, a grammar-failing raw teaches per-value, the toggle named as the fix
    --on-failure	composes exactly as locked: fail aggregates every expanded problem; write records per artifact — expansion problems are spec-authoring facts (the availability family), the toggle never reaches them

- **Consumer half (6b):** **URL directives at read time** select the visible state;
  widgets (by axis kind) drive the URL; degradation stacks everything.

    node	states composition node: dimension + children as the template
    expansion	build-time, per axis value, onto the existing panel machinery — never runtime fetching; CSP forbids network, and self-containment prices in N × content
    selection	URL directives at read time
    widgets	by axis kind: categorical → radio/dropdown, ordered → range slider, subset → checkbox list — state-as-subset is parked open by the record itself
    degradation	no-js and print stack every state — the panels law already decided this
    manifest	unchanged, 0.3.0; the axes block (carrying raws) is future work

- **The composition law:** *selection adds no content and removes no content — it
  only chooses what is visible, and the URL is the chooser of record.* The
  un-enhanced DOM (no JS, print) **is** the full stacked report. This is why the two
  halves compose without coupling: 6b is presentational over exactly what 6a produced.

### The record's consumer-half ruling (verbatim, from the earlier discussion — authoritative)

node states composition node: dimension + children as the template expansion build-time, per axis value, onto the existing panel machinery — never runtime fetching; CSP forbids network, and self-containment prices in N × content selection URL directives at read time widgets by axis kind: categorical → radio/dropdown, ordered → range slider, subset → checkbox list — state-as-subset is parked open by the record itself degradation no-js and print stack every state — the panels law already decided this manifest unchanged, 0.3.0; the axes block (carrying raws) is future work


Unpacked: expansion is build-time only — **never runtime fetching** (CSP forbids
network; self-containment prices in N×content, accepted). Selection is URL-driven at
read time. The widget vocabulary follows `kind`: categorical → radio/dropdown,
ordered → range slider; **subset (checkbox list) is parked**. No-js and print stack
every state — the tab-panels precedent already decided this; **do not re-litigate**.
The manifest is untouched by feature 6; a future *axes block* (carrying raw axis
values from the pipeline) is work beyond this feature.

### Producer-half rulings already gated (carry these; they are law, not sketch)

- **R1 — one door.** `values:` declared is the axis, order as written; **absent means
  derived** from the manifest's artifact types, in declaration order. Absence is
  derivation, not contradiction.
- **R2 — `kind` declared, never inferred.** `categorical` (default — peers, no
  position means anything) or `ordered` (the axis is a sequence). `["1","2","3"]` are
  labels unless the author declares `ordered`.
- **R3 — the reference lands with the node.** Done: `schemas.rst` carries the states
  row, migration bullets, orphan rule.
- **R4 — declared-empty teaches at load** (model validator); **derived-empty is a
  build-time fact** — the node collapses (collapse-travels-upward) and records an
  **informational** diagnostic.
- **Dimension = placeholder name**, grammar `[a-z][a-z0-9_-]*`, single-homed as
  `DIMENSION_NAME_RE` in `text.py`; `expansion.py`'s `_PLACEHOLDER` **derives** from it.
- **Placement `id` refuses placeholders** (loader teaches; builder never re-teaches).
  **Orphan placeholders outside states teach at load** — composition strings get the
  "add a states node" fix; unbindable strings (report identity, tab titles) get
  "write the literal text"; declared paths (`theme`/`logo`/`favicon`) are deliberately
  unchecked (resolution strings fail their own not-found teaching).
- **Only `{` opens the placeholder language**; a lone `}` rides. **No escape for a
  literal `{` in rendered strings** — accepted cost (standing ruling).
- **The page is where a template must never arrive raw.**
- **Parameters substitute through `substitute_raw`** — one law for every string leaf,
  keys and values, recursively; raws substitute **verbatim** (no slug).
- **Pinned teachings are load-bearing.** `expand_template`'s mismatch teaching shipped
  byte-identical through the scope change; its spec-flavored wording gets reworded
  only with the expansion test file's pins pasted.
- **States nodes nest**, including states over different dimensions inside another's
  children.

---

## 3. Status — done and gated green (trust as done)

1. **6a-1 (gated):** version flip (`LAYOUT_SCHEMA_VERSION = "0.3.0"`, pinning test
   green), `_require_dimension_name`, the full `StatesNode` model (`type`,
   `dimension`, `kind` default `"categorical"`, `values: tuple[VisibleText, ...] |
   None`, `children` min 1, `_declared_axis_laws`), dispatch/union/rebuilds, the
   0.2.0 migration teaching, the orphan-placeholder loader machinery (`_reject_brace`
   with composable/unbindable fixes, `_reject_id_brace`, `_reject_brace_json`,
   `_walk_orphan`, `_walk_scoped`, `_reject_orphan_placeholders`), docs sweep
   (`schemas.rst` states row + bullets, `macros.jinja` comment, examples, sanity
   fixture).
2. **Suite single-sourcing (gated):** fixtures interpolate `LAYOUT_SCHEMA_VERSION`;
   shipped example files carry the literal; version-gate tests keep literals;
   `minimal_yaml_with(*keys)` helper anchors insertions structurally; new
   `test_0_2_0_layout_is_taught_the_migration`; mypy enforced the law statically.
3. **`expansion.py` scope delta (gated), eight bounded edits:** `expand_template`
   gained keyword-only `scope: Sequence[str] | None = None`; `bound = tuple(scope) if
   scope is not None else (dimension,)`; a pass-through branch (`name in bound` →
   append `match.group(0)`, continue) before the **unchanged** teachings; `_PLACEHOLDER`
   derived from `DIMENSION_NAME_RE`; docstrings; import. M5 callers
   behavior-identical by construction.

**Live gap (pre-named, by design):** with 6a-1 gated but 6a-2/6a-3 unapplied, a
states node **loads** but the builder's `_walk` ends in
`assert isinstance(node, CardNode)` (raises `AssertionError`) and the renderer has an
analogous union-exhausted assert. 6a-2/6a-3 replace them.

---

## 4. Producer half — remaining work

### 4.1 — 6a-2: document models + builder

**Materials:** read `report.py`, `builder.py`, `expansion.py`

**(a) `expansion.py` rider:** `substitute_raw` gains the same keyword-only
`scope: Sequence[str] | None = None`, threaded into its three `expand_template`
calls; M5 calls unchanged. (Without it, states parameter substitution mis-teaches on
nested placeholders.)

**(b) `report.py`:** insert after `CardEntry`:
- `StatePanel` — `value: str` (the axis value; panel label),
  `children: tuple[DocumentNode, ...]`; `__post_init__` requires non-empty children
  (+ `has_visible_text(value)` per the models' guard idiom).
- `StatesEntry` — `dimension: str`, `kind` (shared `StatesKind` Literal in
  `layout.py` is the clean spelling — **carrying `kind` on the document is now doubly
  motivated: 6b's widget renders by it**), `panels: tuple[StatePanel, ...]`;
  `__post_init__` ≥1 panel.
- `DocumentNode = … | CardEntry | StatesEntry`.
- Module docstring: **insert** after the collapse sentence — a states node becomes a
  `StatesEntry` with one `StatePanel` per axis value in axis order; the document is
  the **expanded** tree; no placeholder survives into it. (Do not rewrite existing
  prose.)

**(c) `builder.py` — decided architecture (per-round pre-pass substitution):**
- `_WalkState` gains `layout_path: Path` (the `SpecError`→`LayoutError` boundary
  needs it).
- Scope threading: `_walk(state, node, scope_prefix=())`, `_walk_all(state, nodes,
  scope_prefix=())` — defaults keep every existing call unchanged.
- `_pending_dimensions(node) -> tuple[str, ...]` — dimensions states nodes inside
  the subtree will bind.
- `_expand_node(node, *, dimension, raw, bound, path) -> LayoutNode` — one
  substitution round over a **copy** (`model_copy(update=...)`; frozen but copyable):
  placement `title` expanded, `parameters` through `substitute_raw(..., scope=bound)`;
  `id`/policies untouched; card `title` expanded; children recursed; nested
  `StatesNode` recursed with `values` and children substituted (open point O1),
  structure fields kept; `bound` includes pending dimensions so inner placeholders
  pass this round.
- `_walk_states(state, node, scope_prefix)`: axis = `node.values` or derived
  (distinct manifest artifact types, first-occurrence order — O3); derived-empty →
  informational diagnostic + `None` (R4); per value, substitute each child under
  `try/except SpecError as e: raise LayoutError(f"{state.layout_path}: {e}") from e`,
  walk with `scope_prefix + (node.dimension,)`; a value whose children all collapse
  drops its panel; no panels → `None`; return `StatesEntry(...)`.
- `_walk` dispatch: `if isinstance(node, StatesNode): return _walk_states(...)` before
  the `CardNode` assert (which then correctly exhausts the union again).
- New `DiagnosticKind` (e.g. `STATES_EMPTY = "states_empty"`, informational — not in
  `_PROBLEM_KINDS`): **check `render.py` first** — if the renderer maps kinds
  exhaustively, the member's rendering belongs to 6a-3; add it in whichever turn
  holds both sides.

**Rationale (decided):** each round substitutes exactly its own dimension across the
whole subtree, passing through placeholders nested nodes will bind later; nesting
resolves by round order; the existing walk/render/collapse machinery is reused
unchanged. The walk-integrated alternative needs a stack-consuming engine change
with no added semantics — rejected.

**Producer-half open points (rule these first, then record):**
- **O1** nested declared `values` carrying an outer placeholder → recommend
  **substitute them in the outer round** (one-law-for-every-string-leaf; the loader
  lets braces in `values` pass).
- **O2** dimension shadowing → per-round substitution makes the outer round win;
  document as behavior, pin it.
- **O3** derived-axis dedup → distinct types, first-occurrence order.
- **O4** `kind` on the document → yes (6b needs it); a `data-kind` attribute is the
  cheap page marker.

### 4.2 — 6a-3: the renderer — now designed with 6b in hand

**Materials:** read `render.py` whole  and `templates/` (at least
`macros.jinja` + stylesheet templates).

- Add the `StatesEntry` branch to the document walks (the union asserts raise on it
  today).
- Render panels **in axis order** (tuple order preserves it); each panel: the value
  as a visible, **escaped** heading + its children through the existing node
  renderers.
- **The panel-identity contract (required by 6b — ship it here, or 6b-1 re-touches
  this code):** each panel wrapper carries a stable `id`,
  `data-state-dimension="<dimension>"`, `data-state-value="<raw value>"`; the states
  wrapper carries `data-states-dimension` and optionally `data-kind`. Print CSS must
  leave all panels visible; no-JS must leave all panels in the DOM (see 6b-1).
- Style from the existing card vocabulary (a `coda-states`/`coda-state` family is the
  natural proposal — decide with the templates in hand).
- Wire the new `DiagnosticKind` member if 6a-2 added one.

### 4.3 — 6a test waves (all states teachings currently unpinned)

- **Model/loader:** dimension grammar rejections; `kind` literals + unknown refusal;
  `values` empty/duplicate teachings; children ≥1; nesting through every level; a
  states YAML loads end-to-end; orphan teachings (composable vs unbindable vs id fix;
  lone `}` rides; malformed placeholder).
- **Builder:** declared axis order; derived axis (declaration order, dedup);
  derived-empty collapse + informational diagnostic; substitution of titles/parameter
  keys and values, raws verbatim; nested pass-through both directions; shadowing
  pinned; unbound placeholder → `LayoutError` naming the layout path; per-panel and
  whole-node collapse.
- **Renderer:** panels in axis order with escaped headings; children through existing
  paths; new diagnostic kind renders.
- **Reword rider:** with the expansion spec test file pasted, reword the mismatch
  teaching for its second consumer and update its pins in the same turn.

---

## 5. Consumer half — 6b: read-time state selection

### 5.1 What is ruled (the six lines, only)

Build-time expansion with N×content priced in; never runtime fetching. Selection by
URL directives at read time. Widgets by axis kind: categorical → radio/dropdown,
ordered → range slider; subset → checkbox list, **parked**. No-js and print stack
every state (the panels law — the tab precedent — already decided this; do not
re-litigate). Manifest untouched.

Everything below §5.1 is **proposed architecture and open points** — the earlier
session never ruled beyond the six lines. The new session rules first, records the
rulings, then builds.

### 5.2 Architecture proposal

- **Selection state is one mapping `dimension → value`, global to the report.** URL
  directives address dimensions; nested states compose (both dimensions selected);
  two states nodes over the same dimension must stay in sync, and one global
  selection per dimension guarantees it structurally.
- **The URL is the source of truth.** On load and on `hashchange`, the script parses
  the directive(s) and applies them; widget interactions write the URL. No directive
  → default (open point W2).
- **Progressive enhancement, tabs-style.** The DOM ships with every panel present
  (that *is* the no-js/print report — the panels law satisfied by construction, no
  duplicate rendering paths). JS adds the hiding enhancement and the widget chrome.
  The mechanism (a root class set by the framework script? inline `hidden`?) —
  mirror whatever the existing tab script does; that is the precedent to reuse, and
  the reason `render.py` must be pasted before any 6b ruling.
- **The states script and styles are framework chrome**, inline, joining the existing
  script/stylesheet channels (the page's inline scripts already prove CSP permits
  them — verify any CSP meta tag). No `src`, no network, no eval. Emitted
  conditionally, only when a `StatesEntry` exists (the tab script's ≥2-tabs
  precedent).
- **Attribute-driven wiring.** The script is fully static: it discovers panels via
  `data-state-dimension`/`data-state-value` and widget controls via the same pairs —
  no per-page JS codegen, `render.py` stays a pure template pass.

### 5.3 Steps

- **6b-1 — URL selection core:** directive grammar (W1); parse/apply on load +
  `hashchange`; default selection (W2); the hide/show enhancement mechanism mirroring
  tabs; print rule (all visible); panel-identity contract present (from 6a-3; lands
  here if 6a-3 shipped without it). Tests: markup/CSS/script-block pins.
- **6b-2 — widgets by kind:** the control per `kind` (W4/W5/W6), aria wiring
  (radiogroup / labelled slider with `aria-valuetext` = raw value), hash writes on
  interaction, cross-node sync for shared dimensions, axis-length-1 suppression (W3 —
  one tab is not navigation; one state is not selection). Tests + the docs rider
  (tutorial beat + a worked example).

### 5.4 Open design points (rule each, with recommendation)

| # | Point | Recommendation |
|---|---|---|
| W1 | **Directive grammar.** Reports are read as local files — the directive must live in the **hash fragment** (query strings are unreliable on `file://`). Exact spelling ruled with the tab precedent in hand (the tab panel ids like `2-composition` suggest a fragment-addressable pattern may already exist — if the tab script deep-links, states joins **one grammar** for all read-time selection). | hash fragment; one grammar with tabs if one exists |
| W2 | **Default with JS, no directive.** | First axis value per dimension — the default-active-tab precedent; no-js/print already cover "see everything" |
| W3 | **One state, no widget.** | Suppress the widget when the axis has ≤1 panel — the single-tab precedent |
| W4 | **Widget scope.** | One widget per states node, all reflecting the single global selection per dimension (simplest DOM locality; sync is trivial — every control reads/writes the one URL) |
| W5 | **Categorical: radio or dropdown?** | By axis size (threshold needs ruling) or one vocabulary for v1 — rule with render.py in hand |
| W6 | **Ordered slider semantics.** | Single position for v1; a range is subset-shaped → parked with subset |
| W7 | **Values whose panels collapsed at build.** | Widget lists only values whose panels exist — the document tree is the truth; for ordered, positions index the existing panels |
| W8 | **Value addressing in ids/URL.** Raw values are arbitrary visible text. Percent-encoding is **injective** (distinct raws → distinct directives); slugifying is not (`Run A` vs `run-a`). | URL addresses the **percent-encoded raw value**; DOM ids stable per build (index- or value-derived — any injective spelling) |
| W9 | **Widget label.** | The dimension verbatim for v1; a `StatesNode.title` key is a **future layout flip's** question (the 0.3.0 docstring says states is the whole flip — adding keys after gating is a new version question, do not smuggle it in) |
| W10 | **Print rule.** | Mirror the tabs' print handling exactly (all panels forced visible) |
| W11 | **Layout keys for 6b.** | **None in v1** — the widget is automatic by kind; opt-outs are future flips. Feature 6 stays manifest-free **and** (beyond 6a-1's node) layout-free |

### 5.5 Test waves for 6b

pytest is markup-level (the suite pins page bytes — `test_tutorials` style): widget
presence by axis size (incl. W3 suppression); aria structure; panel
`id`/`data-*` stability across builds; script block emitted exactly once, only when
states exist (existing `page.count("<script>")` pins change only in states-bearing
examples — account for that); print CSS rule present; directive grammar constants
visible in markup; no-js = all panels present in the raw DOM (structurally true —
assert the script never removes panels). Interaction behavior itself is beyond
pytest's reach — pin markup, state the boundary in the docs beat.

---

## 6. Parked / future (by the record — do not build, do not delete)

- **Subset kind** (checkbox list, multi-select states) — parked open by the record;
  `kind` gains no member.
- **Manifest axes block** (carrying raws) — future work beyond feature 6; the
  derived door keeps reading artifact types until it exists.
- **Literal-`{` escape in rendered strings** — accepted cost, standing ruling.
- **Orphan-check extension to `theme`/`logo`/`favicon`** — optional rider, one line
  each if ever wanted.

---

## 7. Riders and residues (consolidated)

| # | Rider | Needs |
|---|---|---|
| 1 | `tests/test_core_seam.py`: literal → interpolation conversion | read whole |
| 2 | `tests/test_registry.py` comment wording review (only the version literal was swapped; "a type type system" is suspect) | read whole |
| 3 | `core/*.rst` ×6 stale manifest-version example lines (M4 residue) | read or verify against the core plugin's declaration |
| 4 | `.skills/framework-development.md:325` manifest rider | owner's file |
| 5 | `docs/examples/build/` regeneration (0.2.0-era envelope; stale `report.html`) — after the docs beat lands, so the example exercises states end-to-end | rebuild from shipped files |
| 6 | Mojibake check: `git grep 'ΓÇö'` once — disk presumed clean (channel-only law) | one command |
| 7 | `tmp/report.html` stale artifact | regenerate at leisure |
| 8 | Docs: states authoring beat + worked example + the **N×content cost teaching** | after 6b-2 |
| 9 | Expansion mismatch-teaching reword | the expansion test file pasted |

---

## 8. Working protocol (the laws that got it this far — keep them)

2. **Emission-failure protocol.** On a corrupted emission attempt: stop, name the
   fault in the open, pre-commit the next emission's shape. Never let a seeded fault
   ship.
3. **Pinned teachings are load-bearing.** Never reword a message the suite pins;
   rewords ship with the paste that brings the pins.
4. **Version single-source law.** Fixtures are source (interpolate the constant);
   shipped files carry the literal; only version-gate tests keep literals. mypy
   enforces statically. A flip greens everything but the gate's own tests.
5. **Sweep law.** A version flip's grep covers every axis, roots include `tests/`;
   hits on another axis are the previous flip's unpaid residue — disposition, don't
   skip. Checklist item contradicted by grep silence = re-verification trigger, never
   closure.
6. **Mojibake law.** `ΓÇö` is channel corruption (em-dash as CP1252) until `git grep`
   proves otherwise; teach from reconstructed glyphs; never normalize emissions to
   match a mangled paste.
7. **Gates, in order:** ruff → mypy → pytest → docs build. These are ran
   through pixi commands: `pixi lint-fix` `pixi test` `pixi docs`. State the
   expected result before running; unexpected reds are analyzed against the
   census, never patched blind.
8. **The record.** Each working turn ends with: bounded edits, **Honest
   flags**, **Gates** expectation, and a **Ledger** entry when a new law fires.

---

## 9. Materials checklist, in order

1. This spec.
2. **6a-2:** read `report.py`, `builder.py`, `expansion.py` (current). Then rule
   O1–O4, emit the deltas.
3. **6a-3:** read `render.py` + `templates/`. Rule the panel-identity details;
   emit.
4. **6a tests:** `ls tests/`; paste the builder/renderer test files + `factories.py`
   + the expansion spec test file.
5. **6b:** rule W1–W11 (with `render.py` and the tab-script precedent in hand);
   read any framework script/style assets touched.
6. **Riders:** files named in §7, as each is worked.

---

## 10. Honest boundary

- **Ruled and gated:** everything in §3 and §2's producer rulings; the six verbatim
  consumer lines.
- **Proposed, never ruled:** all of §5 beyond the six lines (architecture, W1–W11
  recommendations, the 6b-1/6b-2 split). The old session sketched the consumer half
  at exactly the fragment's altitude — the new session rules, records, then builds.
- **Never held in the old window:** `render.py`, the templates beyond one grep line,
  the builder/renderer/verification-spec test files, `core/*.rst`. 6b in particular
  is decided *by the tab precedent* — and the tab script's actual mechanism was never
  seen. Paste before ruling.
- 6a is one small step; this spec covers feature 6 entire — and the record named
  nothing beyond it. Do not assume 6b-2 is the project's end.
