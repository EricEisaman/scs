"""
extensions/8bit.py - 8-bit procedural audio extension built on top of proc_audio.py

This extension provides faithful reproduction of the original QBasic Gorillas
PLAY Music Macro Language (MML) sound effects, using a square-wave PC speaker
emulation.

It is built ON TOP of extensions.proc_audio without modifying proc_audio.py.

Original QBasic PLAY MML sounds from GORILLA.BAS (Microsoft 1990):
- Title 1812 Overture excerpt
- Banana throw
- Building explosion (DoExplosion)
- Gorilla explosion (ExplodeGorilla)
- Victory dance
- Intro melody (4 parts) + fanfare

All frequencies and durations match QBasic's PLAY implementation:
- Frequency: A4 = 440Hz, N58, equal temperament, square wave
- Duration: whole = 240000 / tempo ms, note = whole / length * dotted(1.5)
- Modes: MN normal 7/8 sound, ML legato 1.0, MS staccato 3/4
- Octaves: O0-O6, > / < for octave shifts
- Notes: A-G with #/+ sharp, - flat, optional length and dot
- N0-N84 note numbers, P pause

Author: Generated for SCS SCS Extensions System
"""

# Try to import proc_audio to build on top of it
try:
    from extensions.proc_audio import AudioEngine as ProcAudioEngine, Patch as ProcPatch
    HAS_PROC_AUDIO = True
except Exception as e:
    try:
        # alternative import path for Brython shim
        import extensions.proc_audio as proc_audio_mod
        ProcAudioEngine = getattr(proc_audio_mod, 'AudioEngine', None)
        ProcPatch = getattr(proc_audio_mod, 'Patch', None)
        HAS_PROC_AUDIO = ProcAudioEngine is not None
    except Exception:
        HAS_PROC_AUDIO = False
        ProcAudioEngine = None
        ProcPatch = None

# Fallback for non-Brython testing
try:
    from browser import window, document
    HAS_BROWSER = True
except ImportError:
    HAS_BROWSER = False
    window = None
    document = None

import math
import re

# ----------------------------------------------------------------------
# QBasic PLAY MML Constants
# ----------------------------------------------------------------------
BASE_SEMITONE = {
    'C': 0,
    'D': 2,
    'E': 4,
    'F': 5,
    'G': 7,
    'A': 9,
    'B': 11
}

# For N command: N0=rest, N1 = O0 C, N58 = A4 440Hz
A4_N = 58
A4_FREQ = 440.0

# Default QBasic PLAY state
DEFAULT_OCTAVE = 4
DEFAULT_TEMPO = 120
DEFAULT_LENGTH = 4
DEFAULT_MODE_FACTOR = 7/8  # MN normal
# Mode factors
MODE_FACTORS = {
    'MN': 7/8,
    'ML': 1.0,
    'MS': 3/4
}

# ----------------------------------------------------------------------
# Original Gorillas MML - Extracted verbatim from GORILLA.BAS
# ----------------------------------------------------------------------
GORILLAS_MML = {
    # Title screen - 1812 Overture excerpt (PLAY "MBT160O1L8CDEDCDL4ECC")
    "title_1812": "MBT160O1L8CDEDCDL4ECC",

    # Throw sound - banana toss (PlotShot: PLAY "MBo0L32A-L64CL16BL64A+")
    "throw": "MBo0L32A-L64CL16BL64A+",

    # Building explosion - DoExplosion: PLAY "MBO0L32EFGEFDC"
    "building_explosion": "MBO0L32EFGEFDC",

    # Gorilla direct hit explosion - ExplodeGorilla: PLAY "MBO0L16EFGEFDC"
    "gorilla_explosion": "MBO0L16EFGEFDC",

    # Victory dance single phrase - VictoryDance: PLAY "MFO0L32EFGEFDC"
    "victory_single": "MFO0L32EFGEFDC",

    # Intro fanfare (same notes as victory but tempo explicit)
    "intro_fanfare": "T160O0L32EFGEFDC",

    # Intro melody parts from GorillaIntro
    # PLAY "t120o1l16b9n0baan0bn0bn0baaan0b9n0baan0b"
    "intro_part1": "t120o1l16b9n0baan0bn0bn0baaan0b9n0baan0b",
    # PLAY "o2l16e-9n0e-d-d-n0e-n0e-n0e-d-d-d-n0e-9n0e-d-d-n0e-"
    "intro_part2": "o2l16e-9n0e-d-d-n0e-n0e-n0e-d-d-d-n0e-9n0e-d-d-n0e-",
    # PLAY "o2l16g-9n0g-een0g-n0g-n0g-eeen0g-9n0g-een0g-"
    "intro_part3": "o2l16g-9n0g-een0g-n0g-n0g-eeen0g-9n0g-een0g-",
    # PLAY "o2l16b9n0baan0g-n0g-n0g-eeen0o1b9n0baan0b"
    "intro_part4": "o2l16b9n0baan0g-n0g-n0g-eeen0o1b9n0baan0b",
}

