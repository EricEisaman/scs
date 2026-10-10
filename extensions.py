"""
extensions.py - Root shim for SCS Extensions System

Brython tries ./extensions.py before ./extensions/__init__.py.
This shim ensures `from extensions.xxx import yyy` always works in both
index.html and sandbox.html by manually injecting modules into sys.modules.

Add new extensions here as they are created.
"""

import sys
import types

# ------------------------------------------------------------------
# Create package marker `extensions` if not already present
# ------------------------------------------------------------------
if 'extensions' not in sys.modules:
    pkg = types.ModuleType('extensions')
    sys.modules['extensions'] = pkg
else:
    pkg = sys.modules['extensions']
pkg.__path__ = getattr(pkg, '__path__', ['extensions'])

# ------------------------------------------------------------------
# Helper to inject a submodule
# ------------------------------------------------------------------
def _inject(name, module_obj):
    full = f'extensions.{name}'
    sys.modules[full] = module_obj
    # Also attach to parent package for attribute access
    setattr(sys.modules['extensions'], name, module_obj)

# ------------------------------------------------------------------
# Load real implementations from extensions/ directory
# ------------------------------------------------------------------
# The real packages live in extensions/__init__.py + extensions/*.py
# We attempt to import them; if import fails (e.g. in sandbox without path),
# we create a placeholder that will be overwritten once the package loads.

try:
    import extensions.fetch as _fetch_mod
    _inject('fetch', _fetch_mod)
except Exception as _e:
    # Create stub - will be replaced when extensions/fetch.py is loaded via pythonpath
    # The real fetch module should be importable via extensions/__init__.py mechanism
    pass

try:
    import extensions.transformers as _trans_mod
    _inject('transformers', _trans_mod)
except Exception as _e:
    pass

try:
    import extensions.ui as _ui_mod
    _inject('ui', _ui_mod)
except Exception:
    pass

try:
    import extensions.file_loader as _fl_mod
    _inject('file_loader', _fl_mod)
except Exception:
    pass

try:
    import extensions.pyodide as _pyodide_mod
    _inject('pyodide', _pyodide_mod)
except Exception:
    pass

try:
    import extensions.proc_audio as _proc_mod
    _inject('proc_audio', _proc_mod)
except Exception:
    pass

__all__ = ['fetch', 'transformers', 'ui', 'file_loader', 'pyodide', 'proc_audio']
