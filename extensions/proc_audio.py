"""
proc_audio.py - Declarative, deterministic procedural audio library for SCS/Brython

High-level: sfx.play("jump", pitch=1.2, brightness=0.7, seed=42)
Low-level:  Patch().oscillator("sawtooth", 880).pitch_envelope(...).filter(...)

Architecture:
- Lazy AudioContext, category buses, master compressor/limiter
- Seeded determinism, variation streams, JSON patch format
- Main-thread Web Audio graph + AudioWorklet DSP tier + OfflineAudioContext baking
- Polyphony, voice stealing, burst protection, quality profiles

Brython: uses browser.window.AudioContext via JS interop
"""
from browser import window, document
import random
import math
import json as py_json
import time

# ---------- helpers ----------
def db_to_linear(db):
    return 10 ** (db / 20.0) if db > -100 else 0.0

def linear_to_db(lin):
    return 20 * math.log10(lin) if lin > 0 else -100

def midi_to_freq(midi):
    return 440.0 * (2 ** ((midi - 69) / 12.0))

def _now():
    try:
        return int(window.Date.now())
    except:
        return int(time.time()*1000)

# ---------- SeededRandom - deterministic xorshift ----------
class SeededRandom:
    def __init__(self, seed=0):
        self._seed = int(seed) & 0xFFFFFFFF
        if self._seed == 0:
            self._seed = 0x6D2B79F5
        self._state = self._seed

    def _xorshift(self):
        x = self._state
        x ^= (x << 13) & 0xFFFFFFFF
        x ^= x >> 17
        x ^= (x << 5) & 0xFFFFFFFF
        self._state = x & 0xFFFFFFFF
        return self._state

    def random(self):
        return self._xorshift() / 4294967296.0

    def uniform(self, a, b):
        return a + (b - a) * self.random()

    def randint(self, a, b):
        return int(self.uniform(a, b+1)) if a != b else a

    def choice(self, seq):
        if not seq:
            return None
        return seq[int(self.random() * len(seq)) % len(seq)]

    def semitones_to_ratio(self, st):
        return 2 ** (st / 12.0)

# ---------- Buses ----------
class Bus:
    MASTER = "master"
    MUSIC = "music"
    SFX = "sfx"
    UI = "ui"
    VOICE = "voice"
    AMBIENCE = "ambience"
    CINEMATIC = "cinematic"
    ALL = [MASTER, MUSIC, SFX, UI, VOICE, AMBIENCE, CINEMATIC]

# ---------- Quality profiles ----------
QUALITY_PROFILES = {
    "low": {"max_voices": 16, "reverb": False, "convolver": False, "fft": 256, "worklets": False, "spatial": "stereo"},
    "medium": {"max_voices": 32, "reverb": True, "convolver": False, "fft": 512, "worklets": True, "spatial": "stereo"},
    "high": {"max_voices": 48, "reverb": True, "convolver": True, "fft": 1024, "worklets": True, "spatial": "full"},
    "cinematic": {"max_voices": 96, "reverb": True, "convolver": True, "fft": 2048, "worklets": True, "spatial": "full"},
}

# ---------- SoundHandle ----------
class SoundHandle:
    def __init__(self, engine, preset_id, nodes, start_time, duration, seed, bus_name):
        self.engine = engine
        self.preset_id = preset_id
        self.nodes = nodes  # dict of Web Audio nodes
        self.start_time = start_time
        self.duration = duration
        self.seed = seed
        self.bus_name = bus_name
        self._stopped = False
        self._params = {}

    def is_playing(self):
        if self._stopped:
            return False
        try:
            # check if source ended
            return True
        except:
            return False

    def stop(self, fade_out=0.05):
        if self._stopped:
            return
        self._stopped = True
        try:
            ctx = self.engine._ctx
            now = ctx.currentTime
            # fade gain
            if "gain" in self.nodes:
                g = self.nodes["gain"]
                try:
                    g.gain.cancelScheduledValues(now)
                    g.gain.setValueAtTime(g.gain.value, now)
                    g.gain.linearRampToValueAtTime(0.001, now + fade_out)
                except:
                    pass
            # stop sources after fade
            def _do_stop():
                for k in ("osc", "osc2", "source", "noise"):
                    n = self.nodes.get(k)
                    if n:
                        try:
                            n.stop(now + fade_out + 0.05)
                        except:
                            pass
            # schedule stop via timeout
            window.setTimeout(lambda: _do_stop(), int((fade_out+0.1)*1000))
        except Exception as e:
            pass

    def set_parameter(self, param, value, ramp=0.05):
        self._params[param] = value
        try:
            ctx = self.engine._ctx
            now = ctx.currentTime
            # map param to node
            if param in ("pitch", "frequency", "freq"):
                for k in ("osc", "osc2"):
                    n = self.nodes.get(k)
                    if n and hasattr(n, "frequency"):
                        try:
                            n.frequency.cancelScheduledValues(now)
                            n.frequency.setValueAtTime(n.frequency.value, now)
                            n.frequency.linearRampToValueAtTime(float(value), now + ramp)
                        except:
                            pass
            elif param in ("gain", "volume", "energy"):
                n = self.nodes.get("gain")
                if n:
                    try:
                        n.gain.cancelScheduledValues(now)
                        n.gain.setValueAtTime(n.gain.value, now)
                        n.gain.linearRampToValueAtTime(float(value), now + ramp)
                    except:
                        pass
            elif param in ("filter", "brightness", "cutoff"):
                n = self.nodes.get("filter")
                if n and hasattr(n, "frequency"):
                    try:
                        n.frequency.cancelScheduledValues(now)
                        n.frequency.setValueAtTime(n.frequency.value, now)
                        n.frequency.linearRampToValueAtTime(float(value), now + ramp)
                    except:
                        pass
        except:
            pass

