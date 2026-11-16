# workflow-coda — plugin authoring skills

You are writing a **workflow-coda report plugin**: installed code
that contributes **components** — the units that render a workflow's
artifacts into a report page. A report is built from two author
files (a JSON *manifest* of what the run produced; a YAML *layout*
of how the report reads), plus plugins like yours that turn
artifacts into content. The output page is a read-time artifact:
emailed, archived, opened offline, printed, read in locked-down
browsers. Every design decision answers to that reader.

This file has two tiers, deliberately:

- **The minimum bar** — what every plugin must do, third-party or
  core. Miss any of it and the plugin is dishonest, whatever else
  it does.
- **The core standard** — what official `core.*` components are
  additionally held to. Core components are the reference
  implementations: third parties will copy you, so you must be
  worth copying.

Framework development itself is governed by
`.skills/framework-development.md` — read it for the architecture,
the store contract, and the page-chrome channel mechanics. The laws
bind plugin authors too: honest data, complete-and-unscripted,
formats are claims, errors teach, version axes are independent.

## Anatomy of a plugin

A plugin is a **factory + metadata + components**:

```python
from importlib import metadata


def get_plugin() -> ReportPlugin:
    return ReportPlugin(
        metadata=PluginMetadata(
            id="bio",
            name="Bioinformatics components",
            version=metadata.version("my-bio-plugin"),
            description="Tree and sequence renderings for QC reports.",
            supported_schema_versions=frozenset({"0.3.0"}),
        ),
        components=(NEWICK,),
    )
```

- The factory returns a **fresh plugin on every call** — it is a
  factory, not a singleton (the framework's own plugin is pinned on
  exactly this).
- Register the factory in your package's entry points, under the
  framework's group **`workflow_coda.plugins`**:

  ```toml
  [project.entry-points."workflow_coda.plugins"]
  my_bio = "my_bio.plugin:get_plugin"
  ```
- `supported_schema_versions` must be honest: the builder gates
  every placement against the manifest's schema version and
  *excludes* your component with a diagnostic naming both versions
  when it does not match. Exclusion is graceful; claiming support
  you have not tested is the only wrong answer.

A component:

```python
NEWICK: Final[ReportComponent] = ReportComponent(
    id="bio.newick",
    title="Phylogenetic tree",
    description="One artifact-backed tree rendering.",
    render=render_newick,
    chrome=ComponentChrome.CARD,
    css=_NEWICK_CSS,  # optional
    js=_NEWICK_JS,  # optional
)
```

- The component **id carries your plugin id as prefix**
  (`core.kpi`, `bio.newick`); the author places it by this id.
- `chrome` chooses who paints the card:
  - **CARD** — the framework paints the card *and* the placement's
    resolved title, and wraps your html in the card body. You return
    the body alone; do not paint a card or a heading. The
    `PlacementInfo` argument is not yours.
  - **TILE** — you paint your own card (title, plate, corners) from
    `info.title`; the framework contributes only the
    `data-component` wrapper.
- `title` is the default card title; a placement's `title` overrides
  it. `description` is author-facing prose.

The render function:

```python
def render_newick(
    context: RenderContext, info: PlacementInfo,
    parameters: ComponentParameters,
) -> RenderedComponent:
```

- `context.store` is your only route to artifacts; `context.theme`
  carries the design tokens.
- `parameters` is the placement's `parameters:` mapping —
  JSON-shaped values, raw. You validate every key yourself.
- Return `RenderedComponent.from_html(...)` for content,
  `RenderedComponent.unavailable(...)` for missing data. A render
  call is independent: same inputs, same output; the page may place
  your component many times.

## The minimum bar — every plugin

### Read artifacts through the store, never the filesystem

`artifact = context.store.require(type)` resolves the declaration,
gates the status, checks existence and containment, and raises
`ArtifactUnavailableError` with a teaching message (undeclared /
non-`complete` status / missing file). Convert it:

```python
except ArtifactUnavailableError as e:
    return RenderedComponent.unavailable(str(e))
```

Then read with `read_json()`, `read_text()` (UTF-8), or
`read_bytes()` (the binary door). The store gives you, for free and
only through these readers: **checksum verification at read time,
path containment, existence, teaching decode failures**. Never open
artifact files yourself; never touch a path.

The store never dispatches on `format`. If your component needs a
particular format, gate it yourself: compare
`artifact.declaration.format` with plain string equality (it works
for framework values and namespaced strings alike) and teach on
mismatch — do not adapt.

### Escape your artifact data — the renderer will not

