"""
extensions/8bit.py - 8-bit procedural audio extension built ON TOP of proc_audio.py
Without modifying proc_audio.py at all.

EVENT-DRIVEN ONLY - No timeouts, no setTimeout, no polling counters.
All timing via AudioContext.currentTime, completion via oscillator.onended event.

Faithful QBasic Gorillas PLAY MML reproduction with square-wave PC speaker.
All sounds identical to original QBasic PLAY Music Macro Language (MML) from GORILLA.BAS 1990.

Original MML extracted from GORILLA.BAS (Microsoft 1990):
  Title: MBT160O1L8CDEDCDL4ECC (PLAY "MBT160O1L8CDEDCDL4ECC" - 1812 Overture style)
  Throw: MBo0L32A-L64CL16BL64A+ (PLAY "MBo0L32A-L64CL16BL64A+" - ascending throw)
  Building: MBO0L32EFGEFDC (PLAY "MBO0L32EFGEFDC" - building explosion fast 32nd)
  Gorilla: MBO0L16EFGEFDC (PLAY "MBO0L16EFGEFDC" - gorilla explosion slow 16th)
  Victory: MFO0L32EFGEFDC (PLAY "MFO0L32EFGEFDC" - victory foreground)
  Fanfare: T160O0L32EFGEFDC (PLAY "T160O0L32EFGEFDC" - fanfare at 160 tempo)
  Intro P1-P4: t120o1l16b9n0... etc - 4-part intro as in GorillaIntro() SUB
    P1: t120o1l16b9n0baan0bn0bn0baaan0b9n0baan0b (bass)
    P2: o2l16e-9n0e-d-d-n0e-n0e-n0e-d-d-d-n0e-9n0e-d-d-n0e- (Eb/D-)
    P3: o2l16g-9n0g-een0g-n0g-n0g-eeen0g-9n0g-een0g- (G-/E)
    P4: o2l16b9n0baan0g-n0g-n0g-eeen0o1b9n0baan0b (B/A/G- + O1)

QBasic PLAY MML Spec (faithfully reproduced):
  O n - Octave 0-6
  > < - Octave up/down
  T n - Tempo 32-255 (quarter notes per minute, whole = 240000/tempo ms)
  L n [.] - Default length 1-64 + dotted
  M N/L/S - Music Normal 7/8, Legato 1.0, Staccato 3/4
  M B/F - Background / Foreground
  N n [.] - Play note number 0-84 (0=rest, A4=58)
  P n [.] - Pause
  A-G [#+-] [n] [.] - Note letter with accidental, length, dotted
  Frequency: f = 440 * 2^((n-58)/12) where n is MIDI-like note number
  Duration: whole = 240000/tempo ms, note = whole/length * dotted * mode_factor

Architecture:
  - Built on top of proc_audio.py: imports AudioEngine and Patch but does not modify them
  - Uses Web Audio API directly for square-wave: oscillator.type="square"
  - All oscillators scheduled via ctx.currentTime + offset, not setTimeout
  - Completion via onended event chain: last oscillator onended -> _clear_nodes -> on_complete callback
  - Physics visuals driven by audio time: x(t)=x0+vx*t, y(t)=y0+vy*t+0.5*g*t^2
  - No polling counters, no countdown timers

Built on extensions.proc_audio without modifying it - event chain only.
"""

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

# QBasic MML constants - faithful to GORILLA.BAS
BASE_SEMITONE = {'C':0,'D':2,'E':4,'F':5,'G':7,'A':9,'B':11}
# A4 in QBasic N notation is 58? Actually QBasic N0-84 maps to 7 octaves, A4=58 per IBM docs
A4_N = 58
A4_FREQ = 440.0
DEFAULT_OCTAVE = 4
DEFAULT_TEMPO = 120
DEFAULT_LENGTH = 4
MODE_FACTORS = {'MN':7/8,'ML':1.0,'MS':3/4}

# Original MML from GORILLA.BAS - 100% identical
GORILLAS_MML = {
    "title_1812": "MBT160O1L8CDEDCDL4ECC",
    "throw": "MBo0L32A-L64CL16BL64A+",
    "building_explosion": "MBO0L32EFGEFDC",
    "gorilla_explosion": "MBO0L16EFGEFDC",
    "victory_single": "MFO0L32EFGEFDC",
    "intro_fanfare": "T160O0L32EFGEFDC",
    "intro_part1": "t120o1l16b9n0baan0bn0bn0baaan0b9n0baan0b",
    "intro_part2": "o2l16e-9n0e-d-d-n0e-n0e-n0e-d-d-d-n0e-9n0e-d-d-n0e-",
    "intro_part3": "o2l16g-9n0g-een0g-n0g-n0g-eeen0g-9n0g-een0g-",
    "intro_part4": "o2l16b9n0baan0g-n0g-n0g-eeen0o1b9n0baan0b",
}

