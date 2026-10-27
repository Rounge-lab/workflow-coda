"""The render context: the framework services handed to every plugin.

Plugins never touch the filesystem directly and never hard-code colors.
One :class:`RenderContext` is constructed per report and passed to every
plugin render call.  It bundles the services a plugin renders with:

* :attr:`store` — the report's artifact store, the only gateway to
  artifact contents.
* :attr:`theme` — the report's design-token theme, for styling figures
  and other generated output (:mod:`workflow_coda.theme`).

The context is per-report.  Per-component configuration travels
separately as the ``parameters`` argument of the render call; the two
are never merged.  The context is frozen and slotted: a plugin receives
it, it does not own it — fields cannot be rewired, and no new attributes
can be stashed on it.

Later milestones add framework services as new fields of the context;
existing fields are not removed.
"""

from dataclasses import dataclass

from .artifact_store import ArtifactStore
from .icons import IconLibrary
from .theme import DEFAULT_THEME, Theme

_EMPTY_ICONS = IconLibrary(())
"""The icon-free default: direct construction (tests, third-party
tooling) renders icon-free components honestly; the builder always
passes the real library."""


@dataclass(frozen=True, slots=True, kw_only=True)
class RenderContext:
    """Framework services for rendering one report.

    Construction is keyword-only, so fields added in later milestones
    cannot silently break positional call sites.
    """

    store: ArtifactStore
    """The report's artifact store, the only gateway to artifact contents."""

    theme: Theme = DEFAULT_THEME
    """The report's design-token theme, defaulting to :data:`DEFAULT_THEME`."""

    icons: IconLibrary = _EMPTY_ICONS
    """The build's merged icon namespace: unknown names teach as
    layout errors, shipped icon defects as installation errors."""
