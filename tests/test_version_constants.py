"""The schema-version axes' single sources of truth, pinned.

Each version axis (law: the axes are independent — package, manifest
envelope, layout, artifact content) has exactly one runtime constant,
and the type-checker's Literal beside it.  These pins hold the pairs
in agreement, so a bump that flips one side only reddens here first.

Tests elsewhere pin version literals on purpose: assertions verify
the actual value, and a bump's loud red sweep is the mechanism.  The
bump procedure is: flip the constant and the Literal together, then
green the sweep.
"""

from typing import get_args

from workflow_coda.layout import (
    LAYOUT_SCHEMA_VERSION,
    ReportLayout,
)
from workflow_coda.manifest import (
    MANIFEST_SCHEMA_VERSION,
    ReportManifest,
)


def test_the_manifest_constant_is_the_declared_literal() -> None:
    # The two axes bind their Literals differently: the manifest alias
    # is a PEP 695 TypeAliasType (lazy — typing.get_args returns ()
    # for it on Python 3.12), the layout alias a plain assignment
    # (eager — an ordinary typing form get_args reads directly).  The
    # unwrap-with-default reads both shapes: __value__ when the
    # annotation is a TypeAliasType, itself otherwise.
    annotation = ReportManifest.model_fields["schema_version"].annotation
    assert get_args(getattr(annotation, "__value__", annotation)) == (
        MANIFEST_SCHEMA_VERSION,
    )


def test_the_layout_constant_is_the_declared_literal() -> None:
    annotation = ReportLayout.model_fields["schema_version"].annotation
    assert get_args(getattr(annotation, "__value__", annotation)) == (
        LAYOUT_SCHEMA_VERSION,
    )
