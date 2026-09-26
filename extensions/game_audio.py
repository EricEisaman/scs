"""Small, optional procedural-audio adapter for SCS game demos."""

try:
    from extensions.proc_audio import AudioEngine
except Exception:
    AudioEngine = None


def initialize_game_audio(app, seed=0):
    app.audio_engine = None
    app.audio_unlocked = False
    app.audio_sequence = 0
    if not AudioEngine:
        return False
    try:
        app.audio_engine = AudioEngine(
            quality="medium",
            seed=seed,
            master_db=-8,
            category_levels={"sfx": -6, "ui": -8, "ambience": -18},
        )
        return True
    except Exception as ex:
        print(f"[AUDIO] Procedural audio unavailable: {ex}")
        return False


def unlock_game_audio(app):
    engine = getattr(app, "audio_engine", None)
    if not engine or app.audio_unlocked:
        return bool(app.audio_unlocked)
    try:
        app.audio_unlocked = bool(engine.resume())
    except Exception as ex:
        print(f"[AUDIO] Could not unlock audio: {ex}")
        app.audio_unlocked = False
    return app.audio_unlocked


def _event_seed(event_id):
    value = 2166136261
    for char in str(event_id):
        value = ((value ^ ord(char)) * 16777619) & 0x7FFFFFFF
    return value


def play_game_sound(app, preset, event_id):
    engine = getattr(app, "audio_engine", None)
    if not engine or not app.audio_unlocked:
        return False
    try:
        app.audio_sequence += 1
        seed = _event_seed(event_id if event_id else app.audio_sequence)
        return bool(engine.play(preset, seed=seed))
    except Exception as ex:
        print(f"[AUDIO] Could not play {preset}: {ex}")
        return False


def game_audio_status(app):
    if not getattr(app, "audio_engine", None):
        return "SFX UNAVAILABLE"
    return "SFX READY" if app.audio_unlocked else "PRESS KEY FOR SFX"