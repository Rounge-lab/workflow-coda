============
Verification
============

Spec in, manifest out: the library behind ``workflow-coda verify``,
which turns a pipeline's real output files into a verified report
manifest — the stable, versioned interface the report framework
reads. Import from the package directly
(``workflow_coda.verification``); the submodule layout is an
implementation detail.

Spec producer claims are optional and may be partial. The drivers merge
CLI and spec claims field by field, rejecting conflicts. Creation
requires a complete resolved producer identity; updates retain omitted
claims and require supplied values to match the resident manifest.

.. automodule:: workflow_coda.verification
   :members:
   :exclude-members: model_config
