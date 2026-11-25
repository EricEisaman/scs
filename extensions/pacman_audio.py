# extensions/pacman_audio.py - Pac-Man procedural audio built ON TOP of proc_audio.py
# Without modifying proc_audio.py at all.
# EVENT-DRIVEN ONLY - No timeouts, no setTimeout, no polling counters.
# All timing via AudioContext.currentTime, completion via oscillator.onended event.
# WSG wavetable voice, like the original Namco hardware: each voice is
# a 32-sample waveform, rendered as a PeriodicWave from its DFT spectrum,
# plus a faithful two-voice MML intro in the style of extensions/8bit.py.
# Architecture mirrors extensions/8bit.py:
# - Built on top of proc_audio.py: imports AudioEngine and Patch but does not modify them
# - Uses Web Audio API PeriodicWave: DFT of 32-sample WSG waveform ->
#   Fourier coeffs -> createPeriodicWave, per voice (lead / bass)
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

# ---- Namco WSG timbre: proper Fourier spectrum for both tracks ----
# The arcade chip is not a square-wave chip. It is a 3-voice wavetable chip:
# each voice steps through a 32-sample 4-bit waveform from PROM. The timbre
# of a voice is the Fourier spectrum of that waveform, not a square wave
# (square = odd harmonics only, 1, 0, 1/3, 0, 1/5 ...).
# Here both intro voices get their own 32-sample WSG-style waveform, and
# their Fourier spectra are computed from those waveforms by DFT, then
# used as Web Audio PeriodicWave coefficients. No spectrum is asserted
# by hand; it is derived from the waveform.
# Lead: triangle + saw blend. Triangle alone gives odd harmonics only,
# decaying as 1/n^2. Blending in a saw adds even harmonics, so the lead
# is reedy and bright: fundamental 1.0, 2nd 0.30, 3rd 0.22, 4th 0.16,
# then a slow tail. That is the lead cutting through, not a square.
# Bass: pure triangle, 1 cycle over 32 samples. Triangle gives odd
# harmonics only, decaying as 1/n^2: fundamental 1.0, 2nd 0.0,
# 3rd 0.11, 5th 0.04, 7th 0.02. Fundamental-dominant, warm, no harsh
# even harmonics, so it sits under the lead instead of masking it.
def _wsg_lead_wave():
    wave = []
    for n in range(32):
        if n < 16:
            tri = float(n)
        else:
            tri = float(31 - n)
        saw = n * 15.0 / 31.0
        wave.append((tri + saw) / 2.0)
    return wave

def _wsg_bass_wave():
    wave = []
    for n in range(32):
        if n < 16:
            wave.append(float(n))
        else:
            wave.append(float(31 - n))
    return wave

WSG_LEAD_WAVE = _wsg_lead_wave()
WSG_BASS_WAVE = _wsg_bass_wave()

def _wsg_fourier(wave32):
    # DFT of a 32-sample waveform -> PeriodicWave (real, imag) coefficients.
    # real[k] = cosine coeff a_k, imag[k] = sine coeff b_k, k = 0..16.
    # a_k = (2/N) sum x_n cos(2 pi k n / N), b_k = (2/N) sum x_n sin(...)
    # DC removed (real[0] = 0). Normalised so fundamental magnitude = 1.0,
    # so gain, not spectrum, sets loudness.
    n_count = len(wave32)
    mean = sum(wave32) / float(n_count)
    x = [v - mean for v in wave32]
    real = [0.0] * 17
    imag = [0.0] * 17
    for k in range(1, 17):
        a = 0.0
        b = 0.0
        for n in range(n_count):
            ang = 2.0 * math.pi * k * n / n_count
            a = a + x[n] * math.cos(ang)
            b = b + x[n] * math.sin(ang)
        real[k] = (2.0 / n_count) * a
        imag[k] = (2.0 / n_count) * b
    mag1 = math.sqrt(real[1] * real[1] + imag[1] * imag[1])
    if mag1 > 0:
        for k in range(1, 17):
            real[k] = real[k] / mag1
            imag[k] = imag[k] / mag1
    real[0] = 0.0
    imag[0] = 0.0
    return real, imag

WSG_LEAD_SPECTRUM = _wsg_fourier(WSG_LEAD_WAVE)
WSG_BASS_SPECTRUM = _wsg_fourier(WSG_BASS_WAVE)

def _assign_voice_offsets(events, voice, wave, gain):
    # Give a single-voice event list explicit start offsets (seconds)
    # and voice / wave / gain tags, so play_events can schedule it
    # polyphonically. Returns a new list, does not mutate the input.
    out = []
    t = 0.0
    for ev in events:
        e = dict(ev)
        e['start_offset_s'] = t
        e['voice'] = voice
        e['wave'] = wave
        e['gain'] = gain
        out.append(e)
        t = t + ev['total_duration'] / 1000.0
    return out

