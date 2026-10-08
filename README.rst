=============
Workflow Coda
=============

A plugin-based composable static HTML report generator for integration with
pipeline workflows.

Development
-----------

Dependencies
^^^^^^^^^^^^

* python 3.14
* pixi

Installation
^^^^^^^^^^^^

.. code-block:: console
   :caption: Development setup

   pixi install

   # if you want to install the development documentation environment
   pixi install -e docs

Pre-commit hooks ensure compliance with standards before commits and pushes.
Please note that the "ruff check" and "ruff format" hooks may modify files
when detecting fixable errors. If this happens, please stage the automatic
changes and commit again.

.. code-block:: console
   :caption: Set up pre-commit hooks

   pixi run pre-commit-install

To avoid dependency conflicts, the developer documentation tools have a
dedicated environment.

.. code-block::
   :caption: Generate documentation

   pixi run -e docs docs

Checks
^^^^^^

.. code-block:: console
   :caption: Format files

   pixi run format

.. code-block:: console
   :caption: Run checks

   pixi run lint

.. code-block:: console
   :caption: Run tests

   pixi run test