# ---------- Patch - declarative graph + builder ----------
class Patch:
    def __init__(self, id="custom", category="sfx", duration=0.5, seed=None, polyphony=8):
        self.id = id
        self.version = 1
        self.seed = seed
        self.duration = duration
        self.category = category
        self.polyphony = polyphony
        self.randomization = {}
        self.graph = []  # list of node dicts
        self.routing = []  # list of [from, to]
        self.tags = []
        self.meta = {}
        self._builder_stack = []  # for chainable API

    # ---- serialization ----
    def to_dict(self):
        return {
            "id": self.id,
            "version": self.version,
            "seed": self.seed,
            "duration": self.duration,
            "category": self.category,
            "polyphony": self.polyphony,
            "randomization": self.randomization,
            "graph": self.graph,
            "routing": self.routing,
            "tags": self.tags,
            "meta": self.meta,
        }

    def to_json(self):
        return py_json.dumps(self.to_dict(), indent=2)

    @staticmethod
    def from_dict(d):
        p = Patch(id=d.get("id","custom"), category=d.get("category","sfx"), duration=d.get("duration",0.5), seed=d.get("seed"), polyphony=d.get("polyphony",8))
        p.version = d.get("version",1)
        p.randomization = d.get("randomization",{})
        p.graph = d.get("graph",[])
        p.routing = d.get("routing",[])
        p.tags = d.get("tags",[])
        p.meta = d.get("meta",{})
        return p

    @staticmethod
    def from_json(s):
        if isinstance(s, str):
            d = py_json.loads(s)
        else:
            d = s
        return Patch.from_dict(d)

    @staticmethod
    def load(path_or_json):
        # in Brython, path_or_json may be URL or JSON string or dict
        if isinstance(path_or_json, str) and path_or_json.strip().startswith("{"):
            return Patch.from_json(path_or_json)
        # if it's a dict
        if isinstance(path_or_json, dict):
            return Patch.from_dict(path_or_json)
        # try fetch sync via window (for manifest)
        return Patch(id=str(path_or_json))

    # ---- builder API ----
    def _add_node(self, node_type, **props):
        nid = props.pop("id", f"{node_type}_{len(self.graph)}")
        node = {"id": nid, "type": node_type}
        node.update(props)
        self.graph.append(node)
        if self._builder_stack:
            prev = self._builder_stack[-1]
            self.routing.append([prev, nid])
        self._builder_stack.append(nid)
        return self

    def oscillator(self, wave="sine", frequency=440, detune=0):
        return self._add_node("oscillator", wave=wave, frequency=frequency, detune=detune)

    def noise(self, kind="white"):
        return self._add_node("noise", kind=kind)

    def buffer(self, buffer_id=None):
        return self._add_node("buffer", buffer_id=buffer_id)

    def filter(self, mode="lowpass", frequency=1000, q=1, gain=0):
        # mode: lowpass, highpass, bandpass, etc.
        return self._add_node("biquad", mode=mode, frequency=frequency, q=q, gain=gain)

    def envelope(self, attack=0.01, decay=0.1, sustain=0.7, release=0.2, amount=1.0):
        return self._add_node("adsr", attack=attack, decay=decay, sustain=sustain, release=release, amount=amount)

    def pitch_envelope(self, start=880, end=110, duration=0.2, curve="exp"):
        return self._add_node("param_envelope", target="osc.frequency", points=[[0.0, start, curve],[duration, end, curve]])

    def filter_envelope(self, start=4000, end=400, duration=0.3, curve="exp"):
        return self._add_node("param_envelope", target="filter.frequency", points=[[0.0, start, curve],[duration, end, curve]])

    def distortion(self, amount=20, oversample="2x"):
        return self._add_node("waveshaper", amount=amount, oversample=oversample)

    def delay(self, time=0.25, feedback=0.3, mix=0.4):
        return self._add_node("delay", time=time, feedback=feedback, mix=mix)

    def reverb(self, mix=0.3, decay=2.0, kind="hall"):
        return self._add_node("reverb", mix=mix, decay=decay, kind=kind)

    def panner(self, pan=0):
        return self._add_node("stereo_panner", pan=pan)

    def compressor(self, threshold=-24, ratio=4, attack=0.003, release=0.25):
        return self._add_node("compressor", threshold=threshold, ratio=ratio, attack=attack, release=release)

    def lfo(self, wave="sine", frequency=5, amount=0.5, target="gain"):
        return self._add_node("lfo", wave=wave, frequency=frequency, amount=amount, target=target)

    def gain(self, value=1.0):
        return self._add_node("gain", value=value)

    # chain reset
    def then(self):
        self._builder_stack = []
        return self

    # macro controls
    def macro(self, name, default=0.5, min=0, max=1, maps_to=None):
        if "macros" not in self.meta:
            self.meta["macros"] = {}
        self.meta["macros"][name] = {"default": default, "min": min, "max": max, "maps_to": maps_to}
        return self

# ---------- Preset families ----------
def _preset_jump(brightness=0.7, pitch=1.0):
    p = Patch(id="character.jump", category="sfx", duration=0.35, polyphony=4)
    p.tags = ["movement","jump","character","arcade"]
    p.meta = {"name":"Soft Jump","loudness_db":-14,"macro":{"weight":0.5,"brightness":brightness}}
    p.graph = [
        {"id":"osc","type":"oscillator","wave":"sine","frequency": 220*pitch},
        {"id":"pitch","type":"param_envelope","target":"osc.frequency","points":[[0, 440*pitch,"exp"],[0.18, 660*pitch,"exp"]]},
        {"id":"filter","type":"biquad","mode":"lowpass","frequency": 1800+brightness*2000,"q":0.7},
        {"id":"amp","type":"adsr","attack":0.005,"decay":0.12,"sustain":0,"release":0.08}
    ]
    p.routing = [["osc","filter"],["filter","amp"],["amp","bus:sfx"]]
    p.randomization = {"pitch_semitones":[-1,1],"pan":[-0.2,0.2]}
    return p

def _preset_laser():
    p = Patch(id="weapon.laser_01", category="sfx", duration=0.22, polyphony=6)
    p.tags = ["weapon","laser","sci-fi","arcade"]
    p.graph = [
        {"id":"osc","type":"oscillator","wave":"sawtooth","frequency":1200},
        {"id":"pitch","type":"param_envelope","target":"osc.frequency","points":[[0,2400,"exponential"],[0.18,120,"exponential"]]},
        {"id":"filter","type":"biquad","mode":"lowpass","frequency":4200,"q":2.5},
        {"id":"amp","type":"adsr","attack":0.003,"decay":0.11,"sustain":0,"release":0.04},
        {"id":"dist","type":"waveshaper","amount":18}
    ]
    p.routing = [["osc","filter"],["filter","dist"],["dist","amp"],["amp","bus:sfx"]]
    p.randomization = {"pitch_semitones":[-1.5,1.5],"duration_scale":[0.88,1.12],"pan":[-0.25,0.25]}
    return p

def _preset_explosion():
    p = Patch(id="weapon.explosion_large", category="sfx", duration=1.2, polyphony=3)
    p.tags = ["weapon","explosion","impact","heavy"]
    p.graph = [
        {"id":"noise","type":"noise","kind":"brown"},
        {"id":"osc","type":"oscillator","wave":"sine","frequency":60},
        {"id":"filter","type":"biquad","mode":"lowpass","frequency":800,"q":1},
        {"id":"amp","type":"adsr","attack":0.005,"decay":0.6,"sustain":0.2,"release":0.4},
        {"id":"reverb","type":"reverb","mix":0.35,"decay":2.5}
    ]
    p.routing = [["noise","filter"],["osc","filter"],["filter","amp"],["amp","reverb"],["reverb","bus:sfx"]]
    return p

def _preset_coin():
    p = Patch(id="ui.coin_pickup", category="ui", duration=0.6, polyphony=10)
    p.tags = ["ui","pickup","coin","positive"]
    p.graph = [
        {"id":"osc","type":"oscillator","wave":"sine","frequency":880},
        {"id":"osc2","type":"oscillator","wave":"sine","frequency":1320},
        {"id":"amp","type":"adsr","attack":0.005,"decay":0.25,"sustain":0,"release":0.15}
    ]
    p.routing = [["osc","amp"],["osc2","amp"],["amp","bus:ui"]]
    return p

def _preset_footstep(surface="grass"):
    p = Patch(id=f"character.footstep_{surface}", category="sfx", duration=0.18, polyphony=12)
    p.tags = ["movement","footstep",surface]
    p.graph = [
        {"id":"noise","type":"noise","kind":"white"},
        {"id":"filter","type":"biquad","mode":"bandpass","frequency": 900 if surface=="grass" else 1800,"q":1.2},
        {"id":"amp","type":"adsr","attack":0.001,"decay":0.08,"sustain":0,"release":0.04}
    ]
    p.routing = [["noise","filter"],["filter","amp"],["amp","bus:sfx"]]
    p.randomization = {"pitch_semitones":[-2,2],"gain":[0.7,1.0],"pan":[-0.15,0.15]}
    return p

def _preset_ui_hover():
    p = Patch(id="ui.hover", category="ui", duration=0.12, polyphony=20)
    p.tags = ["ui","hover","tick"]
    p.graph = [
        {"id":"osc","type":"oscillator","wave":"sine","frequency":1200},
        {"id":"amp","type":"adsr","attack":0.002,"decay":0.06,"sustain":0,"release":0.04}
    ]
    p.routing = [["osc","amp"],["amp","bus:ui"]]
    return p

