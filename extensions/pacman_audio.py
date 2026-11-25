# extensions/pacman_audio.py - Pac-Man procedural audio built ON TOP of proc_audio.py
# Without modifying proc_audio.py at all.
# EVENT-DRIVEN ONLY - No timeouts, no setTimeout, no polling counters.
# All timing via AudioContext.currentTime, completion via oscillator.onended event.
# Square-wave arcade voice, like the original Namco hardware, plus a
# faithful MML intro melody in the same style as extensions/8bit.py.
# Death is NOT MML: arcade death is a single WSG voice, 90 ticks / 1.5 s,
# two descending pitch sweeps with vibrato plus two low pops. It is
# built in PacManPlayer.play_death with continuous frequency ramps.
# Credit is NOT a jingle either: on the official soundtrack Credit Sound
# is a separate 0:01 track from Start Music (0:05, the opening jingle).
# Credit is one short waka burst - the same single-voice waka as eating
# a dot, a single articulation. It is built in
# PacManPlayer.play_credit -> play_waka, not from MML.
# Waka model (see WAKA_* below): one WSG voice, harmonic-rich ROM-like
# waveform, ~375 Hz fundamental. Wa/ka share the same base frequency
# and differ in shape/envelope, not in fundamental. Forum D+A / C#+G#
# pairs are UNVERIFIED, so they are NOT hardcoded. Clone 543/684 Hz
# triangle is clone tuning, NOT an arcade measurement, so it is NOT
# used as the fundamental. Looser 440 Hz / 500 Hz-1 kHz / 50-100 Hz
# modulation is low-rigor, so it is NOT used.
# Architecture mirrors extensions/8bit.py:
# - Built on top of proc_audio.py: imports AudioEngine and Patch but does not modify them
# - Uses Web Audio API directly for square-wave: oscillator.type = square
# - All oscillators scheduled via ctx.currentTime + offset, not setTimeout
# - Completion via onended event chain: last oscillator onended -> _clear_nodes -> on_complete
# - Siren loops by chaining onended -> schedule next loop chunk, never by timer
# - Waka, power, ghost eaten, death, fruit, extra life, level clear are events

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

BASE_SEMITONE = {'C': 0, 'D': 2, 'E': 4, 'F': 5, 'G': 7, 'A': 9, 'B': 11}
A4_N = 58
A4_FREQ = 440.0
DEFAULT_OCTAVE = 4
DEFAULT_TEMPO = 140
DEFAULT_LENGTH = 4
MODE_FACTORS = {'MN': 7 / 8, 'ML': 1.0, 'MS': 3 / 4}

# Arcade death sound, 90 ticks at 60 Hz = 1.5 s, WSG voice 2 only.
# Sweep 1: 0.00-0.65 s, 1000 -> 100 Hz, vibrato ~9 Hz.
# Sweep 2: 0.65-1.15 s, 700 -> 150 Hz, vibrato ~11 Hz.
# Tail: 1.15-1.50 s, two low pops, 0.08 s each, 0.12 s gap.
DEATH_TOTAL_S = 1.5
DEATH_SWEEP1_START = 1000.0
DEATH_SWEEP1_END = 100.0
DEATH_SWEEP1_DUR = 0.65
DEATH_SWEEP1_VIB_RATE = 9.0
DEATH_SWEEP1_VIB_DEPTH = 45.0
DEATH_SWEEP2_START = 700.0
DEATH_SWEEP2_END = 150.0
DEATH_SWEEP2_DUR = 0.50
DEATH_SWEEP2_VIB_RATE = 11.0
DEATH_SWEEP2_VIB_DEPTH = 35.0
DEATH_POP1_START = 1.15
DEATH_POP2_START = 1.35
DEATH_POP_DUR = 0.08
DEATH_POP_START_FREQ = 200.0
DEATH_POP_END_FREQ = 80.0

