# extensions/__init__.py
# SCS Extensions System
# ---------------------
# Place extension modules in this folder.
# They are importable from any app via:
#   from extensions.fetch import fetch, fetch_json, fetch_text
#   import extensions.fetch
#
# MVC Rule: Extensions are Model layer only.
# They must NOT import scs, App, or perform any drawing.
# They provide data and services. View logic stays in redrawAll.

# This file makes `extensions` a package for Brython's import system.
# No runtime code needed here - Brython will fetch modules via AJAX.

__all__ = ['fetch']
