# Design record: `workflow-coda verify`

**Status:** locked — this is the feature's design record (M0). It
carries every decision *and its rationale*, the command's exact
contract, the implementation map, and the parked future. The pin
suites (M1) are the executable contract: where a pin and this file
disagree, the pin wins and this file is amended. This is not
user-facing documentation — M3 writes that; this is for the people
(and the agents) building the feature.

---

## Context

workflow-coda has four hands: the pipeline produces artifacts, the
report author writes the layout, the plugin author writes
components, the framework owns what must not vary. This feature
serves the **fifth hand — pipeline integration**. Today the
manifest is hand-written JSON; `verify` produces it from real
files, honestly: it checksums what it reads, checks what it can
(shape under the claimed format, plus declared criteria), and
records what it did. A manifest that says `complete` becomes a
*verified* claim.

One command integrates with any workflow manager — Snakemake,
Nextflow, WDL — because the manager's step only ever shells out to
`verify`; the manifest accumulates artifact by artifact; the
report builds from it unchanged. The dividend runs both ways: a
structurally broken tabular file surfaces at pipeline time (the
cheap moment, author present) instead of as a report-time plugin
failure, and the store's read-time checksum verification — today
exercised only by fabricated digests in tests — becomes the live
path for every integrated pipeline.

## The command

verify <FILE(S)> <MANIFEST> cannot express both modes on one argparse parser:
in spec mode there is no FILE, so the single optional positional would swallow
the manifest. The one-parser resolution is manifest-first:

```
Usage: workflow-coda verify [OPTIONS] MANIFEST          (--spec mode)
       workflow-coda verify [OPTIONS] MANIFEST [FILE]   (flags mode)
```

Exactly one mode per invocation: `--spec` together with a FILE
positional, or flags without one, is a usage error (exit 2).

### Flags mode — one artifact, for looping steps

```bash
workflow-coda verify stats.json manifest.json \
    --id stats --type org.example.stats --format json \
    --schema-version "1.0.0" --criterion keys=depth,rate \
    --producer-name fungifunk-pipeline --producer-version 1.3 \
    --run-id 2026-11-11-run7
```

### Spec mode — the pipeline's versioned declaration

```yaml
# bundle.yaml — checkable into the pipeline repo, reviewable in a PR
producer:
  name: fungifunk-pipeline
  version: "1.3"
  run_id: 2026-11-11-run7
artifacts:
  - file: samples.tsv          # resolved against the spec's directory
    id: samples
    type: org.example.samples
    format: core.tabular
    schema_version: "1.0.0"
    criteria:
      columns: [sample_id, depth, status]
      min_rows: 4
  - file: stats.json
    id: stats
    type: org.example.stats
    format: json
    schema_version: "1.0.0"
    criteria:
      keys: [depth, rate]
```

