"""
proc_audio_tetrio.py — TETR.IO kinetic soundscape extension
Built ON TOP of proc_audio.py 1662-line core — does not modify core

Design per spec:
- Arcade kinetic: actions punctuate achievements, forceful + musical, momentum from sustained play
- B2B escalating cues, thunder impact for powerful attacks
- Garbage audible cues, clutch, surge changing with streak = audible conversation of pressure
- BGM varies by mode: TETRA LEAGUE menu/battle/victory/defeat distinct, Quick Play Zenith floor adaptive
- Watchful Eye fades instruments in/out, adds drums while spectating, skips bars on fast climb
- Pitch matches floor key
"""

from browser import window
import random
import math

# Fix import order to avoid 404s in SCS/Brython — extensions path first
try:
    from extensions.proc_audio import Patch, AudioEngine, sfx as base_sfx, SeededRandom, Bus, db_to_linear
except:
    try:
        from proc_audio import Patch, AudioEngine, sfx as base_sfx, SeededRandom, Bus, db_to_linear
    except:
        from .proc_audio import Patch, AudioEngine, sfx as base_sfx, SeededRandom, Bus, db_to_linear

# ---------- TETR.IO SFX Presets — kinetic, musical, consequential ----------

def _make_move():
    # 0.06s tick, sine 1200, very short, like TETR.IO move
    p = Patch(id="tetr.move", category="sfx", duration=0.06, polyphony=32)
    p.tags = ["tetr","move","tick"]
    p.meta = {"name":"TETR Move Tick","loudness_db":-18}
    p.graph = [
        {"id":"osc","type":"oscillator","wave":"sine","frequency":1200},
        {"id":"amp","type":"adsr","attack":0.001,"decay":0.04,"sustain":0,"release":0.02}
    ]
    p.routing = [["osc","amp"],["amp","bus:sfx"]]
    p.randomization = {"pitch_semitones":[-0.2,0.2],"pan":[-0.1,0.1]}
    return p

def _make_rotate():
    # 0.14s chirp 440->660 exp, sine, musical
    p = Patch(id="tetr.rotate", category="sfx", duration=0.14, polyphony=24)
    p.graph = [
        {"id":"osc","type":"oscillator","wave":"sine","frequency":440},
        {"id":"pitch","type":"param_envelope","target":"osc.frequency","points":[[0,440,"exp"],[0.12,660,"exp"]]},
        {"id":"filter","type":"biquad","mode":"lowpass","frequency":3200,"q":0.7},
        {"id":"amp","type":"adsr","attack":0.002,"decay":0.08,"sustain":0,"release":0.04}
    ]
    p.routing = [["osc","filter"],["filter","amp"],["amp","bus:sfx"]]
    p.randomization = {"pitch_semitones":[-0.3,0.3]}
    return p

def _make_hold():
    # 0.28s coin-like: 880+1320 dual sine, positive
    p = Patch(id="tetr.hold", category="ui", duration=0.28, polyphony=16)
    p.graph = [
        {"id":"osc","type":"oscillator","wave":"sine","frequency":880},
        {"id":"osc2","type":"oscillator","wave":"sine","frequency":1320},
        {"id":"filter","type":"biquad","mode":"lowpass","frequency":4000,"q":0.8},
        {"id":"amp","type":"adsr","attack":0.005,"decay":0.18,"sustain":0,"release":0.08}
    ]
    p.routing = [["osc","filter"],["osc2","filter"],["filter","amp"],["amp","bus:ui"]]
    return p

def _make_harddrop():
    # 0.12s thud: sine 80 + brown noise burst + lowpass
    p = Patch(id="tetr.harddrop", category="sfx", duration=0.12, polyphony=20)
    p.graph = [
        {"id":"osc","type":"oscillator","wave":"sine","frequency":80},
        {"id":"noise","type":"noise","kind":"brown"},
        {"id":"filter","type":"biquad","mode":"lowpass","frequency":600,"q":1.2},
        {"id":"amp","type":"adsr","attack":0.001,"decay":0.08,"sustain":0,"release":0.04}
    ]
    p.routing = [["osc","filter"],["noise","filter"],["filter","amp"],["amp","bus:sfx"]]
    return p