Your OK html is treated as trusted installed code and reaches the
page **unescaped**. Every artifact- or author-sourced string you
interpolate must be escaped **by you** (stdlib `html.escape`).
This is the single most important honesty duty: artifact data is
the producer's words, not markup. (The unavailable *message*, by
contrast, is framework-handled text — the renderer escapes it.)

### The three error families — who is wrong decides what the reader sees

- **The layout is wrong** (your parameters): raise `ValueError`
  with a message naming the fix and the offending value → the
  builder shows a failure card in place.
- **The run is partial** (missing data): `ArtifactUnavailableError`
  → returned as unavailable → the notice card. Absent data is a
  fact about the run, not a bug.
- **The artifact lies** (does not parse under its claimed format):
  raise `ArtifactReadError` → a failure card.

Never conflate them. A typo in the layout is not "unavailable"; a
missing file is not a "failure".

### A closed parameter vocabulary

- Accept a fixed key set; validate every key with `isinstance`
  checks, strictly — YAML's `"true"` is not a bool, `30` is not a
  string.
- Call `reject_unknown_parameters("<your component id>",
  parameters, YOUR_KEYS)` — it teaches typos with suggestions, and
  placement keys (`title`, `on_missing`) nested inside
  `parameters:` with the instruction to move them out.
- Shape errors raise **before any data is read**.
- Membership that depends on the data (e.g. column names against a
  header) is taught **at data time, against the artifact's own
  vocabulary** — that is where the data lives.

### Declare your format as a namespaced convention

If your component reads a domain format, claim it as your own:
`format: bio.newick` in the manifest — dotted, lowercase, at least
two segments, your plugin id as prefix. **The grammar lives in your
component**; the framework will never learn it. Read through
`read_text` or `read_bytes` and parse it yourself. A manifest
declaring format X pointed at a component that reads Y teaches —
it never silently adapts.

### If you ship js — enhancement, bound

- **Enhancement only**: the page must be complete without it.
  Never move content generation into script.
- It runs **once**, after the framework's scripts, on an
  established DOM. There is **no tab-shown event yet** — do not wait
  for one; panels hide and show, nothing re-renders.
- The page's CSP blocks **all network**: no fetching, no CDNs. All
  your data must already be in the HTML — stamp what the script
  needs at **build time** (e.g. `data-*` attributes), and have the
  script consume stamps, never re-derive facts the build knew.
- Write for **N instances**: one script enhances every placed
  instance (`querySelectorAll`), each independently — sorting one
  table must not move another.
- Hide by class, never by deletion; announce state (`aria-*`);
  give nameless controls explicit labels.
- Gate interactive affordances on the framework's `coda-js` class
  (the page marks itself scripted) — nothing looks interactive that
  is not.

### If you ship css

- Theme tokens only (`var(--coda-*)`); your own class vocabulary
  (`coda-<id>__…`); never restyle framework classes.
- Enhancement chrome is hidden until `coda-js`; anything hidden by
  script for viewing is restored under print.

### Ink: text on colors

Ink on a colored surface is chosen, never declared: call
`context.theme.text_on(background)` — one background for a solid
plate, both stops for a gradient — and interpolate the returned
`#rrggbb` into your markup or css. The theme's light-or-dark pair
resolves by WCAG contrast at build time; you never pick which.
Direct token reads (`theme.colors[...]`) are for declared color
roles — including your own custom tokens — and your css may
reference any emitted property (`var(--coda-muted)`, your tokens,
the derived `var(--coda-text)`). The `text` token is retired:
`--coda-text` is now a derived page property — read it, but never
assume it suits a colored surface; that is what `text_on` is for.

### Icons, if you ship them

Optional — a plugin with no icons declares nothing, and a layout
that asks for one teaches honestly. When you do ship icons:

- Declare the package on your metadata:
  `icons_package="my_bio"` — the importable package whose
  `assets/icons/` directory holds your SVGs. An empty directory
  is legal (it ships nothing); a missing one under a declaration
  is a broken installation.
- Name every file `<plugin_id>-<name>.svg`. The prefix is law,
  enforced when the report's icon index is assembled: a mis-named
  file or a cross-plugin duplicate fails the build as
  `PluginAssetError` — a defect in your installation, never the
  author's layout.
- Each file is plain SVG declaring a `viewBox`; the framework
  sanitizes it at first use through the public
  `validate_icon_markup` (shapes, groups, SMIL animation —
  nothing else rides).
- Load icons in your render through the context —
  `context.icons.load(name)` — cached per build; an unknown name
  teaches as the author's typo. Never read your icon files
  yourself.

### Figures, if you chart