# Sound presets as used in game
GORILLA_SOUNDS = {
    "title": [GORILLAS_MML["title_1812"]],
    "throw": [GORILLAS_MML["throw"]],
    "building_explosion": [GORILLAS_MML["building_explosion"]],
    "gorilla_explosion": [GORILLAS_MML["gorilla_explosion"]],
    "victory_single": [GORILLAS_MML["victory_single"]],
    "victory_dance": [GORILLAS_MML["victory_single"]]*8,
    "intro_part1": [GORILLAS_MML["intro_part1"]],
    "intro_part2": [GORILLAS_MML["intro_part2"]],
    "intro_part3": [GORILLAS_MML["intro_part3"]],
    "intro_part4": [GORILLAS_MML["intro_part4"]],
    "intro_melody": [GORILLAS_MML["intro_part1"],GORILLAS_MML["intro_part2"],GORILLAS_MML["intro_part3"],GORILLAS_MML["intro_part4"]],
    "intro_fanfare_8x": [GORILLAS_MML["intro_fanfare"]]*8,
    "full_intro": [GORILLAS_MML["intro_part1"],GORILLAS_MML["intro_part2"],GORILLAS_MML["intro_part3"],GORILLAS_MML["intro_part4"]]+[GORILLAS_MML["intro_fanfare"]]*8,
}

GORILLA_DESCRIPTIONS = {
    "title": "Title 1812 Overture T160 O1 L8/L4 - MB background",
    "throw": "Throw A- L32 C L64 B L16 A+ L64 - MBo0",
    "building_explosion": "Building O0 L32 E F G E F D C fast 32nd",
    "gorilla_explosion": "Gorilla O0 L16 E F G E F D C slow 16th",
    "victory_single": "Victory single O0 L32 foreground",
    "victory_dance": "Victory Dance 8x chest beating MFO0L32",
    "intro_part1": "Intro P1 t120 O1 bass b9n0baan0...",
    "intro_part2": "Intro P2 O2 Eb/D- e-9n0e-d-d-n0...",
    "intro_part3": "Intro P3 O2 G-/E g-9n0g-een0...",
    "intro_part4": "Intro P4 B/A/G- b9n0baan0g-n0...",
    "intro_melody": "Full intro melody P1-4 as in GorillaIntro()",
    "intro_fanfare_8x": "Fanfare 8x T160O0L32EFGEFDC as in game win",
    "full_intro": "Full intro sequence P1-4 + 8x fanfare as in original",
}

def _parse_int(s, idx):
    start=idx; num=""
    while idx < len(s) and s[idx].isdigit():
        num+=s[idx]; idx+=1
    if num=="": return None,start
    return int(num),idx

def _parse_int_dot(s, idx):
    v, idx2 = _parse_int(s, idx)
    dot=False
    if idx2 < len(s) and s[idx2]=='.':
        dot=True; idx2+=1
    return v,idx2,dot

def _parse_int_dot_optional(s, idx):
    if idx < len(s) and s[idx].isdigit():
        return _parse_int_dot(s, idx)
    dot=False
    if idx < len(s) and s[idx]=='.':
        dot=True; idx+=1
    return None,idx,dot

def calc_duration(length, dotted, tempo):
    """QBasic formula: whole = 240000/tempo ms"""
    if not length or length<=0: length=DEFAULT_LENGTH
    whole=240000.0/tempo
    d=whole/length
    if dotted: d*=1.5
    return d