def _make_lock():
    p = Patch(id="tetr.lock", category="sfx", duration=0.09, polyphony=24)
    p.graph = [
        {"id":"noise","type":"noise","kind":"white"},
        {"id":"filter","type":"biquad","mode":"bandpass","frequency":900,"q":1.4},
        {"id":"amp","type":"adsr","attack":0.001,"decay":0.05,"sustain":0,"release":0.03}
    ]
    p.routing = [["noise","filter"],["filter","amp"],["amp","bus:sfx"]]
    return p

def _make_clear(level):
    # level 1-4, increasingly consequential, musical
    # Clear1: 261Hz (C4) sine 0.22s, Clear2: 329Hz (E4), Clear3: 392Hz (G4), Clear4: 523Hz (C5) + thunder
    freqs = {1:261, 2:329, 3:392, 4:523}
    base = freqs.get(level, 261)
    if level < 4:
        p = Patch(id=f"tetr.clear{level}", category="sfx", duration=0.22 + level*0.06, polyphony=16)
        # Musical triad: root + fifth
        p.graph = [
            {"id":"osc","type":"oscillator","wave":"sine","frequency":base},
            {"id":"osc2","type":"oscillator","wave":"sine","frequency":base*1.5},
            {"id":"filter","type":"biquad","mode":"lowpass","frequency":2800 + level*400,"q":0.8},
            {"id":"amp","type":"adsr","attack":0.005,"decay":0.12+level*0.02,"sustain":0,"release":0.08}
        ]
        p.routing = [["osc","filter"],["osc2","filter"],["filter","amp"],["amp","bus:sfx"]]
        p.randomization = {"pitch_semitones":[-0.15,0.15]}
        return p
    else:
        # Clear4 thunder impact — forceful
        p = Patch(id="tetr.clear4", category="sfx", duration=0.55, polyphony=8)
        p.graph = [
            {"id":"osc","type":"oscillator","wave":"sine","frequency":55},
            {"id":"osc2","type":"oscillator","wave":"triangle","frequency":110},
            {"id":"noise","type":"noise","kind":"brown"},
            {"id":"filter","type":"biquad","mode":"lowpass","frequency":1200,"q":1.1},
            {"id":"dist","type":"waveshaper","amount":24},
            {"id":"amp","type":"adsr","attack":0.002,"decay":0.32,"sustain":0.12,"release":0.18},
            {"id":"reverb","type":"reverb","mix":0.28,"decay":1.4}
        ]
        p.routing = [["osc","filter"],["osc2","filter"],["noise","filter"],["filter","dist"],["dist","amp"],["amp","reverb"],["reverb","bus:sfx"]]
        return p

def _make_tspin(mini=False):
    # T-Spin: 440->880 saw with distortion, punctuated achievement
    id_ = "tetr.tspin_mini" if mini else "tetr.tspin"
    p = Patch(id=id_, category="sfx", duration=0.38, polyphony=12)
    p.graph = [
        {"id":"osc","type":"oscillator","wave":"sawtooth","frequency":440},
        {"id":"pitch","type":"param_envelope","target":"osc.frequency","points":[[0,440,"exp"],[0.18,880,"exp"],[0.32,330,"exp"]]},
        {"id":"filter","type":"biquad","mode":"lowpass","frequency":3400,"q":1.8},
        {"id":"dist","type":"waveshaper","amount":22},
        {"id":"amp","type":"adsr","attack":0.003,"decay":0.22,"sustain":0,"release":0.12}
    ]
    p.routing = [["osc","filter"],["filter","dist"],["dist","amp"],["amp","bus:sfx"]]
    p.randomization = {"pitch_semitones":[-0.5,0.5]}
    return p

def _make_perfect_clear():
    # Portal open: 110->880->55 with delay — magical
    p = Patch(id="tetr.perfect_clear", category="sfx", duration=1.1, polyphony=6)
    p.graph = [
        {"id":"osc","type":"oscillator","wave":"sawtooth","frequency":220},
        {"id":"pitch","type":"param_envelope","target":"osc.frequency","points":[[0,110,"exp"],[0.6,880,"exp"],[1.0,55,"exp"]]},
        {"id":"filter","type":"biquad","mode":"lowpass","frequency":2600,"q":1.6},
        {"id":"delay","type":"delay","time":0.16,"feedback":0.38,"mix":0.32},
        {"id":"amp","type":"adsr","attack":0.12,"decay":0.48,"sustain":0.22,"release":0.42}
    ]
    p.routing = [["osc","filter"],["filter","delay"],["delay","amp"],["amp","bus:sfx"]]
    return p

