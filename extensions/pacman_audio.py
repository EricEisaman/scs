# extensions/pacman_audio.py - Pac-Man procedural audio built ON TOP of proc_audio.py
# Without modifying proc_audio.py at all.
# EVENT-DRIVEN ONLY - No timeouts, no setTimeout, no polling counters.
# All timing via AudioContext.currentTime, completion via oscillator.onended event.
# Death is NOT MML: arcade death is a single WSG voice, 90 ticks / 1.5 s,
# two descending pitch sweeps with vibrato plus two low pops.
# Credit is NOT waka. Waka is NOT a chirp. Intro is NOT single-track.
# Credit: one WSG voice, fixed pitch, no sweep, short.
# Waka: one WSG voice, same wave, pitch sweeps up then down.
# Intro: two voices at once, melody + bass, same start, same duration.

# Build on top of proc_audio - do NOT modify it
try:
    from extensions.proc_audio import AudioEngine as ProcAudioEngine, Patch as ProcPatch
    HAS_PROC_AUDIO = True
except Exception:
    try:
        import extensions.proc_audio as _mod
        ProcAudioEngine = getattr(_mod, 'AudioEngine', None)
        ProcPatch = getattr(_mod, 'Patch', None)
        HAS_PROC_AUDIO = ProcAudioEngine is not None
    except Exception:
        HAS_PROC_AUDIO = False
        ProcAudioEngine = None
        ProcPatch = None

try:
    from browser import window
    HAS_BROWSER = True
except ImportError:
    HAS_BROWSER = False
    window = None

import math

# Core WSG voice: one PeriodicWave, harmonic-rich, imag = 1, 1/2, 1/3, ...
# Built once per context, cached in _wsg_wave. Not square, not sawtooth.
WSG_WAVE_IMAG = [0.0, 1.0, 0.5, 0.33, 0.25, 0.2, 0.16, 0.14]
# Waka: centre 375, sweep +/-75, symmetric. 300 -> 450 -> 300, 0.11 s.
# One smooth up-then-down sweep. Not two pitches, not a chirp.
WAKA_CENTRE = 375.0
WAKA_SWEEP = 75.0
WAKA_START = WAKA_CENTRE - WAKA_SWEEP
WAKA_PEAK = WAKA_CENTRE + WAKA_SWEEP
WAKA_END = WAKA_CENTRE - WAKA_SWEEP
WAKA_TOTAL = 0.11
WAKA_HALF = WAKA_TOTAL / 2.0
WAKA_ATTACK = 0.003
WAKA_GAIN = 0.35
# Credit: same WSG voice, fixed pitch, no sweep. Short, distinct.
# Fixed vs swept is what separates credit from waka.
CREDIT_FREQ = 1000.0
CREDIT_DUR = 0.08
CREDIT_GAIN = 0.30

BASE_SEMITONE = {'C': 0, 'D': 2, 'E': 4, 'F': 5, 'G': 7, 'A': 9, 'B': 11}
A4_N = 58
A4_FREQ = 440.0
DEFAULT_OCTAVE = 4
DEFAULT_TEMPO = 140
DEFAULT_LENGTH = 4
MODE_FACTORS = {'MN': 7 / 8, 'ML': 1.0, 'MS': 3 / 4}

# Pac-Man intro melody in MML. Tempo and phrasing follow the arcade jingle.
# B B F# D# B F# D# C C G E C G E B B F# D# B F# D# D# E F F# G G# A B
# Intro bass: 4 held roots (ML legato, L8). Phrase 1 B,
# phrase 2 C, phrase 3 B, phrase 4 B. 29 notes, ML = held,
# same total duration as melody, so both tracks end together.
INTRO_BASS_MML = "T150O2MLL8B B B B B B B C C C C C C C B B B B B B B B B B B B B B B"
INTRO_BASS_SHORT_MML = "T150O2MLL8B B B B B B B"
PACMAN_MML = {
    "intro": "T150O5L8B B F# D# B F# D# C C G E C G E B B F# D# B F# D# D# E F F# G G# A B",
    "intro_bass": INTRO_BASS_MML,
    "intro_short": "T150O5L8B B F# D# B F# D#",
    "intro_short_bass": INTRO_BASS_SHORT_MML,
    "level_clear": "T150O5L8C E G C E G C",
    "extra_life": "T180O6L16C E G C E G C E G",
    "fruit": "T180O6L16E G C E",
    "fruit_eaten": "T180O6L16G E C",
    "power": "T120O4L16C D E F G A B C",
    "ghost_eaten": "T200O5L32C D E F G A B C D E F G",
    "waka1": "T220O6L64C B",
    "waka2": "T220O6L64B C",
    "siren_loop": "T120O3L8C C C C",
    "fright_loop": "T140O4L16C D C D C D C",
    "eyes_loop": "T200O6L32C D E F G",
    "ghost_revive": "T160O5L16C E G",
}

