# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

project = "workflow-coda"
copyright = "2026, Sverre Branders"
author = "Sverre Branders"
release = "0.1.0"

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = [
    "sphinx_rtd_dark_mode",
    "sphinx_copybutton",
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
