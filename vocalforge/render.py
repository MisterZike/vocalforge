"""Full render pipeline: text + parameters -> finished stereo sample."""
from __future__ import annotations

import time
from typing import Callable

import numpy as np

from . import dsp, effects as fx, melody, params, synth, vocoder

# The signal chain, in order.  Each entry is (label, callable).
CHAIN: list[tuple[str, Callable]] = [
    ("gate", fx.gate_fx),
    ("eq", fx.eq),
    ("de-ess", fx.deesser),
    ("compressor", fx.compressor),
    ("saturation", fx.saturate),
    ("chorus", fx.chorus),
    ("phaser", fx.phaser),
    ("delay", fx.delay_fx),
    ("reverb", fx.reverb),
    ("width", fx.width),
]


def render(text: str, raw_params: dict | None = None,
           progress: Callable[[str, float], None] | None = None
           ) -> tuple[np.ndarray, int, dict]:
    """Render ``text`` with ``raw_params``.  Returns (stereo audio, sr, info)."""
    p = params.normalize_params(raw_params)
    sr = int(p["render.sr"])
    seed = int(p["render.seed"])
    rng = np.random.default_rng(seed if seed else None)
    t_start = time.time()

    def tick(stage: str, frac: float):
        if progress:
            progress(stage, frac)

    # ---- 1. voice ---------------------------------------------------------
    tick("synthesising voice", 0.05)
    notes = melody.parse_melody(str(p.get("pitch.melody", "")))
    dry, segs, f0, detail = synth.render_voice(text, notes, p, sr, rng)
    voice_len = len(dry)

    # ---- 2. post formant shift -------------------------------------------
    if abs(float(p["fx.formant_shift"])) > 1e-3:
        tick("formant shift", 0.25)
        dry = fx.formant_shift(dry, sr, float(p["fx.formant_shift"]))

    # ---- 3. vocoder -------------------------------------------------------
    voc_mix = float(p["voc.mix"])
    if voc_mix > 0.0:
        tick("vocoding", 0.35)
        car = vocoder.carrier(f0[:len(dry)], sr, p, rng)
        wet = vocoder.vocode(dry, car, sr, p)
        x = dsp.stereo(dry) * (1.0 - voc_mix) + wet * voc_mix
    else:
        x = dry

    # ---- 4. harmony and unison -------------------------------------------
    if float(p["harm.mix"]) > 0.0 and str(p["harm.intervals"]).strip():
        tick("harmonising", 0.45)
        x = fx.harmonize(x, sr, p, rng)
    if int(p["uni.voices"]) > 0:
        tick("unison", 0.5)
        x = fx.unison(x, sr, p, rng)

    # ---- 5. effect chain --------------------------------------------------
    for i, (label, func) in enumerate(CHAIN):
        tick(label, 0.55 + 0.4 * i / len(CHAIN))
        x = func(x, sr, p, rng)

    # ---- 6. output stage --------------------------------------------------
    tick("output", 0.96)
    x = dsp.stereo(x)
    keep = voice_len + int(float(p["render.tail"]) * sr)
    if len(x) > keep:
        x = x[:keep]
    x = x * dsp.db_to_lin(float(p["out.gain"]))
    if p["out.normalize"]:
        x = dsp.normalize(x, float(p["out.ceiling"]))
    x = fx.limiter(x, sr, p, rng)
    if p["out.normalize"]:
        x = dsp.normalize(x, float(p["out.ceiling"]))
    x = dsp.fade(x, sr, 3.0, 20.0)

    info = {
        "duration": len(x) / sr,
        "sample_rate": sr,
        "render_time": round(time.time() - t_start, 3),
        "phonemes": " ".join(s.phone.name for s in segs),
        "peak_db": round(float(dsp.lin_to_db(np.max(np.abs(x)) if x.size else 0)), 2),
    }
    info.update(alignment(segs, detail["notes"], detail["syllables"],
                          detail["midi"], detail["gate"], sr,
                          float(p["pitch.bpm"]), voice_len / sr))
    tick("done", 1.0)
    return x, sr, info


