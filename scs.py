"""scs.py -- backwards-compat alias.

All logic lives in scs_entrypoint.py. This file exists only so that
user code doing ``from scs import *`` keeps working in Brython, where
``import scs`` resolves to a real module file. No boilerplate here:
no loop, no events, no renderer code.
"""
from scs_entrypoint import *  # noqa: F401,F403
from scs_entrypoint import __all__

try:
    import sys as _sys
    import scs_entrypoint as _ep
    _sys.modules['scs'] = _ep
except Exception:
    pass

# v39: scs.run shim - see scs_entrypoint.py. scs is a file, not a package.
try:
    import sys as _sys2
    _sys2.modules['scs.run'] = _ep
    try:
        _ep.__path__ = []
    except Exception:
        pass
    _ep.run = _ep
    _sys2.modules['scs'].run = _ep
except Exception:
    pass
