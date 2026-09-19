"""Declarative parameter schema.

One table defines every control: its range, default, unit and help text.  The
CLI, the preset loader and the web UI all read this, so adding a parameter here
makes it appear everywhere without touching any other file.
"""
from __future__ import annotations

from typing import Any

from .melody import SCALES
from .vocoder import WAVES

# kind: f = float, i = int, b = bool, e = enum, s = string
# (key, label, kind, default, lo, hi, step, unit, help)
SCHEMA: list[dict[str, Any]] = []


def _p(group, key, label, kind, default, lo=None, hi=None, step=None,
       unit="", help="", choices=None, panel=""):
    SCHEMA.append(dict(group=group, panel=panel or group, key=key, label=label,
                       kind=kind, default=default, lo=lo, hi=hi, step=step,
                       unit=unit, help=help, choices=choices))


# ======================================================================
# VOICE -- the instrument itself
# ======================================================================
_p("Voice", "voice.tract_length", "Tract length", "f", 1.0, 0.45, 2.0, 0.01, "x",
   "Vocal tract size. Below 1 = smaller/brighter (child, Miku), above 1 = larger/darker.")
_p("Voice", "voice.formant_shift", "Formant shift", "f", 0.0, -24.0, 24.0, 0.1, "st",
   "Moves all formants without touching pitch. The main gender/size control.")
_p("Voice", "voice.formant_spread", "Formant spread", "f", 1.0, 0.3, 2.0, 0.01, "x",
   "Scales the distance of F2-F5 from F1. High values sound hollow and synthetic.")
_p("Voice", "voice.formant_q", "Formant Q", "f", 1.0, 0.3, 4.0, 0.01, "x",
   "Narrows every formant. High Q = sharply resonant, vocoder-like and inhuman.")
_p("Voice", "voice.f1", "F1 offset", "f", 0.0, -12.0, 12.0, 0.1, "st", "Tune the first formant alone (jaw openness).")
_p("Voice", "voice.f2", "F2 offset", "f", 0.0, -12.0, 12.0, 0.1, "st", "Tune the second formant alone (tongue position).")
_p("Voice", "voice.f3", "F3 offset", "f", 0.0, -12.0, 12.0, 0.1, "st", "Tune the third formant alone (lip rounding / 'r' colour).")
_p("Voice", "voice.n_formants", "Formant count", "i", 5, 2, 5, 1, "",
   "How many resonators run. Two or three gives a deliberately crude retro vowel.")
_p("Voice", "voice.effort", "Vocal effort", "f", 0.5, 0.0, 1.0, 0.01, "",
   "Pushed/belted vs relaxed. Raises F1 and tightens its bandwidth.")

_p("Voice", "voice.open_quotient", "Open quotient", "f", 0.62, 0.2, 0.92, 0.01, "",
   "Fraction of each cycle the glottis is open. High = soft and breathy, low = buzzy and bright.", panel="Source")
_p("Voice", "voice.speed_quotient", "Speed quotient", "f", 2.2, 1.0, 5.0, 0.05, "",
   "Asymmetry of the glottal pulse. Higher = sharper closure = more high harmonics.", panel="Source")
_p("Voice", "voice.tilt", "Spectral tilt", "f", 0.0, -24.0, 18.0, 0.1, "dB",
   "Overall source brightness. Negative is dark and intimate, positive is edgy.", panel="Source")
_p("Voice", "voice.breathiness", "Breathiness", "f", 0.12, 0.0, 1.5, 0.01, "",
   "Aspiration noise mixed into the glottal source, gated to the open phase.", panel="Source")
_p("Voice", "voice.shimmer", "Shimmer", "f", 0.03, 0.0, 0.6, 0.005, "",
   "Cycle-to-cycle amplitude variation. A little is human; a lot is rough.", panel="Source")
_p("Voice", "voice.pitch_jitter", "Jitter", "f", 0.04, 0.0, 1.0, 0.005, "st",
   "Micro pitch instability. Set to 0 for a perfectly steady machine voice.", panel="Source")
_p("Voice", "voice.growl", "Growl", "f", 0.0, 0.0, 1.0, 0.01, "",
   "Period-doubling subharmonic. Creaky, aggressive, good for phonk and hard dance.", panel="Source")
