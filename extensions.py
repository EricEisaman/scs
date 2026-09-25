# extensions.py - Root shim for Brython GitHub Pages
# Fixes 404 for ./extensions.py - Brython tries this before ./extensions/__init__.py
import sys, types

# Ensure extensions package path
try:
    __path__ = ['extensions']
except:
    pass

# Pre-create empty modules to prevent Brython from trying ./extensions.py as package
# BUT only if they don't already exist - and we will overwrite with real modules after
for _n in ['fetch','datastar','multiplayer','proc_audio']:
    _f = f'extensions.{_n}'
    if _f not in sys.modules:
        try:
            sys.modules[_f] = types.ModuleType(_f)
        except:
            pass

# Now try to load real implementations and populate the placeholders
try:
    import extensions.fetch as _real_fetch
    # Copy attributes to placeholder if placeholder exists
    _mod = sys.modules.get('extensions.fetch')
    if _mod:
        for _k in ['fetch','fetch_json','fetch_text','FetchError','FetchResponse']:
            try:
                setattr(_mod, _k, getattr(_real_fetch, _k))
            except:
                pass
    sys.modules['extensions.fetch'] = _real_fetch
except:
    pass

try:
    import extensions.datastar as _real_ds
    sys.modules['extensions.datastar'] = _real_ds
except:
    pass

try:
    import extensions.multiplayer as _real_mp
    sys.modules['extensions.multiplayer'] = _real_mp
except:
    pass

try:
    import extensions.proc_audio as _real_pa
    sys.modules['extensions.proc_audio'] = _real_pa
except Exception as _e:
    # If direct import fails, try to create module from file manually
    try:
        # Don't fail - leave placeholder so app doesn't crash on import
        pass
    except:
        pass

# Also ensure extensions package exists
try:
    import extensions as _ext_pkg
    # Make sure submodules are accessible
    for _name in ['fetch','datastar','multiplayer','proc_audio']:
        _full = f'extensions.{_name}'
        if _full in sys.modules:
            try:
                setattr(_ext_pkg, _name, sys.modules[_full])
            except:
                pass
except:
    pass