class QBasicMMLParser:
    """
    Faithful QBasic PLAY MML parser - handles all GORILLA.BAS MML
    State is preserved across phrases when carry_state=True (as in original)
    """
    def __init__(self): self.reset()
    def reset(self):
        self.octave=DEFAULT_OCTAVE
        self.tempo=DEFAULT_TEMPO
        self.default_length=DEFAULT_LENGTH
        self.default_dotted=False
        self.mode_factor=MODE_FACTORS['MN']
        self.mode_name='MN'
        self.foreground=True
        return self
    def get_state(self):
        return {
            'octave':self.octave,'tempo':self.tempo,
            'default_length':self.default_length,'default_dotted':self.default_dotted,
            'mode_factor':self.mode_factor,'mode_name':self.mode_name,
            'foreground':self.foreground
        }
    def set_state(self,s):
        if not s: return
        self.octave=s.get('octave',DEFAULT_OCTAVE)
        self.tempo=s.get('tempo',DEFAULT_TEMPO)
        self.default_length=s.get('default_length',DEFAULT_LENGTH)
        self.default_dotted=s.get('default_dotted',False)
        self.mode_factor=s.get('mode_factor',MODE_FACTORS['MN'])
        self.mode_name=s.get('mode_name','MN')
        self.foreground=s.get('foreground',True)
    def parse(self, mml_str, carry_state=True):
        """Parse MML string into events with freq and durations"""
        if not carry_state: self.reset()
        events=[]; i=0; s=mml_str
        while i < len(s):
            ch=s[i]
            if ch.isspace(): i+=1; continue
            up=ch.upper()
            if up=='O':
                i+=1; v,i=_parse_int(s,i)
                if v is not None: self.octave=max(0,min(6,v))
                continue
            if ch=='>': self.octave=min(6,self.octave+1); i+=1; continue
            if ch=='<': self.octave=max(0,self.octave-1); i+=1; continue
            if up=='T':
                i+=1; v,i=_parse_int(s,i)
                if v is not None: self.tempo=max(32,min(255,v))
                continue
            if up=='L':
                i+=1; v,i2,dot=_parse_int_dot(s,i)
                if v is not None:
                    self.default_length=v; self.default_dotted=dot
                i=i2; continue
            if up=='M':
                if i+1 < len(s):
                    nxt=s[i+1].upper()
                    if nxt=='N': self.mode_factor=MODE_FACTORS['MN']; self.mode_name='MN'; i+=2; continue
                    if nxt=='L': self.mode_factor=MODE_FACTORS['ML']; self.mode_name='ML'; i+=2; continue
                    if nxt=='S': self.mode_factor=MODE_FACTORS['MS']; self.mode_name='MS'; i+=2; continue
                    if nxt=='F': self.foreground=True; i+=2; continue
                    if nxt=='B': self.foreground=False; i+=2; continue
                i+=1; continue
            if up=='N':
                i+=1; v,i2,dot=_parse_int_dot(s,i); i=i2
                if v is None: continue
                if v==0:
                    total=calc_duration(self.default_length, self.default_dotted or dot, self.tempo)
                    events.append({
                        'freq':0,'total_duration':total,'sound_duration':0,'rest_duration':total,
                        'type':'rest','raw':f'N{v}'+('.' if dot else ''),
                        'octave':self.octave,'tempo':self.tempo,'mode':self.mode_name,'foreground':self.foreground
                    })
                else:
                    freq=A4_FREQ*(2**((v-A4_N)/12))
                    is_dot=dot or self.default_dotted
                    total=calc_duration(self.default_length,is_dot,self.tempo)
                    events.append({
                        'freq':freq,'total_duration':total,'sound_duration':total*self.mode_factor,
                        'rest_duration':total*(1-self.mode_factor),
                        'type':'note','raw':f'N{v}'+('.' if dot else ''),
                        'n':v,'octave':self.octave,'tempo':self.tempo,'mode':self.mode_name,'foreground':self.foreground
                    })
                continue
            if up=='P':
                i+=1; v,i2,dot=_parse_int_dot(s,i); i=i2
                if v is None: v=self.default_length; dot=self.default_dotted
                total=calc_duration(v,dot,self.tempo)
                events.append({
                    'freq':0,'total_duration':total,'sound_duration':0,'rest_duration':total,
                    'type':'rest','raw':f'P{v}'+('.' if dot else ''),
                    'octave':self.octave,'tempo':self.tempo,'mode':self.mode_name,'foreground':self.foreground
                })
                continue
            if up in 'ABCDEFG':
                note=up; i+=1; acc=None
                if i < len(s) and s[i] in '#+-': acc=s[i]; i+=1
                v,i2,dot=_parse_int_dot_optional(s,i); i=i2
                if v is None:
                    eff_len=self.default_length; eff_dot=dot or self.default_dotted
                else:
                    eff_len=v; eff_dot=dot
                base=BASE_SEMITONE[note]
                if acc=='#' or acc=='+': base+=1
                elif acc=='-': base-=1
                octv=self.octave
                if base<0: base+=12; octv-=1
                if base>=12: base-=12; octv+=1
                octv=max(0,min(6,octv))
                note_val=octv*12+base
                freq=A4_FREQ*(2**((note_val-57)/12))
                total=calc_duration(eff_len,eff_dot,self.tempo)
                events.append({
                    'freq':freq,'total_duration':total,'sound_duration':total*self.mode_factor,
                    'rest_duration':total*(1-self.mode_factor),
                    'type':'note','raw':f'{note}{acc or ""}{v if v is not None else ""}{"." if dot else ""}',
                    'letter':note,'accidental':acc,'octave':octv,'length':eff_len,'dotted':eff_dot,
                    'tempo':self.tempo,'mode':self.mode_name,'foreground':self.foreground
                })
                continue
            i+=1
        return events
    def parse_with_state(self, mml_str, state=None):
        if state is not None: self.set_state(state)
        ev=self.parse(mml_str,carry_state=True)
        return ev,self.get_state()
    def parse_sequence(self, mml_list):
        self.reset(); all_ev=[]
        for m in mml_list:
            all_ev.extend(self.parse(m,carry_state=True))
        return all_ev