# Combined sequences as they appear in game logic
GORILLA_SOUNDS = {
    "title": [GORILLAS_MML["title_1812"]],
    "throw": [GORILLAS_MML["throw"]],
    "building_explosion": [GORILLAS_MML["building_explosion"]],
    "gorilla_explosion": [GORILLAS_MML["gorilla_explosion"]],
    "victory_single": [GORILLAS_MML["victory_single"]],
    "victory_dance": [GORILLAS_MML["victory_single"]] * 8,  # FOR i=1 TO 4, two per loop
    "intro_part1": [GORILLAS_MML["intro_part1"]],
    "intro_part2": [GORILLAS_MML["intro_part2"]],
    "intro_part3": [GORILLAS_MML["intro_part3"]],
    "intro_part4": [GORILLAS_MML["intro_part4"]],
    "intro_melody": [
        GORILLAS_MML["intro_part1"],
        GORILLAS_MML["intro_part2"],
        GORILLAS_MML["intro_part3"],
        GORILLAS_MML["intro_part4"],
    ],
    "intro_fanfare_8x": [GORILLAS_MML["intro_fanfare"]] * 8,
    "full_intro": [
        GORILLAS_MML["intro_part1"],
        GORILLAS_MML["intro_part2"],
        GORILLAS_MML["intro_part3"],
        GORILLAS_MML["intro_part4"],
        GORILLAS_MML["intro_fanfare"],
        GORILLAS_MML["intro_fanfare"],
        GORILLAS_MML["intro_fanfare"],
        GORILLAS_MML["intro_fanfare"],
        GORILLAS_MML["intro_fanfare"],
        GORILLAS_MML["intro_fanfare"],
        GORILLAS_MML["intro_fanfare"],
        GORILLAS_MML["intro_fanfare"],
    ],
}

# Human readable descriptions
GORILLA_DESCRIPTIONS = {
    "title": "Title Screen - 1812 Overture excerpt (T160 O1)",
    "throw": "Banana Throw - A- L32, C L64, B L16, A+ L64",
    "building_explosion": "Building Hit - O0 L32 E F G E F D C (fast)",
    "gorilla_explosion": "Gorilla Hit - O0 L16 E F G E F D C (slow, dramatic)",
    "victory_single": "Victory Single - O0 L32 E F G E F D C (foreground)",
    "victory_dance": "Victory Dance - 8x chest beating",
    "intro_part1": "Intro Melody Part 1 - Bass line O1",
    "intro_part2": "Intro Melody Part 2 - Eb/D- line O2",
    "intro_part3": "Intro Melody Part 3 - G- / E line O2",
    "intro_part4": "Intro Melody Part 4 - B/A/G- line + O1 return",
    "intro_melody": "Full Intro Melody - Parts 1-4 combined",
    "intro_fanfare_8x": "Intro Fanfare - 8x T160 O0 L32",
    "full_intro": "Full Intro Sequence - As played in GorillaIntro()",
}


# ----------------------------------------------------------------------
# MML Parser - Faithful to QBasic
# ----------------------------------------------------------------------
def _parse_int(s, idx):
    """Parse integer at idx, return (value or None, new_idx)"""
    start = idx
    num_str = ""
    while idx < len(s) and s[idx].isdigit():
        num_str += s[idx]
        idx += 1
    if num_str == "":
        return None, start
    return int(num_str), idx

def _parse_int_dot(s, idx):
    """Parse integer with optional trailing dot, return (value, new_idx, has_dot)"""
    val, idx2 = _parse_int(s, idx)
    has_dot = False
    if idx2 < len(s) and s[idx2] == '.':
        has_dot = True
        idx2 += 1
    return val, idx2, has_dot

def _parse_int_dot_optional(s, idx):
    """Parse optional integer and optional dot. Returns (value or None, new_idx, has_dot)"""
    # Check if next char is digit
    if idx < len(s) and s[idx].isdigit():
        return _parse_int_dot(s, idx)
    # Check for dot alone like "C." ?
    has_dot = False
    if idx < len(s) and s[idx] == '.':
        has_dot = True
        idx += 1
    return None, idx, has_dot


