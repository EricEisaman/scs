"""
extensions.py - Root shim for Brython - makes import extensions.* work
Per SCS spec: ship both extensions.py and extensions/__init__.py
"""

import sys, types

# Ensure extensions package exists
try:
    import extensions as _ext_pkg
except:
    _ext_pkg = types.ModuleType('extensions')
    sys.modules['extensions'] = _ext_pkg

# Inject submodules
try:
    from extensions import multiplayer as _mp
    sys.modules['extensions.multiplayer'] = _mp
    _ext_pkg.multiplayer = _mp
except Exception as e:
    try:
        from browser import window
        window.console.warn("[extensions.py shim] multiplayer load failed", e)
    except:
        pass

try:
    from extensions import datastar as _ds
    sys.modules['extensions.datastar'] = _ds
    _ext_pkg.datastar = _ds
except Exception as e:
    try:
        from browser import window
        window.console.warn("[extensions.py shim] datastar load failed", e)
    except:
        pass

try:
    from extensions import fetch as _ft
    sys.modules['extensions.fetch'] = _ft
    _ext_pkg.fetch = _ft
except Exception as e:
    pass
