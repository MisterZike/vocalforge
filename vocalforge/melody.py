"""Note parsing, syllable/note alignment and pitch-contour generation."""
from __future__ import annotations

import re
from dataclasses import dataclass

import numpy as np

from . import dsp

NOTE_OFFSETS = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}

SCALES: dict[str, tuple[int, ...]] = {
    "chromatic":       (0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11),
    "major":           (0, 2, 4, 5, 7, 9, 11),
    "natural_minor":   (0, 2, 3, 5, 7, 8, 10),
    "harmonic_minor":  (0, 2, 3, 5, 7, 8, 11),
    "dorian":          (0, 2, 3, 5, 7, 9, 10),
    "phrygian":        (0, 1, 3, 5, 7, 8, 10),
    "lydian":          (0, 2, 4, 6, 7, 9, 11),
    "mixolydian":      (0, 2, 4, 5, 7, 9, 10),
    "locrian":         (0, 1, 3, 5, 6, 8, 10),
    "major_pentatonic": (0, 2, 4, 7, 9),
    "minor_pentatonic": (0, 3, 5, 7, 10),
    "blues":           (0, 3, 5, 6, 7, 10),
    "whole_tone":      (0, 2, 4, 6, 8, 10),
}

_NOTE_RE = re.compile(
    r"^([A-Ga-g])([#bs]*)(-?\d+)?(?::([0-9./]+))?(?::([0-9./]+))?$")
_REST_RE = re.compile(r"^(?:r|R|-|_|\.)(?::([0-9./]+))?$")


@dataclass
class Note:
    """One step of the melody.

    ``beats`` is how far the note advances the cursor; ``length`` is how long
    it actually sounds.  A length shorter than the step leaves silence after
    the note -- that is what makes staccato possible without writing a rest
    after every note.  ``length`` of None means "the whole step".
    """
    midi: float | None          # None == rest
    beats: float = 1.0          # step: how much time this note consumes
    length: float | None = None  # sounding duration in beats (None = beats)
    start: float = 0.0          # seconds, filled in by build_timeline
    end: float = 0.0            # seconds, end of the *sounding* part
    slot_end: float = 0.0       # seconds, end of the step (start of the next)

    @property
    def sounding(self) -> float:
        return max(self.end - self.start, 0.0)


def parse_note_name(tok: str, default_octave: int = 4) -> float | None:
    m = _NOTE_RE.match(tok)
    if not m:
        return None
    letter, accs, octv = m.groups()[:3]
    semi = NOTE_OFFSETS[letter.upper()]
    for a in accs:
        semi += 1 if a in "#s" else -1
    octave = int(octv) if octv is not None else default_octave
    return float((octave + 1) * 12 + semi)


def _dur(text: str | None) -> float:
    if not text:
        return 1.0
    if "/" in text:
        a, b = text.split("/", 1)
        try:
            return float(a) / float(b)
        except (ValueError, ZeroDivisionError):
            return 1.0
    try:
        return float(text)
    except ValueError:
        return 1.0


def parse_melody(text: str, default_octave: int = 4) -> list[Note]:
    """Parse ``"C4 Eb4:2 R:0.5 G4"`` into notes.

    Tokens are ``NAME[octave][:beats]``; ``R``/``-`` is a rest.  Octave carries
    over from the previous note when omitted.
    """
    notes: list[Note] = []
    octave = default_octave
    for tok in text.replace(",", " ").split():
        rm = _REST_RE.match(tok)
        if rm:
            notes.append(Note(None, _dur(rm.group(1))))
            continue
        m = _NOTE_RE.match(tok)
        if not m:
            continue
        midi = parse_note_name(tok, octave)
        if midi is None:
            continue
        if m.group(3) is not None:
            octave = int(m.group(3))
        step = _dur(m.group(4))
        length = _dur(m.group(5)) if m.group(5) else None
        notes.append(Note(midi, step, length))
    return notes