_p("Voice", "voice.wave_blend", "Wave blend", "f", 0.0, 0.0, 1.0, 0.01, "",
   "Crossfade the glottal pulse into a raw oscillator. The fastest route to a synthetic voice.", panel="Source")
_p("Voice", "voice.alt_wave", "Blend wave", "e", "saw", choices=["saw", "square", "triangle", "pulse", "supersaw"],
   help="Which oscillator the wave blend fades into.", panel="Source")
_p("Voice", "voice.pulse_width", "Pulse width", "f", 0.5, 0.02, 0.98, 0.01, "",
   "Duty cycle for the square/pulse blend wave.", panel="Source")

# ======================================================================
# PITCH
# ======================================================================
# ======================================================================
# MELODY -- note timing lives in its own group, edited by the piano roll
# ======================================================================
_p("Melody", "pitch.melody", "Melody", "s", "",
   help="Notes, e.g. 'C4 Eb4 G4:2 R:0.5 Bb4'. NAME[octave][:step[:length]]; R is a rest. Empty = auto.")
_p("Melody", "pitch.bpm", "Tempo", "f", 124.0, 40.0, 220.0, 0.5, "BPM",
   "Drives note lengths, the trance gate and tempo-synced delay.", panel="Timing")
_p("Melody", "pitch.note_length", "Note length", "f", 1.0, 0.05, 1.0, 0.01, "x",
   "Fraction of each note's slot that actually sounds. 1.0 is legato, lower is staccato. "
   "Notes given their own length in the roll ignore this.", panel="Timing")
_p("Melody", "pitch.swing", "Swing", "f", 0.0, 0.0, 0.6, 0.01, "",
   "Delays every second short note.", panel="Timing")
_p("Melody", "pitch.portamento", "Portamento", "f", 45.0, 0.0, 400.0, 1.0, "ms",
   "Glide time between notes. Set to 0 for the stepped, quantised hard-tune sound.",
   panel="Timing")
_p("Melody", "pitch.root", "Root note", "f", 60.0, 24.0, 96.0, 1.0, "MIDI",
   "Base pitch for auto melodies and scale snapping. 60 = C4.", panel="Key")
_p("Melody", "pitch.scale", "Scale", "e", "minor_pentatonic", choices=sorted(SCALES),
   help="Used by the auto melody and by Pitch snap.", panel="Key")
_p("Melody", "pitch.auto_style", "Auto melody", "e", "monotone",
   choices=["monotone", "rise", "fall", "arp", "wander"],
   help="Shape used when the roll is empty.", panel="Key")

_p("Pitch", "pitch.transpose", "Transpose", "f", 0.0, -24.0, 24.0, 1.0, "st", "Shifts pitch only; formants stay put.")
_p("Pitch", "pitch.fine", "Fine tune", "f", 0.0, -100.0, 100.0, 1.0, "cents", "Fine pitch offset.")

_p("Pitch", "pitch.quantize", "Pitch snap", "f", 0.0, 0.0, 1.0, 0.01, "",
   "Forces the pitch track onto the scale. 1.0 is full hard-tune.", panel="Expression")
_p("Pitch", "pitch.vibrato_depth", "Vibrato depth", "f", 0.25, 0.0, 3.0, 0.01, "st", "", panel="Expression")
_p("Pitch", "pitch.vibrato_rate", "Vibrato rate", "f", 5.5, 0.5, 12.0, 0.1, "Hz", "", panel="Expression")
_p("Pitch", "pitch.vibrato_delay", "Vibrato delay", "f", 260.0, 0.0, 1500.0, 10.0, "ms",
   "How long each note waits before vibrato begins.", panel="Expression")
