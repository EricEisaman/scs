"""SCS Extensions - Well-designed Python APIs"""
try:
    from . import fetch
except: pass
try:
    from . import datastar
except: pass
try:
    from . import multiplayer
except: pass
# proc_audio - import last, don't break package if it fails
try:
    from . import proc_audio
except Exception as _e:
    # Don't break entire extensions package if proc_audio has error
    # print(f"proc_audio load failed: {_e}")
    pass