`workflow-coda verify manifest.json --spec bundle.yaml` — one
invocation, N artifacts, all-or-nothing. The spec scales from one
artifact to many; there is no separate bulk mode. The spec's
`file:` values resolve against the *spec's* directory; the
`path:` written into the manifest is *manifest-relative*, computed
by the CLI (and taught, never repaired, when the file cannot be
expressed inside the manifest's tree).

### Flags

| Flag | Mode | Meaning |
|---|---|---|
| `--id`, `--type`, `--format`, `--schema-version` | flags | Required identity of the one artifact |
| `--criterion KEY=VALUE` (repeatable) | flags | Criteria as string transport — see §6 |
| `--producer-name`, `--producer-version` | both | Required on create; on append must match recorded or be omitted |
| `--run-id`, `--module-id` | both | Optional; same match-or-omit rule |
| `--on-failure {fail,write}` | both | Default `fail` — see §4 |
| `--spec FILE` | spec | The spec file (`.yaml`/`.yml`) |

The MANIFEST positional is **not** an input-checked path — it may
not exist yet, because creation is the point. It carries the
`.json` extension contract (`check_output_file`) and is
pre-flighted with `check_writable_destination` before any work,
the `build` precedent.

### Exit codes

- **0** — the manifest was written: everything verified, or
  failures recorded under `--on-failure write`.
- **1** — a framework teaching on stderr (one message): a
  verification failure under `fail`, a spec or flag problem, a
  version refusal, a write failure. The exit code reflects
  *whether the manifest write happened* — nothing else.
- **2** — usage (argparse), unchanged.

### Output lines (M1 pins these byte-for-byte)

```
created {manifest} (producer {name} {version}) — verified and appended artifact {id}
created {manifest} (producer {name} {version}, run {run_id}) — verified and appended artifact {id}
verified {file} — appended artifact {id} to {manifest}
verified {file} — updated artifact {id} in {manifest}
verified {n} artifacts — appended {a}, updated {u} in {manifest}          (spec mode)
verified {n} artifacts — appended {a}, updated {u}, {f} recorded as failed in {manifest}   (spec + write)
warning: artifact {id} failed verification — recorded as failed: {message}   (stderr, per failed artifact under write)
```

## Locked decisions

### 1. Architecture — verifiers, transport, conscious dispatch

The framework provides verifiers for the agnostic trio; plugins
register verifiers for their namespaced formats through a new
`artifact_verifiers` roster on `ReportPlugin`. **Criteria are
transport**: a `dict[str, JsonValue]` the verifier owns, exactly
like component `parameters` — the framework interprets none of it.

**The store's no-format-dispatch pin stands untouched.** verify
is a *new, deliberate dispatch surface* — the one place whose
job is format-awareness — and gets its own design pin, so a
future "fix" of the store can never cite it.

### 2. Surface — flags xor spec

Exactly one of `--spec` or the inline flags. The spec is not bulk
convenience; it is the pipeline author's **declaration of what
its outputs promise** — versioned with the code, reviewable in a
PR, YAML-typed criteria instead of CLI comma-strings. Spec
authoring failures teach like the layout's own failures (file
named, duplicate keys rejected with key and line, boolean traps
explained, violations as paths into the file) because it *is* a
human-authored YAML file with the same traps. It loads through the
same `UniqueKeySafeLoader`.

### 3. Lifecycle — create, append, update

- **Missing manifest → create.** Producer required
  (name + version; run_id/module_id optional). Schema version
  written: `"0.3.0"`, always.
- **Existing manifest → append/update.** Loaded through the real
  loader first (corruption teaches). A `0.2.0` manifest teaches —
  regenerate it with verify; the pre-release clean-break law.
- **Same id + same type → update**: new bytes, new sha256, new
  verification record, *position kept*.
- Same id, different type → teach. New id, colliding type →
  teach, both ids named.
- **One manifest, one producer, one run**: producer flags on
  append must match the recorded producer or be omitted. The spec
  always carries its producer block; on append it must equal the
  recorded one or teach.
- **Atomicity**: every write is tmp-file + `os.replace` in the
  manifest's directory; *no teaching ever leaves a partial
  manifest*. Spec mode is all-or-nothing over its N artifacts.
- The writer **builds models, never raw dicts**; output is
  indent-2 JSON, one trailing newline, strict UTF-8, no BOM,
  declaration order preserved.

### 4. Failure handling — `--on-failure fail|write`, default `fail`

- **`fail`**: the teaching on stderr, exit 1, nothing written.
  Spec mode aggregates *every* problem — merged-validator shape:
  sorted, counted, nothing written.
- **`write`**: the declaration is appended with `status: failed`,
  the failure message rides the verification record, a warning
  line prints per failed artifact, exit 0.

**Rationale for the default**: verification failing usually
means the step is wrong — stop the graph now. `write` names the
other owner: the *report* owns the failure (the framework already
renders non-complete declarations as unavailable notices — a fact
about the run, no new honesty machinery), so a Snakemake rule
whose output is the manifest may proceed and the report tells the
partial-run story end to end. The exit code reflects the write;
the pipeline that chose `write` reads its honesty from the
manifest, not the exit code.