Use the framework's figure constructor, `RenderedComponent.from_figure`: the
renderer detects figures by the framework's own marker class and inlines
Plotly.js exactly when the document contains figures. Do not inline chart
libraries yourself. Import your charting library inside the render call — a
chartless report builds on machines without it, and a missing library teaches
as `RenderError` (the environment family) with the fix in the message. Return
through `from_figure` with an inferred accessibility label — the figure's own
facts (type, subject, size, grouping), never the author's — and ride
informational messages on the notes channel: OK-only, merged into the report's
diagnostics ledger.

### Test the honest way

You do not need the framework's suite. The cheapest honest test:
write a real manifest + real artifact files + a real layout, build
with the CLI, and read the page **with scripting off** — that
baseline is your contract. For unit tests, construct what the
framework constructs — `ArtifactStore.from_manifest_file` +
`RenderContext(store, theme)` — and call your render function
directly; your fixtures are then real bundles by construction. Pin
your teaching messages **byte-for-byte from your landed source**,
never from memory.

## The core standard — official `core.*` components

Everything above, plus:

### Exemplary grammar

- Full teaching grammar: required/optional keys, strict types,
  duplicates refused, cross-key rules refused at parse with the
  reason; shape-validated **before** any data is touched
  (parse → read → apply → assemble); one failure family per helper
  — a complexity flag means refactor, never `noqa`.
- Messages **branch-independent** where a field is a union:
  interpolate, never `.value` (mypy is the gate).
- **Honest boundaries stated and pinned**: what the parser cannot
  see (e.g. a uniformly wrong delimiter reads every line as one
  field and renders misread) is documented as a boundary, not
  hidden as a bug.
- Conventions that are detected are **never configurable** — a
  blank first header cell declares an index column; there is no
  parameter for it.

### Exemplary visual contract

- js in the house dialect: strict-mode IIFE, `var` only, zero
  dependencies, zero network; feedback honest **both ways** (the
  success count and the refusal message), transient state restored.
- css: tokens only; a **print block honoring the panels law**
  (controls removed, script-hidden rows restored); ARIA state
  (`aria-sort` and its kind).

### The channel contract

- Contribute css/js as **bare constants** — no banners; the channel
  stamps `/* <id> */` and `// <id>` at assembly, once per report,
  merged. The once-per-report dedup is the channel's job, not yours.
- Contribute chrome as **real files** at this tier: core ships
  `core/assets/<id>.css` and `.js`, read once at import through
  `core.assets.read_core_asset`; the constants carry the
  docstrings, the files carry exactly what ships, and the channel
  stamps the banners as always.  Third parties may keep small
  literal chrome at the minimum bar — adopt the files pattern once
  css or js outgrows a literal (`importlib.resources` on your own
  package is the whole door).
- Theme tokens only (`var(--coda-*)`); class names under your
  plugin's namespace (`coda-<plugin_id>-…` — the user docs' prefix
  rule; core alone owns bare `coda-*`); never restyle framework
  classes.

### Icon shipping

- Core ships the built-in icon set under `core/assets/icons/` —
  `core-` prefixed, sanitized through the public validator,
  declared through the same `icons_package` field third parties
  use, and served through the context's library like anyone
  else's: the reference implementation of plugin-owned icons, no
  private doors.

### Exemplary tests

- The suite in the framework's house pattern (see
  `.skills/framework-development.md`): real files through the real
  loader; transcribed pins; census pins stating their arithmetic;
  **design pins** for deliberate non-features; knowing shifts
  documented (was → now → why); one grammar family per section; the
  seam exercised through the real CLI.

### Docs, eyeball, ledger

- A reference page per component: the grammar with its honest-data
  split, detected conventions, the three-family teaching table,
  honest boundaries, and a **buildable** manifest+layout example
  pair.
- A kept **sanity bundle** on disk and an eyeball session with
  keyed checks for every visual change — including trap fixtures
  that distinguish correct from plausible (numeric sort `9, 10, 100`
  vs lexicographic `10, 100, 9`), instance independence, print, and
  a clean CSP console.
- When a failure teaches a rule, **bank it**: state it, encode it
  in the next pin, update the skills files.

### Roster discipline

- **Append-only**: new components append, never insert; ids never
  change; the roster order is pinned.
- **Dogfood only**: core uses the same channels third parties use —
  no private store internals, no renderer bypasses, no format
  dispatch, no framework shortcuts a third party could not take.

## Never — either tier

- Never read artifact files outside the store.
- Never emit unescaped artifact- or author-sourced strings in OK
  html.
- Never generate content in script; never fetch in script (the CSP
  blocks it).
- Never report missing data as a failure, or a bad layout as
  unavailable.
- Never claim schema-version support you have not tested.
- Never let a plugin's script make the page a lie: if scripting is
  off, the reader still reads everything.
- Never load or sanitize icons outside `context.icons` — the
  library owns caching, teaching, and sanitization.