def _merge_intro_events(melody_events, bass_events):
    # Merge two voices with the same rhythm into one polyphonic list.
    # Both start at 0. Bass is tagged wave='bass', gain 0.34; melody is
    # wave='lead', gain 0.38, so bass is present but does not mask lead.
    mel = _assign_voice_offsets(melody_events, 'melody', 'lead', 0.38)
    bas = _assign_voice_offsets(bass_events, 'bass', 'bass', 0.34)
    merged = mel + bas
    merged.sort(key=lambda e: (e['start_offset_s'], 0 if e['voice'] == 'melody' else 1))
    return merged


# Pac-Man intro in MML, two WSG voices, same rhythm, 29 eighth notes each.
# Melody (lead, O5): B B F# D# B F# D# C C G E C G E B B F# D# B F# D# D# E F F# G G# A B
# Bass (O3, two octaves below melody): alternates root / fifth under each
# chord, then doubles the final chromatic climb in octaves, so the two
# voices converge on the final B. Phrase 1 B major: B F# B F# B F# B.
# Phrase 2 C major: C G C G C G C. Phrase 3 B major again. Phrase 4:
# D# E F F# G G# A B, exactly the melody an octave pair below.
PACMAN_MML = {
    "intro": "T150O5L8B B F# D# B F# D# C C G E C G E B B F# D# B F# D# D# E F F# G G# A B",
    "intro_melody": "T150O5L8B B F# D# B F# D# C C G E C G E B B F# D# B F# D# D# E F F# G G# A B",
    "intro_bass": "T150O3L8B F# B F# B F# B C G C G C G C B F# B F# B F# B D# E F F# G G# A B",
    "intro_short": "T150O5L8B B F# D# B F# D#",
    "intro_short_bass": "T150O3L8B F# B F# B F# B",
    "level_clear": "T150O5L8C E G C E G C",
    "extra_life": "T180O6L16C E G C E G C E G",
    "fruit": "T180O6L16E G C E",
    "fruit_eaten": "T180O6L16G E C",
    "power": "T120O4L16C D E F G A B C",
    "ghost_eaten": "T200O5L32C D E F G A B C D E F G",
    "death": "T120O4L8B A G F E D C B A G F E D C",
    "death_tail": "T120O3L16B A B A B",
    "waka1": "T220O6L64C B",
    "waka2": "T220O6L64B C",
    "siren_loop": "T120O3L8C C C C",
    "fright_loop": "T140O4L16C D C D C D C",
    "eyes_loop": "T200O6L32C D E F G",
    "ghost_revive": "T160O5L16C E G",
}

PACMAN_SOUNDS = {
    "intro": [PACMAN_MML["intro_melody"], PACMAN_MML["intro_bass"]],
    "intro_short": [PACMAN_MML["intro_short"], PACMAN_MML["intro_short_bass"]],
    "level_clear": [PACMAN_MML["level_clear"]],
    "extra_life": [PACMAN_MML["extra_life"]],
    "fruit": [PACMAN_MML["fruit"]],
    "fruit_eaten": [PACMAN_MML["fruit_eaten"]],
    "power": [PACMAN_MML["power"]],
    "ghost_eaten": [PACMAN_MML["ghost_eaten"]],
    "death": [PACMAN_MML["death"], PACMAN_MML["death_tail"]],
    "waka": [PACMAN_MML["waka1"]],
    "waka_alt": [PACMAN_MML["waka2"]],
    "siren": [PACMAN_MML["siren_loop"]],
    "fright": [PACMAN_MML["fright_loop"]],
    "eyes": [PACMAN_MML["eyes_loop"]],
    "ghost_revive": [PACMAN_MML["ghost_revive"]],
}