PACMAN_SOUNDS = {
    "intro": [PACMAN_MML["intro"]],
    "intro_bass": [PACMAN_MML["intro_bass"]],
    "intro_short": [PACMAN_MML["intro_short"]],
    "intro_short_bass": [PACMAN_MML["intro_short_bass"]],
    "level_clear": [PACMAN_MML["level_clear"]],
    "extra_life": [PACMAN_MML["extra_life"]],
    "fruit": [PACMAN_MML["fruit"]],
    "fruit_eaten": [PACMAN_MML["fruit_eaten"]],
    "power": [PACMAN_MML["power"]],
    "ghost_eaten": [PACMAN_MML["ghost_eaten"]],
    "waka": [PACMAN_MML["waka1"]],
    "waka_alt": [PACMAN_MML["waka2"]],
    "siren": [PACMAN_MML["siren_loop"]],
    "fright": [PACMAN_MML["fright_loop"]],
    "eyes": [PACMAN_MML["eyes_loop"]],
    "ghost_revive": [PACMAN_MML["ghost_revive"]],
}

PACMAN_DESCRIPTIONS = {
    "intro": "Intro: higher synth melody + bass, two tracks at once",
    "intro_bass": "Intro bass track, root notes, low octave",
    "intro_short": "Intro first phrase only, melody + bass",
    "level_clear": "Level clear jingle",
    "extra_life": "Extra life jingle",
    "fruit": "Fruit spawn chime",
    "fruit_eaten": "Fruit eaten chime",
    "power": "Power pellet sweep",
    "ghost_eaten": "Ghost eaten ascending sweep",
    "death": "Death: two descending WSG sweeps with vibrato + two low pops, 1.5 s, 90 ticks",
    "credit": "Credit: one WSG voice, fixed pitch, no sweep",
    "waka": "Waka: one WSG voice, 300->450->300 Hz sweep, 0.11 s",
    "waka_alt": "Waka: same single-voice waka (no alternate chirp)",
    "siren": "Background siren loop chunk",
    "fright": "Fright mode loop chunk",
    "eyes": "Eyes returning loop chunk",
    "ghost_revive": "Ghost revive chime",
}

def _parse_int(s, idx):
    start = idx
    num = ""
    while idx < len(s) and s[idx].isdigit():
        num = num + s[idx]
        idx = idx + 1
    if num == "":
        return None, start
    return int(num), idx

def _parse_int_dot(s, idx):
    v, idx2 = _parse_int(s, idx)
    dot = False
    if idx2 < len(s) and s[idx2] == '.':
        dot = True
        idx2 = idx2 + 1
    return v, idx2, dot

def _parse_int_dot_optional(s, idx):
    if idx < len(s) and s[idx].isdigit():
        return _parse_int_dot(s, idx)
    dot = False
    if idx < len(s) and s[idx] == '.':
        dot = True
        idx = idx + 1
    return None, idx, dot

def calc_duration(length, dotted, tempo):
    if not length or length <= 0:
        length = DEFAULT_LENGTH
    whole = 240000.0 / tempo
    d = whole / length
    if dotted:
        d = d * 1.5
    return d

