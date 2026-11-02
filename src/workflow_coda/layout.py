"""The report layout contract: how a report author composes a report.

The layout is the framework's most human-facing input: a small YAML
file in which the author declares the report's identity (title, optional
subtitle, logo, favicon, theme, header color) and an ordered list of
*tabs*, each composing components through a small layout grammar.
This module is the layout's *data model* — the shape of that file as
strict pydantic models, format-agnostic.  The layout loader turns
YAML text into these models with teaching errors; the report builder
consumes them, resolving component ids against the live plugin
registry.

The grammar has two kinds of node, told apart by shape.  A node
carrying ``id`` is a *placement*: one component instance with its
optional title, parameters, and placement policies (on_missing,
on_unavailable).  A node carrying
``type`` is a *composition node*: ``row`` lays its children side by
side under optional width ratios, ``grid`` flows children row-major
into ratio-given columns, ``card`` groups its children in an
optionally titled box with its own arrangement, and ``diagnostics``
places the report's diagnostics panel.  Nodes nest — a tab's list, a
row's, a grid's, and a card's children all speak the same grammar —
so layouts compose the way frames do in a design tool.  Tabs are the
report's navigation: the rendered tab bar is generated from them, and
a single-tab report shows no bar.

The layout is the "third flavor" of the validation rules: it is
deserialized from a file like the manifest (strict pydantic models,
unknown keys rejected), but authored by hand like the plugin
contracts, so its text fields additionally require *visible* text —
a whitespace-only title is always an authoring mistake.  Values are
otherwise preserved exactly as written.

Validation is two-stage, following the find/require line.  The
models check *shape*: ids look like component ids, tabs are
non-empty, split ratios are positive numbers, and composition is
consistent (a row's ratios match its child count, a stack takes no
split).  Resolution questions — does the component exist, does the
theme file exist — belong to the report builder, which has the live
registry and the filesystem.

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
from typing import Annotated, Final, Literal, Self

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    ValidationError,
    model_validator,
)
from pydantic_core import ErrorDetails

from .artifact_store import JsonValue
from .components import COMPONENT_ID_PATTERN
from .text import has_visible_text
from .theme import ThemeToken

LayoutSchemaVersion = Literal["0.2.0"]
"""The layout contract's own version.

An axis entirely distinct from manifest schema versions: the manifest
version gates plugins, the layout version versions the layout file
format itself.  The two are never compared.

Version 0.2.0 renamed ``sections:`` to ``tabs:`` and made tabs the
report's navigation (the ``toc:`` key is gone; layouts now compose
through row, grid, card, and diagnostics nodes).  The loader teaches
the migration for 0.1.0 files.
"""


def _require_visible_text(value: str) -> str:
    """Reject whitespace-only text: always an authoring mistake."""
    if not has_visible_text(value):
        raise ValueError("must contain visible text, not only whitespace")
    return value


def _require_token_name(value: object) -> object:
    """Teach the literal trap: the header color names a theme token."""
    if isinstance(value, str) and value.startswith("#"):
        raise ValueError(
            "the header color is a theme token name (e.g. 'primary'), "
            "never a color literal — declare the color in the report's "
            "theme and name the token here"
        )
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
        record the missing id — the shared-layout scenario, where one
        layout serves runs whose installed plugins vary.
    ``skip``
        No component and no diagnostic.
    """

    FAIL = "fail"
    NOTICE = "notice"
    SKIP = "skip"


class UnavailablePolicy(Enum):
    """The placement policy when a component's render returns an
    ``unavailable`` outcome — its data is missing.

    The second of the two placement gates: ``on_missing`` governs
    component *resolution* (does the environment offer the
    component?); this governs the *outcome* (did the pipeline
    produce the component's data?).  Missing data is expected
    pipeline behavior — a branch not taken, a partial run — so the
    default is ``notice``, not ``fail``.

    ``notice``
        The framework's notice card carries the outcome's message in
        place.  The default.
    ``skip``
        The component is omitted from the report; the diagnostics
        record the omission as a note, with the outcome's message.
    ``fail``
        The build refuses: the report considers this component's
        data fundamentally required, and the report does not exist
        without it.
    """

    NOTICE = "notice"
    SKIP = "skip"
    FAIL = "fail"