PACMAN_DESCRIPTIONS = {
    "intro": "Pac-Man arcade intro jingle, two WSG voices, lead + bass, PeriodicWave timbres",
    "intro_short": "Intro first phrase only, lead + bass",
    "level_clear": "Level clear jingle",
    "extra_life": "Extra life jingle",
    "fruit": "Fruit spawn chime",
    "fruit_eaten": "Fruit eaten chime",
    "power": "Power pellet sweep",
    "ghost_eaten": "Ghost eaten ascending sweep",
    "death": "Death descending wobble",
    "waka": "Waka pellet chirp variant 1",
    "waka_alt": "Waka pellet chirp variant 2",
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
        self._wave_lead = None
        self._wave_bass = None
        self._wave_lead_coeffs = None
        self._wave_bass_coeffs = None
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
    def _make_periodic_wave(self, wave32):
        # DFT -> PeriodicWave. real/imag are Fourier coeffs, DC = 0.
        real, imag = _wsg_fourier(wave32)
        try:
            if HAS_BROWSER and window is not None:
                try:
                    Float32Array = getattr(window, 'Float32Array', None)
                    if Float32Array is not None:
                        real_a = Float32Array.new(real)
                        imag_a = Float32Array.new(imag)
                    else:
                        real_a = real
                        imag_a = imag
                except Exception:
                    real_a = real
                    imag_a = imag
            else:
                real_a = real
                imag_a = imag
            try:
                return self.ctx.createPeriodicWave(real_a, imag_a, {'disableNormalization': True})
            except Exception:
                return self.ctx.createPeriodicWave(real_a, imag_a)
        except Exception:
            return None
    def _ensure_waves(self):
        if self.ctx is None:
            return
        if self._wave_lead is None:
            self._wave_lead_coeffs = _wsg_fourier(WSG_LEAD_WAVE)
            self._wave_lead = self._make_periodic_wave(WSG_LEAD_WAVE)
        if self._wave_bass is None:
            self._wave_bass_coeffs = _wsg_fourier(WSG_BASS_WAVE)
            self._wave_bass = self._make_periodic_wave(WSG_BASS_WAVE)
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
        self._ensure_waves()
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
        base = now + 0.02
        t = base
        last_osc = None
        last_stop_time = base
        played = 0
        for ev in events:
            total_s = ev['total_duration'] / 1000.0
            sound_s = ev['sound_duration'] / 1000.0
            if 'start_offset_s' in ev and ev['start_offset_s'] is not None:
                start = base + float(ev['start_offset_s'])
            else:
                start = t
                t = t + total_s
            if ev['freq'] > 0 and sound_s > 0.002:
                try:
                    osc = ctx.createOscillator()
                    gain = ctx.createGain()
                    wave_name = ev.get('wave', 'lead')
                    if wave_name == 'bass' and self._wave_bass is not None:
                        try:
                            osc.setPeriodicWave(self._wave_bass)
                        except Exception:
                            osc.type = "triangle"
                    elif self._wave_lead is not None:
                        try:
                            osc.setPeriodicWave(self._wave_lead)
                        except Exception:
                            osc.type = "square"
                    else:
                        osc.type = "square"
                    osc.frequency.value = ev['freq']
                    try:
                        gain.gain.value = float(ev.get('gain', 0.38))
                    except Exception:
                        gain.gain.value = 0.38
                    osc.connect(gain)
                    gain.connect(self.master_gain or ctx.destination)
                    osc.start(start)
                    osc.stop(start + sound_s)
                    self._active_nodes.append((osc, gain))
                    if start + sound_s >= last_stop_time:
                        last_osc = osc
                        last_stop_time = start + sound_s
                    played = played + 1
                except Exception:
                    pass
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
            if name in ('intro', 'intro_short') and len(mlist) == 2:
                mel = self.parser.parse(mlist[0], carry_state=False)
                bas = self.parser.parse(mlist[1], carry_state=False)
                evs = _merge_intro_events(mel, bas)
                self.presets[name] = {'mml': mlist, 'description': PACMAN_DESCRIPTIONS.get(name, ""), 'events': evs}
            else:
                raw = self.parser.parse_sequence(mlist)
                evs = _assign_voice_offsets(raw, 'melody', 'lead', 0.38)
                self.presets[name] = {'mml': mlist, 'description': PACMAN_DESCRIPTIONS.get(name, ""), 'events': evs}
    def resume(self):
        self.player.resume()
        if self.proc_engine:
            try:
                self.proc_engine.resume()
            except Exception:
                pass
    def play(self, sound_name, seed=None, spatial=False, position=None, on_complete=None):
        self.resume()
        # Waka alternates between two chirps, like the arcade
        if sound_name == 'waka':
            self._waka_flip = not self._waka_flip
            if self._waka_flip:
                sound_name = 'waka_alt'
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

__all__ = ['PacManMMLParser', 'PacManPlayer', 'PacManAudioEngine', 'PACMAN_MML', 'PACMAN_SOUNDS', 'PACMAN_DESCRIPTIONS', 'WSG_LEAD_WAVE', 'WSG_BASS_WAVE', 'WSG_LEAD_SPECTRUM', 'WSG_BASS_SPECTRUM', 'get_engine', 'play', 'play_mml', 'resume', 'HAS_PROC_AUDIO']
