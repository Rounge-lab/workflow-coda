"""Loading report manifests from files.

The loader owns the file side of the manifest contract: read the file as
strict UTF-8, parse it as JSON, and validate it against the envelope
model.  Every failure mode is wrapped in :class:`ManifestError` with the
file path for context, so callers never see a bare :class:`OSError`,
:class:`json.JSONDecodeError`, or pydantic :class:`ValidationError`.

Loading validates the envelope only: it does not touch artifact files.
A manifest whose declared schema version is not one this framework reads fails with the
declared and expected versions named, before envelope validation.  Existence,
containment, and checksums are the artifact store's concern.
"""

import json
from pathlib import Path

from pydantic import ValidationError

from ..errors import ManifestError
from .envelope import MANIFEST_SCHEMA_VERSION, ReportManifest

_UTF8_BOM = "\ufeff"
"""Byte-order mark that strict UTF-8 manifest files must not begin with."""


def load_manifest(path: Path | str) -> ReportManifest:
    """Load and validate a report manifest file.

    Raises :class:`workflow_coda.errors.ManifestError` when the file is
    unreadable, not strict UTF-8, not valid JSON, or violates the
    manifest envelope contract.  The original exception, when there is
    one, is attached as ``__cause__``.
    """
    manifest_path = Path(path)
    try:
        text = manifest_path.read_text(encoding="utf-8")
    except OSError as e:
        raise ManifestError(f"could not read manifest {manifest_path}: {e}") from e
    except UnicodeDecodeError as e:
        raise ManifestError(f"manifest {manifest_path} is not valid UTF-8: {e}") from e
    if text.startswith(_UTF8_BOM):
        raise ManifestError(
            f"manifest {manifest_path} starts with a UTF-8 byte order mark; "
            "write plain UTF-8 without a BOM"
        )
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as e:
        raise ManifestError(
            f"manifest {manifest_path} is not valid JSON "
            f"at line {e.lineno}, column {e.colno}: {e.msg}"
        ) from e
    if isinstance(payload, dict):
        declared_version = payload.get("schema_version")
        if (
            isinstance(declared_version, str)
            and declared_version != MANIFEST_SCHEMA_VERSION
        ):
            raise ManifestError(
                f"manifest {manifest_path}: the manifest's schema_version must be "
                f'"{MANIFEST_SCHEMA_VERSION}", but this file declares '
                f"{declared_version!r} — regenerate this manifest with "
                f"'workflow-coda verify'"
            )
    try:
        return ReportManifest.model_validate(payload)
    except ValidationError as e:
        details = str(e).replace("\n", "\n  ")
        raise ManifestError(f"manifest {manifest_path} is invalid:\n  {details}") from e
