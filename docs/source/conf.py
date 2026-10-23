# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

import importlib.metadata
import sys
from pathlib import Path

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

project = "workflow-coda"
copyright = "2026, Sverre Branders"
author = "Sverre Branders"

# The version comes from the installed package, so pyproject.toml stays
# the single source of truth — the same policy the core plugin follows.
try:
    release = importlib.metadata.version("workflow-coda")
except importlib.metadata.PackageNotFoundError:
    release = "unknown"

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

sys.path.insert(0, str(Path(__file__).resolve().parent / "_ext"))

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.viewcode",
    "sphinx_rtd_dark_mode",
    "sphinx_copybutton",
    "coda_theme_swatches",
]

templates_path = ["_templates"]
exclude_patterns: list[str] = []


# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

# -- Sphinx copybutton
copybutton_prompt_text = r">>> |\$ "
copybutton_prompt_is_regexp = True

# -- Styling
html_theme_options = {
    "logo_only": False,
}

html_theme = "sphinx_rtd_theme"
html_static_path = ["_static"]

html_css_files = [
    "docs_theme.css",
]

# -- Autodoc
autodoc_default_options = {
    "member-order": "bysource",
    "show-inheritance": True,
}