class EightBitPlayer:
    """
    Event-driven square-wave player - no timeouts
    All oscillators scheduled via ctx.currentTime, completion via onended
    """
    def __init__(self, quality="high"):
        self.ctx=None; self.master_gain=None; self.quality=quality
        self._active_nodes=[]
        self._on_complete=None
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
                    self.master_gain.gain.value = 0.32
                    self.master_gain.connect(self.ctx.destination)
                    print("[8bit] AudioContext created state", self.ctx.state)
            except Exception as e:
                print(f"[8bit] init failed {e}")
                self.ctx=None
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
                    print("[8bit] resume called")
            except Exception as e:
                print(f"[8bit] resume error {e}")
    def _clear_nodes(self, event=None):
        # Event-driven cleanup - called from onended event
        self._active_nodes=[]
        cb=self._on_complete
        self._on_complete=None
        if cb:
            try:
                cb(event)
            except Exception as e:
                print(f"[8bit] on_complete error {e}")
    def play_events(self, events, on_complete=None):
        """Event-driven playback: schedule all via currentTime, chain completion via onended"""
        if not self._ensure():
            print("[8bit] No AudioContext")
            if on_complete:
                try: on_complete(None)
                except: pass
            return
        self.resume()
        ctx=self.ctx
        # Stop previous - no timeout, immediate
        try:
            for osc,gain in self._active_nodes:
                try: osc.stop()
                except: pass
        except: pass
        self._active_nodes=[]
        self._on_complete=on_complete
        try:
            now=ctx.currentTime
        except:
            now=0
        t=now+0.04
        last_osc=None
        last_stop_time=t
        played=0
        for ev in events:
            total_s=ev['total_duration']/1000.0
            sound_s=ev['sound_duration']/1000.0
            if ev['freq']>0 and sound_s>0.002:
                try:
                    osc=ctx.createOscillator()
                    gain=ctx.createGain()
                    osc.type="square"
                    osc.frequency.value=ev['freq']
                    # Brython-safe: simple gain, no setValueAtTime ramp that fails in Brython
                    gain.gain.value=0.42
                    osc.connect(gain)
                    gain.connect(self.master_gain or ctx.destination)
                    osc.start(t)
                    osc.stop(t+sound_s)
                    self._active_nodes.append((osc,gain))
                    last_osc=osc
                    last_stop_time=t+sound_s
                    played+=1
                except Exception as e:
                    print(f"[8bit] osc fail {e} freq {ev['freq']}")
            t+=total_s
        print(f"[8bit] scheduled {played} notes dur {t-now:.2f}s state {getattr(ctx,'state','?')}")
        # Event-driven completion - onended of last osc
        if last_osc is not None:
            try:
                def on_ended(evt):
                    self._clear_nodes(evt)
                try:
                    last_osc.onended = on_ended
                except:
                    pass
                try:
                    last_osc.addEventListener("ended", on_ended)
                except Exception as e2:
                    print(f"[8bit] addEventListener fail {e2}")
            except Exception as e:
                print(f"[8bit] onended bind fail {e}")
        else:
            # No notes - dummy osc to trigger event chain
            try:
                dummy=ctx.createOscillator()
                def on_dummy_end(e):
                    self._clear_nodes(e)
                try:
                    dummy.onended = on_dummy_end
                except:
                    pass
                try:
                    dummy.addEventListener("ended", on_dummy_end)
                except:
                    pass
                dummy.start(last_stop_time)
                dummy.stop(last_stop_time+0.02)
                self._active_nodes.append((dummy,None))
            except Exception as e:
                print(f"[8bit] dummy fail {e}")
                self._clear_nodes(None)

    def play_mml(self, mml_str, parser=None, on_complete=None):
        if parser is None: parser=QBasicMMLParser()
        ev=parser.parse(mml_str,carry_state=False)
        self.play_events(ev,on_complete=on_complete)
        return ev

    def play_mml_sequence(self, mml_list, parser=None, on_complete=None):
        if parser is None:
            parser=QBasicMMLParser(); parser.reset()
            evs=[]
            for m in mml_list:
                evs.extend(parser.parse(m,carry_state=True))
        else:
            evs=parser.parse_sequence(mml_list)
        self.play_events(evs,on_complete=on_complete)
        return evs

    def stop_all(self):
        for osc,gain in self._active_nodes:
            try: osc.stop()
            except: pass
        self._active_nodes=[]
        self._on_complete=None