_p("Pitch", "pitch.vibrato_ramp", "Vibrato ramp", "f", 220.0, 10.0, 2000.0, 10.0, "ms", "Fade-in time of the vibrato.", panel="Expression")
_p("Pitch", "pitch.drift", "Pitch drift", "f", 0.05, 0.0, 1.0, 0.01, "st", "Slow random wander. Humanising.", panel="Expression")
_p("Pitch", "pitch.scoop", "Scoop", "f", 0.0, 0.0, 4.0, 0.05, "st", "Slide up into each note from below.", panel="Expression")
_p("Pitch", "pitch.scoop_time", "Scoop time", "f", 70.0, 5.0, 500.0, 5.0, "ms", "", panel="Expression")
_p("Pitch", "pitch.fall", "Fall-off", "f", 0.0, 0.0, 6.0, 0.05, "st", "Drop in pitch at the end of each note.", panel="Expression")
_p("Pitch", "pitch.fall_time", "Fall time", "f", 90.0, 5.0, 600.0, 5.0, "ms", "", panel="Expression")

# ======================================================================
# ARTICULATION
# ======================================================================
_p("Articulation", "art.speed", "Diction speed", "f", 1.0, 0.3, 3.0, 0.01, "x", "Scales all consonant lengths.")
_p("Articulation", "art.consonant_length", "Consonant length", "f", 1.0, 0.2, 3.0, 0.01, "x", "Stretch or clip consonants independently of tempo.")
_p("Articulation", "art.consonant_gain", "Consonant level", "f", 1.0, 0.0, 3.0, 0.01, "x", "Loudness of plosives and fricatives.")
_p("Articulation", "art.sibilance", "Sibilance", "f", 1.0, 0.0, 3.0, 0.01, "x", "Level of S/SH/F noise specifically.")
_p("Articulation", "art.glide", "Coarticulation", "f", 32.0, 2.0, 200.0, 1.0, "ms",
   "How smoothly formants move between phonemes. High values slur; low values are crisp and robotic.")
_p("Articulation", "art.diphthong", "Diphthong glide", "f", 1.0, 0.0, 2.0, 0.01, "x", "How far diphthongs travel toward their second target.")
_p("Articulation", "art.legato", "Legato", "f", 0.5, 0.0, 1.0, 0.01, "", "Holds vowels into the following consonant.")
_p("Articulation", "art.release", "Release tail", "f", 120.0, 0.0, 1500.0, 10.0, "ms", "Extra time after the last note.")
_p("Articulation", "text.espeak", "Use espeak-ng", "b", False, help="Use espeak-ng for phonemes if it is installed. The built-in rules are used otherwise.")

# ======================================================================
# VOCODER
# ======================================================================
_p("Vocoder", "voc.mix", "Vocoder mix", "f", 0.0, 0.0, 1.0, 0.01, "", "Dry voice to fully vocoded.")
_p("Vocoder", "voc.bands", "Bands", "i", 24, 2, 128, 1, "",
   "Few bands = coarse and obviously robotic. Many bands = intelligible and smooth.")
_p("Vocoder", "voc.spacing", "Band spacing", "e", "log", choices=["log", "mel", "linear"], help="How band centres are distributed.")
_p("Vocoder", "voc.low_hz", "Low bound", "f", 110.0, 40.0, 1000.0, 5.0, "Hz", "")
_p("Vocoder", "voc.high_hz", "High bound", "f", 8000.0, 2000.0, 18000.0, 100.0, "Hz", "")
_p("Vocoder", "voc.order", "Filter order", "i", 4, 2, 8, 2, "", "Steeper bands are more separated and more metallic.")
_p("Vocoder", "voc.attack", "Env attack", "f", 3.0, 0.1, 80.0, 0.1, "ms", "Fast attack keeps consonants punchy.")
_p("Vocoder", "voc.release", "Env release", "f", 22.0, 1.0, 400.0, 1.0, "ms", "Long release smears words into a pad.")
_p("Vocoder", "voc.band_shift", "Band shift", "i", 0, -24, 24, 1, "",
   "Offsets analysis bands against synthesis bands - a formant shift with a hardware-vocoder character.")
_p("Vocoder", "voc.tilt", "Band tilt", "f", 0.0, -24.0, 24.0, 0.5, "dB", "Tilts level from low bands to high bands.")
_p("Vocoder", "voc.sibilance", "Sibilance thru", "f", 0.35, 0.0, 1.5, 0.01, "",
   "Blends the raw high band past the vocoder so S and T stay audible.")
