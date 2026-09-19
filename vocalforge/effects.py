"""The effect rack.

Every effect takes ``(x, sr, p, rng)`` where ``p`` is the flat parameter dict
and returns audio of the same length.  Mono input is promoted to stereo by the
first effect that needs it; ``render`` keeps track.
"""
from __future__ import annotations

import numpy as np
from scipy import ndimage, signal

from . import dsp

# --------------------------------------------------------------------------
# pitch shifting (also used by the harmoniser, unison and shimmer reverb)
# --------------------------------------------------------------------------

def pitch_shift(x: np.ndarray, sr: int, semis: float,
                window_ms: float = 55.0) -> np.ndarray:
    """Two-head crossfading delay-line pitch shifter.

    Transparent for the small shifts used by unison/detune, and musically
    usable for harmony intervals.  Fully vectorised.
    """
    if abs(semis) < 1e-4:
        return x
    mono_in = x.ndim == 1
    X = x[:, None] if mono_in else x
    n = X.shape[0]
    r = 2.0 ** (semis / 12.0)
    W = max(int(window_ms * 1e-3 * sr), 64)

    t = np.arange(n, dtype=np.float64)
    ph = np.mod((1.0 - r) * t / W, 1.0)
    i1 = t - ph * W
    i2 = t - np.mod(ph + 0.5, 1.0) * W
    w1 = np.sin(np.pi * ph) ** 2
    w2 = 1.0 - w1

    out = np.empty_like(X)
    for c in range(X.shape[1]):
        ch = X[:, c]
        out[:, c] = (dsp.fractional_delay_read(ch, i1) * w1 +
                     dsp.fractional_delay_read(ch, i2) * w2)
    return out[:, 0] if mono_in else out


# --------------------------------------------------------------------------
# formant shifting (spectral envelope warp)
# --------------------------------------------------------------------------

def formant_shift(x: np.ndarray, sr: int, semis: float) -> np.ndarray:
    """Shift the spectral envelope without moving pitch.

    Works by lifting the cepstral envelope out of each STFT frame, resampling
    it along the frequency axis, and re-applying the ratio.
    """
    if abs(semis) < 1e-3:
        return x
    mono_in = x.ndim == 1
    X = x[:, None] if mono_in else x
    n_fft, hop = 2048, 512
    ratio = 2.0 ** (semis / 12.0)
    out = np.empty_like(X)
    bins = n_fft // 2 + 1
    src = np.clip(np.arange(bins) / ratio, 0, bins - 1)

    for c in range(X.shape[1]):
        spec, win = dsp.stft(X[:, c], n_fft, hop)
        mag = np.abs(spec) + 1e-9
        logm = np.log(mag)
        ceps = np.fft.irfft(logm, axis=1)
        ceps[:, 40:-40] = 0.0
        env = np.exp(np.real(np.fft.rfft(ceps, axis=1)))[:, :bins]
        new_env = np.empty_like(env)
        for i in range(env.shape[0]):
            new_env[i] = np.interp(src, np.arange(bins), env[i])
        spec = spec * (new_env / np.maximum(env, 1e-9))
        out[:, c] = dsp.pad_to(dsp.istft(spec, n_fft, hop, win, X.shape[0]),
                               X.shape[0])
    return out[:, 0] if mono_in else out


# --------------------------------------------------------------------------
# dynamics
# --------------------------------------------------------------------------

def _follow(x: np.ndarray, sr: int, atk_ms: float, rel_ms: float,
            rms: bool = False) -> np.ndarray:
    det = np.sqrt(dsp.smooth(x ** 2, sr, 8.0)) if rms else np.abs(x)
    a = max(int(sr * atk_ms * 1e-3), 1)
    peak = ndimage.maximum_filter1d(det, size=a, mode="nearest")
    r = np.exp(-1.0 / max(sr * rel_ms * 1e-3, 1.0))
    return signal.lfilter([1.0 - r], [1.0, -r], peak)