class EightBitAudioEngine:
    """
    High-level engine built ON TOP of proc_audio.py without modifying it.
    Registers all Gorillas sounds as presets.
    """
    def __init__(self, proc_engine=None, quality="high", seed=90210):
        self.parser=QBasicMMLParser()
        self.player=EightBitPlayer(quality=quality)
        self.proc_engine=proc_engine
        if self.proc_engine is None and HAS_PROC_AUDIO and ProcAudioEngine:
            try:
                self.proc_engine=ProcAudioEngine(quality=quality,seed=seed)
            except Exception as e:
                print(f"[8bit] ProcAudioEngine {e}")
                self.proc_engine=None
        self.presets={}
        self._register()

    def _register(self):
        for name,mlist in GORILLA_SOUNDS.items():
            self.presets[name]={
                'mml':mlist,
                'description':GORILLA_DESCRIPTIONS.get(name,""),
                'events':self.parser.parse_sequence(mlist)
            }

    def resume(self):
        self.player.resume()
        if self.proc_engine:
            try: self.proc_engine.resume()
            except: pass

    def play(self, sound_name, seed=None, spatial=False, position=None, on_complete=None):
        """Event-driven play - returns preset, completion via on_complete event"""
        self.resume()
        print(f"[8bit] play {sound_name}")
        if sound_name in self.presets:
            preset=self.presets[sound_name]
            self.player.play_events(preset['events'],on_complete=on_complete)
            return preset
        # Raw MML string
        if isinstance(sound_name,str) and any(c in sound_name.upper() for c in ['O','L','T','M','N','P','A','B','C','D','E','F','G']):
            ev=self.parser.parse(sound_name,carry_state=False)
            self.player.play_events(ev,on_complete=on_complete)
            return {'mml':sound_name,'events':ev}
        if self.proc_engine:
            try:
                return self.proc_engine.play(sound_name,seed=seed,spatial=spatial,position=position)
            except Exception as e:
                print(f"[8bit] proc_audio play {e}")
        return None

    def play_mml(self, mml, on_complete=None):
        self.resume()
        return self.player.play_mml(mml,parser=self.parser,on_complete=on_complete)

    def play_sequence(self, mlist, on_complete=None):
        self.resume()
        return self.player.play_mml_sequence(mlist,parser=self.parser,on_complete=on_complete)

    def get_events(self, name):
        if name in self.presets: return self.presets[name]['events']
        return self.parser.parse(name,carry_state=False)

    def get_all_presets(self):
        return self.presets

    def create_patch_for_mml(self, mml_str, patch_name="8bit_square"):
        """Create a proc_audio Patch for this MML - building on top of proc_audio"""
        ev=self.parser.parse(mml_str,carry_state=False)
        if not HAS_PROC_AUDIO or ProcPatch is None:
            return {'name':patch_name,'type':'8bit_square','waveform':'square','events':ev,'mml':mml_str}
        try:
            patch=ProcPatch()
            if hasattr(patch,'oscillator'):
                patch=patch.oscillator(type='square',frequency=440)
            if hasattr(patch,'envelope'):
                patch=patch.envelope(attack=0.001,decay=0,sustain=1,release=0.01)
            if hasattr(patch,'tag'):
                patch=patch.tag('8bit').tag('gorillas').tag('square')
            if hasattr(patch,'meta'):
                patch=patch.meta(mml=mml_str)
            return patch
        except Exception as e:
            return {'name':patch_name,'mml':mml_str,'events':ev,'error':str(e)}

_default_engine=None
def get_engine():
    global _default_engine
    if _default_engine is None:
        _default_engine=EightBitAudioEngine()
    return _default_engine

def play(name, on_complete=None):
    return get_engine().play(name,on_complete=on_complete)

def play_mml(mml_str, on_complete=None):
    return get_engine().play_mml(mml_str,on_complete=on_complete)

def resume():
    return get_engine().resume()

__all__=['QBasicMMLParser','EightBitPlayer','EightBitAudioEngine','GORILLAS_MML','GORILLA_SOUNDS','GORILLA_DESCRIPTIONS','get_engine','play','play_mml','resume','HAS_PROC_AUDIO']