def _make_combo(n):
    # Combo escalates: pitch = 400 + n*35, brightness rises
    base = 400 + n*38
    p = Patch(id=f"tetr.combo{n}", category="sfx", duration=0.26, polyphony=20)
    p.graph = [
        {"id":"osc","type":"oscillator","wave":"sine","frequency":base},
        {"id":"osc2","type":"oscillator","wave":"sine","frequency":base*1.25},
        {"id":"filter","type":"biquad","mode":"lowpass","frequency":3000 + n*120,"q":0.7},
        {"id":"amp","type":"adsr","attack":0.004,"decay":0.14,"sustain":0,"release":0.08}
    ]
    p.routing = [["osc","filter"],["osc2","filter"],["filter","amp"],["amp","bus:sfx"]]
    return p

def _make_b2b(n):
    # B2B escalating: 300 + n*28, saw, more distortion as chain grows
    base = 300 + n*28
    p = Patch(id=f"tetr.b2b{n}", category="sfx", duration=0.32, polyphony=16)
    p.graph = [
        {"id":"osc","type":"oscillator","wave":"sawtooth","frequency":base},
        {"id":"pitch","type":"param_envelope","target":"osc.frequency","points":[[0,base,"exp"],[0.14,base*1.6,"exp"]]},
        {"id":"filter","type":"biquad","mode":"lowpass","frequency":2600 + n*90,"q":1.2},
        {"id":"dist","type":"waveshaper","amount":12 + n*1.8},
        {"id":"amp","type":"adsr","attack":0.003,"decay":0.18,"sustain":0,"release":0.1}
    ]
    p.routing = [["osc","filter"],["filter","dist"],["dist","amp"],["amp","bus:sfx"]]
    return p

def _make_surge(n):
    # Surge rising with B2B streak: 250->500, delay grows
    base = 250 + n*18
    p = Patch(id=f"tetr.surge{n}", category="sfx", duration=0.42, polyphony=12)
    p.graph = [
        {"id":"osc","type":"oscillator","wave":"triangle","frequency":base},
        {"id":"lfo","type":"lfo","wave":"sine","frequency":4 + n*0.5,"amount":120,"target":"filter.frequency"},
        {"id":"filter","type":"biquad","mode":"bandpass","frequency":base*2.2,"q":0.9},
        {"id":"delay","type":"delay","time":0.12 + n*0.015,"feedback":0.28,"mix":0.22},
        {"id":"amp","type":"adsr","attack":0.02,"decay":0.22,"sustain":0.08,"release":0.16}
    ]
    p.routing = [["osc","filter"],["filter","delay"],["delay","amp"],["amp","bus:sfx"]]
    return p

def _make_garbage():
    # Audible pressure cue, not 5s noise — short brown burst with pitch indicating lines
    p = Patch(id="tetr.garbage_incoming", category="sfx", duration=0.24, polyphony=16)
    p.graph = [
        {"id":"noise","type":"noise","kind":"brown"},
        {"id":"filter","type":"biquad","mode":"lowpass","frequency":480,"q":1.0},
        {"id":"amp","type":"adsr","attack":0.008,"decay":0.14,"sustain":0,"release":0.08}
    ]
    p.routing = [["noise","filter"],["filter","amp"],["amp","bus:sfx"]]
    return p

def _make_clutch():
    # Clutch clear: bright major 7th 880+1320+1660
    p = Patch(id="tetr.clutch", category="sfx", duration=0.48, polyphony=10)
    p.graph = [
        {"id":"osc","type":"oscillator","wave":"sine","frequency":880},
        {"id":"osc2","type":"oscillator","wave":"sine","frequency":1320},
        {"id":"osc3","type":"oscillator","wave":"sine","frequency":1660},
        {"id":"filter","type":"biquad","mode":"lowpass","frequency":3800,"q":0.9},
        {"id":"delay","type":"delay","time":0.14,"feedback":0.32,"mix":0.24},
        {"id":"amp","type":"adsr","attack":0.01,"decay":0.28,"sustain":0.12,"release":0.18}
    ]
    p.routing = [["osc","filter"],["osc2","filter"],["osc3","filter"],["filter","delay"],["delay","amp"],["amp","bus:sfx"]]
    return p

