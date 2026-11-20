========================
How workflow-coda works
========================

Every design decision in ``workflow-coda`` traces back to a small
set of ideas.  This page states them plainly: who owns what in a
report, and the three commitments that shape the framework's
behavior — reports are honest, declaration is a promise, and the
report is one self-contained file.  The tutorials and guides show
you *what to do*; this page explains *why it works that way*.

Four hands build a report
-------------------------

A report is assembled from four kinds of contribution, each
owned by someone with different knowledge:

* **The pipeline** knows what a run produced.  It writes the
  artifacts and the manifest — a claim list of what exists and
  where.  It knows nothing about reports.
* **The report author** knows what the report should say.  They
  write the layout, and optionally the theme: which content, in
  what order, under what titles, in which colors.  They know
  nothing about how components are implemented.
* **The plugin author** knows how to turn one kind of artifact
  into presentable content.  They write components and register
  them.  They know nothing about any particular run.
* **The framework** owns everything that must not vary: reading
  and validating the files, resolving components, composing the
  page, and the honest presentation of everything that did or did
  not happen.

The seams are the files and contracts you have already met: the
manifest speaks pipeline-to-framework, the layout speaks
author-to-framework, and the component contracts speak
plugin-to-framework (:doc:`../reference/schemas/index`).  No
party needs to know more about the others than these files say —
which is why a report survives its pipeline, its author, and its
plugin author all moving on.

Reports are honest
------------------

A report is a record of a real run, and real runs are partial:
steps fail, data is missing, deadlines pass.  The framework's
first commitment is that the report never pretends otherwise.
Every omission is either visible in the page or recorded in the
diagnostics ledger, and most are both.  Nothing is dropped
silently — not the default theme, not an omitted logo, not a
component excluded over schema versions.

Honesty requires telling two failure families apart:

* **Missing data is a fact.**  When a component's inputs are
  absent, the outcome is *unavailable* — a quiet notice saying
  what and why.  Partial runs are normal; the report shows what
  the run produced and states plainly what it did not.
* **Broken code is a bug.**  When a component raises, the builder
  catches it, records a plugin bug, and renders a failure card
  quoting the exact error.  Bugs are loud on purpose — someone
  must fix them, and the report is where they are found.

The channels are distinct by construction, so neither family can
masquerade as the other: an exception from a render call is always
collected as a plugin bug, whatever it was, and an ``unavailable``
outcome is always a notice.  The convention that keeps the split
honest is the one the tutorials teach: a missing artifact is a
fact about the run, while a present artifact whose content breaks
the documented contract raises.  The tutorial demonstrates it
(:doc:`../tutorials/first-plugin`); the reference defines it
(:doc:`../reference/framework/api/components`).

Declaration is a promise
------------------------

Most optional pieces of a report follow one rule: **declared,
then strict**.  Omitting a theme, a logo, or a favicon is a
valid, recorded absence — the report builds, and the ledger notes
how to add what is missing.  But the moment one is *declared*, it
becomes a promise: the file must exist, load, and be what it
claims to be, and a build that cannot keep the promise refuses —
naming the file, the problem, and the fix.

The rule exists because of *when* failure can happen.  A missing
file at build time is a cheap moment: the author is right there,
and one message fixes it.  A missing file at read time — a broken
image in a reader's browser — is a broken report.  So the build
resolves and verifies everything it can while the author is
present, and embeds the rest (the next section says where the
rest goes).

The refusal message is where the rule meets the author, and the
messages are designed to be read as documentation: duplicated
mapping keys name the key and its line; an unknown
``header_color`` token names the tokens the theme actually
declares; a nonexistent path is refused before the pipeline even
starts.  This is why exit code ``1``
(:doc:`../reference/cli`) always means one teaching
message on stderr — never a traceback.

One file, no dependencies
-------------------------

The finished report is a single HTML page, and everything it
references is embedded at build time: the theme becomes generated
CSS on the page; the logo and favicon become data URIs (an SVG
logo inlines as markup, which is also why a logo authored with
``"currentColor"`` follows the header's text color — markup
inherits, an image cannot); figures embed with Plotly.js inlined
exactly once; component css and js ride inline in their
namespaced blocks.  The page loads no fonts and fetches nothing.

Self-containment is enforced, not just practiced: the page
declares a Content-Security-Policy that blocks every network
request at read time.  A reader's browser refuses to fetch
*anything* the page might ask for — a plugin's stylesheet could
not load a font if it tried.  The guarantee holds even for
components the framework has never seen.

The point is portability.  A report travels by email, sits in a
ticket, opens on an air-gapped machine years after the pipeline
that produced it is gone.  It needs no server, no internet, and
no installed software beyond a browser — the artifacts, the
build machine, and the whole software stack behind them are all
allowed to disappear, and the report stays complete and correct.

When behavior seems arbitrary
-----------------------------

When the framework refuses a build, drops an emptied section, or
insists on a token instead of a color literal, it is acting on
one of these three commitments.  If a design decision ever seems
arbitrary, check it against honesty, promise, and portability —
the reason is almost always one of the three.

* For getting started: :doc:`../tutorials/hello-report`.
* For doing: the :doc:`how-to guides <../how-to/index>`.
* For every key and contract in exact shape:
  the :doc:`reference documentation <../reference/index>`.
