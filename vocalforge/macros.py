"""Macro controls: a handful of knobs that drive many parameters at once.

Each macro owns a set of target parameters and a breakpoint curve per target.
Turning a macro writes all of its targets; it never reads them back, so the
model is simply "this knob owns these values".

One target is marked as the macro's ``probe``.  Loading a preset does *not*
run the curves (that would flatten the preset) -- instead the probe curve is
inverted to work out roughly where each knob is sitting, so the panel shows a
truthful starting position for whatever voice is loaded.

Curves are plain data so the browser and the CLI evaluate them identically.
A breakpoint is ``[macro_position, parameter_value]`` with positions in 0..1.
String values (enum parameters) step rather than interpolate.
"""
from __future__ import annotations

from typing import Any

from . import params


def _m(key, label, colour, blurb, probe, targets, lo_label, hi_label):
    return {
        "key": key, "label": label, "colour": colour, "blurb": blurb,
        "probe": probe, "targets": targets,
        "lo": lo_label, "hi": hi_label,
    }


MACROS: list[dict[str, Any]] = [
    # ---------------------------------------------------------- the voice ---
    _m("body", "BODY", "#FF8A3D",
       "Size of the singer: vocal tract length and where the formants sit.",
       "voice.tract_length", {
           "voice.tract_length":  [[0, 0.60], [0.5, 1.00], [1, 1.45]],
           "voice.formant_shift": [[0, 5.0], [0.5, 0.0], [1, -5.0]],
       }, "tiny", "huge"),

    _m("air", "AIR", "#8FE3FF",
       "Breath in the tone: aspiration noise, how open the glottis sits, "
       "and how much sibilance comes through.",
       "voice.breathiness", {
           "voice.breathiness":    [[0, 0.0], [0.5, 0.25], [1, 1.20]],
           "voice.open_quotient":  [[0, 0.45], [0.5, 0.62], [1, 0.88]],
           "voice.speed_quotient": [[0, 3.0], [0.5, 2.2], [1, 1.4]],
           "art.sibilance":        [[0, 0.8], [0.5, 1.0], [1, 1.6]],
       }, "pressed", "breathy"),

    _m("tone", "TONE", "#FFD21E",
       "Dark and round through to bright and forward.",
       "voice.tilt", {
           "voice.tilt":      [[0, -10.0], [0.5, 0.0], [1, 6.0]],
           "eq.high_gain":    [[0, -5.0], [0.5, 1.0], [1, 7.0]],
           "eq.low_gain":     [[0, 4.0], [0.5, 0.5], [1, -2.0]],
           "eq.lp":           [[0, 3200], [0.4, 12000], [1, 20000]],
           "voice.formant_q": [[0, 0.85], [0.5, 1.0], [1, 1.30]],
       }, "dark", "bright"),

    _m("grit", "GRIT", "#FF3B30",
       "Roughness: vocal effort, subharmonic growl, saturation and bit crush.",
       "sat.drive", {
           "sat.drive":     [[0, 0.0], [0.5, 7.0], [1, 22.0]],
           "voice.growl":   [[0, 0.0], [0.45, 0.0], [1, 0.60]],
           "voice.effort":  [[0, 0.35], [0.5, 0.5], [1, 0.85]],
           "sat.bits":      [[0, 16], [0.75, 16], [1, 7]],
           "sat.type":      [[0, "tube"], [0.6, "tape"], [0.85, "fold"]],
       }, "clean", "savage"),

    # --------------------------------------------------------- performance ---
    _m("life", "LIFE", "#FF5FA2",
       "Machine to human: pitch jitter, shimmer, drift, glide and how hard "
       "the pitch is snapped to the scale.",
       "voice.pitch_jitter", {
           "voice.pitch_jitter": [[0, 0.0], [0.5, 0.045], [1, 0.12]],
           "voice.shimmer":      [[0, 0.0], [0.5, 0.04], [1, 0.12]],
           "pitch.drift":        [[0, 0.0], [0.5, 0.06], [1, 0.25]],
           "pitch.quantize":     [[0, 1.0], [0.35, 0.55], [0.6, 0.0], [1, 0.0]],
           "pitch.portamento":   [[0, 0.0], [0.35, 25], [1, 110]],
           "pitch.scoop":        [[0, 0.0], [0.6, 0.0], [1, 0.9]],
       }, "machine", "human"),

    _m("motion", "MOTION", "#4D7CFF",
       "Vibrato depth and speed, and how soon it arrives on each note.",
       "pitch.vibrato_depth", {
           "pitch.vibrato_depth": [[0, 0.0], [0.5, 0.35], [1, 1.20]],
           "pitch.vibrato_rate":  [[0, 4.5], [0.5, 5.5], [1, 6.8]],
           "pitch.vibrato_delay": [[0, 700], [0.5, 280], [1, 60]],
           "pitch.vibrato_ramp":  [[0, 500], [0.5, 220], [1, 90]],
       }, "still", "operatic"),

    _m("diction", "DICTION", "#3DDC6B",
       "Slurred and legato through to clipped and consonant-forward.",
       "art.glide", {
           "art.glide":            [[0, 110], [0.5, 32], [1, 8]],
           "art.consonant_length": [[0, 1.35], [0.5, 1.0], [1, 0.75]],
           "art.consonant_gain":   [[0, 0.7], [0.5, 1.0], [1, 1.7]],
           "art.legato":           [[0, 0.95], [0.5, 0.5], [1, 0.15]],
       }, "slurred", "crisp"),

    # ------------------------------------------------------------ treatment ---
    _m("robot", "ROBOT", "#00E0C6",
       "Vocoder amount. Turn it up and the voice plays a synth instead of "
       "its own vocal cords.",
       "voc.mix", {
           "voc.mix":       [[0, 0.0], [1, 1.0]],
           "voc.bands":     [[0, 32], [0.5, 24], [1, 14]],
           "voc.sibilance": [[0, 0.35], [1, 0.50]],
           "voc.sub":       [[0, 0.25], [1, 0.40]],
       }, "vocal", "robot"),

    _m("thick", "THICK", "#B15CFF",
       "Stacked detuned copies and stereo spread.",
       "uni.voices", {
           "uni.voices":  [[0, 0], [0.25, 2], [0.6, 4], [1, 7]],
           "uni.detune":  [[0, 6], [0.5, 13], [1, 28]],
           "uni.mix":     [[0, 0.30], [0.5, 0.55], [1, 0.78]],
           "st.width":    [[0, 1.0], [0.5, 1.25], [1, 1.70]],
       }, "single", "wall"),

    _m("space", "SPACE", "#9FB0D0",
       "Reverb and delay: how far away the voice sounds.",
       "rev.mix", {
           "rev.mix":   [[0, 0.0], [0.5, 0.28], [1, 0.60]],
           "rev.size":  [[0, 0.5], [0.5, 0.85], [1, 1.40]],
           "rev.decay": [[0, 0.60], [0.5, 0.80], [1, 0.93]],
           "dly.mix":   [[0, 0.0], [0.5, 0.18], [1, 0.42]],
       }, "dry", "cathedral"),
]