def _make_topout():
    p = Patch(id="tetr.topout", category="sfx", duration=0.85, polyphony=6)
    p.graph = [
        {"id":"noise","type":"noise","kind":"brown"},
        {"id":"osc","type":"oscillator","wave":"sine","frequency":55},
        {"id":"filter","type":"biquad","mode":"lowpass","frequency":700,"q":1.0},
        {"id":"amp","type":"adsr","attack":0.005,"decay":0.52,"sustain":0.1,"release":0.28},
        {"id":"reverb","type":"reverb","mix":0.42,"decay":2.2}
    ]
    p.routing = [["noise","filter"],["osc","filter"],["filter","amp"],["amp","reverb"],["reverb","bus:sfx"]]
    return p

def _make_levelup():
    p = Patch(id="tetr.levelup", category="ui", duration=0.52, polyphony=12)
    p.graph = [
        {"id":"osc","type":"oscillator","wave":"sine","frequency":523},
        {"id":"osc2","type":"oscillator","wave":"sine","frequency":659},
        {"id":"osc3","type":"oscillator","wave":"sine","frequency":784},
        {"id":"amp","type":"adsr","attack":0.01,"decay":0.32,"sustain":0.08,"release":0.18}
    ]
    p.routing = [["osc","amp"],["osc2","amp"],["osc3","amp"],["amp","bus:ui"]]
    return p

# Build dict
TETR_PRESETS = {
    "tetr.move": _make_move(),
    "tetr.rotate": _make_rotate(),
    "tetr.hold": _make_hold(),
    "tetr.softdrop": _make_move(),
    "tetr.harddrop": _make_harddrop(),
    "tetr.lock": _make_lock(),
    "tetr.clear1": _make_clear(1),
    "tetr.clear2": _make_clear(2),
    "tetr.clear3": _make_clear(3),
    "tetr.clear4": _make_clear(4),
    "tetr.tspin": _make_tspin(False),
    "tetr.tspin_mini": _make_tspin(True),
    "tetr.perfect_clear": _make_perfect_clear(),
    "tetr.garbage_incoming": _make_garbage(),
    "tetr.clutch": _make_clutch(),
    "tetr.topout": _make_topout(),
    "tetr.levelup": _make_levelup(),
}
# Expand combos 1-12, b2b 1-12, surge 0-12
for i in range(1,13):
    TETR_PRESETS[f"tetr.combo{i}"] = _make_combo(i)
    TETR_PRESETS[f"tetr.b2b{i}"] = _make_b2b(i)
for i in range(0,13):
    TETR_PRESETS[f"tetr.surge{i}"] = _make_surge(i)

# ---------- BGM Engine — mode-varying, Watchful Eye, Zenith adaptive ----------