def _fmt_beats(v: float) -> str:
    """Render a beat count compactly, preferring simple fractions."""
    for den in (2, 3, 4, 6, 8, 16):
        num = v * den
        if abs(num - round(num)) < 1e-6:
            num = int(round(num))
            if den == 1 or num % den == 0:
                return str(num // den)
            return f"{num}/{den}"
    return f"{v:g}"


def to_text(notes: list[Note], default_octave: int = 4) -> str:
    """Serialise notes back to the melody syntax (inverse of parse_melody)."""
    names = ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]
    out: list[str] = []
    octave = None
    for nt in notes:
        if nt.midi is None:
            out.append("R" + (f":{_fmt_beats(nt.beats)}" if nt.beats != 1.0 else ""))
            continue
        m = int(round(nt.midi))
        oct_ = m // 12 - 1
        tok = names[m % 12] + (str(oct_) if oct_ != octave else "")  # octave carries over
        octave = oct_
        has_len = nt.length is not None and abs(nt.length - nt.beats) > 1e-6
        if has_len:
            tok += f":{_fmt_beats(nt.beats)}:{_fmt_beats(nt.length)}"
        elif nt.beats != 1.0:
            tok += f":{_fmt_beats(nt.beats)}"
        out.append(tok)
    return " ".join(out)


def scale_degrees(root_midi: float, scale: str) -> np.ndarray:
    """All MIDI pitches of a scale across the full range, for quantisation."""
    steps = SCALES.get(scale, SCALES["chromatic"])
    root_pc = float(root_midi) % 12.0
    out = []
    for octv in range(-1, 10):
        for s in steps:
            out.append(root_pc + s + 12 * octv)
    return np.array(sorted(p for p in out if 0.0 <= p <= 127.0))


def quantize(midi: np.ndarray, grid: np.ndarray, amount: float = 1.0) -> np.ndarray:
    """Snap a pitch track to the nearest scale tone by ``amount`` (0..1)."""
    if amount <= 0.0 or grid.size == 0:
        return midi
    idx = np.searchsorted(grid, midi)
    idx = np.clip(idx, 1, len(grid) - 1)
    lo, hi = grid[idx - 1], grid[idx]
    target = np.where(np.abs(midi - lo) <= np.abs(hi - midi), lo, hi)
    return midi + (target - midi) * float(np.clip(amount, 0.0, 1.0))


