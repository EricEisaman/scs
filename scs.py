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
