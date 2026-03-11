import os
import sys
import django

# 1. Point Sphinx to your project root
sys.path.insert(0, os.path.abspath(".."))

# 2. Tell Sphinx which settings file to use
os.environ["DJANGO_SETTINGS_MODULE"] = "core.settings"

# 3. Initialize Django so Sphinx can import models
django.setup()

# -- Project information -----------------------------------------------------
project = "ai-fire-monitoring-system"
copyright = "2026, SYED NABIL AFIFI BIN SYED AZIMAN"
author = "SYED NABIL AFIFI BIN SYED AZIMAN"

# -- General configuration ---------------------------------------------------
# Put ALL extensions in one list here
extensions = [
    "sphinx.ext.autodoc",  # Reads your code
    "sphinx.ext.napoleon",  # Supports clean docstrings
    "sphinx.ext.viewcode",  # Shows source code in docs
    "sphinx.ext.githubpages",
]

templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

# -- Options for HTML output -------------------------------------------------
# Consider changing "alabaster" to "sphinx_rtd_theme" for a more professional look
html_theme = "alabaster"
html_static_path = ["_static"]