# --------------------------------------------------------------------------
# alignment -- what the melody editor draws
# --------------------------------------------------------------------------

NOTE_NAMES = ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]


def note_name(midi: float) -> str:
    m = int(round(midi))
    return f"{NOTE_NAMES[m % 12]}{m // 12 - 1}"


def alignment(segs, notes, sylls, midi_track, gate_track, sr: int,
              bpm: float, voice_dur: float, points: int = 900) -> dict:
    """Package the phoneme/note/pitch mapping for the UI."""
    beat = 60.0 / max(bpm, 1.0)
    note_rows = []
    at = 0.0                              # running position in beats
    for i, nt in enumerate(notes):
        note_rows.append({
            "i": i, "midi": nt.midi,
            "name": note_name(nt.midi) if nt.midi is not None else "rest",
            "start": round(nt.start, 4), "end": round(nt.end, 4),
            "slot_end": round(nt.slot_end, 4),
            "beats": nt.beats, "length": nt.length,
            "start_beat": round(at, 6),
            "len_beats": round(nt.length if nt.length is not None else nt.beats, 6),
            "sound_beats": round((nt.end - nt.start) / beat, 6),
        })
        at += nt.beats

    seg_rows = [{
        "p": s.phone.name, "cls": s.phone.cls, "role": s.role,
        "syl": s.syl, "note": s.note_idx, "word": s.word,
        "s": round(s.start, 4), "e": round(s.end, 4),
    } for s in segs]

    syl_rows = []
    for i, sy in enumerate(sylls):
        mine = [s for s in segs if s.syl == i]
        if not mine:
            continue
        nuc = next((s for s in mine if s.role == "nucleus"), None)
        syl_rows.append({
            "i": i, "text": sy.text, "word": sy.word,
            "note": mine[0].note_idx,
            "s": round(min(s.start for s in mine), 4),
            "e": round(max(s.end for s in mine), 4),
            "vowel_on": round(nuc.start, 4) if nuc else None,
            "nucleus": sy.nucleus,
            "phones": sy.phones,
        })

    n = len(midi_track)
    if n:
        step = max(n // points, 1)
        idx = np.arange(0, n, step)
        pitch = {
            "hz": round(sr / step, 3),
            "midi": [round(float(v), 3) for v in midi_track[idx]],
            "gate": [int(v > 0.5) for v in gate_track[idx]],
        }
    else:
        pitch = {"hz": 1.0, "midi": [], "gate": []}

    return {
        "notes": note_rows, "segments": seg_rows, "syllables": syl_rows,
        "pitch": pitch, "bpm": bpm, "beat": beat,
        "total_beats": round(at, 6),
        "voice_duration": round(voice_dur, 4),
    }


def align(text: str, raw_params: dict | None = None, curve_hz: int = 400) -> dict:
    """Compute the phoneme/note mapping without synthesising any audio.

    Fast enough (a few milliseconds) to run on every edit in the melody editor.
    """
    p = params.normalize_params(raw_params)
    seed = int(p["render.seed"])
    rng = np.random.default_rng(seed if seed else 0)
    notes = melody.parse_melody(str(p.get("pitch.melody", "")))
    _, _, notes, segs, lead, total, sylls = synth.prepare(text, notes, p, rng)
    n = max(int(total * curve_hz), 2)
    midi, gate = melody.contour(notes, curve_hz, n, p, rng)
    out = alignment(segs, notes, sylls, midi, gate, curve_hz,
                    float(p["pitch.bpm"]), total)
    out["duration"] = round(total, 4)
    out["lead"] = round(lead, 4)
    return out


def waveform_preview(x: np.ndarray, points: int = 900) -> list[list[float]]:
    """Min/max envelope pairs for drawing the waveform in the UI."""
    m = dsp.mono(x)
    if len(m) == 0:
        return []
    step = max(len(m) // points, 1)
    n = len(m) // step * step
    blocks = m[:n].reshape(-1, step)
    return [[round(float(v), 4), round(float(w), 4)]
            for v, w in zip(blocks.min(axis=1), blocks.max(axis=1))]
