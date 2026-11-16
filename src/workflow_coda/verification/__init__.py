"""The verify command's library: spec in, manifest out.

``workflow-coda verify`` is the pipeline hand's door: it turns real
output files into a verified report manifest — the stable interface
the report framework reads.  This package is the library behind the
subcommand; the CLI is a thin edge that validates its own invocation
and hands everything to code that already knows how to fail with
teaching messages.

The package is layered by what each part owns:

* :mod:`~workflow_coda.verification.spec` — the hand-authored half
  of the contract: the spec's models and its loader, sharing the
  layout loader's YAML machinery and inheriting its
  hand-authored-file law — duplicate keys rejected with key and
  line, YAML's boolean traps explained with the quoting rule, every
  failure one teaching :class:`~workflow_coda.errors.SpecError`;
* :mod:`~workflow_coda.verification.engine` — the verification
  unit: bytes in, record and digest out — the same bytes the
  verifier checks are the bytes the sha256 digests — criteria
  riding verbatim under the caller-owns-IO law;
* :mod:`~workflow_coda.verification.declarations` — the manifest
  side: the atomic writer, the two declarations a verification can
  produce, the create-or-load door, and the placement law —
  append, or update in place;
* :mod:`~workflow_coda.verification.drivers` — the command's
  surface: flags mode, spec mode, and
  :func:`~workflow_coda.verification.run_verify`, the one door
  both route through, each driver returning a
  :class:`~workflow_coda.verification.VerifyOutcome` the CLI is
  the only printer of.

:mod:`~workflow_coda.verification.expansion` holds the spec's
``for_each`` expansion language — template, slug, collision —
and :mod:`~workflow_coda.verification.sources` its three value
sources (``values``, ``samplesheet``, ``glob``); both are wired
into the spec loader's expansion stage, between YAML parse and
validation.

This ``__init__`` re-exports the public surface the old module
carried, so ``from workflow_coda.verification import run_verify``
keeps its meaning — the package is the module, grown.
"""

from .declarations import (
    apply_artifact_declaration,
    build_failed_declaration,
    build_verified_declaration,
    check_producer_agreement,
    load_or_init_manifest,
    write_manifest_atomically,
)
from .drivers import (
    VerifyOutcome,
    parse_criteria,
    run_flags_verify,
    run_spec_verify,
    run_verify,
)
from .engine import verify_artifact_file
from .spec import (
    SpecArtifact,
    SpecProducer,
    VerifySpec,
    load_verify_spec,
)

__all__ = [
    "SpecArtifact",
    "SpecProducer",
    "VerifyOutcome",
    "VerifySpec",
    "apply_artifact_declaration",
    "build_failed_declaration",
    "build_verified_declaration",
    "check_producer_agreement",
    "load_or_init_manifest",
    "load_verify_spec",
    "parse_criteria",
    "run_flags_verify",
    "run_spec_verify",
    "run_verify",
    "verify_artifact_file",
    "write_manifest_atomically",
]
