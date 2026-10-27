# workflow-coda — framework development skills

You are changing **workflow-coda**: a Python framework that builds
one **self-contained HTML page** — a workflow's report — from two
author files: a JSON *manifest* (what the run produced) and a YAML
*layout* (how the report reads). Plugins — installed code —
contribute the components that render artifacts. The output page is
a **read-time artifact**: it is emailed, archived, opened offline,
printed, and read in locked-down browsers. Every design decision
answers to that reader.

Plugin authorship is a separate discipline with its own skills file,
`.skills/plugin-authoring.md`. This file governs the framework
itself. The two share the laws below; the plugin file states the
minimum bar for third-party authors and the higher standard the
official core components are held to.

## The laws

Non-negotiable. Check every change against these.

1. **Honest data.** Producer data renders verbatim: escaped, never
   reinterpreted, never "cleaned" — the producer's own formatting is
   data. Parameters are the author's declared *policy* (shape
   policy, presentation policy, authorship prose), and every grammar
   states its honest-data split explicitly. Unknown parameter keys
   teach at the parse boundary; placement keys nested inside
   `parameters:` teach the move out.
2. **Complete and unscripted** (the honest-visuals law). Content
   ships complete in the HTML. Scripted enhancement — sort, filter,
   tabs — operates on rows that are already on the page: a reader
   without scripting reads everything, and printing shows the whole
   document (the *panels law*: print styles restore hidden content
   and remove controls). Nothing looks interactive that is not:
   enhancement chrome is display-none until the page marks itself
   scripted (`coda-js`).
3. **Formats are claims, not services.** An artifact's `format` is
   metadata. The framework's values are the agnostic trio `json`,
   `txt`, `bytes`; anything else is a *namespaced plugin
   convention* (`core.table`, `bio.newick`) whose grammar lives in
   its owning plugin. The store never dispatches on format — a
   reader is the consumer's explicit command. This is pinned
   (`test_readers_are_explicit_not_format_dispatched`): adding a
   dispatch layer must be a conscious decision, not a "fix".
4. **Errors teach.** Every failure message names the fix and the
   offending value. Three families are kept distinct — *who is
   wrong decides what the reader sees*:
   - the layout is wrong (missing/malformed parameters, bad
     references): `ValueError` → a plugin failure, reported in place;
   - the run is partial (undeclared artifact, non-`complete` status,
     absent file): `ArtifactUnavailableError` → the unavailable
     notice, a fact about the run;
   - the artifact lies (does not parse under its claimed format):
     `ArtifactReadError` → a plugin failure, never a quiet notice.
5. **Version axes are independent.** Package version, manifest
   envelope version, layout schema version, and the artifact-level
   `schema_version` (the *content axis*) are separate questions.
   Version gates are exact (a `Literal`, not a prefix); an unknown
   version fails with the declared and expected versions named.
   Alignment is enjoyed, never encoded. Pre-release, a breaking
   schema change is a clean break — no migration prose.
6. **Value semantics.** Models are frozen and hashable; declared
   order is preserved; extra fields are forbidden; strings are
   strict. Duplicate ids and types are detected by a *merged*
   validator that reports all problems, aggregated, sorted, counted
   (pydantic stops a field's validator chain at the first failure —
   separate validators would only ever report one problem).

## Architecture

One direction of flow: CLI → loader → builder → renderer. The loader
is the only reader of manifest files; the store is the only toucher
of artifact files; the renderer is a pure function of the document.

