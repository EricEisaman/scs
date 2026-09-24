# extensions.py - Root shim for Brython on GitHub Pages
__path__ = ['extensions']  # point to folder

# Pre-register submodules so import doesn't 404 immediately
for _name in ['fetch','datastar','multiplayer']:
    sys.modules[f'extensions.{_name}'] = ModuleType(...)

# Then try real imports from folder (works when .nojekyll serves it)
try:
    from extensions.multiplayer import MultiplayerClient
except: pass