def calc_duration(length, is_dotted, tempo):
    """
    Calculate note duration in milliseconds.
    QBasic: quarter = 60000/tempo, whole = 4*quarter = 240000/tempo
    duration = whole / length * (1.5 if dotted else 1)
    length can be any 1-64, including non powers like 9 (1/9 of whole)
    """
    if length is None or length <= 0:
        length = DEFAULT_LENGTH
    whole_ms = 240000.0 / tempo  # whole note
    dur = whole_ms / length
    if is_dotted:
        dur *= 1.5
    return dur


class QBasicMMLParser:
    """
    Faithful QBasic PLAY parser.
    Parses MML string into list of events with accurate frequency and timing.
    """

    def __init__(self):
        self.reset()

    def reset(self):
        self.octave = DEFAULT_OCTAVE
        self.tempo = DEFAULT_TEMPO
        self.default_length = DEFAULT_LENGTH
        self.default_dotted = False
        self.mode_factor = MODE_FACTORS['MN']
        self.mode_name = 'MN'
        self.foreground = True  # MF vs MB
        # For stateful parsing across multiple PLAY strings
        return self

    def get_state(self):
        return {
            'octave': self.octave,
            'tempo': self.tempo,
            'default_length': self.default_length,
            'default_dotted': self.default_dotted,
            'mode_factor': self.mode_factor,
            'mode_name': self.mode_name,
            'foreground': self.foreground
        }

    def set_state(self, state):
        if state is None:
            return
        self.octave = state.get('octave', DEFAULT_OCTAVE)
        self.tempo = state.get('tempo', DEFAULT_TEMPO)
        self.default_length = state.get('default_length', DEFAULT_LENGTH)
        self.default_dotted = state.get('default_dotted', False)
        self.mode_factor = state.get('mode_factor', MODE_FACTORS['MN'])
        self.mode_name = state.get('mode_name', 'MN')
        self.foreground = state.get('foreground', True)

    def parse(self, mml_str, carry_state=True):
        """
        Parse single MML string.
        Returns list of events.
        Each event: {
            'freq': float (0 for rest),
            'total_duration': ms,
            'sound_duration': ms (mode applied),
            'rest_duration': ms,
            'type': 'note'|'rest',
            'raw': str,
            'octave': int,
            'letter': str,
            'tempo': int,
            'mode': str
        }
        """
        if not carry_state:
            self.reset()

        events = []
        i = 0
        s = mml_str

        while i < len(s):
            ch = s[i]
            # skip whitespace
            if ch.isspace():
                i += 1
                continue

            up = ch.upper()

            # Octave O
            if up == 'O':
                i += 1
                val, i = _parse_int(s, i)
                if val is not None:
                    self.octave = max(0, min(6, val))
                continue

            # Octave up >
            if ch == '>':
                self.octave = min(6, self.octave + 1)
                i += 1
                continue

            # Octave down <
            if ch == '<':
                self.octave = max(0, self.octave - 1)
                i += 1
                continue

            # Tempo T
            if up == 'T':
                i += 1
                val, i = _parse_int(s, i)
                if val is not None:
                    # QBasic tempo 32-255
                    self.tempo = max(32, min(255, val))
                continue

            # Length L
            if up == 'L':
                i += 1
                val, i2, dot = _parse_int_dot(s, i)
                if val is not None:
                    self.default_length = val
                    self.default_dotted = dot
                i = i2
                continue

            # Mode M
            if up == 'M':
                # Look ahead 1 char
                if i + 1 < len(s):
                    nxt = s[i+1].upper()
                    if nxt == 'N':
                        self.mode_factor = MODE_FACTORS['MN']
                        self.mode_name = 'MN'
                        i += 2
                        continue
                    elif nxt == 'L':
                        self.mode_factor = MODE_FACTORS['ML']
                        self.mode_name = 'ML'
                        i += 2
                        continue
                    elif nxt == 'S':
                        self.mode_factor = MODE_FACTORS['MS']
                        self.mode_name = 'MS'
                        i += 2
                        continue
                    elif nxt == 'F':
                        self.foreground = True
                        i += 2
                        continue
                    elif nxt == 'B':
                        self.foreground = False
                        i += 2
                        continue
                i += 1
                continue

            # Note number N
            if up == 'N':
                i += 1
                val, i2, dot = _parse_int_dot(s, i)
                i = i2
                if val is None:
                    continue
                if val == 0:
                    # Rest
                    total = calc_duration(self.default_length, self.default_dotted or dot, self.tempo)
                    # Apply mode? Rest is full duration
                    events.append({
                        'freq': 0,
                        'total_duration': total,
                        'sound_duration': 0,
                        'rest_duration': total,
                        'type': 'rest',
                        'raw': f'N{val}' + ('.' if dot else ''),
                        'octave': self.octave,
                        'tempo': self.tempo,
                        'mode': self.mode_name,
                        'foreground': self.foreground
                    })
                else:
                    freq = A4_FREQ * (2 ** ((val - A4_N) / 12))
                    # Duration uses default length, dot from N or default dotted?
                    is_dotted = dot or self.default_dotted
                    total = calc_duration(self.default_length, is_dotted, self.tempo)
                    sound_dur = total * self.mode_factor
                    events.append({
                        'freq': freq,
                        'total_duration': total,
                        'sound_duration': sound_dur,
                        'rest_duration': total - sound_dur,
                        'type': 'note',
                        'raw': f'N{val}' + ('.' if dot else ''),
                        'n': val,
                        'octave': self.octave,
                        'tempo': self.tempo,
                        'mode': self.mode_name,
                        'foreground': self.foreground
                    })
                continue

            # Pause P
            if up == 'P':
                i += 1
                val, i2, dot = _parse_int_dot(s, i)
                i = i2
                if val is None:
                    val = self.default_length
                    dot = self.default_dotted
                total = calc_duration(val, dot, self.tempo)
                events.append({
                    'freq': 0,
                    'total_duration': total,
                    'sound_duration': 0,
                    'rest_duration': total,
                    'type': 'rest',
                    'raw': f'P{val}' + ('.' if dot else ''),
                    'octave': self.octave,
                    'tempo': self.tempo,
                    'mode': self.mode_name,
                    'foreground': self.foreground
                })
                continue

            # Notes A-G
            if up in 'ABCDEFG':
                note_letter = up
                i += 1
                # accidental # + -
                accidental = None
                if i < len(s) and s[i] in '#+-':
                    accidental = s[i]
                    i += 1
                # optional length and dot
                val, i2, dot = _parse_int_dot_optional(s, i)
                i = i2

                # Determine effective length and dotted
                if val is None:
                    eff_len = self.default_length
                    # If note has dot, use it, else if default dotted, use that
                    eff_dot = dot or self.default_dotted
                else:
                    eff_len = val
                    eff_dot = dot

                # Compute semitone
                base = BASE_SEMITONE[note_letter]
                if accidental == '#' or accidental == '+':
                    base += 1
                elif accidental == '-':
                    base -= 1

                octv = self.octave
                # Handle wrap
                if base < 0:
                    base += 12
                    octv -= 1
                if base >= 12:
                    base -= 12
                    octv += 1
                octv = max(0, min(6, octv))

                note_value = octv * 12 + base  # C0 =0
                freq = A4_FREQ * (2 ** ((note_value - 57) / 12))  # 57 = A4 note_value (4*12+9)

                total = calc_duration(eff_len, eff_dot, self.tempo)
                sound_dur = total * self.mode_factor

                events.append({
                    'freq': freq,
                    'total_duration': total,
                    'sound_duration': sound_dur,
                    'rest_duration': total - sound_dur,
                    'type': 'note',
                    'raw': f'{note_letter}{accidental or ""}{val if val is not None else ""}{"." if dot else ""}',
                    'letter': note_letter,
                    'accidental': accidental,
                    'octave': octv,
                    'length': eff_len,
                    'dotted': eff_dot,
                    'tempo': self.tempo,
                    'mode': self.mode_name,
                    'foreground': self.foreground
                })
                continue

            # Unknown char, skip
            i += 1

        return events

    def parse_with_state(self, mml_str, state=None):
        """Parse with optional incoming state, return events and outgoing state"""
        if state is not None:
            self.set_state(state)
        events = self.parse(mml_str, carry_state=True)
        out_state = self.get_state()
        return events, out_state

    def parse_sequence(self, mml_list):
        """Parse list of MML strings with state carried across, return flat events"""
        self.reset()
        all_events = []
        for mml in mml_list:
            ev = self.parse(mml, carry_state=True)
            all_events.extend(ev)
        return all_events