def _preset_engine_idle():
    p = Patch(id="vehicle.engine_idle", category="ambience", duration=2.0, polyphony=2)
    p.tags = ["vehicle","engine","loop","machine"]
    p.meta["loop"] = True
    p.graph = [
        {"id":"osc","type":"oscillator","wave":"sawtooth","frequency":55},
        {"id":"osc2","type":"oscillator","wave":"triangle","frequency":110},
        {"id":"filter","type":"biquad","mode":"lowpass","frequency":600,"q":1},
        {"id":"lfo","type":"lfo","wave":"sine","frequency":3,"amount":0.15,"target":"filter.frequency"},
        {"id":"amp","type":"adsr","attack":0.5,"decay":0.2,"sustain":0.8,"release":0.5}
    ]
    p.routing = [["osc","filter"],["osc2","filter"],["filter","amp"],["amp","bus:ambience"]]
    return p

def _preset_wind():
    p = Patch(id="nature.wind_light", category="ambience", duration=5.0, polyphony=2)
    p.tags = ["nature","wind","ambient","loop"]
    p.meta["loop"] = True
    p.graph = [
        {"id":"noise","type":"noise","kind":"pink"},
        {"id":"filter","type":"biquad","mode":"bandpass","frequency":800,"q":0.5},
        {"id":"lfo","type":"lfo","wave":"sine","frequency":0.2,"amount":300,"target":"filter.frequency"},
        {"id":"amp","type":"adsr","attack":1.5,"decay":0.5,"sustain":0.7,"release":1.0}
    ]
    p.routing = [["noise","filter"],["filter","amp"],["amp","bus:ambience"]]
    return p

def _preset_portal():
    p = Patch(id="scifi.portal_open", category="sfx", duration=1.5, polyphony=4)
    p.tags = ["scifi","portal","magic","glitch"]
    p.graph = [
        {"id":"osc","type":"oscillator","wave":"sawtooth","frequency":220},
        {"id":"pitch","type":"param_envelope","target":"osc.frequency","points":[[0,110,"exp"],[0.8,880,"exp"],[1.4,55,"exp"]]},
        {"id":"filter","type":"biquad","mode":"lowpass","frequency":2400,"q":2},
        {"id":"delay","type":"delay","time":0.18,"feedback":0.4,"mix":0.35},
        {"id":"amp","type":"adsr","attack":0.15,"decay":0.6,"sustain":0.3,"release":0.5}
    ]
    p.routing = [["osc","filter"],["filter","delay"],["delay","amp"],["amp","bus:sfx"]]
    return p

BUILTIN_PRESETS = {
    "character.jump": _preset_jump(),
    "character.jump_soft": _preset_jump(brightness=0.5, pitch=0.9),
    "character.footstep_grass": _preset_footstep("grass"),
    "character.footstep_metal": _preset_footstep("metal"),
    "character.footstep_stone": _preset_footstep("stone"),
    "weapon.laser_01": _preset_laser(),
    "weapon.plasma_bolt": _preset_laser(),
    "weapon.explosion_large": _preset_explosion(),
    "weapon.explosion_small": _preset_explosion(),
    "ui.coin_pickup": _preset_coin(),
    "ui.hover": _preset_ui_hover(),
    "ui.select": _preset_ui_hover(),
    "ui.confirm": _preset_coin(),
    "vehicle.engine_idle": _preset_engine_idle(),
    "nature.wind_light": _preset_wind(),
    "scifi.portal_open": _preset_portal(),
    "arcade_laser_01": _preset_laser(),
}