def compressor(x: np.ndarray, sr: int, p: dict, rng=None) -> np.ndarray:
    ratio = max(float(p.get("comp.ratio", 3.0)), 1.0)
    if ratio <= 1.001 or not p.get("comp.on", True):
        return x
    thr = float(p.get("comp.threshold", -18.0))
    knee = max(float(p.get("comp.knee", 6.0)), 0.01)
    atk = float(p.get("comp.attack", 6.0))
    rel = float(p.get("comp.release", 90.0))
    mix = float(np.clip(p.get("comp.mix", 1.0), 0.0, 1.0))

    det = dsp.mono(x)
    env = _follow(det, sr, atk, rel, rms=bool(p.get("comp.rms", True)))
    lvl = dsp.lin_to_db(env)
    over = lvl - thr
    # soft knee
    gr = np.where(
        over <= -knee / 2, 0.0,
        np.where(over >= knee / 2,
                 over * (1.0 / ratio - 1.0),
                 (1.0 / ratio - 1.0) * (over + knee / 2) ** 2 / (2 * knee)))
    gain = dsp.db_to_lin(gr + float(p.get("comp.makeup", 0.0)))
    gain = dsp.smooth(gain, sr, 1.5)
    g = gain if x.ndim == 1 else gain[:, None]
    return x * (1.0 - mix) + x * g * mix


def deesser(x: np.ndarray, sr: int, p: dict, rng=None) -> np.ndarray:
    amt = float(np.clip(p.get("deess.amount", 0.0), 0.0, 1.0))
    if amt <= 0.0:
        return x
    fc = float(p.get("deess.freq", 6200.0))
    hp = dsp.sos_apply(dsp.biquad_highpass(sr, fc, 0.7), dsp.mono(x))
    env = _follow(hp, sr, 1.0, 30.0)
    thr = dsp.db_to_lin(float(p.get("deess.threshold", -30.0)))
    gr = np.clip(thr / np.maximum(env, 1e-6), 0.0, 1.0) ** (amt * 2.0)
    gr = dsp.smooth(gr, sr, 2.0)
    band = dsp.sos_apply(dsp.biquad_highpass(sr, fc, 0.7), x)
    g = gr if x.ndim == 1 else gr[:, None]
    return x - band * (1.0 - g)


def gate_fx(x: np.ndarray, sr: int, p: dict, rng=None) -> np.ndarray:
    """Rhythmic trance gate synced to the project tempo."""
    depth = float(np.clip(p.get("gate.depth", 0.0), 0.0, 1.0))
    if depth <= 0.0:
        return x
    bpm = float(p.get("pitch.bpm", 120.0))
    div = float(p.get("gate.division", 8.0))          # 8 == 1/8 notes
    period = 60.0 / max(bpm, 1.0) * (4.0 / max(div, 0.25))
    duty = float(np.clip(p.get("gate.duty", 0.5), 0.02, 0.99))
    n = x.shape[0]
    t = np.arange(n) / sr
    ph = np.mod(t / period + float(p.get("gate.offset", 0.0)), 1.0)
    env = (ph < duty).astype(np.float64)
    env = dsp.dezip(env, sr, max(float(p.get("gate.smooth", 6.0)), 0.1))
    env = 1.0 - depth * (1.0 - env)
    return x * (env if x.ndim == 1 else env[:, None])


# --------------------------------------------------------------------------
# tone
# --------------------------------------------------------------------------

def eq(x: np.ndarray, sr: int, p: dict, rng=None) -> np.ndarray:
    if not p.get("eq.on", True):
        return x
    y = x
    if float(p.get("eq.hp", 0.0)) > 20.0:
        y = dsp.sos_apply(dsp.biquad_highpass(sr, p["eq.hp"], 0.707), y)
        y = dsp.sos_apply(dsp.biquad_highpass(sr, p["eq.hp"], 0.707), y)
    if float(p.get("eq.low_gain", 0.0)) != 0.0:
        y = dsp.sos_apply(dsp.biquad_lowshelf(sr, float(p.get("eq.low_freq", 180.0)),
                                              0.7, float(p["eq.low_gain"])), y)
    for i in (1, 2):
        g = float(p.get(f"eq.mid{i}_gain", 0.0))
        if g != 0.0:
            y = dsp.sos_apply(dsp.biquad_peak(
                sr, float(p.get(f"eq.mid{i}_freq", 1000.0 * i)),
                float(p.get(f"eq.mid{i}_q", 1.0)), g), y)
    if float(p.get("eq.high_gain", 0.0)) != 0.0:
        y = dsp.sos_apply(dsp.biquad_highshelf(sr, float(p.get("eq.high_freq", 6000.0)),
                                               0.7, float(p["eq.high_gain"])), y)
    lp = float(p.get("eq.lp", 20000.0))
    if lp < sr * 0.45:
        y = dsp.sos_apply(dsp.biquad_lowpass(sr, lp, 0.707), y)
        y = dsp.sos_apply(dsp.biquad_lowpass(sr, lp, 0.707), y)
    return y