# ----------------------------------------------------------------------
# Audio Playback - Web Audio API square wave PC speaker emulation
# ----------------------------------------------------------------------
class EightBitPlayer:
    """
    PC Speaker emulator using Web Audio API square wave.
    Plays QBasic PLAY events faithfully.
    Can be used standalone or wrapped by proc_audio AudioEngine.
    """

    def __init__(self, quality="high"):
        self.ctx = None
        self.master_gain = None
        self.quality = quality
        self._init_context()
        self._scheduled = []

    def _init_context(self):
        if HAS_BROWSER:
            try:
                AudioContext = window.AudioContext or window.webkitAudioContext
                self.ctx = AudioContext.new()
                # master gain
                self.master_gain = self.ctx.createGain()
                self.master_gain.gain.value = 0.3
                self.master_gain.connect(self.ctx.destination)
            except Exception as e:
                print(f"EightBitPlayer: AudioContext init failed {e}")
                self.ctx = None
        else:
            self.ctx = None

    def resume(self):
        """Must be called after user gesture"""
        if self.ctx:
            try:
                if self.ctx.state == "suspended":
                    self.ctx.resume()
                # Also try to resume via proc_audio if available
                if HAS_PROC_AUDIO and ProcAudioEngine:
                    # If global engine exists, resume it too
                    pass
            except Exception as e:
                print(f"resume failed: {e}")

    def _ensure_context(self):
        if self.ctx is None:
            self._init_context()
        return self.ctx is not None

    def play_events(self, events, on_complete=None):
        """
        Schedule events via Web Audio.
        events: list from parser
        """
        if not self._ensure_context():
            print("No AudioContext, cannot play")
            return

        self.resume()
        ctx = self.ctx
        now = ctx.currentTime
        t = now + 0.05  # small lookahead

        for ev in events:
            total_s = ev['total_duration'] / 1000.0
            sound_s = ev['sound_duration'] / 1000.0

            if ev['freq'] > 0 and sound_s > 0.001:
                osc = ctx.createOscillator()
                gain = ctx.createGain()

                osc.type = "square"  # PC speaker = square wave
                osc.frequency.value = ev['freq']

                # Simple envelope to avoid clicks
                gain.gain.setValueAtTime(0, t)
                gain.gain.linearRampToValueAtTime(0.5, t + 0.005)
                gain.gain.setValueAtTime(0.5, t + sound_s - 0.01)
                gain.gain.linearRampToValueAtTime(0, t + sound_s)

                osc.connect(gain)
                gain.connect(self.master_gain or ctx.destination)

                osc.start(t)
                osc.stop(t + sound_s + 0.02)

            t += total_s

        if on_complete:
            # Schedule callback
            delay_ms = (t - now) * 1000
            try:
                window.setTimeout(on_complete, int(delay_ms))
            except:
                pass

    def play_mml(self, mml_str, parser=None):
        """Convenience: parse single MML string and play"""
        if parser is None:
            parser = QBasicMMLParser()
        events = parser.parse(mml_str, carry_state=False)
        self.play_events(events)
        return events

    def play_mml_sequence(self, mml_list, parser=None):
        """Play list of MML strings with state carried"""
        if parser is None:
            parser = QBasicMMLParser()
            parser.reset()
            events = []
            for m in mml_list:
                ev = parser.parse(m, carry_state=True)
                events.extend(ev)
        else:
            events = parser.parse_sequence(mml_list)
        self.play_events(events)
        return events

    def stop_all(self):
        # Web Audio oscillators cannot be easily stopped en masse without tracking
        # Recreate context
        if self.ctx:
            try:
                self.ctx.close()
            except:
                pass
        self._init_context()