_p("Vocoder", "voc.sib_hz", "Sibilance freq", "f", 4500.0, 1500.0, 12000.0, 100.0, "Hz", "")

_p("Vocoder", "voc.carrier_wave", "Carrier", "e", "supersaw", choices=list(WAVES), help="Oscillator the vocoder plays through.", panel="Carrier")
_p("Vocoder", "voc.pitch_source", "Carrier pitch", "e", "follow", choices=["follow", "fixed"],
   help="'follow' makes the carrier sing your melody. 'fixed' holds one drone note.", panel="Carrier")
_p("Vocoder", "voc.fixed_note", "Fixed note", "f", 48.0, 12.0, 84.0, 1.0, "MIDI", "", panel="Carrier")
_p("Vocoder", "voc.transpose", "Carrier octave", "f", -12.0, -36.0, 24.0, 1.0, "st", "", panel="Carrier")
_p("Vocoder", "voc.chord", "Carrier chord", "s", "0", help="Stacked intervals in semitones, e.g. '0 3 7 12' for a minor chord.", panel="Carrier")
_p("Vocoder", "voc.unison", "Carrier unison", "i", 3, 1, 9, 1, "", "", panel="Carrier")
_p("Vocoder", "voc.detune", "Carrier detune", "f", 14.0, 0.0, 80.0, 0.5, "cents", "", panel="Carrier")
_p("Vocoder", "voc.spread", "Carrier spread", "f", 0.6, 0.0, 1.0, 0.01, "", "Stereo spread of the unison voices.", panel="Carrier")
_p("Vocoder", "voc.pulse_width", "Carrier PW", "f", 0.42, 0.02, 0.98, 0.01, "", "", panel="Carrier")
_p("Vocoder", "voc.sub", "Carrier sub", "f", 0.25, 0.0, 1.5, 0.01, "", "Sub-octave square under the carrier.", panel="Carrier")
_p("Vocoder", "voc.noise", "Carrier noise", "f", 0.0, 0.0, 1.0, 0.01, "", "Blends noise into the carrier - whispered robot.", panel="Carrier")

# ======================================================================
# STACK
# ======================================================================
_p("Stack", "fx.formant_shift", "Post formant", "f", 0.0, -12.0, 12.0, 0.1, "st",
   "Spectral-envelope shift applied after synthesis. Independent of the voice's own formants.")
_p("Stack", "uni.voices", "Unison voices", "i", 0, 0, 8, 1, "", "Detuned copies for a wide stacked vocal.")
_p("Stack", "uni.detune", "Unison detune", "f", 12.0, 0.0, 100.0, 0.5, "cents", "")
_p("Stack", "uni.spread", "Unison spread", "f", 0.8, 0.0, 1.0, 0.01, "", "")
_p("Stack", "uni.delay", "Unison delay", "f", 14.0, 0.0, 60.0, 0.5, "ms", "Small offsets thicken; large offsets smear.")
_p("Stack", "uni.mix", "Unison mix", "f", 0.6, 0.0, 1.0, 0.01, "", "")
_p("Stack", "harm.intervals", "Harmony", "s", "", help="Semitone intervals to stack, e.g. '-12 3 7'. Empty disables.")
_p("Stack", "harm.mix", "Harmony mix", "f", 0.0, 0.0, 1.0, 0.01, "", "")
_p("Stack", "harm.spread", "Harmony spread", "f", 0.7, 0.0, 1.0, 0.01, "", "")

# ======================================================================
# EFFECTS
# ======================================================================
_p("Effects", "gate.depth", "Gate depth", "f", 0.0, 0.0, 1.0, 0.01, "", "Trance gate, synced to tempo.", panel="Gate")
_p("Effects", "gate.division", "Gate rate", "f", 8.0, 1.0, 32.0, 1.0, "1/n", "8 = eighth notes, 16 = sixteenths.", panel="Gate")
_p("Effects", "gate.duty", "Gate duty", "f", 0.5, 0.02, 0.99, 0.01, "", "", panel="Gate")
_p("Effects", "gate.smooth", "Gate smooth", "f", 6.0, 0.1, 80.0, 0.1, "ms", "", panel="Gate")
_p("Effects", "gate.offset", "Gate offset", "f", 0.0, 0.0, 1.0, 0.01, "", "", panel="Gate")