def saturate(x: np.ndarray, sr: int, p: dict, rng=None) -> np.ndarray:
    drive = float(p.get("sat.drive", 0.0))
    bits = float(p.get("sat.bits", 16.0))
    ds = float(p.get("sat.downsample", 1.0))
    if drive <= 0.0 and bits >= 16.0 and ds <= 1.0:
        return x
    y = x
    if drive > 0.0:
        kind = str(p.get("sat.type", "tube"))
        g = dsp.db_to_lin(drive)
        z = y * g
        if kind == "tube":
            y = np.sign(z) * (1.0 - np.exp(-np.abs(z)))
        elif kind == "tape":
            y = np.tanh(z * 0.8) * 1.05
        elif kind == "fold":
            y = np.sin(np.clip(z, -8, 8) * 1.2)
        elif kind == "clip":
            y = np.clip(z, -1.0, 1.0)
        elif kind == "diode":
            y = np.where(z > 0, np.tanh(z), 0.55 * np.tanh(z * 1.7))
        else:
            y = np.tanh(z)
        y /= max(dsp.db_to_lin(drive * 0.35), 1e-6)
    if bits < 16.0:
        q = 2.0 ** max(bits, 1.0)
        y = np.round(y * q) / q
    if ds > 1.0:
        step = int(np.clip(ds, 1, 200))
        idx = (np.arange(y.shape[0]) // step) * step
        y = y[idx]
    mix = float(np.clip(p.get("sat.mix", 1.0), 0.0, 1.0))
    return x * (1.0 - mix) + y * mix


# --------------------------------------------------------------------------
# modulation / space
# --------------------------------------------------------------------------

def unison(x: np.ndarray, sr: int, p: dict, rng=None) -> np.ndarray:
    """Detuned, delayed copies -- the classic thick EDM vocal stack."""
    voices = int(np.clip(p.get("uni.voices", 0), 0, 8))
    if voices <= 0:
        return dsp.stereo(x)
    detune = float(p.get("uni.detune", 12.0)) / 100.0      # cents -> semitones
    spread = float(np.clip(p.get("uni.spread", 0.8), 0.0, 1.0))
    delay_ms = float(p.get("uni.delay", 14.0))
    mix = float(np.clip(p.get("uni.mix", 0.6), 0.0, 1.0))
    m = dsp.mono(x)
    n = len(m)
    acc = np.zeros((n, 2))
    for v in range(voices):
        off = (v / max(voices - 1, 1) - 0.5) * 2.0 if voices > 1 else 0.0
        sh = pitch_shift(m, sr, off * detune)
        d = int(sr * delay_ms * 1e-3 * (0.35 + 0.65 * abs(off)))
        sh = np.concatenate([np.zeros(d), sh])[:n]
        pan = 0.5 + 0.5 * off * spread
        acc[:, 0] += sh * np.sqrt(1.0 - pan)
        acc[:, 1] += sh * np.sqrt(pan)
    acc /= np.sqrt(voices)
    base = dsp.stereo(x)
    return base * (1.0 - mix * 0.5) + acc * mix


def harmonize(x: np.ndarray, sr: int, p: dict, rng=None) -> np.ndarray:
    ivs = str(p.get("harm.intervals", "")).replace(",", " ").split()
    mix = float(np.clip(p.get("harm.mix", 0.0), 0.0, 1.0))
    if not ivs or mix <= 0.0:
        return x
    base = dsp.stereo(x)
    m = dsp.mono(x)
    acc = np.zeros_like(base)
    spread = float(np.clip(p.get("harm.spread", 0.7), 0.0, 1.0))
    for i, tok in enumerate(ivs):
        try:
            iv = float(tok)
        except ValueError:
            continue
        v = pitch_shift(m, sr, iv, window_ms=float(p.get("harm.window", 70.0)))
        pan = 0.5 + 0.5 * ((i / max(len(ivs) - 1, 1)) - 0.5) * 2.0 * spread
        acc[:, 0] += v * np.sqrt(1.0 - pan)
        acc[:, 1] += v * np.sqrt(pan)
    acc /= np.sqrt(max(len(ivs), 1))
    return base + acc * mix


def chorus(x: np.ndarray, sr: int, p: dict, rng=None) -> np.ndarray:
    depth = float(p.get("cho.depth", 0.0))
    if depth <= 0.0:
        return dsp.stereo(x)
    X = dsp.stereo(x)
    n = X.shape[0]
    rate = float(p.get("cho.rate", 0.6))
    base_ms = float(p.get("cho.delay", 18.0))
    mix = float(np.clip(p.get("cho.mix", 0.4), 0.0, 1.0))
    fb = float(np.clip(p.get("cho.feedback", 0.0), -0.9, 0.9))
    voices = int(np.clip(p.get("cho.voices", 2), 1, 6))
    t = np.arange(n) / sr
    out = np.zeros_like(X)
    for v in range(voices):
        phase = 2 * np.pi * (v / voices)
        for c in range(2):
            lfo = np.sin(2 * np.pi * rate * t + phase + c * np.pi / 2)
            d = (base_ms + depth * lfo) * 1e-3 * sr
            src = X[:, c]
            if fb:
                src = dsp.comb_feedback(src, max(int(base_ms * 1e-3 * sr), 1), fb)
            out[:, c] += dsp.fractional_delay_read(src, np.arange(n) - d)
    out /= voices
    return X * (1.0 - mix) + out * mix


def phaser(x: np.ndarray, sr: int, p: dict, rng=None) -> np.ndarray:
    depth = float(np.clip(p.get("pha.depth", 0.0), 0.0, 1.0))
    if depth <= 0.0:
        return x
    X = dsp.stereo(x)
    n = X.shape[0]
    stages = int(np.clip(p.get("pha.stages", 6), 2, 12))
    rate = float(p.get("pha.rate", 0.35))
    fb = float(np.clip(p.get("pha.feedback", 0.4), -0.95, 0.95))
    t = np.arange(n) / sr
    out = np.zeros_like(X)
    block = 256
    nb = dsp.n_blocks(n, block)
    for c in range(2):
        lfo = 0.5 + 0.5 * np.sin(2 * np.pi * rate * t + c * np.pi / 3)
        f = 250.0 * (16.0 ** lfo)
        fb_blk = dsp.blockify(f, block)
        y = X[:, c].copy()
        if fb:
            y = y + fb * dsp.comb_feedback(y, max(int(0.003 * sr), 1), fb * 0.5)
        zi = np.zeros((stages, 2))
        res = np.empty(n)
        for i in range(nb):
            s, e = i * block, min((i + 1) * block, n)
            if s >= e:
                break
            fc = float(np.clip(fb_blk[i], 60.0, sr * 0.45))
            # allpass stages via a peak-free notch pair
            w = dsp.TWO_PI * fc / sr
            a = (np.tan(w / 2) - 1) / (np.tan(w / 2) + 1)
            sos = np.tile(np.array([a, 1.0, 0.0, 1.0, a, 0.0]), (stages, 1))
            res[s:e], zi = signal.sosfilt(sos, y[s:e], zi=zi)
        out[:, c] = res
    mix = float(np.clip(p.get("pha.mix", 0.5), 0.0, 1.0))
    return X * (1.0 - mix * depth) + out * (mix * depth)


def width(x: np.ndarray, sr: int, p: dict, rng=None) -> np.ndarray:
    X = dsp.stereo(x)
    w = float(p.get("st.width", 1.0))
    haas = float(p.get("st.haas", 0.0))
    if haas > 0.0:
        d = int(sr * haas * 1e-3)
        if d > 0:
            X = X.copy()
            X[:, 1] = np.concatenate([np.zeros(d), X[:d and -d or None, 1]])[:len(X)]
    mid = (X[:, 0] + X[:, 1]) * 0.5
    side = (X[:, 0] - X[:, 1]) * 0.5 * w
    mono_below = float(p.get("st.mono_below", 0.0))
    if mono_below > 20.0:
        side = dsp.sos_apply(dsp.biquad_highpass(sr, mono_below, 0.707), side)
    return np.column_stack((mid + side, mid - side))


def delay_fx(x: np.ndarray, sr: int, p: dict, rng=None) -> np.ndarray:
    mix = float(np.clip(p.get("dly.mix", 0.0), 0.0, 1.0))
    if mix <= 0.0:
        return x
    X = dsp.stereo(x)
    n = X.shape[0]
    bpm = float(p.get("pitch.bpm", 120.0))
    if p.get("dly.sync", True):
        div = float(p.get("dly.division", 8.0))
        tm = 60.0 / max(bpm, 1.0) * (4.0 / max(div, 0.25))
        if p.get("dly.dotted", False):
            tm *= 1.5
        if p.get("dly.triplet", False):
            tm *= 2.0 / 3.0
    else:
        tm = float(p.get("dly.time", 330.0)) * 1e-3
    d = max(int(tm * sr), 1)
    fb = float(np.clip(p.get("dly.feedback", 0.35), 0.0, 0.95))
    damp = float(np.clip(p.get("dly.damp", 0.3), 0.0, 0.95))
    tail = int(sr * 3.0)
    pad = np.vstack([X, np.zeros((tail, 2))])
    wet = np.zeros_like(pad)
    if p.get("dly.pingpong", True):
        a = dsp.comb_feedback(pad[:, 0] + pad[:, 1] * 0.5, d * 2, fb, damp)
        b = dsp.comb_feedback(pad[:, 1] + pad[:, 0] * 0.5, d * 2, fb, damp)
        wet[:, 0] = a
        wet[:, 1] = np.concatenate([np.zeros(d), b])[:len(b)]
    else:
        for c in range(2):
            wet[:, c] = dsp.comb_feedback(pad[:, c], d, fb, damp)
    hp = float(p.get("dly.hp", 200.0))
    lp = float(p.get("dly.lp", 6000.0))
    wet = dsp.sos_apply(dsp.biquad_highpass(sr, hp, 0.707), wet)
    wet = dsp.sos_apply(dsp.biquad_lowpass(sr, lp, 0.707), wet)
    out = np.vstack([X, np.zeros((tail, 2))]) * (1.0 - mix * 0.25) + wet * mix
    return out


_COMB = (1116, 1188, 1277, 1356, 1422, 1491, 1557, 1617)
_ALLP = (556, 441, 341, 225)


def reverb(x: np.ndarray, sr: int, p: dict, rng=None) -> np.ndarray:
    mix = float(np.clip(p.get("rev.mix", 0.0), 0.0, 1.0))
    if mix <= 0.0:
        return x
    X = dsp.stereo(x)
    size = float(np.clip(p.get("rev.size", 0.7), 0.05, 1.6))
    decay = float(np.clip(p.get("rev.decay", 0.78), 0.1, 0.97))
    damp = float(np.clip(p.get("rev.damp", 0.35), 0.0, 0.95))
    pre = int(float(p.get("rev.predelay", 20.0)) * 1e-3 * sr)
    tail = int(sr * (1.0 + 6.0 * decay * size))
    scale = size * sr / 44100.0

    pad = np.vstack([X, np.zeros((tail + pre, 2))])
    src = dsp.mono(pad)
    if pre > 0:
        src = np.concatenate([np.zeros(pre), src])[:len(src)]
    src = dsp.sos_apply(dsp.biquad_highpass(sr, float(p.get("rev.hp", 250.0)), 0.7), src)

    wet = np.zeros((len(src), 2))
    for c in range(2):
        acc = np.zeros(len(src))
        for k, d in enumerate(_COMB):
            dd = max(int(d * scale) + (c * 23), 1)
            acc += dsp.comb_feedback(src, dd, decay, damp)
        acc /= len(_COMB)
        for d in _ALLP:
            acc = dsp.allpass(acc, max(int(d * scale) + c * 11, 1), 0.5)
        wet[:, c] = acc

    shim = float(np.clip(p.get("rev.shimmer", 0.0), 0.0, 1.0))
    if shim > 0.0:
        up = pitch_shift(wet, sr, float(p.get("rev.shimmer_semis", 12.0)))
        wet = wet * (1.0 - shim * 0.5) + up * shim

    wet = dsp.sos_apply(dsp.biquad_lowpass(sr, float(p.get("rev.lp", 7000.0)), 0.7), wet)
    w = float(p.get("rev.width", 1.0))
    mid = (wet[:, 0] + wet[:, 1]) * 0.5
    side = (wet[:, 0] - wet[:, 1]) * 0.5 * w
    wet = np.column_stack((mid + side, mid - side))

    dry = np.vstack([X, np.zeros((len(src) - len(X), 2))])
    return dry * (1.0 - mix * 0.3) + wet * mix * 1.4


def limiter(x: np.ndarray, sr: int, p: dict, rng=None) -> np.ndarray:
    ceil = dsp.db_to_lin(float(p.get("out.ceiling", -0.8)))
    look = max(int(sr * 0.002), 1)
    det = np.abs(dsp.mono(x))
    peak = ndimage.maximum_filter1d(det, size=look * 3, mode="nearest")
    gr = np.minimum(1.0, ceil / np.maximum(peak, 1e-9))
    gr = dsp.smooth(gr, sr, 4.0)
    gr = np.minimum(gr, 1.0)
    y = x * (gr if x.ndim == 1 else gr[:, None])
    return dsp.soft_limit(y, ceil)