### 5. The verification record — and the `0.3.0` bump

`ArtifactDeclaration` grows `verification:
dict[str, JsonValue] | None = None` — **opaque transport** (the
`parameters` precedent): the verifier's account of what it
checked, under which reading, and on failure why. The framework
stores and round-trips it, interpreting nothing; the report may
surface it later.

The manifest is *the pipeline's own record of itself* — a
declaration claiming "complete, checksummed, checked to carry
these columns with ≥4 rows" is strictly more honest than "complete",
and self-contained provenance independent of the pipeline repo.
That is worth the cost: `extra="forbid"` makes the field a
**breaking envelope change → `0.2.0` becomes `0.3.0`**, read-time
accepts `0.3.0` only, and the cascade lands wholesale in M2:
loader pre-check message, `ManifestSchemaVersion` literal, core
plugin's `supported_schema_versions={"0.3.0"}` (or the framework's
own plugin gates itself out of every manifest), `tests/factories.py`,
every fixture and tutorial bundle, the sanity bundle, docs
strings, the e2e. The bump happens now, while the world has one
reader.

### 6. Criteria — declared, then strict

- **Omitted** = a valid, recorded absence: the *basic format check*.
- **Declared** = a promise: checked, and taught on breach.

And the coherence rule: **the verifier's default reading is the
component's default reading.** A file that passes basic
`core.tabular` verification is a file `core.table` renders under
its own defaults with no policy overrides — the two consumers
agree because they share one grammar, reused from the owning
module (`table.py`'s parse helpers already teach
`ArtifactReadError` with label-rich messages).

**Flags criteria are string transport all the way down**: the CLI
never splits a comma. `--criterion columns=a,b` arrives as
`{"columns": "a,b"}`; `--criterion min_rows=4` as `{"min_rows":
"4"}`. The *verifier's grammar* accepts `str | list` / `str | int`
/ `str | bool` (spec mode arrives YAML-typed, flags as strings)
and teaches on what it cannot parse. The framework stays
transport-pure; values needing literal commas belong in the spec.
Unknown criteria keys teach with a closest-match suggestion —
`reject_unknown_parameters`' law at the verifier boundary.

### 7. Registry — reserved trio, conflicts, version gating

- The framework builds the `json`/`txt`/`bytes` verifiers
  unconditionally; **the trio is reserved** — a plugin registering
  a verifier for those names teaches at registry assembly
  (`PluginConflictError`, the reserved formats named).
- Duplicate format claims across plugins → `PluginConflictError`,
  `x{n}` details — the registry mirror of its component-id law.
- Unknown format at lookup → teaching listing available formats —
  `require_component`'s shape.
- Verifiers come from plugins **supporting the version being
  written** (`0.3.0`) — the same gate as components.
