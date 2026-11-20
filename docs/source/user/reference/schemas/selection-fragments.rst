==========================
Report selection fragments
==========================

Generated reports use the URL hash fragment to select tabs and
:doc:`layout states <layout>`, including when opened as local files.
Selection changes visibility; all surviving state content is embedded
in the report.

Grammar
-------

Structured fragments contain ``&``-separated ``key=value``
directives:

.. code-block:: text

   #tab=1-headlines&state.batch=b

.. list-table::
   :header-rows: 1

   * - Directive
     - Value
     - Meaning
   * - ``tab``
     - Generated tab-panel id
     - Selects a tab. The id starts with its 1-based document
       position, followed by a slug of its title.
   * - ``state.<dimension>``
     - Raw axis value
     - Selects that value report-wide for the dimension.

Keys and values are percent-encoded UTF-8. A literal plus sign is not
a space. Values are not normalized: ``Run%20A`` and ``run-a`` address
different values.

A directive splits at its first ``=``. Unknown keys, invalid
dimension names, duplicate keys, empty values, and malformed percent
encoding produce feedback. A tab or state dimension may be selected at
most once.

A fragment without ``=`` or ``&`` is accepted as a legacy tab-panel
anchor, such as ``#1-headlines``. An empty fragment declares no
selection.

Initial load and ``hashchange`` read the URL without rewriting it.
Interactions serialize selections while preserving other parsed state
directives; malformed directives are not carried through. The History
API's ``replaceState`` is used when available, otherwise the hash is
updated directly.

Defaults and shared axes
------------------------

Without a tab directive, the first document tab is selected. Without a
state directive, the default is the first available value in
first-occurrence order in the selected outer context.

Each dimension has one report-wide selection. Shared categorical axes
use the union of surviving values in first-occurrence document order.
Shared ordered axes merge their precedence constraints; first
occurrence breaks ties between unconstrained values. The default is
chosen from first-occurrence order before this merge.

Contradictory ordering or differing shared kinds disables selection for
that dimension. Nested availability uses nodes whose ancestor panels
match selected outer dimensions. An unselected or degraded outer
dimension leaves its contexts available. Cyclic cross-dimension
dependencies disable unresolved dimensions.

Controls
--------

A shared control appears above tab content when its dimension is not
disabled, its available axis has at least two values, and an active
states node using it exists on the displayed tab. With tabs stacked,
relevance is evaluated across all displayed tabs. Changing tabs hides
irrelevant controls without resetting shared selections.

Categorical controls are labeled dropdowns. Ordered controls are
single-position sliders with the raw label displayed and exposed as
``aria-valuetext``. A degraded ordered selection uses a temporary
``-1`` non-axis position labeled as unselected; choosing a real value
restores the ordinary range.

Controls replan after tab or outer-context changes. Focus returns to
the same dimension's control when available. Otherwise it moves to the
active tab button, the first tab button when tabs are stacked, or the
tab panel if there is no tab bar.

Failures and degradation
------------------------

Selection failures preserve content:

* An explicit value absent from the global axis or selected outer
  context leaves that dimension stacked and produces feedback. The
  URL retains the value until an interaction changes it.
* Malformed, duplicate, or empty directives for a valid dimension
  leave that dimension stacked.
* A malformed structured fragment, including an unknown key, invalid
  dimension name, or invalid tab directive, leaves tabs and state
  dimensions stacked.
* A syntactically valid but unknown tab id stacks tabs; otherwise valid
  state selections still apply.
* A directive for a dimension absent from the report produces
  feedback; known dimensions continue their ordinary selection.
* Shared-kind conflicts, contradictory ordered axes, and cyclic
  dependencies disable affected dimensions and show feedback.
* A globally valid selection missing from one active states node hides
  that node's nonmatching panels and shows a no-content message there.

Independent or nested dimensions may continue to filter content while
another dimension is stacked.

Without JavaScript, every tab and state is present and visible, and
selection controls are absent or hidden. Print styles restore all tabs
and state panels and hide navigation, controls, and selection feedback.

Reveal events notify visible content through ``coda:tab-shown`` and
``coda:state-shown``; the framework uses them to resize visible Plotly
figures. Build diagnostics are independent of read-time selection
feedback.