def auto_melody(n_syllables: int, root: float, scale: str, style: str,
                rng: np.random.Generator) -> list[Note]:
    """Generate a melody when the user has not written one."""
    n = max(1, n_syllables)
    steps = SCALES.get(scale, SCALES["minor_pentatonic"])
    if style == "monotone":
        return [Note(root, 1.0) for _ in range(n)]
    if style == "rise":
        deg = [steps[min(i, len(steps) - 1) % len(steps)] for i in range(n)]
    elif style == "fall":
        deg = [steps[(len(steps) - 1 - i) % len(steps)] for i in range(n)]
    elif style == "arp":
        pattern = [0, 2, 4, 2] if len(steps) > 4 else [0, 1, 2, 1]
        deg = [steps[pattern[i % len(pattern)] % len(steps)] +
               12 * (pattern[i % len(pattern)] // len(steps)) for i in range(n)]
    else:  # "wander"
        deg, cur = [], 0
        for _ in range(n):
            deg.append(steps[cur % len(steps)] + 12 * (cur // len(steps)))
            cur = int(np.clip(cur + rng.integers(-2, 3), 0, len(steps) + 2))
    return [Note(root + d, 1.0) for d in deg]


def build_timeline(notes: list[Note], bpm: float, swing: float = 0.0,
                   gate: float = 1.0) -> float:
    """Assign absolute times to every note.  Returns the total length.

    ``gate`` scales the sounding length of notes that do not carry an explicit
    one, so a single control can make the whole line staccato or legato.
    """
    spb = 60.0 / max(bpm, 1.0)
    gate = float(min(max(gate, 0.05), 1.0))
    t = 0.0
    for i, nt in enumerate(notes):
        step = nt.beats * spb
        if swing and nt.beats <= 0.55:
            step *= (1.0 + swing) if i % 2 == 0 else (1.0 - swing)
        length = (nt.length * spb) if nt.length is not None else step * gate
        length = min(max(length, 1e-4), step)
        nt.start = t
        nt.end = t + length
        nt.slot_end = t + step
        t = nt.slot_end
    return t


# --------------------------------------------------------------------------
# pitch contour
# --------------------------------------------------------------------------

def contour(notes: list[Note], sr: int, n: int, p: dict,
            rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray]:
    """Build a per-sample MIDI pitch track plus a voiced/gate mask.

    Applies portamento, vibrato (with onset delay and ramp), random drift,
    cycle-to-cycle jitter, and per-note scoop/fall gestures.
    """
    t = np.arange(n) / sr
    base = np.full(n, float(p.get("pitch.root", 60.0)))
    gate = np.zeros(n)

    voiced_notes = [x for x in notes if x.midi is not None]
    if voiced_notes:
        for nt in notes:
            s = int(nt.start * sr)
            e_snd = min(int(nt.end * sr), n)
            e_slot = min(int(nt.slot_end * sr), n)
            if nt.midi is None:
                continue          # a rest leaves the pitch where it was, gate 0
            if e_slot > s:
                base[s:e_slot] = nt.midi
            if e_snd > s:
                gate[s:e_snd] = 1.0
        # hold the last pitch through any trailing samples
        last = voiced_notes[-1]
        e = min(int(last.slot_end * sr), n)
        if e < n:
            base[e:] = last.midi

    # ---- scoop into / fall out of notes -----------------------------------
    scoop = float(p.get("pitch.scoop", 0.0))
    scoop_ms = float(p.get("pitch.scoop_time", 70.0))
    fall = float(p.get("pitch.fall", 0.0))
    fall_ms = float(p.get("pitch.fall_time", 90.0))
    gesture = np.zeros(n)
    for nt in notes:
        if nt.midi is None:
            continue
        if scoop:
            s = int(nt.start * sr)
            ln = max(1, int(scoop_ms * 1e-3 * sr))
            e = min(s + ln, n)
            if e > s:
                ramp = np.linspace(1.0, 0.0, e - s) ** 2
                gesture[s:e] -= scoop * ramp
        if fall:
            e = min(int(nt.end * sr), n)
            ln = max(1, int(fall_ms * 1e-3 * sr))
            s = max(0, e - ln)
            if e > s:
                ramp = np.linspace(0.0, 1.0, e - s) ** 2
                gesture[s:e] -= fall * ramp

    # ---- portamento -------------------------------------------------------
    port = float(p.get("pitch.portamento", 45.0))
    track = dsp.dezip(base, sr, port) if port > 0 else base

    # ---- vibrato ----------------------------------------------------------
    rate = float(p.get("pitch.vibrato_rate", 5.5))
    depth = float(p.get("pitch.vibrato_depth", 0.0))
    delay = float(p.get("pitch.vibrato_delay", 250.0)) * 1e-3
    ramp_t = max(float(p.get("pitch.vibrato_ramp", 200.0)) * 1e-3, 1e-4)
    vib = np.zeros(n)
    if depth > 0.0:
        # vibrato restarts on every note so it feels sung, not LFO-modulated
        env = np.zeros(n)
        for nt in notes:
            if nt.midi is None:
                continue
            s = int(nt.start * sr)
            e = min(int(nt.end * sr), n)
            if e <= s:
                continue
            local = (np.arange(e - s) / sr) - delay
            env[s:e] = np.clip(local / ramp_t, 0.0, 1.0)
        drift_rate = rate * (1.0 + 0.04 * np.sin(2 * np.pi * 0.37 * t))
        phase = 2 * np.pi * np.cumsum(drift_rate) / sr
        vib = depth * env * np.sin(phase)

    # ---- drift and jitter -------------------------------------------------
    drift_amt = float(p.get("pitch.drift", 0.0))
    drift = np.zeros(n)
    if drift_amt > 0.0:
        w = rng.standard_normal(n)
        drift = dsp.dezip(w, sr, 260.0)
        m = np.max(np.abs(drift)) or 1.0
        drift = drift / m * drift_amt

    jit_amt = float(p.get("voice.pitch_jitter", 0.0))
    jitter = np.zeros(n)
    if jit_amt > 0.0:
        w = rng.standard_normal(n)
        jitter = dsp.dezip(w, sr, 12.0)
        m = np.max(np.abs(jitter)) or 1.0
        jitter = jitter / m * jit_amt

    track = track + vib + drift + jitter + gesture
    track += float(p.get("pitch.transpose", 0.0))
    track += float(p.get("pitch.fine", 0.0)) / 100.0

    q = float(p.get("pitch.quantize", 0.0))
    if q > 0.0:
        grid = scale_degrees(float(p.get("pitch.root", 60.0)),
                             str(p.get("pitch.scale", "chromatic")))
        track = quantize(track, grid, q)

    return np.clip(track, 8.0, 127.0), gate