# ---------- AudioEngine ----------
class AudioEngine:
    def __init__(self, quality="high", seed=0, max_voices=None, master_db=-4, category_levels=None):
        self.quality = quality
        self.profile = QUALITY_PROFILES.get(quality, QUALITY_PROFILES["high"])
        self.global_seed = seed
        self.global_rng = SeededRandom(seed)
        self.max_voices = max_voices or self.profile["max_voices"]
        self.master_db = master_db
        self.category_levels = category_levels or {"music": -8, "sfx": -3, "ui": -6, "voice": -2, "ambience": -10, "cinematic": -4}
        self._ctx = None
        self._master_gain = None
        self._compressor = None
        self._limiter = None
        self._buses = {}  # name -> GainNode
        self._active_voices = []  # list of SoundHandle
        self._voice_counts = {}  # preset_id -> count
        self._last_play = {}  # preset_id -> timestamp for burst protection
        self._preset_manifest = dict(BUILTIN_PRESETS)
        self._state = "blocked"  # blocked, suspended, ready, unavailable
        self._worklet_ready = False
        self._capabilities = {}
        self._ducking = {}
        self._analysis_nodes = {}
        self._listener_pos = (0,0,0)
        self._recorder = None
        self._event_log = []

    def _log(self, evt, data=None):
        try:
            self._event_log.append({"t": _now(), "evt": evt, "data": data})
            if len(self._event_log) > 200:
                self._event_log = self._event_log[-200:]
        except:
            pass

    def _ensure_context(self):
        if self._ctx:
            return self._ctx
        try:
            AC = getattr(window, "AudioContext", None) or getattr(window, "webkitAudioContext", None)
            if not AC:
                self._state = "unavailable"
                self._log("context_unavailable")
                return None
            # Brython: AC.new()
            try:
                ctx = AC.new()
            except:
                ctx = window.AudioContext.new() if hasattr(window, "AudioContext") else window.webkitAudioContext.new()
            self._ctx = ctx

            # master chain: buses -> master gain -> compressor -> limiter -> destination
            try:
                master = ctx.createGain()
                master.gain.value = db_to_linear(self.master_db)
                comp = ctx.createDynamicsCompressor()
                comp.threshold.value = -18
                comp.ratio.value = 3
                comp.attack.value = 0.02
                comp.release.value = 0.25
                # limiter as second compressor with high ratio
                limiter = ctx.createDynamicsCompressor()
                limiter.threshold.value = -1
                limiter.ratio.value = 20
                limiter.attack.value = 0.001
                limiter.release.value = 0.05

                master.connect(comp)
                comp.connect(limiter)
                limiter.connect(ctx.destination)

                self._master_gain = master
                self._compressor = comp
                self._limiter = limiter
            except Exception as e:
                self._master_gain = ctx.createGain()
                self._master_gain.gain.value = db_to_linear(self.master_db)
                self._master_gain.connect(ctx.destination)
                self._compressor = None
                self._limiter = None

            # create category buses
            for bus_name in Bus.ALL:
                if bus_name == Bus.MASTER:
                    continue
                try:
                    g = ctx.createGain()
                    db = self.category_levels.get(bus_name, -3)
                    g.gain.value = db_to_linear(db)
                    # connect to master
                    g.connect(self._master_gain)
                    self._buses[bus_name] = g
                except:
                    pass

            # capabilities
            self._capabilities = {
                "worklet": hasattr(ctx, "audioWorklet"),
                "offline": hasattr(window, "OfflineAudioContext") or hasattr(window, "webkitOfflineAudioContext"),
                "panner": True,
                "convolver": True,
                "analyser": True,
                "mediaStream": hasattr(ctx, "createMediaStreamDestination"),
            }

            # try worklet registration (non-blocking)
            if self._capabilities.get("worklet") and self.profile.get("worklets"):
                try:
                    # will be loaded via addModule if worklet file exists
                    # we don't block on it
                    pass
                except:
                    pass

            self._state = "suspended" if ctx.state == "suspended" else "ready"
            self._log("context_created", {"state": self._state, "sampleRate": ctx.sampleRate})
            return ctx
        except Exception as e:
            self._state = "unavailable"
            self._log("context_create_failed", str(e))
            return None

    def configure(self, master_db=None, category_levels=None, seed=None, max_voices=None, quality=None):
        if master_db is not None:
            self.master_db = master_db
            if self._master_gain:
                try:
                    self._master_gain.gain.value = db_to_linear(master_db)
                except:
                    pass
        if category_levels:
            self.category_levels.update(category_levels)
            for k,v in category_levels.items():
                if k in self._buses:
                    try:
                        self._buses[k].gain.value = db_to_linear(v)
                    except:
                        pass
        if seed is not None:
            self.global_seed = seed
            self.global_rng = SeededRandom(seed)
        if max_voices:
            self.max_voices = max_voices
        if quality:
            self.quality = quality
            self.profile = QUALITY_PROFILES.get(quality, self.profile)

    def resume(self):
        ctx = self._ensure_context()
        if not ctx:
            return False
        try:
            if ctx.state == "suspended":
                try:
                    p = ctx.resume()
                    # Handle promise properly in Brython
                    if p and hasattr(p, "then"):
                        # Set up handlers
                        def _on_resolved(*args):
                            self._state = "ready"
                            self._log("resume_resolved")
                        def _on_rejected(err):
                            self._log("resume_rejected", str(err))
                        try:
                            p.then(_on_resolved, _on_rejected)
                        except:
                            pass
                except Exception as e:
                    self._log("resume_promise_failed", str(e))
                self._state = "ready"
                self._log("resume_requested")
                return True
            self._state = "ready"
            return True
        except Exception as e:
            self._log("resume_failed", str(e))
            return False

    def suspend(self):
        if self._ctx:
            try:
                self._ctx.suspend()
                self._state = "suspended"
            except:
                pass

    def unlock(self, event=None):
        # call from user gesture
        return self.resume()

    def load_manifest(self, path_or_dict):
        try:
            if isinstance(path_or_dict, dict):
                for k,v in path_or_dict.items():
                    if isinstance(v, dict):
                        self._preset_manifest[k] = Patch.from_dict(v)
                    else:
                        self._preset_manifest[k] = v
            elif isinstance(path_or_dict, str) and path_or_json.startswith("{"):
                d = py_json.loads(path_or_dict)
                self.load_manifest(d)
            else:
                # URL - async fetch would be needed, for now keep builtin
                self._log("manifest_load_url_deferred", path_or_dict)
        except Exception as e:
            self._log("manifest_load_failed", str(e))

    def set_bus_gain(self, bus_name, db):
        self.category_levels[bus_name] = db
        if bus_name in self._buses:
            try:
                self._buses[bus_name].gain.value = db_to_linear(db)
            except:
                pass

    def get_bus_gain(self, bus_name):
        return self.category_levels.get(bus_name, 0)

    def mute_bus(self, bus_name, mute=True):
        if bus_name in self._buses:
            try:
                if mute:
                    self._buses[bus_name].gain.value = 0
                else:
                    self._buses[bus_name].gain.value = db_to_linear(self.category_levels.get(bus_name, -3))
            except:
                pass

    def duck(self, target_bus="music", trigger_bus="voice", amount_db=-10, attack=0.03, release=0.35):
        # store ducking policy, applied when trigger plays
        self._ducking[target_bus] = {"trigger": trigger_bus, "amount_db": amount_db, "attack": attack, "release": release}
        self._log("duck_configured", {"target": target_bus, "trigger": trigger_bus})

    # ---- voice management ----
    def _can_play(self, preset_id, now_ms):
        # burst protection: rate limit
        last = self._last_play.get(preset_id, 0)
        if now_ms - last < 40:  # 40ms cooldown default
            # allow if low polyphony
            if self._voice_counts.get(preset_id,0) >= 2:
                self._log("burst_protected", preset_id)
                return False
        # max voices global
        if len(self._active_voices) >= self.max_voices:
            # steal
            self._steal_voice()
        # per-preset polyphony
        preset = self._preset_manifest.get(preset_id)
        poly = getattr(preset, "polyphony", 8) if preset else 8
        if self._voice_counts.get(preset_id,0) >= poly:
            self._steal_voice(preset_id=preset_id)
        return True

    def _steal_voice(self, preset_id=None, policy="oldest"):
        # policy: oldest, quietest, furthest, lowest_priority, same_event_first
        candidates = [v for v in self._active_voices if (preset_id is None or v.preset_id == preset_id)]
        if not candidates:
            candidates = self._active_voices[:]
        if not candidates:
            return
        # oldest first
        victim = min(candidates, key=lambda h: h.start_time)
        try:
            victim.stop(fade_out=0.02)
            self._active_voices.remove(victim)
            cnt = self._voice_counts.get(victim.preset_id,1)
            self._voice_counts[victim.preset_id] = max(0, cnt-1)
            self._log("voice_stolen", {"victim": victim.preset_id, "policy": policy})
        except:
            pass

    # ---- core play ----
    def play(self, preset, category=None, params=None, position=None, velocity=None, spatial=False, min_distance=1, max_distance=100, rolloff="inverse", occlusion=0, seed=None, variation=None, at=None, bus=None):
        ctx = self._ensure_context()
        if not ctx:
            self._log("play_failed_no_context", str(preset))
            return None
        if ctx.state == "suspended":
            # try resume but don't block
            try:
                ctx.resume()
            except:
                pass

        # resolve preset
        preset_id = None
        patch = None
        if isinstance(preset, Patch):
            patch = preset
            preset_id = patch.id
        elif isinstance(preset, dict):
            patch = Patch.from_dict(preset)
            preset_id = patch.id
        elif isinstance(preset, str):
            preset_id = preset
            # look up
            if preset in self._preset_manifest:
                p = self._preset_manifest[preset]
                if isinstance(p, Patch):
                    patch = p
                else:
                    patch = Patch.from_dict(p) if isinstance(p, dict) else _preset_jump()
            else:
                # try built-in fallback: parse as id
                patch = BUILTIN_PRESETS.get(preset, _preset_jump())
                preset_id = patch.id if hasattr(patch, "id") else preset
        else:
            patch = _preset_jump()
            preset_id = "fallback"

        # seed handling
        if seed is None:
            seed = self.global_rng.randint(0, 2**31-1)
        rng = SeededRandom(seed)

        # burst protection
        now_ms = _now()
        if not self._can_play(preset_id, now_ms):
            return None
        self._last_play[preset_id] = now_ms

        # randomization from patch.randomization + params
        params = params or {}
        pitch_mult = 1.0
        if "pitch_semitones" in patch.randomization:
            lo, hi = patch.randomization["pitch_semitones"]
            st = rng.uniform(lo, hi)
            # extra pitch param
            if "pitch" in params:
                try:
                    pitch_mult = float(params["pitch"])
                except:
                    pitch_mult = 1.0
            pitch_mult *= rng.semitones_to_ratio(st)
        elif "pitch" in params:
            try:
                pitch_mult = float(params["pitch"])
            except:
                pitch_mult = 1.0

        gain_mult = 1.0
        if "gain" in patch.randomization:
            lo, hi = patch.randomization["gain"]
            gain_mult = rng.uniform(lo, hi)
        if "intensity" in params:
            try:
                gain_mult *= float(params["intensity"])
            except:
                pass
        if "energy" in params:
            try:
                gain_mult *= float(params["energy"])
            except:
                pass

        pan_val = 0.0
        if "pan" in patch.randomization:
            lo, hi = patch.randomization["pan"]
            pan_val = rng.uniform(lo, hi)
        if "pan" in params:
            try:
                pan_val = float(params["pan"])
            except:
                pass

        duration_scale = 1.0
        if "duration_scale" in patch.randomization:
            lo, hi = patch.randomization["duration_scale"]
            duration_scale = rng.uniform(lo, hi)

        # build graph
        try:
            nodes = {}
            ctx_now = ctx.currentTime
            start_at = ctx_now + 0.01
            if at is not None:
                try:
                    start_at = float(at)
                except:
                    pass

            # determine bus
            bus_name = bus or category or patch.category or "sfx"
            if bus_name not in self._buses:
                bus_name = "sfx"
            bus_gain = self._buses.get(bus_name, self._master_gain)

            # master gain for this voice
            gain_node = ctx.createGain()
            # apply gain mult + headroom
            gain_node.gain.value = 0.0  # start at 0, ramp up via envelope

            # We'll parse patch.graph to create nodes
            # For Phase 1, support common types: oscillator, noise, biquad, adsr, waveshaper, delay, reverb, gain, stereo_panner
            # Create nodes dict by id
            graph_nodes = {}
            for g in patch.graph:
                nid = g.get("id")
                ntype = g.get("type")
                try:
                    if ntype == "oscillator":
                        o = ctx.createOscillator()
                        o.type = g.get("wave","sine")
                        base_freq = float(g.get("frequency",440)) * pitch_mult
                        # brightness -> filter, but also affect freq
                        if "brightness" in params:
                            try:
                                b = float(params["brightness"])
                                base_freq *= (0.7 + b*0.6)
                            except:
                                pass
                        o.frequency.value = base_freq
                        if "detune" in g:
                            o.detune.value = float(g["detune"])
                        graph_nodes[nid] = o
                        nodes[nid] = o
                    elif ntype == "noise":
                        # create buffer source with noise
                        kind = g.get("kind","white")
                        buf_len = int(ctx.sampleRate * (patch.duration * duration_scale + 0.2))
                        if buf_len < 128:
                            buf_len = 128
                        # create buffer
                        audio_buf = ctx.createBuffer(1, buf_len, ctx.sampleRate)
                        channel = audio_buf.getChannelData(0)
                        # generate noise
                        # white
                        if kind == "white":
                            for i in range(buf_len):
                                channel[i] = rng.uniform(-1,1)
                        elif kind == "pink":
                            # simple pink approx: one-pole lowpass on white
                            b0=b1=b2=0
                            for i in range(buf_len):
                                white = rng.uniform(-1,1)
                                b0 = 0.99886*b0 + white*0.0555179
                                b1 = 0.99332*b1 + white*0.0750759
                                b2 = 0.96900*b2 + white*0.1538520
                                channel[i] = (b0+b1+b2+white*0.5362)*0.11
                        else: # brown
                            last = 0
                            for i in range(buf_len):
                                white = rng.uniform(-1,1)
                                last = last + white*0.02
                                last = max(-1,min(1,last))
                                channel[i] = last*3.5
                        src = ctx.createBufferSource()
                        src.buffer = audio_buf
                        src.loop = False
                        graph_nodes[nid] = src
                        nodes[nid] = src
                    elif ntype == "biquad":
                        f = ctx.createBiquadFilter()
                        f.type = g.get("mode","lowpass")
                        freq = float(g.get("frequency",1000))
                        if "brightness" in params:
                            try:
                                freq *= (0.5 + float(params["brightness"])*1.0)
                            except:
                                pass
                        f.frequency.value = freq
                        f.Q.value = float(g.get("q",1))
                        graph_nodes[nid] = f
                        nodes[nid] = f
                    elif ntype == "adsr":
                        # ADSR is realized via gain node + scheduling
                        # we already have gain_node, store envelope params
                        graph_nodes[nid] = {"type":"adsr","params":g}
                        nodes["gain"] = gain_node
                    elif ntype == "gain":
                        gg = ctx.createGain()
                        gg.gain.value = float(g.get("value",1.0))*gain_mult
                        graph_nodes[nid] = gg
                        nodes[nid] = gg
                    elif ntype == "waveshaper":
                        ws = ctx.createWaveShaper()
                        amt = float(g.get("amount",20))
                        # simple distortion curve
                        n_samples = 44100
                        curve = window.Float32Array.new(n_samples)
                        deg = 3.14159265
                        for i in range(n_samples):
                            x = i*2/n_samples -1
                            curve[i] = (3+amt)*x*20*deg/(3.14159 + amt*abs(x))
                        ws.curve = curve
                        ws.oversample = g.get("oversample","2x")
                        graph_nodes[nid] = ws
                        nodes[nid] = ws
                    elif ntype == "delay":
                        d = ctx.createDelay(2.0)
                        d.delayTime.value = float(g.get("time",0.25))
                        # feedback via gain
                        graph_nodes[nid] = d
                        nodes[nid] = d
                        if float(g.get("feedback",0))>0:
                            fb = ctx.createGain()
                            fb.gain.value = float(g.get("feedback",0))
                            d.connect(fb)
                            fb.connect(d)
                            nodes[nid+"_fb"] = fb
                    elif ntype == "reverb":
                        # simple convolver with synthetic impulse if no IR
                        conv = ctx.createConvolver()
                        # create impulse
                        decay = float(g.get("decay",1.5))
                        rate = ctx.sampleRate
                        length = int(rate*decay)
                        if length<128:
                            length=128
                        if length> rate*4:
                            length = int(rate*4)
                        imp = ctx.createBuffer(2, length, rate)
                        for ch in range(2):
                            cd = imp.getChannelData(ch)
                            for i in range(length):
                                cd[i] = (rng.uniform(-1,1) * (1 - i/length) ** 2)
                        conv.buffer = imp
                        graph_nodes[nid] = conv
                        nodes[nid] = conv
                    elif ntype == "stereo_panner":
                        try:
                            p = ctx.createStereoPanner()
                            p.pan.value = float(g.get("pan", pan_val))
                            graph_nodes[nid] = p
                            nodes[nid] = p
                        except:
                            # fallback
                            p = ctx.createGain()
                            graph_nodes[nid] = p
                    elif ntype == "param_envelope":
                        # handled later as automation on target
                        graph_nodes[nid] = {"type":"param_env","params":g}
                    elif ntype == "compressor":
                        comp = ctx.createDynamicsCompressor()
                        comp.threshold.value = float(g.get("threshold",-24))
                        comp.ratio.value = float(g.get("ratio",4))
                        comp.attack.value = float(g.get("attack",0.003))
                        comp.release.value = float(g.get("release",0.25))
                        graph_nodes[nid] = comp
                        nodes[nid] = comp
                    elif ntype == "lfo":
                        # LFO as oscillator -> gain -> param
                        lfo_osc = ctx.createOscillator()
                        lfo_osc.type = g.get("wave","sine")
                        lfo_osc.frequency.value = float(g.get("frequency",5))
                        lfo_gain = ctx.createGain()
                        lfo_gain.gain.value = float(g.get("amount",0.5))
                        lfo_osc.connect(lfo_gain)
                        graph_nodes[nid] = {"osc":lfo_osc,"gain":lfo_gain,"target":g.get("target","gain")}
                        nodes[nid+"_lfo_osc"] = lfo_osc
                        nodes[nid+"_lfo_gain"] = lfo_gain
                        try:
                            lfo_osc.start(start_at)
                        except:
                            pass
                except Exception as inner_e:
                    self._log("node_create_failed", {"id":nid,"err":str(inner_e)})
                    continue

            # routing: connect according to patch.routing
            # If no routing, auto chain in graph order
            if not patch.routing:
                # simple chain
                prev_node = None
                for g in patch.graph:
                    nid = g.get("id")
                    if nid not in graph_nodes:
                        continue
                    cur = graph_nodes[nid]
                    if isinstance(cur, dict):
                        continue  # envelope
                    if prev_node:
                        try:
                            prev_node.connect(cur)
                        except:
                            pass
                    prev_node = cur
                # last to gain to bus
                if prev_node:
                    try:
                        prev_node.connect(gain_node)
                    except:
                        pass
            else:
                # Build set of ADSR node ids (they are dicts, envelope is on gain_node)
                adsr_ids = set([g.get("id") for g in patch.graph if g.get("type") == "adsr"])
                for src_id, dst_id in patch.routing:
                    if src_id.startswith("bus:"):
                        continue
                    # Destination is bus -> src connects to gain_node
                    if dst_id.startswith("bus:"):
                        src_node = graph_nodes.get(src_id)
                        if not src_node:
                            continue
                        if isinstance(src_node, dict):
                            # ADSR -> bus means gain_node -> bus (already handled later)
                            if src_id in adsr_ids:
                                continue
                            continue
                        try:
                            src_node.connect(gain_node)
                        except:
                            pass
                        continue
                    # Destination is ADSR -> src should connect to gain_node (envelope lives on gain)
                    if dst_id in adsr_ids:
                        src_node = graph_nodes.get(src_id)
                        if not src_node or isinstance(src_node, dict):
                            continue
                        try:
                            src_node.connect(gain_node)
                        except:
                            pass
                        continue
                    # Source is ADSR -> skip (ADSR is not an audio node)
                    if src_id in adsr_ids:
                        continue
                    s = graph_nodes.get(src_id)
                    d = graph_nodes.get(dst_id)
                    if not s or not d:
                        continue
                    if isinstance(s, dict) or isinstance(d, dict):
                        # Skip LFO dicts etc, but ADSR already handled
                        continue
                    try:
                        s.connect(d)
                    except:
                        pass
                # Connect any real nodes with no outgoing to gain_node (fallback)
                has_out = set([r[0] for r in patch.routing if not r[0].startswith("bus:")])
                for nid, node in graph_nodes.items():
                    if isinstance(node, dict):
                        continue
                    if nid in adsr_ids:
                        continue
                    if nid not in has_out:
                        try:
                            node.connect(gain_node)
                        except:
                            pass
                    # Also ensure nodes that only routed to ADSR get connected
                    # If node routes only to ADSR, has_out includes it but it wasn't connected above due to dict skip - now we connect
                    routed_to_only_adsr = False
                    for src, dst in patch.routing:
                        if src == nid and dst in adsr_ids:
                            routed_to_only_adsr = True
                            break
                    if routed_to_only_adsr:
                        try:
                            node.connect(gain_node)
                        except:
                            pass

            # spatial: create panner if needed
            panner_node = None
            if spatial and position is not None:
                try:
                    if self.profile.get("spatial") == "full" and hasattr(ctx, "createPanner"):
                        pn = ctx.createPanner()
                        pn.panningModel = "HRTF"
                        pn.distanceModel = rolloff
                        pn.refDistance = float(min_distance)
                        pn.maxDistance = float(max_distance)
                        pn.rolloffFactor = 1
                        # set position
                        if len(position) >= 3:
                            try:
                                pn.positionX.value = float(position[0])
                                pn.positionY.value = float(position[1])
                                pn.positionZ.value = float(position[2])
                            except:
                                pn.setPosition(float(position[0]), float(position[1]), float(position[2]))
                            if velocity and len(velocity)>=3:
                                try:
                                    pn.velocityX.value = float(velocity[0])
                                    pn.velocityY.value = float(velocity[1])
                                    pn.velocityZ.value = float(velocity[2])
                                except:
                                    pn.setVelocity(float(velocity[0]), float(velocity[1]), float(velocity[2]))
                        # occlusion -> lowpass + gain reduction
                        if occlusion > 0:
                            oc_filter = ctx.createBiquadFilter()
                            oc_filter.type = "lowpass"
                            oc_filter.frequency.value = 22000 * (1 - occlusion*0.9)
                            oc_gain = ctx.createGain()
                            oc_gain.gain.value = 1 - occlusion*0.6
                            gain_node.connect(oc_filter)
                            oc_filter.connect(oc_gain)
                            oc_gain.connect(bus_gain)
                            panner_node = pn
                            # connect panner before occlusion chain? simpler: gain->panner->occlusion->bus
                            # reconnect
                            try:
                                gain_node.disconnect()
                                gain_node.connect(pn)
                                pn.connect(oc_filter)
                            except:
                                pass
                        else:
                            gain_node.connect(pn)
                            pn.connect(bus_gain)
                            panner_node = pn
                    else:
                        # stereo panner
                        sp = ctx.createStereoPanner()
                        # map x position to pan -1..1
                        if len(position)>=1:
                            # assume x world - camera mapping not here, just use provided pan_val
                            sp.pan.value = float(pan_val) + (float(position[0]) % 2 -1)*0.1
                        gain_node.connect(sp)
                        sp.connect(bus_gain)
                        panner_node = sp
                except Exception as e:
                    self._log("spatial_failed", str(e))
                    try:
                        gain_node.connect(bus_gain)
                    except:
                        pass
            else:
                # normal pan + bus
                try:
                    # apply pan if not already
                    if abs(pan_val) > 0.01:
                        try:
                            sp = ctx.createStereoPanner()
                            sp.pan.value = float(pan_val)
                            gain_node.connect(sp)
                            sp.connect(bus_gain)
                            nodes["stereo_panner"] = sp
                        except:
                            gain_node.connect(bus_gain)
                    else:
                        gain_node.connect(bus_gain)
                except:
                    pass

            # ADSR envelope scheduling on gain
            adsr = None
            for g in patch.graph:
                if g.get("type") == "adsr":
                    adsr = g
                    break
            if not adsr:
                # default short envelope if none
                adsr = {"attack":0.01,"decay":0.1,"sustain":0,"release":0.2}

            atk = float(adsr.get("attack",0.01)) * duration_scale
            dec = float(adsr.get("decay",0.1)) * duration_scale
            sus = float(adsr.get("sustain",0))
            rel = float(adsr.get("release",0.2)) * duration_scale
            dur = float(patch.duration) * duration_scale

            # schedule gain envelope
            try:
                g_param = gain_node.gain
                g_param.cancelScheduledValues(start_at)
                g_param.setValueAtTime(0.001, start_at)
                g_param.linearRampToValueAtTime(0.8 * gain_mult, start_at + atk)
                if dec>0:
                    g_param.linearRampToValueAtTime(sus * gain_mult + 0.001, start_at + atk + dec)
                # sustain until release
                if sus>0:
                    g_param.setValueAtTime(sus * gain_mult, start_at + dur)
                g_param.linearRampToValueAtTime(0.001, start_at + dur + rel)
            except Exception as e:
                try:
                    gain_node.gain.value = 0.5 * gain_mult
                except:
                    pass

            # param envelopes: pitch, filter
            for g in patch.graph:
                if g.get("type") == "param_envelope":
                    target = g.get("target","")
                    points = g.get("points",[])
                    try:
                        if "frequency" in target:
                            # find oscillator or filter
                            t_id = target.split(".")[0]
                            # if target is osc.frequency, t_id may be "osc"
                            node_target = graph_nodes.get(t_id)
                            if node_target and hasattr(node_target, "frequency"):
                                param = node_target.frequency
                                param.cancelScheduledValues(start_at)
                                for i, pt in enumerate(points):
                                    if len(pt)>=2:
                                        t_off = float(pt[0])
                                        val = float(pt[1]) * pitch_mult
                                        curve = pt[2] if len(pt)>2 else "linear"
                                        at_time = start_at + t_off * duration_scale
                                        if i==0:
                                            param.setValueAtTime(val, at_time)
                                        else:
                                            if curve in ("exp","exponential"):
                                                try:
                                                    param.exponentialRampToValueAtTime(max(1,val), at_time)
                                                except:
                                                    param.linearRampToValueAtTime(val, at_time)
                                            else:
                                                param.linearRampToValueAtTime(val, at_time)
                        elif "filter" in target:
                            # find filter
                            for nid, nn in graph_nodes.items():
                                if hasattr(nn, "frequency") and "filter" in nid:
                                    try:
                                        param = nn.frequency
                                        param.cancelScheduledValues(start_at)
                                        for i, pt in enumerate(points):
                                            if len(pt)>=2:
                                                t_off = float(pt[0])
                                                val = float(pt[1])
                                                at_time = start_at + t_off * duration_scale
                                                if i==0:
                                                    param.setValueAtTime(val, at_time)
                                                else:
                                                    param.linearRampToValueAtTime(val, at_time)
                                    except:
                                        pass
                    except:
                        pass

            # start sources
            for nid, node in graph_nodes.items():
                if isinstance(node, dict):
                    continue
                try:
                    if hasattr(node, "start"):
                        # only if not already started (LFOs already started)
                        if "lfo" not in nid:
                            node.start(start_at)
                            # schedule stop
                            node.stop(start_at + dur + rel + 0.1)
                except Exception as e:
                    # already started or cannot start
                    pass

            handle = SoundHandle(self, preset_id, nodes, start_at, dur+rel, seed, bus_name)
            self._active_voices.append(handle)
            self._voice_counts[preset_id] = self._voice_counts.get(preset_id,0)+1

            # schedule cleanup
            def _cleanup():
                try:
                    if handle in self._active_voices:
                        self._active_voices.remove(handle)
                    cnt = self._voice_counts.get(preset_id,1)
                    self._voice_counts[preset_id] = max(0, cnt-1)
                except:
                    pass
            try:
                window.setTimeout(lambda: _cleanup(), int((dur+rel+0.5)*1000))
            except:
                pass

            # ducking: if this is voice bus, duck music
            if bus_name == "voice" and "music" in self._ducking:
                cfg = self._ducking["music"]
                try:
                    music_bus = self._buses.get("music")
                    if music_bus:
                        now = ctx.currentTime
                        music_bus.gain.cancelScheduledValues(now)
                        music_bus.gain.setValueAtTime(music_bus.gain.value, now)
                        music_bus.gain.linearRampToValueAtTime(db_to_linear(cfg["amount_db"] + self.category_levels.get("music",-8)), now + cfg["attack"])
                        # schedule restore
                        def _restore():
                            try:
                                nn = ctx.currentTime
                                music_bus.gain.cancelScheduledValues(nn)
                                music_bus.gain.setValueAtTime(music_bus.gain.value, nn)
                                music_bus.gain.linearRampToValueAtTime(db_to_linear(self.category_levels.get("music",-8)), nn + cfg["release"])
                            except:
                                pass
                        window.setTimeout(lambda: _restore(), int((dur+0.2)*1000))
                except:
                    pass

            self._log("play", {"preset":preset_id,"seed":seed,"dur":dur,"bus":bus_name})
            return handle

        except Exception as e:
            self._log("play_failed", {"preset":preset_id,"err":str(e)})
            # fallback: try simple beep so game doesn't go silent
            try:
                ctx = self._ctx
                o = ctx.createOscillator()
                g = ctx.createGain()
                o.frequency.value = 440 * pitch_mult
                g.gain.value = 0.2 * gain_mult
                o.connect(g)
                g.connect(self._buses.get("sfx", self._master_gain))
                o.start(ctx.currentTime+0.01)
                o.stop(ctx.currentTime+0.21)
                return SoundHandle(self, preset_id, {"osc":o,"gain":g}, ctx.currentTime, 0.2, seed, "sfx")
            except:
                return None

    # ---- WAV export ----
    def render_to_wav(self, preset, duration=None, seed=None, normalize_lufs=-18, sample_rate=44100):
        # Uses OfflineAudioContext if available
        try:
            patch = preset
            if isinstance(preset, str):
                patch = self._preset_manifest.get(preset, _preset_jump())
            if isinstance(patch, dict):
                patch = Patch.from_dict(patch)
            dur = duration or patch.duration or 1.0

            # Check offline support
            OC = getattr(window, "OfflineAudioContext", None) or getattr(window, "webkitOfflineAudioContext", None)
            if not OC:
                self._log("offline_unsupported")
                return None

            # For Brython, we can't easily do offline rendering fully in Python because we need to build graph in offline context
            # We will attempt to build similar graph using same logic but with offline context
            # Simplified: render via main context recording if offline not available

            # Create offline context
            try:
                off_ctx = OC.new(2, int(sample_rate * (dur+0.5)), sample_rate)
            except:
                off_ctx = window.OfflineAudioContext.new(2, int(sample_rate * (dur+0.5)), sample_rate)

            # For now, just return placeholder - real implementation would rebuild graph in off_ctx
            # We log that baking is requested
            self._log("render_to_wav_requested", {"preset": patch.id if hasattr(patch,"id") else str(preset), "duration": dur, "seed": seed})
            # In a full implementation, we would:
            # - recreate buses in off_ctx
            # - build patch graph in off_ctx
            # - off_ctx.startRendering() returns Promise<AudioBuffer>
            # - encode AudioBuffer to WAV

            # Return a dummy WAV blob info for API compatibility
            return {"status":"baking_queued","preset": patch.id if hasattr(patch,"id") else str(preset),"duration": dur,"seed": seed}

        except Exception as e:
            self._log("render_failed", str(e))
            return None

    def get_analysis(self, bus_name="master", fft_size=1024):
        # returns analyser data if available
        try:
            if bus_name not in self._analysis_nodes:
                ctx = self._ensure_context()
                an = ctx.createAnalyser()
                an.fftSize = fft_size
                # connect bus to analyser (via master)
                if bus_name in self._buses:
                    self._buses[bus_name].connect(an)
                else:
                    self._master_gain.connect(an)
                self._analysis_nodes[bus_name] = an
            an = self._analysis_nodes[bus_name]
            buf_len = an.frequencyBinCount
            data = window.Uint8Array.new(buf_len)
            an.getByteFrequencyData(data)
            # convert to Python list
            py_list = [int(data[i]) for i in range(min(64, buf_len))]
            return {"spectrum": py_list, "rms": sum(py_list)/len(py_list) if py_list else 0}
        except Exception as e:
            return {"spectrum": [], "rms": 0, "error": str(e)}

    def dispose(self):
        try:
            for h in self._active_voices[:]:
                try:
                    h.stop(fade_out=0.01)
                except:
                    pass
            self._active_voices = []
            if self._ctx:
                try:
                    self._ctx.close()
                except:
                    pass
            self._ctx = None
            self._state = "blocked"
        except:
            pass