class PacManMMLParser:
    def __init__(self):
        self.reset()
    def reset(self):
        self.octave = DEFAULT_OCTAVE
        self.tempo = DEFAULT_TEMPO
        self.default_length = DEFAULT_LENGTH
        self.default_dotted = False
        self.mode_factor = MODE_FACTORS['MN']
        self.mode_name = 'MN'
        self.foreground = True
        return self
    def get_state(self):
        return {'octave': self.octave, 'tempo': self.tempo, 'default_length': self.default_length, 'default_dotted': self.default_dotted, 'mode_factor': self.mode_factor, 'mode_name': self.mode_name, 'foreground': self.foreground}
    def set_state(self, s):
        if not s:
            return
        self.octave = s.get('octave', DEFAULT_OCTAVE)
        self.tempo = s.get('tempo', DEFAULT_TEMPO)
        self.default_length = s.get('default_length', DEFAULT_LENGTH)
        self.default_dotted = s.get('default_dotted', False)
        self.mode_factor = s.get('mode_factor', MODE_FACTORS['MN'])
        self.mode_name = s.get('mode_name', 'MN')
        self.foreground = s.get('foreground', True)
    def parse(self, mml_str, carry_state=True):
        if not carry_state:
            self.reset()
        events = []
        i = 0
        s = mml_str
        while i < len(s):
            ch = s[i]
            if ch.isspace():
                i = i + 1
                continue
            up = ch.upper()
            if up == 'O':
                i = i + 1
                v, i = _parse_int(s, i)
                if v is not None:
                    self.octave = max(0, min(6, v))
                continue
            if ch == '>':
                self.octave = min(6, self.octave + 1)
                i = i + 1
                continue
            if ch == '<':
                self.octave = max(0, self.octave - 1)
                i = i + 1
                continue
            if up == 'T':
                i = i + 1
                v, i = _parse_int(s, i)
                if v is not None:
                    self.tempo = max(32, min(255, v))
                continue
            if up == 'L':
                i = i + 1
                v, i2, dot = _parse_int_dot(s, i)
                if v is not None:
                    self.default_length = v
                    self.default_dotted = dot
                i = i2
                continue
            if up == 'M':
                if i + 1 < len(s):
                    nxt = s[i + 1].upper()
                    if nxt == 'N':
                        self.mode_factor = MODE_FACTORS['MN']
                        self.mode_name = 'MN'
                        i = i + 2
                        continue
                    if nxt == 'L':
                        self.mode_factor = MODE_FACTORS['ML']
                        self.mode_name = 'ML'
                        i = i + 2
                        continue
                    if nxt == 'S':
                        self.mode_factor = MODE_FACTORS['MS']
                        self.mode_name = 'MS'
                        i = i + 2
                        continue
                    if nxt == 'F':
                        self.foreground = True
                        i = i + 2
                        continue
                    if nxt == 'B':
                        self.foreground = False
                        i = i + 2
                        continue
                i = i + 1
                continue
            if up == 'N':
                i = i + 1
                v, i2, dot = _parse_int_dot(s, i)
                i = i2
                if v is None:
                    continue
                if v == 0:
                    total = calc_duration(self.default_length, self.default_dotted or dot, self.tempo)
                    events.append({'freq': 0, 'total_duration': total, 'sound_duration': 0, 'rest_duration': total, 'type': 'rest', 'raw': 'N0', 'octave': self.octave, 'tempo': self.tempo, 'mode': self.mode_name, 'foreground': self.foreground})
                else:
                    freq = A4_FREQ * (2 ** ((v - A4_N) / 12))
                    is_dot = dot or self.default_dotted
                    total = calc_duration(self.default_length, is_dot, self.tempo)
                    events.append({'freq': freq, 'total_duration': total, 'sound_duration': total * self.mode_factor, 'rest_duration': total * (1 - self.mode_factor), 'type': 'note', 'raw': 'N', 'n': v, 'octave': self.octave, 'tempo': self.tempo, 'mode': self.mode_name, 'foreground': self.foreground})
                continue
            if up == 'P':
                i = i + 1
                v, i2, dot = _parse_int_dot(s, i)
                i = i2
                if v is None:
                    v = self.default_length
                    dot = self.default_dotted
                total = calc_duration(v, dot, self.tempo)
                events.append({'freq': 0, 'total_duration': total, 'sound_duration': 0, 'rest_duration': total, 'type': 'rest', 'raw': 'P', 'octave': self.octave, 'tempo': self.tempo, 'mode': self.mode_name, 'foreground': self.foreground})
                continue
            if up in 'ABCDEFG':
                note = up
                i = i + 1
                acc = None
                if i < len(s) and s[i] in '#+-':
                    acc = s[i]
                    i = i + 1
                v, i2, dot = _parse_int_dot_optional(s, i)
                i = i2
                if v is None:
                    eff_len = self.default_length
                    eff_dot = dot or self.default_dotted
                else:
                    eff_len = v
                    eff_dot = dot
                base = BASE_SEMITONE[note]
                if acc == '#' or acc == '+':
                    base = base + 1
                elif acc == '-':
                    base = base - 1
                octv = self.octave
                if base < 0:
                    base = base + 12
                    octv = octv - 1
                if base >= 12:
                    base = base - 12
                    octv = octv + 1
                octv = max(0, min(6, octv))
                note_val = octv * 12 + base
                freq = A4_FREQ * (2 ** ((note_val - 57) / 12))
                total = calc_duration(eff_len, eff_dot, self.tempo)
                events.append({'freq': freq, 'total_duration': total, 'sound_duration': total * self.mode_factor, 'rest_duration': total * (1 - self.mode_factor), 'type': 'note', 'raw': note, 'letter': note, 'accidental': acc, 'octave': octv, 'length': eff_len, 'dotted': eff_dot, 'tempo': self.tempo, 'mode': self.mode_name, 'foreground': self.foreground})
                continue
            i = i + 1
        return events
    def parse_with_state(self, mml_str, state=None):
        if state is not None:
            self.set_state(state)
        ev = self.parse(mml_str, carry_state=True)
        return ev, self.get_state()
    def parse_sequence(self, mml_list):
        self.reset()
        all_ev = []
        for m in mml_list:
            all_ev.extend(self.parse(m, carry_state=True))
        return all_ev

