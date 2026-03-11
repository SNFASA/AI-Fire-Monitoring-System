# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html


import os
import sys
import django

# 1. Point Sphinx to your project root
sys.path.insert(0, os.path.abspath('..'))

# 2. Tell Sphinx which settings file to use
os.environ['DJANGO_SETTINGS_MODULE'] = 'core.settings'

# 3. Initialize Django so Sphinx can import models
django.setup()

# 4. Add the 'autodoc' extension to the extensions list
extensions = [
    'sphinx.ext.autodoc',
    'sphinx.ext.napoleon', # Supports Google/NumPy style docstrings
    'sphinx.ext.viewcode', # Adds links to your source code
]

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information
project = "ai-fire-monitoring-system"
copyright = "2026, SYED NABIL AFIFI BIN SYED AZIMAN"
author = "SYED NABIL AFIFI BIN SYED AZIMAN"

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = []

templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]


# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

html_theme = "alabaster"
html_static_path = ["_static"]