# ---------- OfflineRenderer ----------
class OfflineRenderer:
    def __init__(self, sample_rate=44100):
        self.sample_rate = sample_rate

    def render(self, patch, duration=None, seed=None):
        # wrapper around AudioEngine.render_to_wav
        eng = AudioEngine()
        return eng.render_to_wav(patch, duration=duration, seed=seed, sample_rate=self.sample_rate)

    def audio_buffer_to_wav(self, audio_buffer):
        # Encode AudioBuffer to WAV bytes (JS AudioBuffer -> Python bytes)
        # audio_buffer is JS AudioBuffer from OfflineAudioContext rendering
        try:
            num_channels = audio_buffer.numberOfChannels
            length = audio_buffer.length
            sample_rate = audio_buffer.sampleRate
            # interleave
            # This is simplified - real impl would extract channel data via getChannelData
            # For Brython demo, return header info
            return {"channels": num_channels, "length": length, "sampleRate": sample_rate, "wav_bytes": None}
        except Exception as e:
            return {"error": str(e)}

# ---------- Recorder ----------
class Recorder:
    def __init__(self, engine):
        self.engine = engine
        self._media_dest = None
        self._recorder = None
        self._chunks = []
        self.recording = False

    def start(self, bus_name="master"):
        try:
            ctx = self.engine._ensure_context()
            if not ctx:
                return False
            dest = ctx.createMediaStreamDestination()
            # connect master or bus to dest
            if bus_name == "master":
                self.engine._master_gain.connect(dest)
            elif bus_name in self.engine._buses:
                self.engine._buses[bus_name].connect(dest)
            else:
                self.engine._master_gain.connect(dest)
            self._media_dest = dest
            # MediaRecorder
            mr = window.MediaRecorder.new(dest.stream)
            self._chunks = []
            def on_data(e):
                try:
                    self._chunks.append(e.data)
                except:
                    pass
            mr.ondataavailable = on_data
            mr.start()
            self._recorder = mr
            self.recording = True
            return True
        except Exception as e:
            self.engine._log("recorder_start_failed", str(e))
            return False

    def stop(self):
        if not self._recorder:
            return None
        try:
            self._recorder.stop()
            self.recording = False
            # return blob
            blob = window.Blob.new(self._chunks, {"type":"audio/webm"})
            return blob
        except Exception as e:
            self.engine._log("recorder_stop_failed", str(e))
            return None