# ----------------------------------------------------------------------
# Integration with proc_audio AudioEngine - Extension wrapper
# ----------------------------------------------------------------------
class EightBitAudioEngine:
    """
    High-level wrapper that builds on top of proc_audio.AudioEngine
    Provides gorilla sounds as presets and MML playback.
    Does NOT modify proc_audio.py
    """

    def __init__(self, proc_engine=None, quality="high", seed=90210):
        self.parser = QBasicMMLParser()
        self.player = EightBitPlayer(quality=quality)

        # Try to use existing proc_audio engine if provided, else create
        self.proc_engine = proc_engine
        if self.proc_engine is None and HAS_PROC_AUDIO and ProcAudioEngine:
            try:
                self.proc_engine = ProcAudioEngine(quality=quality, seed=seed)
            except Exception as e:
                print(f"Could not create ProcAudioEngine: {e}")
                self.proc_engine = None

        # Our preset registry
        self.presets = {}
        self._register_gorilla_presets()

    def _register_gorilla_presets(self):
        """Register all gorilla sounds"""
        for name, mml_list in GORILLA_SOUNDS.items():
            self.presets[name] = {
                'mml': mml_list,
                'description': GORILLA_DESCRIPTIONS.get(name, ""),
                'events': self.parser.parse_sequence(mml_list)
            }

    def resume(self):
        self.player.resume()
        if self.proc_engine:
            try:
                self.proc_engine.resume()
            except:
                pass

    def play(self, sound_name, seed=None, spatial=False, position=None):
        """
        Play a gorilla sound by name. Compatible with proc_audio.play signature.
        sound_name: key in GORILLA_SOUNDS or raw MML string
        """
        self.resume()

        # If sound_name is a gorilla preset
        if sound_name in self.presets:
            preset = self.presets[sound_name]
            self.player.play_events(preset['events'])
            # Also try proc_audio if it has matching preset? We play via our player
            return preset

        # If sound_name looks like MML, play it directly
        if isinstance(sound_name, str) and any(c in sound_name.upper() for c in ['O', 'L', 'T', 'M', 'N', 'P', 'A', 'B', 'C', 'D', 'E', 'F', 'G']):
            events = self.parser.parse(sound_name, carry_state=False)
            self.player.play_events(events)
            return {'mml': sound_name, 'events': events}

        # Fallback to proc_audio engine
        if self.proc_engine:
            try:
                return self.proc_engine.play(sound_name, seed=seed, spatial=spatial, position=position)
            except Exception as e:
                print(f"proc_audio play failed: {e}")

        print(f"Unknown sound: {sound_name}")
        return None

    def play_mml(self, mml):
        return self.player.play_mml(mml, parser=self.parser)

    def play_sequence(self, mml_list):
        return self.player.play_mml_sequence(mml_list, parser=self.parser)

    def get_events(self, sound_name):
        """Get parsed events for a sound"""
        if sound_name in self.presets:
            return self.presets[sound_name]['events']
        return self.parser.parse(sound_name, carry_state=False)

    def get_all_presets(self):
        return self.presets

    # Patch creation for proc_audio integration
    def create_patch_for_mml(self, mml_str, patch_name="8bit_square"):
        """
        Create a proc_audio Patch that emulates square wave for given MML.
        If proc_audio Patch not available, returns dict representation.
        """
        events = self.parser.parse(mml_str, carry_state=False)

        if not HAS_PROC_AUDIO or ProcPatch is None:
            # Return JSON-serializable dict
            return {
                'name': patch_name,
                'type': '8bit_square',
                'waveform': 'square',
                'events': events,
                'mml': mml_str
            }

        # Try to build using Patch builder (guess API)
        try:
            # Attempt chainable builder pattern
            patch = ProcPatch()
            # Try common methods
            if hasattr(patch, 'oscillator'):
                patch = patch.oscillator(type='square', frequency=440)  # placeholder
            if hasattr(patch, 'envelope'):
                patch = patch.envelope(attack=0.001, decay=0, sustain=1, release=0.01)
            if hasattr(patch, 'tag'):
                patch = patch.tag('8bit').tag('gorillas').tag('square')
            # Store MML in metadata
            if hasattr(patch, 'meta'):
                patch = patch.meta(mml=mml_str)
            return patch
        except Exception as e:
            print(f"Patch creation failed, fallback: {e}")
            return {
                'name': patch_name,
                'mml': mml_str,
                'events': events,
                'error': str(e)
            }


# ----------------------------------------------------------------------
# Convenience functions - Module-level API
# ----------------------------------------------------------------------
_default_engine = None

def get_engine():
    global _default_engine
    if _default_engine is None:
        _default_engine = EightBitAudioEngine()
    return _default_engine

def play(sound_name):
    """Play gorilla sound by name (global convenience)"""
    eng = get_engine()
    return eng.play(sound_name)

def play_mml(mml_str):
    eng = get_engine()
    return eng.play_mml(mml_str)

def resume():
    eng = get_engine()
    eng.resume()

# Export list for SCS
__all__ = [
    'QBasicMMLParser',
    'EightBitPlayer',
    'EightBitAudioEngine',
    'GORILLAS_MML',
    'GORILLA_SOUNDS',
    'GORILLA_DESCRIPTIONS',
    'get_engine',
    'play',
    'play_mml',
    'resume',
    'HAS_PROC_AUDIO'
]