| Module | Contract |
|---|---|
| `manifest/` | The envelope models (`ReportManifest`, `ProducerMetadata`, `ArtifactDeclaration`), the constrained type aliases, and `load_manifest` — which wraps every OS/JSON/pydantic failure in `ManifestError` with the cause chained, rejects a leading BOM, and pre-checks the declared schema version with a teaching message. |
| `artifact_store` | `ArtifactStore`: `require(type)` resolves and gates; `read_json` / `read_text` / `read_bytes` are the only artifact readers. |
| `components` | The component and plugin value models, the `RenderedComponent` outcomes, and `reject_unknown_parameters` (typo suggestions; the nested-placement-key teaching). |
| `context` | `RenderContext(store, theme, icons)` — what a render function receives: the store, the theme, and the build's merged icon library (an empty default for direct construction; the builder wires the real one from the gated plugins' declarations). |
| `theme` | Design tokens, rendered as `--coda-*` custom properties; additional tokens are usable by plugin css automatically. |
| `icons` | The icon library: `IconSource` (one plugin's declared, import-probed icon package), `IconLibrary` (the per-build merged name→source index — the two namespace laws, prefix and cross-plugin duplicate, hard-fail at assembly — with lazy, cached loads), and the public `validate_icon_markup`. Icons are plugin-owned files under `assets/icons/`, named `<plugin_id>-<name>.svg`. |
| `report` / the builder | The report document model and its assembly: plugin resolution, schema-version gating, `on_missing` placement policy, diagnostics collection, version-gate exclusion stories, and the per-build icon library — assembled from the *gated* plugins' declarations, so a gated-out plugin's icon defects cannot fail an unrelated report. |
| `render` | A pure function of the document: the tree walk, generated split CSS, the page-chrome channel, provenance footer. No registry, no user files, no decisions. |
| `cli` | `build`: manifest + layout → the written page. |
| `core/` | The framework's own plugin (`core.kpi`, `core.table`) — dogfooding the same channels third parties use. |
| `errors` | The taxonomy below. |

## The store contract

`require` is cheap and safe: declared → status `complete` → file
exists → regular file → contained (the resolved path stays inside
the root; a symlink that stays inside is legal, an escape teaches).
A non-complete status or missing file is an *unavailable fact*, not
an error. The optional `sha256` is verified at read time, over the
exact bytes a read parses — `require` defers. Readers decode UTF-8
with teaching failures. The store parses nothing, ever.
`ArtifactStore.from_manifest_file` roots at the manifest's *real*
parent (a symlinked manifest roots at its real location, where its
relative paths resolve).

## Error taxonomy

`WorkflowCodaError` is the root and the recovery boundary: every
failure a caller might catch is one type. Beneath it: `ManifestError`
(wrapping — `__cause__` always set), the store family
(`ArtifactStoreError` → `ArtifactUnavailableError`,
`ArtifactResolutionError`, `ArtifactChecksumError`,
`ArtifactReadError`), and `RenderError` — *environment failures
only* (missing chrome files, plotly not installed): with a validated
document, rendering has no decisions left.
`PluginAssetError` — a shipped plugin asset is broken, all one
family and never an authoring error: missing or unreadable chrome,
read at import where the plugin's constants read their files (the
core loader is `core.assets.read_core_asset`); or a defect on the
icon side — an unimportable declared icon package, a mis-prefixed
icon name, a cross-plugin duplicate, an unreadable or
unsanitizable icon at load.

Rules: teaching messages carry the offending value and the fix;
wrapped errors name the file and the cause; a raw `ValidationError`
or `OSError` never leaks across a module boundary.

## The page-chrome channel