_p("Effects", "eq.hp", "High-pass", "f", 80.0, 0.0, 800.0, 5.0, "Hz", "", panel="EQ")
_p("Effects", "eq.low_freq", "Low freq", "f", 180.0, 40.0, 500.0, 5.0, "Hz", "", panel="EQ")
_p("Effects", "eq.low_gain", "Low gain", "f", 0.0, -18.0, 18.0, 0.1, "dB", "", panel="EQ")
_p("Effects", "eq.mid1_freq", "Mid 1 freq", "f", 900.0, 200.0, 4000.0, 10.0, "Hz", "", panel="EQ")
_p("Effects", "eq.mid1_gain", "Mid 1 gain", "f", 0.0, -18.0, 18.0, 0.1, "dB", "", panel="EQ")
_p("Effects", "eq.mid1_q", "Mid 1 Q", "f", 1.0, 0.2, 8.0, 0.05, "", "", panel="EQ")
_p("Effects", "eq.mid2_freq", "Mid 2 freq", "f", 3000.0, 800.0, 12000.0, 50.0, "Hz", "", panel="EQ")
_p("Effects", "eq.mid2_gain", "Mid 2 gain", "f", 0.0, -18.0, 18.0, 0.1, "dB", "", panel="EQ")
_p("Effects", "eq.mid2_q", "Mid 2 Q", "f", 1.0, 0.2, 8.0, 0.05, "", "", panel="EQ")
_p("Effects", "eq.high_freq", "High freq", "f", 7000.0, 2000.0, 16000.0, 100.0, "Hz", "", panel="EQ")
_p("Effects", "eq.high_gain", "High gain", "f", 0.0, -18.0, 18.0, 0.1, "dB", "", panel="EQ")
_p("Effects", "eq.lp", "Low-pass", "f", 20000.0, 500.0, 20000.0, 100.0, "Hz", "", panel="EQ")

_p("Effects", "comp.ratio", "Ratio", "f", 3.0, 1.0, 20.0, 0.1, ":1", "", panel="Dynamics")
_p("Effects", "comp.threshold", "Threshold", "f", -20.0, -60.0, 0.0, 0.5, "dB", "", panel="Dynamics")
_p("Effects", "comp.attack", "Attack", "f", 6.0, 0.1, 120.0, 0.1, "ms", "", panel="Dynamics")
_p("Effects", "comp.release", "Release", "f", 90.0, 5.0, 800.0, 1.0, "ms", "", panel="Dynamics")
_p("Effects", "comp.knee", "Knee", "f", 6.0, 0.1, 24.0, 0.1, "dB", "", panel="Dynamics")
_p("Effects", "comp.makeup", "Makeup", "f", 0.0, -12.0, 24.0, 0.1, "dB", "", panel="Dynamics")
_p("Effects", "comp.mix", "Comp mix", "f", 1.0, 0.0, 1.0, 0.01, "", "Parallel compression when below 1.", panel="Dynamics")
_p("Effects", "deess.amount", "De-ess", "f", 0.0, 0.0, 1.0, 0.01, "", "", panel="Dynamics")
_p("Effects", "deess.freq", "De-ess freq", "f", 6200.0, 2000.0, 14000.0, 100.0, "Hz", "", panel="Dynamics")
_p("Effects", "deess.threshold", "De-ess thr", "f", -30.0, -60.0, 0.0, 0.5, "dB", "", panel="Dynamics")

_p("Effects", "sat.drive", "Drive", "f", 0.0, 0.0, 36.0, 0.1, "dB", "", panel="Saturation")
_p("Effects", "sat.type", "Character", "e", "tube", choices=["tube", "tape", "fold", "clip", "diode", "soft"], help="", panel="Saturation")
_p("Effects", "sat.mix", "Drive mix", "f", 1.0, 0.0, 1.0, 0.01, "", "", panel="Saturation")
_p("Effects", "sat.bits", "Bit crush", "f", 16.0, 1.0, 16.0, 0.5, "bits", "Lower for lo-fi grit. 16 = off.", panel="Saturation")
_p("Effects", "sat.downsample", "Downsample", "f", 1.0, 1.0, 40.0, 1.0, "x", "Sample-rate reduction. 1 = off.", panel="Saturation")