- The verifier contract: a frozen value model — `format: str`,
  `verify: Callable[[bytes, Mapping[str, JsonValue]],
  dict[str, JsonValue]]`. **Bytes in** — the CLI owns file IO and
  computes the sha256 over exactly the bytes the verifier checks
  (the store's read-time law, mirrored at production time).
  Failure = raise `VerificationError` with a teaching message.
  A verifier that *crashes* (anything else) is a plugin bug —
  loud, exit 1, the builder's plugin-bug boundary mirrored.

### 8. Errors — the `VerifyError` family

`VerifyError(WorkflowCodaError)` joins the taxonomy, split by
correction clock: `SpecError` (fix the spec file),
`VerificationError` (fix the artifact or the criteria; the raised
form under `fail`, the recorded form under `write`), and write
failures wrapped with the destination named. The CLI's existing
`main()` boundary — `WorkflowCodaError` → stderr message, exit 1 —
is reused untouched.

## The core verifiers

| Format | Basic check (criteria omitted) | Criteria |
|---|---|---|
| `json` | strict UTF-8, parses as JSON | `keys`: non-empty unique list; subset of the *top-level object* (payload must be an object to use it — teach otherwise) |
| `txt` | strict UTF-8 decode | none — accepts no criteria (teaches if given) |
| `bytes` | none beyond existence + checksum | none |
| `core.tabular` | strict UTF-8; parses under `sep`; header present; blank first header cell legal (the index convention), no other blank; no duplicate header names; uniform width | `sep` (1 char, default tab), `header` (bool, default true; `header: false` refuses `columns` — the component's own teaching), `columns` (non-empty unique list; **presence check, a set** — order and selection are presentation, `core.table`'s business, not the pipeline's promise), `min_rows` (non-negative int; *data* rows, header excluded) |

**Rationale for the split**: basic = the component's *grammar*
(shape — a headered file with zero data rows passes basic, exactly
as `core.table`'s grammar accepts it); criteria = the pipeline's
*promises* (content). Verify never smuggles content policy into
the basic check.

## What verify does not touch

Store, builder, renderer: unchanged — they read a manifest that
is still just a manifest. The `0.2.0`-era fixture families keep
their shape; only version strings and the new optional field's
round-trip move. `test_readers_are_explicit_not_format_dispatched`
keeps passing untouched — that is the point of §1.

## Parked, with recorded direction

### Report states (its own future feature)

The sketch, recorded so the parked seams don't close: a state
dimension is **tabs with the panel set derived from run data** —
`axes: [{name: sample_id, values: [...]}]` in the manifest,
declarations carrying `key: {sample_id: s1}` (keys, never
per-sample types: the envelope's duplicate-type validator *and*
the id/type patterns make per-sample artifacts inexpressible —
real sample ids like `S1` cannot ride a dotted lowercase type
without loss), a `states` composition node in the layout
(`dimension` + children as the template), the builder expanding
per axis value onto the existing panel machinery. URL directives
select state at read time; widgets map to an axis *kind*
(categorical → radio/dropdown, ordered → range slider, subset →
checkbox list — state-as-subset is an open question). No-js and
print stack every state — the panels law already decided this.
Build-time expansion, never runtime fetching — the CSP forbids
network and self-containment prices in N × content.

### `for_each` (rides states)

The spec's expansion hook — parked with states because without
axes, forty per-sample artifacts have no consumer. Three sources,
one mechanism, house shape: exactly one source key per rule
(zero or multiple teach); `file:` required with `values`/
`samplesheet`, forbidden with `glob`; the glob carries exactly one
`{name}` and it must name the `dimension`; the samplesheet reads
through the tabular grammar (`sep` defaults tab); duplicates and
blank cells teach; first-appearance order — the producer's order
is the story.

```yaml
- for_each: {dimension: sample_id, values: [s1, s2, s3]}
  file: "qc/{sample_id}.json"
  id: "qc-{sample_id}"
- for_each: {dimension: sample_id, samplesheet: {file: samples.csv, column: sample, sep: ","}}
  file: "tables/{sample_id}.tsv"
  id: "table-{sample_id}"
- for_each: {dimension: sample_id, glob: "tables/{sample_id}.tsv"}
  id: "table-{sample_id}"
```

**`sanitize`** — the declared coercion option, because sample
names are end-user data and *silent* lowercasing is the dishonest
fix: raw values interpolate into `file:`/`samplesheet:`/`glob:`
templates (the disk's names are the truth); the **slug**
interpolates into `id:`/`type:` when `sanitize: true`, and a
grammar-failing value teaches per-value with the toggle as the
offered fix. Slug algorithm: lowercase; runs of characters outside
`[a-z0-9_-]` become one `-`; strip edge hyphens; digit-start gets
an `s-` prefix; empty teaches. Collisions teach, both raws named.
The raw name never disappears — `path:` keeps the real filename
and the future axes block carries raw values; ids are addresses,
never display names. Composes with `--on-failure` exactly as
locked: `fail` aggregates every expanded problem; `write` records
per artifact.

### `declare`

Known-failed and missing artifacts remain hand-written in v1 —
rare exception declarations. A `declare` companion command is
parked for them.

## Implementation map

- **M0** — this file; committed.
- **M1** — pin suites, emitted from the design sessions, read-only
  in aider:
  `tests/test_verify_cli.py` (create/append/update, conflict and
  producer teachings, the `0.2.0` refusal, atomicity,
  `--on-failure` both ways, exit codes, output lines) and
  `tests/test_verifiers.py` (the four format contracts under every
  criterion, unknown-criterion and conflict teachings, the
  reserved-trio law, the dispatch design pin, the round-trip gate:
  a written manifest loads green through the real loader).
- **M2** — the green (aider): new `src/workflow_coda/verification.py`
  (spec model + loader, orchestration, the writer) and
  `src/workflow_coda/core/verifiers.py` (the four verifiers);
  grown: `plugins.py` (`ReportPlugin.artifact_verifiers`),
  `registry.py` (verifier index, conflicts, reserved trio),
  `errors.py` (the `VerifyError` family), `cli.py` (the
  subcommand), `manifest/envelope.py` (the `verification` field,
  `Literal["0.3.0"]`), `manifest/loader.py` (pre-check message),
  `core/plugin.py` (`{"0.3.0"}`), `tests/factories.py` and every
  fixture — the cascade, with a census grep for version strings
  run and read to zero.
- **M3** — docs: `cli.rst` (verify), `schemas.rst` (`0.3.0`,
  `verification`), and a new how-to — *producing manifests from a
  workflow manager*, the fifth hand's guide. Recon: `cli.rst` and
  `schemas.rst` have never been held in full — paste before M3.
- **M4** — the eyeball: regenerate `tmp/sanity/manifest.json`
  *with verify*, checksums real; `build` greens off it — the
  round trip, live.

### The M2 aider session, once

Session-per-milestone — fresh `aider`, not `--continue`. Pins
enter read-only:

```
aider
> /read tests/test_verify_cli.py tests/test_verifiers.py
> /add src/workflow_coda/verification.py src/workflow_coda/core/verifiers.py \
       src/workflow_coda/cli.py src/workflow_coda/errors.py \
       src/workflow_coda/plugins.py src/workflow_coda/registry.py \
       src/workflow_coda/manifest/envelope.py src/workflow_coda/manifest/loader.py \
       src/workflow_coda/core/plugin.py
> M2 — green the verify suites. This file is the design record; the
> suites are the contract. Teach every failure. The writer builds
> models, never raw dicts. Criteria are transport — the framework
> never splits a comma. No format dispatch in the store; verify's
> dispatch is its own pinned surface.
```

Human-owned, always: read aider's diffs (splice boundaries are
where accidents hide), run and *read* the gates in your own
terminal, commit per milestone.

## Banked lessons that bind this feature

- **Pins are byte-transcriptions** of teachings, never paraphrase.
- **Census ripples**: a roster or version-string change reddens
  every census that satisfies the old one — grep for
  `len(plugin.components)` and version strings before landing M2.
- **Splice blocks are whole syntactic units**; when a delta is
  smaller than its block, name the delta in prose instead.
- **Replace-deltas name their boundaries** — the rules that
  survive a region are as much the delta as the rules that change.
- **Sweep greps are gates**, run and read to zero.
- **No silent behavior change where a pin exists** — change pins
  knowingly, with the shift documented in the comment.
- **The dispatch pin**: verify's format dispatch is deliberate
  and new; the store's law is untouched and keeps passing.

## Open items

- The `layout_loader.py` except-clause forensics (repr probe) —
  run before M2; unrelated to this feature, but aider reads source.
- `plugins.py` has never been held in full — read it before M1
  pins the `ReportPlugin` field.
- `cli.rst` / `schemas.rst` — paste before M3.