class PacManPlayer:
    def __init__(self, quality="high"):
        self.ctx = None
        self.master_gain = None
        self.quality = quality
        self._active_nodes = []
        self._on_complete = None
        self._wsg_wave_cached = None
        self._init_context()
    def _init_context(self):
        if HAS_BROWSER:
            try:
                AudioContext = getattr(window, 'AudioContext', None)
                if AudioContext is None:
                    AudioContext = getattr(window, 'webkitAudioContext', None)
                if AudioContext is not None:
                    self.ctx = AudioContext.new()
                    self.master_gain = self.ctx.createGain()
                    self.master_gain.gain.value = 0.28
                    self.master_gain.connect(self.ctx.destination)
            except Exception:
                self.ctx = None
    def _ensure(self):
        if self.ctx is None:
            self._init_context()
        return self.ctx is not None
    def resume(self):
        if self.ctx:
            try:
                state = getattr(self.ctx, 'state', 'running')
                if state == "suspended":
                    self.ctx.resume()
            except Exception:
                pass
    def _clear_nodes(self, event=None):
        self._active_nodes = []
        cb = self._on_complete
        self._on_complete = None
        if cb:
            try:
                cb(event)
            except Exception:
                pass
    def play_events(self, events, on_complete=None):
        if not self._ensure():
            if on_complete:
                try:
                    on_complete(None)
                except Exception:
                    pass
            return
        self.resume()
        ctx = self.ctx
        try:
            for osc, gain in self._active_nodes:
                try:
                    osc.stop()
                except Exception:
                    pass
        except Exception:
            pass
        self._active_nodes = []
        self._on_complete = on_complete
        try:
            now = ctx.currentTime
        except Exception:
            now = 0
        t = now + 0.02
        last_osc = None
        last_stop_time = t
        played = 0
        for ev in events:
            total_s = ev['total_duration'] / 1000.0
            sound_s = ev['sound_duration'] / 1000.0
            if ev['freq'] > 0 and sound_s > 0.002:
                try:
                    osc = ctx.createOscillator()
                    gain = ctx.createGain()
                    osc.type = "square"
                    osc.frequency.value = ev['freq']
                    gain.gain.value = 0.38
                    osc.connect(gain)
                    gain.connect(self.master_gain or ctx.destination)
                    osc.start(t)
                    osc.stop(t + sound_s)
                    self._active_nodes.append((osc, gain))
                    last_osc = osc
                    last_stop_time = t + sound_s
                    played = played + 1
                except Exception:
                    pass
            t = t + total_s
        if last_osc is not None:
            try:
                def on_ended(evt):
                    self._clear_nodes(evt)
                try:
                    last_osc.onended = on_ended
                except Exception:
                    pass
                try:
                    last_osc.addEventListener("ended", on_ended)
                except Exception:
                    pass
            except Exception:
                pass
        else:
            try:
                dummy = ctx.createOscillator()
                def on_dummy_end(e):
                    self._clear_nodes(e)
                try:
                    dummy.onended = on_dummy_end
                except Exception:
                    pass
                try:
                    dummy.addEventListener("ended", on_dummy_end)
                except Exception:
                    pass
                dummy.start(last_stop_time)
                dummy.stop(last_stop_time + 0.02)
                self._active_nodes.append((dummy, None))
            except Exception:
                self._clear_nodes(None)
    def _death_sweep(self, ctx, t0, dur, start_freq, end_freq, vib_rate, vib_depth):
        osc = ctx.createOscillator()
        gain = ctx.createGain()
        osc.type = "square"
        try:
            osc.frequency.setValueAtTime(start_freq, t0)
        except Exception:
            try:
                osc.frequency.value = start_freq
            except Exception:
                pass
        try:
            osc.frequency.exponentialRampToValueAtTime(end_freq, t0 + dur)
        except Exception:
            pass
        try:
            gain.gain.setValueAtTime(0.38, t0)
            gain.gain.setValueAtTime(0.38, t0 + dur - 0.01)
            gain.gain.linearRampToValueAtTime(0.0, t0 + dur)
        except Exception:
            try:
                gain.gain.value = 0.38
            except Exception:
                pass
        lfo = None
        lfo_gain = None
        try:
            lfo = ctx.createOscillator()
            lfo_gain = ctx.createGain()
            lfo.type = "sine"
            try:
                lfo.frequency.value = vib_rate
            except Exception:
                pass
            try:
                lfo_gain.gain.value = vib_depth
            except Exception:
                pass
            lfo.connect(lfo_gain)
            lfo_gain.connect(osc.frequency)
        except Exception:
            lfo = None
            lfo_gain = None
        osc.connect(gain)
        gain.connect(self.master_gain or ctx.destination)
        osc.start(t0)
        osc.stop(t0 + dur)
        if lfo is not None:
            try:
                lfo.start(t0)
                lfo.stop(t0 + dur)
            except Exception:
                pass
        self._active_nodes.append((osc, gain))
        if lfo is not None:
            self._active_nodes.append((lfo, lfo_gain))
        return osc
    def _death_pop(self, ctx, t0, dur, start_freq, end_freq):
        osc = ctx.createOscillator()
        gain = ctx.createGain()
        osc.type = "square"
        try:
            osc.frequency.setValueAtTime(start_freq, t0)
        except Exception:
            try:
                osc.frequency.value = start_freq
            except Exception:
                pass
        try:
            osc.frequency.exponentialRampToValueAtTime(end_freq, t0 + dur)
        except Exception:
            pass
        try:
            gain.gain.setValueAtTime(0.0001, t0)
            gain.gain.exponentialRampToValueAtTime(0.38, t0 + 0.01)
            gain.gain.exponentialRampToValueAtTime(0.0001, t0 + dur)
        except Exception:
            try:
                gain.gain.value = 0.38
            except Exception:
                pass
        osc.connect(gain)
        gain.connect(self.master_gain or ctx.destination)
        osc.start(t0)
        osc.stop(t0 + dur)
        self._active_nodes.append((osc, gain))
        return osc
    def play_death(self, on_complete=None):
        if not self._ensure():
            if on_complete:
                try:
                    on_complete(None)
                except Exception:
                    pass
            return
        self.resume()
        ctx = self.ctx
        try:
            for osc, gain in self._active_nodes:
                try:
                    osc.stop()
                except Exception:
                    pass
        except Exception:
            pass
        self._active_nodes = []
        self._on_complete = on_complete
        try:
            now = ctx.currentTime
        except Exception:
            now = 0
        t0 = now + 0.02
        last_osc = None
        try:
            self._death_sweep(ctx, t0, DEATH_SWEEP1_DUR, DEATH_SWEEP1_START, DEATH_SWEEP1_END, DEATH_SWEEP1_VIB_RATE, DEATH_SWEEP1_VIB_DEPTH)
            self._death_sweep(ctx, t0 + DEATH_SWEEP1_DUR, DEATH_SWEEP2_DUR, DEATH_SWEEP2_START, DEATH_SWEEP2_END, DEATH_SWEEP2_VIB_RATE, DEATH_SWEEP2_VIB_DEPTH)
            self._death_pop(ctx, t0 + DEATH_POP1_START, DEATH_POP_DUR, DEATH_POP_START_FREQ, DEATH_POP_END_FREQ)
            last_osc = self._death_pop(ctx, t0 + DEATH_POP2_START, DEATH_POP_DUR, DEATH_POP_START_FREQ, DEATH_POP_END_FREQ)
        except Exception:
            last_osc = None
        if last_osc is not None:
            try:
                def on_ended(evt):
                    self._clear_nodes(evt)
                try:
                    last_osc.onended = on_ended
                except Exception:
                    pass
                try:
                    last_osc.addEventListener("ended", on_ended)
                except Exception:
                    pass
            except Exception:
                pass
        else:
            self._clear_nodes(None)
    def _wsg_wave(self, ctx):
        # Core WSG voice, built once, cached. Not square, not sawtooth.
        if getattr(self, '_wsg_wave_cached', None) is not None:
            return self._wsg_wave_cached
        try:
            create = getattr(ctx, 'createPeriodicWave', None)
            if create is None:
                return None
            real = [0.0] * len(WSG_WAVE_IMAG)
            wave = create(real, list(WSG_WAVE_IMAG))
            self._wsg_wave_cached = wave
            return wave
        except Exception:
            return None
    def _schedule_track(self, ctx, events, waveform, gain_val, t0):
        # Schedule one track at t0. Returns last oscillator + last stop time.
        # Does NOT stop other tracks. Used by intro (melody + bass together).
        last_osc = None
        last_stop = t0
        tt = t0
        for ev in events:
            total_s = ev['total_duration'] / 1000.0
            sound_s = ev['sound_duration'] / 1000.0
            if ev['freq'] > 0 and sound_s > 0.002:
                try:
                    osc = ctx.createOscillator()
                    gain = ctx.createGain()
                    if waveform == 'periodic':
                        wave = self._wsg_wave(ctx)
                        if wave is not None:
                            try:
                                osc.setPeriodicWave(wave)
                            except Exception:
                                osc.type = "square"
                        else:
                            osc.type = "square"
                    else:
                        osc.type = waveform
                    osc.frequency.value = ev['freq']
                    gain.gain.value = gain_val
                    osc.connect(gain)
                    gain.connect(self.master_gain or ctx.destination)
                    osc.start(tt)
                    osc.stop(tt + sound_s)
                    self._active_nodes.append((osc, gain))
                    last_osc = osc
                    last_stop = tt + sound_s
                except Exception:
                    pass
            tt = tt + total_s
        return last_osc, last_stop
    def play_intro(self, on_complete=None, short=False):
        # Two tracks at once: higher synth melody + bass. Same t0, same
        # tempo, same total duration. Melody is square, brighter and
        # louder. Bass is triangle, lower octave, softer.
        if not self._ensure():
            if on_complete:
                try:
                    on_complete(None)
                except Exception:
                    pass
            return
        self.resume()
        ctx = self.ctx
        try:
            for osc, gain in self._active_nodes:
                try:
                    osc.stop()
                except Exception:
                    pass
        except Exception:
            pass
        self._active_nodes = []
        self._on_complete = on_complete
        try:
            now = ctx.currentTime
        except Exception:
            now = 0
        t0 = now + 0.02
        _parser = PacManMMLParser()
        if short:
            mel = _parser.parse(PACMAN_MML["intro_short"], carry_state=False)
            bass = _parser.parse(PACMAN_MML["intro_short_bass"], carry_state=False)
        else:
            mel = _parser.parse(PACMAN_MML["intro"], carry_state=False)
            bass = _parser.parse(PACMAN_MML["intro_bass"], carry_state=False)
        last_mel, _ = self._schedule_track(ctx, mel, "square", 0.30, t0)
        last_bass, _ = self._schedule_track(ctx, bass, "triangle", 0.26, t0)
        last_osc = last_mel if last_mel is not None else last_bass
        if last_osc is not None:
            try:
                def on_ended(evt):
                    self._clear_nodes(evt)
                try:
                    last_osc.onended = on_ended
                except Exception:
                    pass
                try:
                    last_osc.addEventListener("ended", on_ended)
                except Exception:
                    pass
            except Exception:
                pass
        else:
            self._clear_nodes(None)
    def play_waka(self, on_complete=None):
        # One WSG voice, wave 3, one smooth up-then-down sweep.
        # Not a chirp: no two discrete pitches, no alternation.
        # Does NOT stop other tracks: waka overlaps siren / intro.
        if not self._ensure():
            if on_complete:
                try:
                    on_complete(None)
                except Exception:
                    pass
            return
        self.resume()
        ctx = self.ctx
        try:
            now = ctx.currentTime
        except Exception:
            now = 0
        t0 = now + 0.02
        try:
            osc = ctx.createOscillator()
            gain = ctx.createGain()
            wave = self._wsg_wave(ctx)
            if wave is not None:
                try:
                    osc.setPeriodicWave(wave)
                except Exception:
                    osc.type = "square"
            else:
                osc.type = "square"
            try:
                osc.frequency.setValueAtTime(WAKA_START, t0)
                osc.frequency.linearRampToValueAtTime(WAKA_PEAK, t0 + WAKA_HALF)
                osc.frequency.linearRampToValueAtTime(WAKA_END, t0 + WAKA_TOTAL)
            except Exception:
                try:
                    osc.frequency.value = WAKA_CENTRE
                except Exception:
                    pass
            try:
                gain.gain.setValueAtTime(0.0001, t0)
                gain.gain.exponentialRampToValueAtTime(WAKA_GAIN, t0 + WAKA_ATTACK)
                gain.gain.exponentialRampToValueAtTime(0.0001, t0 + WAKA_TOTAL)
            except Exception:
                try:
                    gain.gain.value = WAKA_GAIN
                except Exception:
                    pass
            osc.connect(gain)
            gain.connect(self.master_gain or ctx.destination)
            osc.start(t0)
            osc.stop(t0 + WAKA_TOTAL)
            self._active_nodes.append((osc, gain))
            last_osc = osc
        except Exception:
            last_osc = None
        if last_osc is not None:
            try:
                def on_ended(evt, _o=last_osc):
                    try:
                        self._active_nodes = [n for n in self._active_nodes if n[0] is not _o]
                    except Exception:
                        pass
                    if on_complete:
                        try:
                            on_complete(evt)
                        except Exception:
                            pass
                try:
                    last_osc.onended = on_ended
                except Exception:
                    pass
                try:
                    last_osc.addEventListener("ended", on_ended)
                except Exception:
                    pass
            except Exception:
                pass
    def play_credit(self, on_complete=None):
        # Core: same WSG voice as waka, fixed pitch, no sweep.
        # One oscillator, one envelope. Distinct from waka by fixed vs swept.
        if not self._ensure():
            if on_complete:
                try:
                    on_complete(None)
                except Exception:
                    pass
            return
        self.resume()
        ctx = self.ctx
        try:
            now = ctx.currentTime
        except Exception:
            now = 0
        t0 = now + 0.02
        last_osc = None
        try:
            osc = ctx.createOscillator()
            gain = ctx.createGain()
            wave = self._wsg_wave(ctx)
            if wave is not None:
                try:
                    osc.setPeriodicWave(wave)
                except Exception:
                    osc.type = "square"
            else:
                osc.type = "square"
            try:
                osc.frequency.value = CREDIT_FREQ
            except Exception:
                pass
            try:
                gain.gain.setValueAtTime(0.0001, t0)
                gain.gain.exponentialRampToValueAtTime(CREDIT_GAIN, t0 + 0.005)
                gain.gain.exponentialRampToValueAtTime(0.0001, t0 + CREDIT_DUR)
            except Exception:
                try:
                    gain.gain.value = CREDIT_GAIN
                except Exception:
                    pass
            osc.connect(gain)
            gain.connect(self.master_gain or ctx.destination)
            osc.start(t0)
            osc.stop(t0 + CREDIT_DUR)
            self._active_nodes.append((osc, gain))
            last_osc = osc
        except Exception:
            last_osc = None
        if last_osc is not None:
            try:
                def on_ended(evt, _o=last_osc):
                    try:
                        self._active_nodes = [n for n in self._active_nodes if n[0] is not _o]
                    except Exception:
                        pass
                    if on_complete:
                        try:
                            on_complete(evt)
                        except Exception:
                            pass
                try:
                    last_osc.onended = on_ended
                except Exception:
                    pass
                try:
                    last_osc.addEventListener("ended", on_ended)
                except Exception:
                    pass
            except Exception:
                pass
    def play_mml(self, mml_str, parser=None, on_complete=None):
        if parser is None:
            parser = PacManMMLParser()
        ev = parser.parse(mml_str, carry_state=False)
        self.play_events(ev, on_complete=on_complete)
        return ev
    def play_mml_sequence(self, mml_list, parser=None, on_complete=None):
        if parser is None:
            parser = PacManMMLParser()
            parser.reset()
            evs = []
            for m in mml_list:
                evs.extend(parser.parse(m, carry_state=True))
        else:
            evs = parser.parse_sequence(mml_list)
        self.play_events(evs, on_complete=on_complete)
        return evs
    def stop_all(self):
        for osc, gain in self._active_nodes:
            try:
                osc.stop()
            except Exception:
                pass
        self._active_nodes = []
        self._on_complete = None

