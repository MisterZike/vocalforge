"""Channel vocoder and its carrier oscillator.

The carrier tracks the voice's own f0 by default, which is what makes a
vocoder sound musical rather than like a ring modulator -- the robot sings the
melody you wrote.  Analysis and synthesis band mapping can be offset, giving a
formant shift that is characteristic of hardware vocoders.
"""
from __future__ import annotations

import numpy as np
from scipy import ndimage, signal

from . import dsp

WAVES = ("saw", "supersaw", "square", "pulse", "triangle", "sine", "noise", "pwm")


def band_edges(n_bands: int, lo: float, hi: float, spacing: str = "log"
               ) -> np.ndarray:
    n_bands = int(np.clip(n_bands, 2, 128))
    lo = max(float(lo), 20.0)
    hi = min(float(hi), 20000.0)
    if spacing == "mel":
        return dsp.mel_inv(np.linspace(dsp.mel(lo), dsp.mel(hi), n_bands + 1))
    if spacing == "linear":
        return np.linspace(lo, hi, n_bands + 1)
    return np.geomspace(lo, hi, n_bands + 1)


def _bp_sos(sr: int, lo: float, hi: float, order: int = 4) -> np.ndarray:
    lo = float(np.clip(lo, 15.0, sr * 0.47))
    hi = float(np.clip(hi, lo * 1.02, sr * 0.48))
    return signal.butter(order // 2, [lo, hi], btype="band", fs=sr, output="sos")


def envelope(x: np.ndarray, sr: int, attack_ms: float, release_ms: float
             ) -> np.ndarray:
    """Peak follower with near-instant attack and exponential release.

    ``maximum_filter1d`` gives the attack without a per-sample branch, and a
    one-pole handles the release; taking the max of the two keeps the attack
    sharp while the tail still decays smoothly.
    """
    a = max(int(sr * attack_ms * 1e-3), 1)
    peak = ndimage.maximum_filter1d(np.abs(x), size=a, mode="nearest")
    if attack_ms > 0.5:
        peak = dsp.smooth(peak, sr, attack_ms * 0.5)
    r = np.exp(-1.0 / max(sr * release_ms * 1e-3, 1.0))
    rel = signal.lfilter([1.0 - r], [1.0, -r], peak)
    return np.maximum(peak * 0.0 + rel, 0.0)


def carrier(f0: np.ndarray, sr: int, p: dict, rng: np.random.Generator
            ) -> np.ndarray:
    """Build the carrier as a stereo signal."""
    n = len(f0)
    wave = str(p.get("voc.carrier_wave", "supersaw"))
    voices = int(np.clip(p.get("voc.unison", 3), 1, 9))
    detune = float(p.get("voc.detune", 14.0)) / 1200.0       # cents -> octaves
    spread = float(np.clip(p.get("voc.spread", 0.6), 0.0, 1.0))
    pw = float(np.clip(p.get("voc.pulse_width", 0.42), 0.02, 0.98))
    sub = float(np.clip(p.get("voc.sub", 0.25), 0.0, 1.5))
    noise_mix = float(np.clip(p.get("voc.noise", 0.0), 0.0, 1.0))

    if str(p.get("voc.pitch_source", "follow")) == "fixed":
        base = np.full(n, dsp.midi_to_hz(float(p.get("voc.fixed_note", 48.0))))
    else:
        base = np.maximum(f0, 20.0)
    base = base * dsp.semitones(float(p.get("voc.transpose", -12.0)))

    chord = [float(v) for v in str(p.get("voc.chord", "0")).replace(",", " ").split()
             if v.strip().lstrip("-").replace(".", "").isdigit() or
             v.strip().lstrip("-").isdigit()]
    if not chord:
        chord = [0.0]

    out = np.zeros((n, 2))
    for iv in chord:
        f = base * dsp.semitones(iv)
        for v in range(voices):
            off = 0.0 if voices == 1 else (v / (voices - 1) - 0.5) * 2.0
            ph = np.cumsum(f * (2.0 ** (off * detune))) / sr
            ph += rng.random()
            x = np.mod(ph, 1.0)
            if wave == "saw":
                w = 2.0 * x - 1.0
            elif wave == "supersaw":
                w = 2.0 * x - 1.0
                w = 0.65 * w + 0.35 * (2.0 * np.mod(ph * 1.005 + 0.3, 1.0) - 1.0)
            elif wave == "square":
                w = np.where(x < 0.5, 1.0, -1.0)
            elif wave == "pulse":
                w = np.where(x < pw, 1.0, -1.0)
            elif wave == "pwm":
                lfo = 0.5 + 0.45 * np.sin(2 * np.pi * 0.7 * np.arange(n) / sr)
                w = np.where(x < lfo * pw * 2.0, 1.0, -1.0)
            elif wave == "triangle":
                w = 4.0 * np.abs(x - 0.5) - 1.0
            elif wave == "sine":
                w = np.sin(2 * np.pi * ph)
            else:
                w = rng.standard_normal(n) * 0.5
            pan = 0.5 + 0.5 * off * spread
            out[:, 0] += w * np.sqrt(1.0 - pan)
            out[:, 1] += w * np.sqrt(pan)
        if sub > 0.0:
            sph = np.cumsum(f * 0.5) / sr
            sw = np.sign(np.sin(2 * np.pi * sph)) * sub
            out[:, 0] += sw
            out[:, 1] += sw

    out /= max(np.sqrt(len(chord) * voices), 1.0)
    if noise_mix > 0.0:
        nz = rng.standard_normal((n, 2)) * 0.4
        out = out * (1.0 - noise_mix) + nz * noise_mix
    return dsp.normalize(out, -6.0)


def vocode(mod: np.ndarray, car: np.ndarray, sr: int, p: dict) -> np.ndarray:
    """Classic channel vocoder.  ``mod`` is mono, ``car`` is stereo."""
    n_bands = int(np.clip(p.get("voc.bands", 24), 2, 128))
    lo = float(p.get("voc.low_hz", 110.0))
    hi = float(p.get("voc.high_hz", 8000.0))
    spacing = str(p.get("voc.spacing", "log"))
    atk = float(p.get("voc.attack", 3.0))
    rel = float(p.get("voc.release", 22.0))
    shift = int(p.get("voc.band_shift", 0))
    tilt = float(p.get("voc.tilt", 0.0))          # dB across the band range
    order = int(np.clip(p.get("voc.order", 4), 2, 8))

    edges = band_edges(n_bands, lo, hi, spacing)
    car = dsp.stereo(car)
    out = np.zeros_like(car)

    sos = [_bp_sos(sr, edges[i], edges[i + 1], order) for i in range(n_bands)]
    envs = []
    for i in range(n_bands):
        b = signal.sosfilt(sos[i], mod)
        envs.append(envelope(b, sr, atk, rel))

    for i in range(n_bands):
        src = int(np.clip(i - shift, 0, n_bands - 1))
        g = envs[src]
        if tilt:
            g = g * dsp.db_to_lin(tilt * (i / max(n_bands - 1, 1) - 0.5))
        cb = signal.sosfilt(sos[i], car, axis=0)
        out += cb * g[:, None]

    # match the modulator's loudness so band count does not change level
    me = np.sqrt(np.mean(mod ** 2)) or 1.0
    oe = np.sqrt(np.mean(out ** 2)) or 1.0
    out *= me / oe

    # unvoiced passthrough keeps consonants intelligible
    sib = float(np.clip(p.get("voc.sibilance", 0.35), 0.0, 1.5))
    if sib > 0.0:
        hp = dsp.sos_apply(dsp.biquad_highpass(sr, float(p.get("voc.sib_hz", 4500.0)),
                                               0.7), mod)
        hpe = envelope(hp, sr, 1.0, 12.0)
        gate = np.clip(hpe / (envelope(np.abs(mod), sr, 1.0, 40.0) + 1e-6), 0.0, 1.0)
        out += (hp * gate * sib)[:, None]

    return out