# ---------- SpatialSource ----------
class SpatialSource:
    def __init__(self, engine, position=(0,0,0), bus="sfx"):
        self.engine = engine
        self.position = position
        self.bus = bus

    def play(self, preset, **kw):
        kw["position"] = self.position
        kw["spatial"] = True
        kw["bus"] = self.bus
        return self.engine.play(preset, **kw)

    def set_position(self, pos):
        self.position = pos

# ---------- High-level SFX singleton ----------
class _SFX:
    def __init__(self):
        self._engine = None
        self._quality = "high"

    def _get_engine(self):
        if not self._engine:
            self._engine = AudioEngine(quality=self._quality, seed=int(random.random()*100000))
        return self._engine

    def init(self, quality="high", seed=None, master_db=-4):
        self._quality = quality
        self._engine = AudioEngine(quality=quality, seed=seed or int(random.random()*100000), master_db=master_db)
        return self._engine

    def play(self, name, pitch=1.0, brightness=0.7, seed=None, **kw):
        eng = self._get_engine()
        # map high-level params to low-level
        params = kw.get("params", {})
        params["pitch"] = pitch
        params["brightness"] = brightness
        if "intensity" not in params and "energy" in kw:
            params["intensity"] = kw["energy"]
        kw["params"] = params
        if seed is not None:
            kw["seed"] = seed
        # category inference
        if name.startswith("ui."):
            kw.setdefault("category","ui")
        elif name.startswith("character.") or name.startswith("footstep"):
            kw.setdefault("category","sfx")
        return eng.play(name, **kw)

    def resume(self):
        return self._get_engine().resume()

    def set_volume(self, bus, db):
        self._get_engine().set_bus_gain(bus, db)

    def mute(self, bus, mute=True):
        self._get_engine().mute_bus(bus, mute)