Components declare `css` and `js` at declaration time; the builder
collects each contribution once per report (deduplicated,
first-use order); the renderer inlines **one merged `<style>` block**
after the framework stylesheet and **one merged `<script>` block**
after the framework's own scripts — so plugin code reads an
established DOM. **The channel stamps the banners** (`/* <id> */`
for css, `// <id>` for js): contributed constants carry none and open
with their first rule. The page's Content-Security-Policy meta makes
self-containment a read-time property, not just a build promise.
Plotly.js inlines exactly when the document contains figures
(detected via the framework's own figure marker class). A
single-tab, figure-free report inlines no `<script>` at all unless a
component contributes one.

## House dialects

**Python** — pydantic v2, frozen/hashable models, `Annotated` type
aliases with `strict=True` constraints, `StrEnum`, `Final` module
constants, `slots=True` dataclasses for internals. mypy and ruff are
gates. A complexity flag (C901) means *refactor into
one-failure-family-per-helper* — never `noqa`.

**Component JS** — strict-mode IIFE, `var` only, zero dependencies,
zero network, enhancement-only (the page is complete without it).
Hide by class, never by deletion. Announce state through ARIA
(`aria-sort`; explicit labels for nameless controls). Feedback is
honest both ways: the success count *and* the refusal message.

**Component CSS** — theme tokens only (`var(--coda-*)`); `coda-js`
gates interactive affordances; a print block honors the panels law.

**Component chrome storage** — shipped chrome lives as real files:
`core/assets/<component>.css` / `.js`, read once at import through
`core.assets.read_core_asset` (`importlib.resources` — the same
door a third-party plugin uses for its own package data).  The
declaration constants stay `Final[str]` and carry the docstrings —
the declaration site is the documentation site, and autodoc reads
them; the files carry exactly what ships: no banners (the channel
stamps those), no leading blank line, exactly one trailing
newline.  A missing or unreadable asset is `PluginAssetError` — a
broken installation, taught at import, cause chained.  New core
components create the files from day one: chrome never lands as a
string literal to be extracted later.

**Docs (rst)** — `-W` is live: warnings fail the build. list-table
continuation lines align at the *content column*, not the dash
column. Tables default to auto widths; `:widths:` only on proven
need, and never around unbreakable literals. Examples are buildable
pairs — a manifest and a layout that would actually run together.

## Development workflow

### Step discipline

Small steps, each closing green — no red windows, ever:

- **New features land dark.** Production lands unregistered (the
  roster, the seam, the docs untouched); the paired test step pins
  it afterward.
- **Removals and pin-breaking edits ride their production step.**
  A deletion cannot stand alone: the paired test deletions and
  vehicle switches land in the same step.
- **Tests and docs are their own steps** when they break no pins.
- A step closes with its gates run *and read*: ruff → mypy → pytest
  (`pixi run test`) → docs (`pixi run docs`).

### Testing patterns

- **Serialized factories.** `tests/factories.py` returns raw dicts,
  not models, so failure modes stay injectable — and writes fixture
  bundles as *real files through the real loader*, so every fixture
  is a valid bundle by construction.
- **Transcribe, don't paraphrase.** Pins on teaching messages are
  byte-for-byte from the landed source.
- **Docs that quote shipped strings are pins.** When a shipped
  metadata or message string changes, grep `docs/` for the old text
  and shift the quote knowingly — `index.rst`'s plugin-description
  quote drifted one growth behind until a reference paste caught it.
- **Census pins state their arithmetic.** A page with inlined
  scripts has *two census authors*: count js-carried constants and
  class strings alongside markup occurrences.
- **Knowing shifts.** When a pin must change because of deliberate
  growth, the test comment documents the shift: was → now → why.
- **Design pins** mark deliberate non-features so a future "fix" is
  a conscious decision.
- **Chrome wiring is pinned both ways.** `test_core_assets.py`
  asserts a test-time `read_core_asset` read equals the import-time
  constants (wrong-file wiring and a stale hardcoded constant both
  redden), the byte discipline (no leading blank line, exactly one
  trailing newline), and the broken-install teaching with the cause
  chained.
- **Icon namespace laws are pinned as design decisions.** The
  library suite pins the two index laws, the family split with
  causes checked (`ModuleNotFoundError` and `ValueError` pinned
  exactly; `OSError` by family — its flavor is the platform's),
  and lazy-by-decision (the index reads names only). The duplicate
  law has a reason to exist: when one plugin id is a
  hyphen-prefix of another, a single filename satisfies both
  prefixes — the index re-checks for exactly that case, as the
  registry does for component ids.
- **Grammar moves home.** When a grammar moves to its owning
  component, its test family moves with it; the old home keeps only
  what is still genuinely its own.
- **Palette pins derive from the theme.** Byte-pinning theme colors
  rots at every palette edit — the second palette edit of the
  session reddened eleven tests at once. Pin the mapping, derive
  the value: `DEFAULT_THEME.colors[...]` and `.series[...]`;
  computed-ink pins mirror `theme.text_on(...)` (the contract: the
  component asks the theme); series bounds derive from
  `len(DEFAULT_THEME.series)` — the hardcoded `series-9` bound
  rotted exactly when the palette grew past nine.

### Verification rules

- **Pins against unheld source are reconstructions.** Read the
  infrastructure's source before pinning its behavior, or mark the
  pin as inferred and settle it on first run.
- **Sweep greps are gates, not prose.** A retirement or version
  landing ends with the grep *run and read to zero* —
  factory-driven tests mask residue in *both* directions, so sweep
  `src/` for production defaults, not just `tests/` for fixtures.
- **Union fields reshape failure output.** Per-branch errors under
  branch-tagged locations: pins assert the *outermost* location,
  never the tag strings. Messages interpolate widened fields
  branch-independently — never `.value` on a union arm; mypy is the
  gate that catches this.
- **Visual work gets an eyeball session.** A kept sanity bundle
  (real manifest + layout, kept on disk as the fixture for future
  changes) plus keyed checks walked by eye. Byte traps — real tabs
  in TSV fixtures — are flagged before they cost ten minutes.

### Emission discipline (for you, the LLM)

Large string literals (component css/js) can emit corrupted. State
each block's contract *before* emitting it; emit shortest-first. If
corruption signatures appear — duplicated rules with the first copy
garbage, mid-rule garbage tokens, self-correcting fragments —
**stop, reject the whole block, and retry fresh in a new turn**:
the design is not the failure; the emission is. Never ask the user
to splice corrupted drafts.
The storage pattern retires the largest risk zone — core chrome is
edited as real `.css`/`.js` files, with no string-literal emission
path; the discipline still governs whatever remains in strings
(test fixtures, generated style blocks, third-party literals).
A second discipline from the same era: **splice blocks are whole
syntactic units** — when a delta edits one region of a larger
unit, emit the enclosing unit in full, or state explicitly which
parts stand. A block ending at an ambiguous boundary (a
close-paren that could close either call) has silently dropped a
required argument and swallowed a raised-family sentence in the
same landing; mypy named one casualty, a paste-read found the
other.

### The ledger

When a failure teaches a rule, it is banked: stated in the step's
post-mortem, encoded in the next pin, and this file is updated. The
ledger is the framework's institutional memory — a rule that isn't
written down will be re-learned the expensive way.

## Current state

- Manifest envelope schema: `0.2.0` (exact gate; the loader's
  version pre-check teaches declared vs. expected). Layout schema:
  `0.2.0`. Artifact content `schema_version`: free-form — the
  content axis, deliberately unpinned.
- Format value space: `json`, `txt`, `bytes`, plus namespaced
  conventions. `tsv` is retired: the tabular grammar lives in
  `core.table` and its suite.
- Core roster: `core.kpi` (TILE, css) and `core.table` (CARD, css +
  js — the js channel's first consumer). The roster is append-only:
  new components are appended, never inserted.
  Chrome ships as files under `core/assets/` (`kpi.css`,
  `table.css`, `table.js`), read once at import; the loader's suite
  is `test_core_assets.py`.
- Icons are plugin-owned: core's set lives under
  `core/assets/icons/` (`core-` prefixed), declared through
  `icons_package` on the plugin metadata and served per build
  through the context's `IconLibrary`. The module-level
  `load_icon`/`icon_names` are retired; the library's suite is
  `test_icons.py`, beside the untouched validator pins.
- Store readers: `read_json`, `read_text`, `read_bytes` (public; the
  binary door for plugin-defined formats).
  The `text` color token is retired: the body ink is derived at
  render — `theme.text_on(background)`, emitted as `--coda-text` in
  the generated `:root` block — and a theme that still declares
  `text` wins (declared tokens ride through; the derivation steps
  aside). The required set is eleven tokens: accent, background,
  border, danger, muted, primary, success, surface, text-dark,
  text-light, warning.

## Never

- No format dispatch and no parsing in the store.
- No silent behavior change where a pin exists — pins are
  load-bearing; change them knowingly, and say so in the comment.
- No escaping of plugin html/css/js (installed code, guarded at
  declaration) — but every *framework* text the renderer
  interpolates is escaped.
- No error without the fix in its message; no cause unchained.
- No migration prose pre-release; no `:widths:` without proven need;
  no `noqa` for complexity — refactor.