class TetrioBGMEngine:
    """
    Implements TETR.IO BGM logic:
    - TETRA LEAGUE: menu/watchful_eye fades instruments, adds drums spectating, battle/victory/defeat distinct
    - Quick Play Zenith: floor adaptive key, transitions support ascent, skip bars on fast climb
    - All BGM via proc_audio buses, not 5s noise
    """
    def __init__(self, base_engine=None):
        self.base_engine = base_engine or base_sfx._get_engine()
        self.current_track = None
        self.floor = 0
        self.last_floor = -1
        self.bar = 0
        self.spectating = False
        self._ctx = None
        self._nodes = {}
        self._gain_layers = {}
        self._is_playing = False
        self._key_root = 110  # A2
        self._watchful_eye_phase = 0

    def _ensure_ctx(self):
        ctx = self.base_engine._ensure_context()
        self._ctx = ctx
        return ctx

    def _stop_all(self):
        try:
            for n in list(self._nodes.values()):
                try:
                    n.stop()
                except:
                    pass
            self._nodes = {}
            self._gain_layers = {}
            self._is_playing = False
        except:
            pass

    def stop(self):
        self._stop_all()
        self.current_track = None
        try:
            self.base_engine.mute_bus("music", mute=True)
            window.setTimeout(lambda: self.base_engine.mute_bus("music", mute=False), 200)
        except:
            pass

    def play(self, name, floor=0, spectating=False):
        ctx = self._ensure_ctx()
        if not ctx:
            return
        if ctx.state == "suspended":
            try:
                ctx.resume()
            except:
                pass
        # Stop previous
        if self.current_track == name and not spectating and floor == self.last_floor:
            # Already playing same, just update
            return
        self._stop_all()
        self.current_track = name
        self.floor = floor
        self.last_floor = floor
        self.spectating = spectating
        self._is_playing = True

        # Map to internal BGM logic
        if "menu_watchful_eye" in name or "menu" in name:
            self._play_watchful_eye(spectating)
        elif "battle" in name or "tetra_league" in name:
            self._play_battle(floor)
        elif "zen" in name:
            self._play_zen(floor)
        elif "40lines" in name:
            self._play_40lines()
        elif "blitz" in name:
            self._play_blitz()
        elif "victory" in name:
            self._play_victory()
        elif "defeat" in name:
            self._play_defeat()
        else:
            self._play_watchful_eye(spectating)

    def _play_watchful_eye(self, spectating=False):
        """
        Watchful Eye: fades instruments in/out, adds drums while spectating
        Original: ambient pad, bass, lead that fade, drums added when spectating
        """
        ctx = self._ctx
        try:
            bus = self.base_engine._buses.get("music", self.base_engine._master_gain)
            # Master music gain
            music_gain = ctx.createGain()
            music_gain.gain.value = db_to_linear(-18)
            music_gain.connect(bus)

            # Layer 1: Bass pad — sine 55Hz with slow attack, fades in/out
            osc_bass = ctx.createOscillator()
            osc_bass.type = "sine"
            osc_bass.frequency.value = 55
            gain_bass = ctx.createGain()
            gain_bass.gain.value = 0.0
            osc_bass.connect(gain_bass)
            gain_bass.connect(music_gain)
            # Fade in
            now = ctx.currentTime
            gain_bass.gain.setValueAtTime(0.0, now)
            gain_bass.gain.linearRampToValueAtTime(0.28, now + 3.5)
            # Slow LFO on bass filter would be ideal, but use gain wobble
            osc_bass.start(now + 0.05)

            # Layer 2: Pad — triangle 110 + 220, very soft
            osc_pad1 = ctx.createOscillator()
            osc_pad1.type = "triangle"
            osc_pad1.frequency.value = 110
            osc_pad2 = ctx.createOscillator()
            osc_pad2.type = "sine"
            osc_pad2.frequency.value = 220
            gain_pad = ctx.createGain()
            gain_pad.gain.value = 0.0
            filter_pad = ctx.createBiquadFilter()
            filter_pad.type = "lowpass"
            filter_pad.frequency.value = 1800
            filter_pad.Q.value = 0.7
            osc_pad1.connect(filter_pad)
            osc_pad2.connect(filter_pad)
            filter_pad.connect(gain_pad)
            gain_pad.connect(music_gain)
            gain_pad.gain.setValueAtTime(0.0, now)
            gain_pad.gain.linearRampToValueAtTime(0.18, now + 5.0)
            osc_pad1.start(now + 0.1)
            osc_pad2.start(now + 0.1)

            # Layer 3: Lead — sine 330 with occasional notes, fades
            osc_lead = ctx.createOscillator()
            osc_lead.type = "sine"
            osc_lead.frequency.value = 330
            gain_lead = ctx.createGain()
            gain_lead.gain.value = 0.0
            osc_lead.connect(gain_lead)
            gain_lead.connect(music_gain)
            gain_lead.gain.setValueAtTime(0.0, now)
            gain_lead.gain.linearRampToValueAtTime(0.14, now + 8.0)
            osc_lead.start(now + 0.2)

            self._nodes = {"bass": osc_bass, "pad1": osc_pad1, "pad2": osc_pad2, "lead": osc_lead}
            self._gain_layers = {"bass": gain_bass, "pad": gain_pad, "lead": gain_lead, "master": music_gain}

            # If spectating, add drums — white noise bursts
            if spectating:
                def _add_drums():
                    try:
                        for i in range(8):
                            # Kick every bar
                            n = ctx.createBufferSource()
                            # Use brown noise burst as kick approximation via buffer
                            buf = ctx.createBuffer(1, int(ctx.sampleRate*0.12), ctx.sampleRate)
                            ch = buf.getChannelData(0)
                            for j in range(len(ch)):
                                ch[j] = (random.random()*2-1) * (1 - j/len(ch))**2
                            n.buffer = buf
                            g = ctx.createGain()
                            g.gain.value = 0.0
                            g.gain.setValueAtTime(0.0, now + i*0.5)
                            g.gain.linearRampToValueAtTime(0.22, now + i*0.5 + 0.01)
                            g.gain.linearRampToValueAtTime(0.0, now + i*0.5 + 0.18)
                            f = ctx.createBiquadFilter()
                            f.type = "lowpass"
                            f.frequency.value = 180
                            n.connect(f)
                            f.connect(g)
                            g.connect(music_gain)
                            n.start(now + i*0.5)
                    except:
                        pass
                window.setTimeout(lambda: _add_drums(), 100)

            # Schedule fade cycle — Watchful Eye fades instruments in/out
            def _cycle():
                try:
                    if self.current_track and "menu" in self.current_track:
                        n = ctx.currentTime
                        # Fade lead out/in
                        if "lead" in self._gain_layers:
                            g = self._gain_layers["lead"].gain
                            cur = g.value
                            target = 0.02 if cur > 0.08 else 0.14
                            g.cancelScheduledValues(n)
                            g.setValueAtTime(cur, n)
                            g.linearRampToValueAtTime(target, n + 4.0)
                        window.setTimeout(lambda: _cycle(), 4000)
                except:
                    pass
            window.setTimeout(lambda: _cycle(), 4000)

        except Exception as e:
            # Fallback silent
            pass

    def _play_battle(self, floor=0):
        # TETRA LEAGUE battle — energetic 140 BPM, bass 55-110, lead 440, drums
        ctx = self._ctx
        try:
            bus = self.base_engine._buses.get("music", self.base_engine._master_gain)
            mg = ctx.createGain()
            mg.gain.value = db_to_linear(-16)
            mg.connect(bus)
            now = ctx.currentTime

            # Driving bass — saw 55 with filter
            osc_bass = ctx.createOscillator()
            osc_bass.type = "sawtooth"
            osc_bass.frequency.value = 55 * (1 + floor*0.02)
            filt = ctx.createBiquadFilter()
            filt.type = "lowpass"
            filt.frequency.value = 900
            filt.Q.value = 1.2
            gain_b = ctx.createGain()
            gain_b.gain.value = 0.32
            osc_bass.connect(filt)
            filt.connect(gain_b)
            gain_b.connect(mg)
            osc_bass.start(now + 0.05)

            # Lead arpeggio — sine 440, changes with B2B would be handled outside
            osc_lead = ctx.createOscillator()
            osc_lead.type = "sine"
            osc_lead.frequency.value = 440
            gain_l = ctx.createGain()
            gain_l.gain.value = 0.0
            osc_lead.connect(gain_l)
            gain_l.connect(mg)
            # Simple arpeggio via scheduled freq changes
            for i, mult in enumerate([1, 1.25, 1.5, 2.0]):
                at = now + i*0.35
                try:
                    osc_lead.frequency.setValueAtTime(440*mult, at)
                    gain_l.gain.setValueAtTime(0.0, at)
                    gain_l.gain.linearRampToValueAtTime(0.18, at+0.04)
                    gain_l.gain.linearRampToValueAtTime(0.0, at+0.28)
                except:
                    pass
            osc_lead.start(now + 0.1)

            self._nodes = {"bass": osc_bass, "lead": osc_lead}
            self._gain_layers = {"master": mg}

            # Loop arpeggio
            def _loop():
                try:
                    if self.current_track and "battle" in self.current_track:
                        nn = ctx.currentTime
                        for i, mult in enumerate([1, 1.25, 1.5, 2.0]):
                            at = nn + i*0.35
                            try:
                                osc_lead.frequency.setValueAtTime(440*mult * (1 + self.floor*0.01), at)
                                gain_l.gain.setValueAtTime(0.0, at)
                                gain_l.gain.linearRampToValueAtTime(0.18, at+0.04)
                                gain_l.gain.linearRampToValueAtTime(0.0, at+0.28)
                            except:
                                pass
                        window.setTimeout(lambda: _loop(), 1400)
                except:
                    pass
            window.setTimeout(lambda: _loop(), 1400)

        except:
            pass

    def _play_zen(self, floor=0):
        # Zenith Tower adaptive — each floor own soundtrack, key = floor
        ctx = self._ctx
        try:
            bus = self.base_engine._buses.get("music", self.base_engine._master_gain)
            mg = ctx.createGain()
            mg.gain.value = db_to_linear(-18)
            mg.connect(bus)
            now = ctx.currentTime

            # Key: C major scale per floor, chromatic ascent
            # floor 0 = C2 65Hz, each floor +2 semitones
            semitone = (floor*2) % 12
            root = 65.41 * (2 ** (semitone/12.0)) * (1 + floor//12 * 0.5)

            osc_root = ctx.createOscillator()
            osc_root.type = "sine"
            osc_root.frequency.value = root
            gain_r = ctx.createGain()
            gain_r.gain.value = 0.0
            osc_root.connect(gain_r)
            gain_r.connect(mg)
            gain_r.gain.setValueAtTime(0.0, now)
            gain_r.gain.linearRampToValueAtTime(0.24, now+2.0)
            osc_root.start(now+0.05)

            osc_fifth = ctx.createOscillator()
            osc_fifth.type = "triangle"
            osc_fifth.frequency.value = root*1.5
            gain_f = ctx.createGain()
            gain_f.gain.value = 0.0
            osc_fifth.connect(gain_f)
            gain_f.connect(mg)
            gain_f.gain.setValueAtTime(0.0, now)
            gain_f.gain.linearRampToValueAtTime(0.16, now+2.5)
            osc_fifth.start(now+0.1)

            self._nodes = {"root": osc_root, "fifth": osc_fifth}
            self._gain_layers = {"root": gain_r, "fifth": gain_f, "master": mg}
            self._key_root = root

            # Handle fast climb: skip bars
            if floor > self.last_floor + 1:
                # Fast climb — skip musical bar, pitch shift
                try:
                    gain_r.gain.cancelScheduledValues(now)
                    gain_r.gain.setValueAtTime(gain_r.gain.value, now)
                    gain_r.gain.linearRampToValueAtTime(0.04, now+0.15)
                    gain_r.gain.linearRampToValueAtTime(0.24, now+0.6)
                    osc_root.frequency.cancelScheduledValues(now)
                    osc_root.frequency.setValueAtTime(root*0.9, now)
                    osc_root.frequency.linearRampToValueAtTime(root, now+0.5)
                except:
                    pass

            self.last_floor = floor

        except:
            pass

    def _play_40lines(self):
        self._play_battle(floor=2)

    def _play_blitz(self):
        self._play_battle(floor=5)

    def _play_victory(self):
        ctx = self._ctx
        try:
            bus = self.base_engine._buses.get("music", self.base_engine._master_gain)
            mg = ctx.createGain()
            mg.gain.value = db_to_linear(-14)
            mg.connect(bus)
            now = ctx.currentTime
            # Major fanfare C-E-G-C
            for i, freq in enumerate([261, 329, 392, 523]):
                o = ctx.createOscillator()
                o.type = "sine"
                o.frequency.value = freq
                g = ctx.createGain()
                g.gain.value = 0.0
                o.connect(g)
                g.connect(mg)
                at = now + i*0.18
                g.gain.setValueAtTime(0.0, at)
                g.gain.linearRampToValueAtTime(0.32, at+0.04)
                g.gain.linearRampToValueAtTime(0.0, at+0.42)
                o.start(at)
                o.stop(at+0.5)
            self._nodes = {}
            self._gain_layers = {"master": mg}
            window.setTimeout(lambda: self._stop_all(), 2200)
        except:
            pass

    def _play_defeat(self):
        ctx = self._ctx
        try:
            bus = self.base_engine._buses.get("music", self.base_engine._master_gain)
            mg = ctx.createGain()
            mg.gain.value = db_to_linear(-14)
            mg.connect(bus)
            now = ctx.currentTime
            # Minor descending A-F-E
            for i, freq in enumerate([220, 174, 164]):
                o = ctx.createOscillator()
                o.type = "triangle"
                o.frequency.value = freq
                g = ctx.createGain()
                g.gain.value = 0.0
                o.connect(g)
                g.connect(mg)
                at = now + i*0.32
                g.gain.setValueAtTime(0.0, at)
                g.gain.linearRampToValueAtTime(0.24, at+0.08)
                g.gain.linearRampToValueAtTime(0.0, at+0.62)
                o.start(at)
                o.stop(at+0.7)
            window.setTimeout(lambda: self._stop_all(), 2500)
        except:
            pass

    def update_floor(self, floor):
        # Called when Zen floor changes — triggers transition
        if floor != self.floor:
            # Fast climb detection for bar skip
            fast = (floor - self.floor) > 1
            self.floor = floor
            if self.current_track and "zen" in self.current_track:
                self._play_zen(floor)
                if fast:
                    # Skip bar — visual feedback would be here
                    pass

    def set_spectating(self, is_spectating):
        if is_spectating != self.spectating:
            self.spectating = is_spectating
            if self.current_track and "menu" in self.current_track:
                self._stop_all()
                self._play_watchful_eye(spectating)

# Singleton instances
tetrio_bgm = TetrioBGMEngine()

# High-level API matching original sfx singleton but with TETR.IO presets
class TetrioSFX:
    def __init__(self):
        self._engine = base_sfx._get_engine()
        # Register TETR presets into engine manifest
        try:
            for k,v in TETR_PRESETS.items():
                self._engine._preset_manifest[k] = v
        except:
            pass
        self._b2b = 0
        self._combo = 0
        self._surge = 0
        self._floor = 0
        self._key = 110

    def _get_engine(self):
        return self._engine

    def resume(self):
        try:
            return self._engine.resume()
        except:
            return False

    def play(self, name, pitch=1.0, brightness=0.7, seed=None, **kw):
        try:
            self._engine.resume()
        except:
            pass
        # Pitch to floor key for Zen
        floor = kw.get("floor", self._floor)
        if floor is not None:
            # Map floor to key — each floor +0.5 semitone, SFX pitch follows
            try:
                key_mult = 2 ** ((floor*0.5)/12.0)
                pitch = float(pitch) * key_mult
            except:
                pass

        # B2B escalating
        if "b2b" in name:
            try:
                n = int(''.join(filter(str.isdigit, name)) or self._b2b)
                self._b2b = n
                # Escalate brightness and pitch
                brightness = min(1.0, 0.5 + n*0.06)
                pitch = pitch * (1 + n*0.045)
            except:
                pass
        if "combo" in name:
            try:
                n = int(''.join(filter(str.isdigit, name)) or self._combo)
                self._combo = n
                pitch = pitch * (1 + n*0.038)
            except:
                pass
        if "surge" in name:
            try:
                n = int(''.join(filter(str.isdigit, name)) or self._surge)
                self._surge = n
                brightness = min(1.0, 0.4 + n*0.05)
            except:
                pass

        # Thunder for powerful attacks (clear4, tspin)
        vol = kw.get("volume", kw.get("gain", 0.5))
        if "clear4" in name or "tspin" in name:
            vol = min(1.2, vol*1.4)

        # Garbage pressure cue — volume scales with lines
        if "garbage" in name:
            lines = kw.get("lines", 1)
            vol = 0.35 + min(0.4, lines*0.08)
            pitch = 1.0 - lines*0.02  # deeper for more garbage

        # Clutch — slightly louder
        if "clutch" in name:
            vol = 0.85

        params = kw.get("params", {})
        params["pitch"] = pitch
        params["brightness"] = brightness
        params["intensity"] = vol
        kw["params"] = params
        if seed is not None:
            kw["seed"] = seed
        else:
            kw["seed"] = random.randint(0, 999999)

        try:
            return self._engine.play(name, **kw)
        except Exception as e:
            # Fallback to base sfx
            try:
                return base_sfx._get_engine().play(name, **kw)
            except:
                return None

    def set_floor(self, floor):
        self._floor = floor
        tetrio_bgm.update_floor(floor)

    def set_b2b(self, streak):
        self._b2b = streak

    def set_combo(self, combo):
        self._combo = combo

    def set_volume(self, bus, db):
        try:
            self._engine.set_bus_gain(bus, db)
        except:
            pass

    def mute(self, bus, mute=True):
        try:
            self._engine.mute_bus(bus, mute)
        except:
            pass

    def play_bgm(self, name, floor=0, spectating=False, **kw):
        tetrio_bgm._ensure_ctx()
        # Ensure base engine context exists
        try:
            self._engine._ensure_context()
        except:
            pass
        tetrio_bgm.play(name, floor=floor, spectating=spectating)

    def stop_bgm(self):
        tetrio_bgm.stop()

    def set_spectating(self, is_spec):
        tetrio_bgm.set_spectating(is_spec)

# Export singleton — this is the proper TETR.IO audio
tetrio_sfx = TetrioSFX()

# Also provide compatibility: sfx alias
sfx = tetrio_sfx

# Manifest for debugging
MANIFEST_TETR = {k: v.to_dict() for k,v in TETR_PRESETS.items()}