BY_KEY = {m["key"]: m for m in MACROS}


# --------------------------------------------------------------------------
# curve evaluation
# --------------------------------------------------------------------------

def eval_curve(points: list, v: float) -> Any:
    """Piecewise-linear for numbers, step for strings."""
    v = min(max(float(v), 0.0), 1.0)
    if not points:
        return None
    if isinstance(points[0][1], str):
        out = points[0][1]
        for x, y in points:
            if v >= x:
                out = y
        return out
    if v <= points[0][0]:
        return float(points[0][1])
    if v >= points[-1][0]:
        return float(points[-1][1])
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        if x0 <= v <= x1:
            t = 0.0 if x1 == x0 else (v - x0) / (x1 - x0)
            return float(y0) + (float(y1) - float(y0)) * t
    return float(points[-1][1])


def invert_curve(points: list, value: Any) -> float:
    """Best-effort inverse: where would the knob be to produce ``value``?"""
    if not points or isinstance(points[0][1], str):
        return 0.5
    ys = [float(y) for _, y in points]
    xs = [float(x) for x, _ in points]
    try:
        value = float(value)
    except (TypeError, ValueError):
        return 0.5
    rising = ys[-1] >= ys[0]
    if (rising and value <= ys[0]) or (not rising and value >= ys[0]):
        return xs[0]
    if (rising and value >= ys[-1]) or (not rising and value <= ys[-1]):
        return xs[-1]
    for i in range(len(ys) - 1):
        a, b = ys[i], ys[i + 1]
        if (a <= value <= b) or (b <= value <= a):
            t = 0.0 if b == a else (value - a) / (b - a)
            return xs[i] + (xs[i + 1] - xs[i]) * t
    return 0.5


# --------------------------------------------------------------------------
# public API
# --------------------------------------------------------------------------

def apply(p: dict, key: str, value: float) -> dict:
    """Write one macro's targets into a parameter dict (mutates and returns)."""
    m = BY_KEY.get(key)
    if not m:
        return p
    for target, points in m["targets"].items():
        if target in params.BY_KEY:
            p[target] = params.coerce(target, eval_curve(points, value))
    return p


def apply_many(p: dict, values: dict[str, float]) -> dict:
    for k, v in values.items():
        apply(p, k, v)
    return p


def derive(p: dict) -> dict[str, float]:
    """Read knob positions back out of a parameter set, via each probe."""
    out = {}
    for m in MACROS:
        probe = m["probe"]
        out[m["key"]] = round(
            invert_curve(m["targets"][probe], p.get(probe)), 4)
    return out


def describe() -> list[dict]:
    """Macro definitions as plain JSON for the UI."""
    rows = []
    for m in MACROS:
        rows.append({
            **{k: m[k] for k in ("key", "label", "colour", "blurb", "probe",
                                 "targets", "lo", "hi")},
            "labels": {t: params.BY_KEY[t]["label"]
                       for t in m["targets"] if t in params.BY_KEY},
            "units": {t: params.BY_KEY[t]["unit"]
                      for t in m["targets"] if t in params.BY_KEY},
        })
    return rows