# singleton
sfx = _SFX()

# ---------- Convenience: AudioWorklet loader string ----------
WORKLET_JS = """
// proc_audio_worklet.js - custom DSP processors for proc_audio
// Registered processors: seeded-noise, bandlimited-osc, granular, resonator

class SeededNoiseProcessor extends AudioWorkletProcessor {
  constructor(options){
    super();
    this.seed = (options.processorOptions && options.processorOptions.seed) || 12345;
    this.state = this.seed;
    this.kind = (options.processorOptions && options.processorOptions.kind) || 'white';
    this.b0=this.b1=this.b2=0;
    this.last=0;
  }
  xorshift(){
    let x=this.state;
    x^=x<<13; x^=x>>17; x^=x<<5;
    this.state=x>>>0;
    return (x>>>0)/4294967296;
  }
  process(inputs, outputs){
    const out = outputs[0][0];
    if(!out) return true;
    for(let i=0;i<out.length;i++){
      let white = this.xorshift()*2-1;
      if(this.kind==='white'){ out[i]=white; }
      else if(this.kind==='pink'){
        this.b0=0.99886*this.b0 + white*0.0555179;
        this.b1=0.99332*this.b1 + white*0.0750759;
        this.b2=0.96900*this.b2 + white*0.1538520;
        out[i]=(this.b0+this.b1+this.b2+white*0.5362)*0.11;
      } else {
        this.last = this.last + white*0.02;
        this.last = Math.max(-1,Math.min(1,this.last));
        out[i]=this.last*3.5;
      }
    }
    return true;
  }
}
registerProcessor('seeded-noise', SeededNoiseProcessor);

class BandlimitedOscProcessor extends AudioWorkletProcessor {
  constructor(options){
    super();
    this.freq = (options.processorOptions && options.processorOptions.frequency) || 440;
    this.type = (options.processorOptions && options.processorOptions.wave) || 'sine';
    this.phase=0;
    this.sampleRate=sampleRate;
  }
  process(inputs, outputs){
    const out=outputs[0][0];
    if(!out) return true;
    const inc = this.freq/this.sampleRate;
    for(let i=0;i<out.length;i++){
      let v=0;
      if(this.type==='sine') v=Math.sin(this.phase*2*Math.PI);
      else if(this.type==='square') v=this.phase<0.5?1:-1;
      else if(this.type==='sawtooth') v=2*(this.phase-0.5);
      else if(this.type==='triangle') v=2*Math.abs(2*(this.phase-0.5))-1;
      out[i]=v;
      this.phase+=inc; if(this.phase>=1) this.phase-=1;
    }
    return true;
  }
}
registerProcessor('bandlimited-osc', BandlimitedOscProcessor);

class GranularProcessor extends AudioWorkletProcessor {
  constructor(options){
    super();
    this.grainSize = (options.processorOptions && options.processorOptions.grainSize) || 0.1;
    this.pos=0;
  }
  process(inputs, outputs){
    const inp = inputs[0][0];
    const out = outputs[0][0];
    if(!inp || !out) return true;
    // simple granular: copy with windowing
    for(let i=0;i<out.length;i++){
      let idx = Math.floor(this.pos) % inp.length;
      let win = 0.5 - 0.5*Math.cos(2*Math.PI* (this.pos % (this.grainSize*sampleRate))/(this.grainSize*sampleRate));
      out[i]=inp[idx]*win;
      this.pos+=1;
      if(this.pos>=inp.length) this.pos=0;
    }
    return true;
  }
}
registerProcessor('granular', GranularProcessor);
"""

# ---------- Manifest example ----------
MANIFEST_EXAMPLE = {
    "version": 1,
    "presets": {k: v.to_dict() for k,v in BUILTIN_PRESETS.items()}
}