class PacManAudioEngine:
    def __init__(self, proc_engine=None, quality="high", seed=1):
        self.parser = PacManMMLParser()
        self.player = PacManPlayer(quality=quality)
        self.proc_engine = proc_engine
        if self.proc_engine is None and HAS_PROC_AUDIO and ProcAudioEngine:
            try:
                self.proc_engine = ProcAudioEngine(quality=quality, seed=seed)
            except Exception:
                self.proc_engine = None
        self.presets = {}
        self._waka_flip = False
        self._siren_on = False
        self._siren_mode = 'siren'
        self._register()
    def _register(self):
        for name, mlist in PACMAN_SOUNDS.items():
            self.presets[name] = {'mml': mlist, 'description': PACMAN_DESCRIPTIONS.get(name, ""), 'events': self.parser.parse_sequence(mlist)}
        self.presets['death'] = {'mml': [], 'description': PACMAN_DESCRIPTIONS.get('death', ""), 'events': [], 'sweep': True}
        self.presets['credit'] = {'mml': [], 'description': PACMAN_DESCRIPTIONS.get('credit', ""), 'events': [], 'waka': True}
        # Waka is a custom single-voice WSG burst, not MML. waka1/waka2
        # MML entries above are legacy only and are not played.
        self.presets['waka'] = {'mml': [], 'description': PACMAN_DESCRIPTIONS.get('waka', ""), 'events': [], 'waka': True}
        self.presets['waka_alt'] = {'mml': [], 'description': PACMAN_DESCRIPTIONS.get('waka_alt', ""), 'events': [], 'waka': True}
    def resume(self):
        self.player.resume()
        if self.proc_engine:
            try:
                self.proc_engine.resume()
            except Exception:
                pass
    def play(self, sound_name, seed=None, spatial=False, position=None, on_complete=None):
        self.resume()
        if sound_name == 'death':
            self.player.play_death(on_complete=on_complete)
            return self.presets.get('death')
        if sound_name == 'credit':
            self.player.play_credit(on_complete=on_complete)
            return self.presets.get('credit')
        if sound_name == 'intro':
            self.player.play_intro(on_complete=on_complete, short=False)
            return self.presets.get('intro')
        if sound_name == 'intro_short':
            self.player.play_intro(on_complete=on_complete, short=True)
            return self.presets.get('intro_short')
        # Waka is one single-voice WSG sweep (wa=up, ka=down inside it).
        # No flip, no alternate chirp, no two-voice alternation.
        if sound_name in ('waka', 'waka_alt'):
            self.player.play_waka(on_complete=on_complete)
            return self.presets.get('waka')
        if sound_name in self.presets:
            preset = self.presets[sound_name]
            self.player.play_events(preset['events'], on_complete=on_complete)
            return preset
        if isinstance(sound_name, str) and any(c in sound_name.upper() for c in ['O', 'L', 'T', 'M', 'N', 'P', 'A', 'B', 'C', 'D', 'E', 'F', 'G']):
            ev = self.parser.parse(sound_name, carry_state=False)
            self.player.play_events(ev, on_complete=on_complete)
            return {'mml': sound_name, 'events': ev}
        if self.proc_engine:
            try:
                return self.proc_engine.play(sound_name, seed=seed, spatial=spatial, position=position)
            except Exception:
                pass
        return None
    def play_mml(self, mml, on_complete=None):
        self.resume()
        return self.player.play_mml(mml, parser=self.parser, on_complete=on_complete)
    def play_sequence(self, mlist, on_complete=None):
        self.resume()
        return self.player.play_mml_sequence(mlist, parser=self.parser, on_complete=on_complete)
    def get_events(self, name):
        if name in self.presets:
            return self.presets[name]['events']
        return self.parser.parse(name, carry_state=False)
    def get_all_presets(self):
        return self.presets
    def start_siren(self, mode='siren'):
        # Event-driven loop: each chunk ends via onended, then schedules the next chunk
        self._siren_on = True
        self._siren_mode = mode
        self._siren_chunk(None)
    def _siren_chunk(self, evt):
        if not self._siren_on:
            return
        preset = self.presets.get(self._siren_mode, self.presets['siren'])
        # Chain next chunk on completion, no timer
        self.player.play_events(preset['events'], on_complete=self._siren_chunk)
    def stop_siren(self):
        self._siren_on = False
        self.player.stop_all()
    def create_patch_for_mml(self, mml_str, patch_name="pacman_square"):
        ev = self.parser.parse(mml_str, carry_state=False)
        if not HAS_PROC_AUDIO or ProcPatch is None:
            return {'name': patch_name, 'type': 'pacman_square', 'waveform': 'square', 'events': ev, 'mml': mml_str}
        try:
            patch = ProcPatch()
            if hasattr(patch, 'oscillator'):
                patch = patch.oscillator(type='square', frequency=440)
            if hasattr(patch, 'envelope'):
                patch = patch.envelope(attack=0.001, decay=0, sustain=1, release=0.01)
            if hasattr(patch, 'tag'):
                patch = patch.tag('pacman').tag('8bit').tag('square')
            if hasattr(patch, 'meta'):
                patch = patch.meta(mml=mml_str)
            return patch
        except Exception as e:
            return {'name': patch_name, 'mml': mml_str, 'events': ev, 'error': str(e)}

_default_engine = None
def get_engine():
    global _default_engine
    if _default_engine is None:
        _default_engine = PacManAudioEngine()
    return _default_engine

def play(name, on_complete=None):
    return get_engine().play(name, on_complete=on_complete)

def play_mml(mml_str, on_complete=None):
    return get_engine().play_mml(mml_str, on_complete=on_complete)

def resume():
    return get_engine().resume()

__all__ = ['PacManMMLParser', 'PacManPlayer', 'PacManAudioEngine', 'PACMAN_MML', 'PACMAN_SOUNDS', 'PACMAN_DESCRIPTIONS', 'get_engine', 'play', 'play_mml', 'resume', 'HAS_PROC_AUDIO']