# Waka: one WSG voice, harmonic-rich waveform, ~375 Hz fundamental.
# Wa/ka share the same base frequency; they differ in envelope/shape,
# not in fundamental. Durations wa 85 ms + ka 60 ms = 145 ms total
# come from clone tuning (durations only, not its 543/684 Hz pitches).
# Forum wa-rises / ka-falls is UNVERIFIED, so the sweep is kept small
# (+12 / -12 Hz), NOT the forum D+A / C#+G# pairs. Clone 543/684 Hz
# and looser 440 Hz / 500 Hz-1 kHz figures are NOT used.
WAKA_FUNDAMENTAL = 375.0
WAKA_WA_DUR = 0.085
WAKA_KA_DUR = 0.060
WAKA_TOTAL = WAKA_WA_DUR + WAKA_KA_DUR
WAKA_ATTACK = 0.005
WAKA_WA_RISE = 12.0
WAKA_KA_FALL = -12.0
# Credit is one waka. Old names kept as aliases only.
CREDIT_WAKA_DUR = WAKA_TOTAL
CREDIT_WAKA_HI = WAKA_FUNDAMENTAL
CREDIT_WAKA_LO = WAKA_FUNDAMENTAL
CREDIT_WAKA_STEP = WAKA_WA_DUR

# Pac-Man intro melody in MML. Tempo and phrasing follow the arcade jingle.
# B B F# D# B F# D# C C G E C G E B B F# D# B F# D# D# E F F# G G# A B
PACMAN_MML = {
    "intro": "T150O5L8B B F# D# B F# D# C C G E C G E B B F# D# B F# D# D# E F F# G G# A B",
    "intro_short": "T150O5L8B B F# D# B F# D#",
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
    "intro_short": [PACMAN_MML["intro_short"]],
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
    "intro": "Pac-Man arcade intro jingle, square wave",
    "intro_short": "Intro first phrase only",
    "level_clear": "Level clear jingle",
    "extra_life": "Extra life jingle",
    "fruit": "Fruit spawn chime",
    "fruit_eaten": "Fruit eaten chime",
    "power": "Power pellet sweep",
    "ghost_eaten": "Ghost eaten ascending sweep",
    "death": "Death: two descending WSG sweeps with vibrato + two low pops, 1.5 s, 90 ticks",
    "credit": "Credit: one single-voice waka burst, 0.145 s, not a jingle",
    "waka": "Waka: one WSG voice, 375 Hz, wa 85 ms + ka 60 ms",
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
    def play_waka(self, on_complete=None):
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
            osc = ctx.createOscillator()
            gain = ctx.createGain()
            # Single WSG voice. Sawtooth = harmonic-rich, all harmonics
            # (odd + even), closer to the ROM wavetable than square
            # (odd only). One oscillator for the whole wa+ka burst.
            osc.type = "sawtooth"
            try:
                osc.frequency.setValueAtTime(WAKA_FUNDAMENTAL, t0)
            except Exception:
                try:
                    osc.frequency.value = WAKA_FUNDAMENTAL
                except Exception:
                    pass
            try:
                # Wa rises slightly, ka falls slightly. Small on purpose:
                # forum pairs are unverified, so no D+A / C#+G# here.
                osc.frequency.linearRampToValueAtTime(WAKA_FUNDAMENTAL + WAKA_WA_RISE, t0 + WAKA_WA_DUR)
            except Exception:
                pass
            try:
                osc.frequency.linearRampToValueAtTime(WAKA_FUNDAMENTAL + WAKA_WA_RISE + WAKA_KA_FALL, t0 + WAKA_TOTAL)
            except Exception:
                pass
            try:
                gain.gain.setValueAtTime(0.0001, t0)
                gain.gain.exponentialRampToValueAtTime(0.38, t0 + WAKA_ATTACK)
            except Exception:
                try:
                    gain.gain.value = 0.38
                except Exception:
                    pass
            try:
                # Dip at the wa/ka boundary articulates ka. Wa/ka share
                # the same base frequency; the boundary is envelope, not
                # a second voice or a pitch jump.
                gain.gain.setValueAtTime(0.38, t0 + WAKA_WA_DUR - 0.005)
                gain.gain.linearRampToValueAtTime(0.22, t0 + WAKA_WA_DUR)
                gain.gain.linearRampToValueAtTime(0.30, t0 + WAKA_WA_DUR + 0.01)
                gain.gain.linearRampToValueAtTime(0.0, t0 + WAKA_TOTAL)
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
    def play_credit(self, on_complete=None):
        # Credit is one waka, same single-voice burst as a dot.
        self.play_waka(on_complete=on_complete)
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
        # Waka is one single-voice burst (wa+ka inside it). No flip,
        # no alternate chirp, no two-voice alternation.
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