_p("Effects", "cho.depth", "Chorus depth", "f", 0.0, 0.0, 20.0, 0.1, "ms", "", panel="Modulation")
_p("Effects", "cho.rate", "Chorus rate", "f", 0.6, 0.02, 8.0, 0.01, "Hz", "", panel="Modulation")
_p("Effects", "cho.delay", "Chorus delay", "f", 18.0, 1.0, 60.0, 0.5, "ms", "", panel="Modulation")
_p("Effects", "cho.voices", "Chorus voices", "i", 2, 1, 6, 1, "", "", panel="Modulation")
_p("Effects", "cho.feedback", "Chorus fb", "f", 0.0, -0.9, 0.9, 0.01, "", "Push up for a flanger.", panel="Modulation")
_p("Effects", "cho.mix", "Chorus mix", "f", 0.4, 0.0, 1.0, 0.01, "", "", panel="Modulation")
_p("Effects", "pha.depth", "Phaser depth", "f", 0.0, 0.0, 1.0, 0.01, "", "", panel="Modulation")
_p("Effects", "pha.rate", "Phaser rate", "f", 0.35, 0.02, 8.0, 0.01, "Hz", "", panel="Modulation")
_p("Effects", "pha.stages", "Phaser stages", "i", 6, 2, 12, 2, "", "", panel="Modulation")
_p("Effects", "pha.feedback", "Phaser fb", "f", 0.4, -0.95, 0.95, 0.01, "", "", panel="Modulation")
_p("Effects", "pha.mix", "Phaser mix", "f", 0.5, 0.0, 1.0, 0.01, "", "", panel="Modulation")

_p("Effects", "dly.mix", "Delay mix", "f", 0.0, 0.0, 1.0, 0.01, "", "", panel="Delay")
_p("Effects", "dly.sync", "Tempo sync", "b", True, help="", panel="Delay")
_p("Effects", "dly.division", "Delay rate", "f", 8.0, 1.0, 32.0, 1.0, "1/n", "", panel="Delay")
_p("Effects", "dly.dotted", "Dotted", "b", False, help="", panel="Delay")
_p("Effects", "dly.triplet", "Triplet", "b", False, help="", panel="Delay")
_p("Effects", "dly.time", "Delay time", "f", 330.0, 10.0, 2000.0, 5.0, "ms", "Used when tempo sync is off.", panel="Delay")
_p("Effects", "dly.feedback", "Delay fb", "f", 0.35, 0.0, 0.95, 0.01, "", "", panel="Delay")
_p("Effects", "dly.pingpong", "Ping-pong", "b", True, help="", panel="Delay")
_p("Effects", "dly.damp", "Delay damp", "f", 0.3, 0.0, 0.95, 0.01, "", "", panel="Delay")
_p("Effects", "dly.hp", "Delay HP", "f", 200.0, 20.0, 2000.0, 10.0, "Hz", "", panel="Delay")
_p("Effects", "dly.lp", "Delay LP", "f", 6000.0, 500.0, 18000.0, 100.0, "Hz", "", panel="Delay")

_p("Effects", "rev.mix", "Reverb mix", "f", 0.0, 0.0, 1.0, 0.01, "", "", panel="Reverb")
_p("Effects", "rev.size", "Size", "f", 0.7, 0.05, 1.6, 0.01, "", "", panel="Reverb")
_p("Effects", "rev.decay", "Decay", "f", 0.78, 0.1, 0.97, 0.005, "", "", panel="Reverb")
_p("Effects", "rev.damp", "Damping", "f", 0.35, 0.0, 0.95, 0.01, "", "", panel="Reverb")
_p("Effects", "rev.predelay", "Pre-delay", "f", 20.0, 0.0, 250.0, 1.0, "ms", "", panel="Reverb")
_p("Effects", "rev.width", "Reverb width", "f", 1.0, 0.0, 2.0, 0.01, "", "", panel="Reverb")
_p("Effects", "rev.hp", "Reverb HP", "f", 250.0, 20.0, 2000.0, 10.0, "Hz", "", panel="Reverb")
_p("Effects", "rev.lp", "Reverb LP", "f", 7000.0, 500.0, 18000.0, 100.0, "Hz", "", panel="Reverb")
_p("Effects", "rev.shimmer", "Shimmer", "f", 0.0, 0.0, 1.0, 0.01, "", "Pitch-shifted reverb tail.", panel="Reverb")
_p("Effects", "rev.shimmer_semis", "Shimmer pitch", "f", 12.0, -24.0, 24.0, 1.0, "st", "", panel="Reverb")