class ComponentPlacement(BaseModel):
    """One component instance placed in the composition.

    A placement is an *instance*, not a reference: the same component
    id may appear any number of times, in the same or different
    nodes, each with its own title and parameters.  A placement may
    sit anywhere a node goes — a tab's list, a row's, a grid's, or a
    card's children.  The builder renders each placement
    independently.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: Annotated[str, AfterValidator(_require_component_id_shape)]
    """The component id, as declared by a plugin."""

    title: VisibleText | None = None
    """Optional title for *this instance*, overriding the component
    declaration's ``title``.  The declaration's title is the plugin's
    default — one name for every placement of the component; a
    per-placement ``title`` names this instance, so a row of KPIs can
    each carry their own heading.  Absent means inherit."""

    parameters: dict[str, JsonValue] = {}
    """Transport: values pass to the component's render call exactly as
    written.  The framework interprets none of them; each plugin reads
    and validates the keys it cares about.  Values must be
    JSON-compatible — YAML's richer types (dates, sets, binary) are
    rejected with an error naming the field."""

    on_missing: MissingPolicy | None = None
    """Per-placement override of the layout-level ``on_missing``; not
    given means inherit."""

    on_unavailable: UnavailablePolicy | None = None
    """The policy when this component's render returns unavailable
    (its data is missing); given means inherit the layout default."""


def _require_positive_ratios(value: object) -> object:
    """Teaching checks on raw split ratios, before any coercion.

    Runs before pydantic converts anything, where the YAML 1.1 traps
    would otherwise hide: a bare ``yes``/``no`` arrives as
    ``True``/``False`` and would coerce to ``1.0``/``0.0`` — a silent
    nonsense split.  Strings are refused outright: a hand-authored
    ratio list has no business being text.
    """
    if not isinstance(value, (list, tuple)):
        return value  # not a list at all: pydantic's type error teaches
    if len(value) < 2:
        raise ValueError(
            f"a split needs at least two ratios (one per region), got {len(value)}"
        )
    for item in value:
        if isinstance(item, bool):
            raise ValueError(
                "split ratios must be numbers — YAML parsed this entry "
                "as a boolean; bare true/false/yes/no/on/off are "
                "booleans in YAML, not words"
            )
        if not isinstance(item, (int, float)):
            raise ValueError(f"split ratios must be numbers, got {item!r}")
        if item <= 0:
            raise ValueError(f"split ratios must be greater than 0, got {item!r}")
    return value


SplitRatios = Annotated[tuple[float, ...], BeforeValidator(_require_positive_ratios)]
"""Width ratios for rows and grid columns: at least two positive
numbers, relative (``[2, 1]`` makes the first region twice the
second).  The framework responsively collapses ratio layouts to a
single column on small screens."""


CardLayoutKind = Literal["stack", "row", "grid"]
"""How a card arranges its children: stacked vertically (the
default), in a ratio-split row, or flowed into ratio-split columns."""


class RowNode(BaseModel):
    """``type: row`` — children side by side under width ratios.

    ``split`` gives one ratio per child; omitted, every child takes
    equal width.  Ratios are relative (``[2, 1]`` makes the first child
    twice the second), and the framework collapses the row to one
    column on small screens.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    type: Literal["row"]
    split: SplitRatios | None = None
    children: tuple[LayoutNode, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _split_matches_children(self) -> Self:
        if self.split is not None and len(self.split) != len(self.children):
            raise ValueError(
                f"'split' gives {len(self.split)} ratios for "
                f"{len(self.children)} children — a row takes exactly "
                "one ratio per child (or no split, for equal widths)"
            )
        return self


class GridLayout(BaseModel):
    """``type: grid`` — children flow row-major into ratio-split columns.

    ``split`` gives the column ratios and is required: without it, a
    grid is just a stack.  Children fill the columns row by row; the
    last row may be short.  The framework collapses the grid to one
    column on small screens.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    type: Literal["grid"]
    split: SplitRatios
    children: tuple[LayoutNode, ...] = Field(min_length=1)


class CardNode(BaseModel):
    """``type: card`` — a titled grouping of components.

    A card is the visual "these belong together": an optional title,
    its own arrangement (``layout``: stack, row, or grid), and at
    least one child.  ``split`` sizes a row or grid layout; a stack
    rejects it, since it would be dead weight.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    type: Literal["card"]
    title: VisibleText | None = None
    layout: CardLayoutKind = "stack"
    split: SplitRatios | None = None
    children: tuple[LayoutNode, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _layout_is_consistent(self) -> Self:
        if self.layout == "stack" and self.split is not None:
            raise ValueError(
                "a stack ignores 'split' — remove it, or set layout: row "
                "or layout: grid to arrange the children side by side"
            )
        if (
            self.layout == "row"
            and self.split is not None
            and len(self.split) != len(self.children)
        ):
            raise ValueError(
                f"'split' gives {len(self.split)} ratios for "
                f"{len(self.children)} children — a row layout takes "
                "exactly one ratio per child (or no split, for equal "
                "widths)"
            )
        return self


class DiagnosticsNode(BaseModel):
    """``type: diagnostics`` — the report's diagnostics panel, placed.

    The builder's diagnostics (problems, then notes) render at this
    spot wherever the author places it, always with state — an empty
    ledger shows "no issues", so the placed panel is predictable.  A
    report that places none shows no diagnostics at all; the builder
    still records everything.  The node carries no keys of its own.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    type: Literal["diagnostics"]


_NODE_TYPES: Final[tuple[str, ...]] = ("row", "grid", "card", "diagnostics")


def _member_message(error: ErrorDetails) -> str:
    """One member-model violation as teaching text, with the YAML
    boolean trap explained where it fires."""
    message = error["msg"]
    if message.startswith("Value error, "):
        message = message.removeprefix("Value error, ")
    if isinstance(error["input"], bool):
        return (
            f"YAML parsed this as the boolean {error['input']} — bare "
            "true/false/yes/no/on/off are booleans in YAML, not words; "
            f"quote the word to make it text. ({message})"
        )
    return message


def _validate_member(model: type[BaseModel], data: dict[str, object]) -> BaseModel:
    """Validate *data* as one node kind, folding field errors into
    teaching text.

    Node validation runs inside the dispatch validator, so pydantic
    reports member errors as one error *at the node*; folding keeps
    each violation a readable ``field: problem`` line instead of a
    nested error blob.
    """
    try:
        return model.model_validate(data)
    except ValidationError as e:
        lines = "; ".join(
            f"{'.'.join(str(part) for part in error['loc']) or 'the node'}: "
            f"{_member_message(error)}"
            for error in e.errors()
        )
        raise ValueError(lines) from e


def _dispatch_node(data: object) -> object:
    """Shape-dispatch one raw layout node to its model.

    The grammar's front door: a node carrying ``id`` is a placement, a
    node carrying ``type`` is a composition — and everything else is
    taught, not guessed.
    """
    if not isinstance(data, dict):
        raise ValueError(
            "a layout node must be a mapping: a placement (id:, "
            "parameters:) or a composition (type:, children:)"
        )
    if "id" in data and "type" in data:
        raise ValueError(
            "a layout node is either a placement ('id') or a "
            "composition ('type'), never both — drop one"
        )
    if "id" in data:
        return _validate_member(ComponentPlacement, data)
    if "type" not in data:
        raise ValueError(
            "a layout node needs either 'id' (to place a component) or "
            "'type' (to compose a row, grid, card, or diagnostics panel)"
        )
    node_type = data["type"]
    if node_type == "row":
        return _validate_member(RowNode, data)
    if node_type == "grid":
        return _validate_member(GridLayout, data)
    if node_type == "card":
        return _validate_member(CardNode, data)
    if node_type == "diagnostics":
        return _validate_member(DiagnosticsNode, data)
    available = ", ".join(repr(name) for name in _NODE_TYPES)
    raise ValueError(
        f"unknown composition type {node_type!r} — compositions are {available}"
    )


LayoutNode = Annotated[
    ComponentPlacement | RowNode | GridLayout | CardNode | DiagnosticsNode,
    BeforeValidator(_dispatch_node),
]
"""One node of the composition grammar, wherever nodes go.

The dispatch validator owns shape discrimination and validation;
the union lets an already-built member instance through and gives
consumers (the builder's walk) a precise type to narrow against."""

RowNode.model_rebuild()
GridLayout.model_rebuild()
CardNode.model_rebuild()
# The node models reference LayoutNode before the alias exists; the
# rebuilds above resolve those forward references now that it does.


class ReportTab(BaseModel):
    """One report tab: a titled composition that becomes one panel.

    Empty tabs are rejected — comment out the whole tab while
    composing::

        # tabs:
        #   - title: Quality control
        #     components:
        #       - id: example_bio.qc
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    title: VisibleText
    """The tab's heading — its label in the tab bar."""

    components: tuple[LayoutNode, ...] = Field(min_length=1)
    """The tab's composition, in declaration order."""


class ReportLayout(BaseModel):
    """The whole report layout: identity plus ordered tabs.

    Constructed by the loader from the layout file's parsed content;
    see the module docstring for the declared-then-strict rule that
    ``theme``, ``logo``, and ``favicon`` follow.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: LayoutSchemaVersion
    """The layout contract version this file is written against."""

    title: VisibleText
    """The report's title, rendered in the page header."""

    subtitle: VisibleText | None = None
    """Optional one-line subtitle under the title."""

    author: VisibleText | None = None
    """Optional free-form author line shown in the report footer —
    a person, a group, several names; whatever should be credited."""

    version: VisibleText | None = None
    """Optional free-form report version, shown in the header under
    the title — "1.2.0", "v2", "draft", a date; whatever identifies
    this revision of the report."""

    theme: VisibleText | None = None
    """Optional path to a theme file, relative to the layout file.
    Omitted means the built-in default theme."""

    logo: VisibleText | None = None
    """Optional path to a logo image, relative to the layout file;
    embedded into the report at build time."""

    favicon: VisibleText | None = None
    """Optional path to a favicon image, relative to the layout file;
    embedded into the report at build time."""

    header_color: Annotated[ThemeToken | None, BeforeValidator(_require_token_name)] = (
        None
    )
    """Optional theme token for the page header's background, e.g.
    ``primary`` (the default) or ``accent``.  A token *name*, never a
    color literal: the header's ink is the theme's own contrast-picked
    text against it, so the bar reads on any theme without the author
    choosing.  The builder validates the token against the loaded
    theme; the renderer derives the page's header properties from it."""

    on_missing: MissingPolicy = MissingPolicy.FAIL
    """The default placement policy when a component id resolves to
    nothing; per-placement ``on_missing`` overrides it."""

    on_unavailable: UnavailablePolicy = UnavailablePolicy.NOTICE
    """The default placement policy when a component's render returns
    unavailable (its data is missing); per-placement
    ``on_unavailable`` overrides it."""

    tabs: tuple[ReportTab, ...] = Field(min_length=1)
    """The report's tabs, in declaration order; each becomes one tab
    panel, and the tab bar is generated from them."""
