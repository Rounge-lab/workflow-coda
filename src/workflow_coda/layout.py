"""The report layout contract: how a report author composes a report.

The layout is the framework's most human-facing input: a small YAML
file in which the author declares the report's identity (title,
optional subtitle, logo, favicon, theme) and an ordered list of
sections, each listing components by id with optional parameters.  This
module is the layout's *data model* — the shape of that file as strict
pydantic models, format-agnostic.  The layout loader turns YAML text
into these models with teaching errors; the report builder consumes
them, resolving component ids against the live plugin registry.

The layout is the "third flavor" of the validation rules: it is
deserialized from a file like the manifest (strict pydantic models,
unknown keys rejected), but authored by hand like the plugin contracts,
so its text fields additionally require *visible* text — a
whitespace-only title is always an authoring mistake.  Values are
otherwise preserved exactly as written.

Validation is two-stage, following the find/require line.  This model
checks *shape*: ids look like component ids, sections are non-empty,
parameters are JSON-compatible.  Resolution questions — does the
component exist, does the theme file exist — belong to the report
builder, which has the live registry and the filesystem.

Three fields follow one rule: declared, then strict.  ``logo`` and
``favicon`` must exist next to the layout file and be embeddable
images, or the build fails; omitted, the report renders without them
and the builder records a diagnostic explaining how to add one.
``theme`` likewise: omitted means the built-in default theme (and a
diagnostic); declared, the file must load.  Assets are embedded into
the single-page report as data URIs at build time — the report file
never references external files.
"""

from enum import Enum
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from .artifact_store import JsonValue
from .components import COMPONENT_ID_PATTERN
from .text import has_visible_text

LayoutSchemaVersion = Literal["0.1.0"]
"""The layout contract's own version.

An axis entirely distinct from manifest schema versions: the manifest
version gates plugins, the layout version version the layout file
format itself.  The two are never compared."""


def _require_visible_text(value: str) -> str:
    """Reject whitespace-only text: always an authoring mistake."""
    if not has_visible_text(value):
        raise ValueError("must contain visible text, not only whitespace")
    return value


VisibleText = Annotated[str, AfterValidator(_require_visible_text)]
"""Non-empty, non-whitespace-only text, preserved exactly as written."""


def _require_component_id_shape(value: str) -> str:
    """Reject ids that do not look like component ids."""
    if COMPONENT_ID_PATTERN.fullmatch(value) is None:
        raise ValueError(
            f"not a component id: {value!r} — expected "
            f"'<plugin_id>.<component_name>', lowercase snake_case on "
            f"both sides of exactly one dot"
        )
    return value


class MissingPolicy(Enum):
    """What the builder does when a placement's component id resolves to
    no loaded component.

    ``fail``
        The build fails with an error listing the available component
        ids.  The default: an unknown id in a freshly authored layout
        is an authoring bug, and the error teaches the vocabulary.
    ``notice``
        The report renders without the component and the diagnostics
        section records the missing id — the shared-layout scenario,
        where one layout serves runs whose installed plugins vary.
    ``skip``
        No component and no diagnostic.
    """

    FAIL = "fail"
    NOTICE = "notice"
    SKIP = "skip"


class ComponentPlacement(BaseModel):
    """One component instance placed in a section.

    A placement is an *instance*, not a reference: the same component
    id may appear any number of times, in the same or different
    sections, each with its own parameters.  The builder renders each
    placement independently.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: Annotated[str, AfterValidator(_require_component_id_shape)]
    """The component id, as declared by a plugin."""

    parameters: dict[str, JsonValue] = {}
    """Transport: values pass to the component's render call exactly as
    written.  The framework interprets none of them; each plugin reads
    and validates the keys it cares about.  Values must be
    JSON-compatible — YAML's richer types (dates, sets, binary) are
    rejected with an error naming the field."""

    on_missing: MissingPolicy | None = None
    """Per-placement override of the layout-level ``on_missing``; not
    given means inherit."""


class ReportSection(BaseModel):
    """An ordered section of the report: a titled group of placements.

    Empty sections are rejected — comment out the whole section while
    composing::

        # - title: Quality control
        #   components:
        #     - id: example_bio.qc
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    title: VisibleText
    """The section's heading."""

    components: list[ComponentPlacement] = Field(min_length=1)
    """The section's placements, in declaration order."""


class ReportLayout(BaseModel):
    """The whole report layout: identity plus ordered sections.

    Constructed by the loader from the layout file's parsed content; see
    the module docstring for the declared-then-strict rule that
    ``theme``, ``logo``, and ``favicon`` follow.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: LayoutSchemaVersion
    """The layout contract version this file is written against."""

    title: VisibleText
    """The report's title, rendered in the page header."""

    subtitle: VisibleText | None = None
    """Optional one-line subtitle under the title."""

    theme: VisibleText | None = None
    """Optional path to a theme file, relative to the layout file.
    Omitted means the built-in default theme."""

    logo: VisibleText | None = None
    """Optional path to a logo image, relative to the layout file;
    embedded into the report at build time."""

    favicon: VisibleText | None = None
    """Optional path to a favicon image, relative to the layout file;
    embedded into the report at build time."""

    toc: bool = True
    """Whether the report includes a table of contents: a navigation
    list linking to the report's sections.  The default is ``True``;
    turn it off with ``toc: false``."""

    on_missing: MissingPolicy = MissingPolicy.FAIL
    """The default placement policy when a component id resolves to
    nothing; per-placement ``on_missing`` overrides it."""

    sections: list[ReportSection] = Field(min_length=1)
    """The report's sections, in declaration order."""