_p("Effects", "st.width", "Stereo width", "f", 1.0, 0.0, 2.5, 0.01, "", "", panel="Output")
_p("Effects", "st.haas", "Haas", "f", 0.0, 0.0, 40.0, 0.5, "ms", "Delays one channel for an instant wide image.", panel="Output")
_p("Effects", "st.mono_below", "Mono below", "f", 0.0, 0.0, 800.0, 10.0, "Hz", "Collapses lows to mono.", panel="Output")
_p("Effects", "out.gain", "Output gain", "f", 0.0, -24.0, 24.0, 0.1, "dB", "", panel="Output")
_p("Effects", "out.ceiling", "Ceiling", "f", -0.8, -12.0, 0.0, 0.1, "dB", "", panel="Output")
_p("Effects", "out.normalize", "Normalise", "b", True, help="Bring the finished sample up to the ceiling.", panel="Output")

# ======================================================================
# RENDER
# ======================================================================
_p("Render", "render.sr", "Sample rate", "i", 48000, 22050, 96000, 1, "Hz", "")
_p("Render", "render.bits", "Bit depth", "e", 24, choices=[16, 24, 32], help="32 is IEEE float.")
_p("Render", "render.seed", "Seed", "i", 0, 0, 999999, 1, "",
   "All randomness (jitter, shimmer, breath) comes from this. Same seed = identical file.")
_p("Render", "render.tail", "Export tail", "f", 0.6, 0.0, 8.0, 0.1, "s", "Extra silence kept after the voice, for reverb and delay tails.")


BY_KEY = {e["key"]: e for e in SCHEMA}

# Tab order in the UI.  Melody comes first: it is the thing you write.
GROUP_ORDER = ["Melody", "Voice", "Pitch", "Articulation", "Vocoder",
               "Stack", "Effects", "Render"]
GROUPS: list[str] = [g for g in GROUP_ORDER
                     if any(e["group"] == g for e in SCHEMA)]
for _e in SCHEMA:
    if _e["group"] not in GROUPS:
        GROUPS.append(_e["group"])


def defaults() -> dict[str, Any]:
    return {e["key"]: e["default"] for e in SCHEMA}


def coerce(key: str, value: Any) -> Any:
    e = BY_KEY.get(key)
    if e is None:
        return value
    k = e["kind"]
    try:
        if k == "f":
            v = float(value)
            return float(np_clip(v, e["lo"], e["hi"]))
        if k == "i":
            v = int(round(float(value)))
            return int(np_clip(v, e["lo"], e["hi"]))
        if k == "b":
            if isinstance(value, str):
                return value.strip().lower() in ("1", "true", "yes", "on")
            return bool(value)
        if k == "e":
            ch = e["choices"] or []
            if value in ch:
                return value
            for c in ch:
                if str(c) == str(value):
                    return c
            return e["default"]
        return str(value)
    except (TypeError, ValueError):
        return e["default"]


def np_clip(v, lo, hi):
    if lo is not None and v < lo:
        return lo
    if hi is not None and v > hi:
        return hi
    return v


def normalize_params(raw: dict[str, Any] | None) -> dict[str, Any]:
    """Merge user values over the defaults, coercing and clamping each one."""
    p = defaults()
    for k, v in (raw or {}).items():
        if k in BY_KEY:
            p[k] = coerce(k, v)
        else:
            p[k] = v            # keep unknown keys (forward compatibility)
    return p


def describe() -> list[dict[str, Any]]:
    """The schema as plain JSON for the web UI."""
    return [dict(e) for e in SCHEMA]
