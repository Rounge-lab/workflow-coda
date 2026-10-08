Security Considerations
=======================

Jinja autoescaping should remain enabled.

Use ``| safe`` only for trusted internal HTML, including:

* Plotly-generated fragments.
* Package-owned SVG assets.
* Package-owned CSS.
* Package-owned JavaScript.
* HTML rendered from trusted package templates.

Do not mark arbitrary metadata, sample names, annotation values, user input, or
untrusted configuration as safe.

All normal text should use Jinja's default escaping.
