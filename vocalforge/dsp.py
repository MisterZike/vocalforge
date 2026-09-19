"""Low-level DSP primitives shared by the synthesiser and the effect rack.

Everything works on float32/float64 numpy arrays.  Mono signals are 1-D of
shape (n,); stereo signals are 2-D of shape (n, 2).  Helpers that can do both
are written against the last axis so they broadcast naturally.
"""
from __future__ import annotations

import numpy as np
from scipy import signal

TWO_PI = 2.0 * np.pi


# --------------------------------------------------------------------------
# conversions
# --------------------------------------------------------------------------

def db_to_lin(db: float | np.ndarray) -> float | np.ndarray:
    return 10.0 ** (np.asarray(db, dtype=np.float64) / 20.0)


def lin_to_db(x: float | np.ndarray, floor: float = 1e-9) -> np.ndarray:
    return 20.0 * np.log10(np.maximum(np.abs(np.asarray(x)), floor))


def semitones(ratio_st: float | np.ndarray) -> np.ndarray:
    """Semitone offset -> frequency ratio."""
    return 2.0 ** (np.asarray(ratio_st, dtype=np.float64) / 12.0)


def midi_to_hz(midi: float | np.ndarray) -> np.ndarray:
    return 440.0 * 2.0 ** ((np.asarray(midi, dtype=np.float64) - 69.0) / 12.0)


def hz_to_midi(hz: float | np.ndarray) -> np.ndarray:
    hz = np.maximum(np.asarray(hz, dtype=np.float64), 1e-6)
    return 69.0 + 12.0 * np.log2(hz / 440.0)


def mel(hz):
    return 2595.0 * np.log10(1.0 + np.asarray(hz, dtype=np.float64) / 700.0)


def mel_inv(m):
    return 700.0 * (10.0 ** (np.asarray(m, dtype=np.float64) / 2595.0) - 1.0)


# --------------------------------------------------------------------------
# shaping helpers
# --------------------------------------------------------------------------

def stereo(x: np.ndarray) -> np.ndarray:
    """Force a signal to shape (n, 2)."""
    x = np.asarray(x, dtype=np.float64)
    if x.ndim == 1:
        return np.column_stack((x, x))
    if x.shape[1] == 1:
        return np.repeat(x, 2, axis=1)
    return x[:, :2]


def mono(x: np.ndarray) -> np.ndarray:
    x = np.asarray(x, dtype=np.float64)
    return x if x.ndim == 1 else x.mean(axis=1)


def pad_to(x: np.ndarray, n: int) -> np.ndarray:
    """Zero-pad (or truncate) along axis 0 to exactly n samples."""
    if x.shape[0] == n:
        return x
    if x.shape[0] > n:
        return x[:n]
    pad = [(0, n - x.shape[0])] + [(0, 0)] * (x.ndim - 1)
    return np.pad(x, pad)


def smooth(x: np.ndarray, sr: int, ms: float) -> np.ndarray:
    """One-pole smoothing of a control signal, in milliseconds."""
    if ms <= 0:
        return x
    a = np.exp(-1.0 / max(1.0, sr * ms * 1e-3))
    return signal.lfilter([1.0 - a], [1.0, -a], x, axis=0)


def dezip(x: np.ndarray, sr: int, ms: float = 2.0) -> np.ndarray:
    """Forward/backward smoothing so control ramps have no group delay."""
    if ms <= 0:
        return x
    a = np.exp(-1.0 / max(1.0, sr * ms * 1e-3))
    b, ar = [1.0 - a], [1.0, -a]
    return signal.filtfilt(b, ar, x, axis=0, padlen=min(len(x) - 1, 64))


def fade(x: np.ndarray, sr: int, in_ms: float = 4.0, out_ms: float = 12.0) -> np.ndarray:
    """Apply short raised-cosine fades so exported samples never click."""
    n = x.shape[0]
    ni = min(int(sr * in_ms * 1e-3), n // 2)
    no = min(int(sr * out_ms * 1e-3), n // 2)
    env = np.ones(n)
    if ni > 1:
        env[:ni] = 0.5 - 0.5 * np.cos(np.linspace(0, np.pi, ni))
    if no > 1:
        env[-no:] = 0.5 + 0.5 * np.cos(np.linspace(0, np.pi, no))
    return x * (env if x.ndim == 1 else env[:, None])


def normalize(x: np.ndarray, peak_db: float = -1.0) -> np.ndarray:
    peak = float(np.max(np.abs(x))) if x.size else 0.0
    if peak < 1e-9:
        return x
    return x * (db_to_lin(peak_db) / peak)


def soft_limit(x: np.ndarray, ceiling: float = 0.995) -> np.ndarray:
    """Smooth saturating limiter -- transparent below the ceiling."""
    return ceiling * np.tanh(x / max(ceiling, 1e-6))


# --------------------------------------------------------------------------
# filters
# --------------------------------------------------------------------------

def biquad_lowpass(sr: int, f: float, q: float = 0.7071) -> np.ndarray:
    return _biquad(sr, f, q, "lp")


def biquad_highpass(sr: int, f: float, q: float = 0.7071) -> np.ndarray:
    return _biquad(sr, f, q, "hp")


def biquad_bandpass(sr: int, f: float, q: float = 1.0) -> np.ndarray:
    return _biquad(sr, f, q, "bp")


def biquad_peak(sr: int, f: float, q: float, gain_db: float) -> np.ndarray:
    return _biquad(sr, f, q, "peak", gain_db)


def biquad_lowshelf(sr: int, f: float, q: float, gain_db: float) -> np.ndarray:
    return _biquad(sr, f, q, "lsh", gain_db)


def biquad_highshelf(sr: int, f: float, q: float, gain_db: float) -> np.ndarray:
    return _biquad(sr, f, q, "hsh", gain_db)


def _biquad(sr: int, f: float, q: float, kind: str, gain_db: float = 0.0) -> np.ndarray:
    """RBJ audio-EQ cookbook biquads, returned as a single second-order section."""
    f = float(np.clip(f, 10.0, sr * 0.49))
    q = max(float(q), 1e-3)
    w0 = TWO_PI * f / sr
    cw, sw = np.cos(w0), np.sin(w0)
    alpha = sw / (2.0 * q)
    A = 10.0 ** (gain_db / 40.0)

    if kind == "lp":
        b = [(1 - cw) / 2, 1 - cw, (1 - cw) / 2]
        a = [1 + alpha, -2 * cw, 1 - alpha]
    elif kind == "hp":
        b = [(1 + cw) / 2, -(1 + cw), (1 + cw) / 2]
        a = [1 + alpha, -2 * cw, 1 - alpha]
    elif kind == "bp":  # constant 0 dB peak gain
        b = [alpha, 0.0, -alpha]
        a = [1 + alpha, -2 * cw, 1 - alpha]
    elif kind == "notch":
        b = [1.0, -2 * cw, 1.0]
        a = [1 + alpha, -2 * cw, 1 - alpha]
    elif kind == "peak":
        b = [1 + alpha * A, -2 * cw, 1 - alpha * A]
        a = [1 + alpha / A, -2 * cw, 1 - alpha / A]
    elif kind == "lsh":
        sa = 2.0 * np.sqrt(A) * alpha
        b = [A * ((A + 1) - (A - 1) * cw + sa),
             2 * A * ((A - 1) - (A + 1) * cw),
             A * ((A + 1) - (A - 1) * cw - sa)]
        a = [(A + 1) + (A - 1) * cw + sa,
             -2 * ((A - 1) + (A + 1) * cw),
             (A + 1) + (A - 1) * cw - sa]
    elif kind == "hsh":
        sa = 2.0 * np.sqrt(A) * alpha
        b = [A * ((A + 1) + (A - 1) * cw + sa),
             -2 * A * ((A - 1) + (A + 1) * cw),
             A * ((A + 1) + (A - 1) * cw - sa)]
        a = [(A + 1) - (A - 1) * cw + sa,
             2 * ((A - 1) - (A + 1) * cw),
             (A + 1) - (A - 1) * cw - sa]
    else:
        raise ValueError(f"unknown biquad kind {kind!r}")

    b = np.asarray(b, dtype=np.float64) / a[0]
    a = np.asarray(a, dtype=np.float64) / a[0]
    return np.concatenate([b, a])          # one SOS row


def sos_apply(sos: np.ndarray, x: np.ndarray) -> np.ndarray:
    """Apply one or more second-order sections along axis 0."""
    sos = np.atleast_2d(sos)
    return signal.sosfilt(sos, x, axis=0)


def resonator(sr: int, freq: float, bw: float) -> tuple[np.ndarray, np.ndarray]:
    """Klatt-style two-pole resonator normalised to unity gain at DC.

    ``bw`` is the -3 dB bandwidth in Hz, which is how formants are specified.
    """
    freq = float(np.clip(freq, 20.0, sr * 0.49))
    bw = float(np.clip(bw, 10.0, sr * 0.4))
    r = np.exp(-np.pi * bw / sr)
    theta = TWO_PI * freq / sr
    a1 = -2.0 * r * np.cos(theta)
    a2 = r * r
    gain = 1.0 + a1 + a2                     # unity at DC
    return np.array([gain, 0.0, 0.0]), np.array([1.0, a1, a2])


def antiresonator(sr: int, freq: float, bw: float) -> tuple[np.ndarray, np.ndarray]:
    """Two-zero anti-resonance (used for nasal / lateral spectral zeros)."""
    freq = float(np.clip(freq, 20.0, sr * 0.49))
    bw = float(np.clip(bw, 10.0, sr * 0.4))
    r = np.exp(-np.pi * bw / sr)
    theta = TWO_PI * freq / sr
    b1 = -2.0 * r * np.cos(theta)
    b2 = r * r
    g = 1.0 / max(1.0 + b1 + b2, 1e-6)
    return np.array([g, g * b1, g * b2]), np.array([1.0, 0.0, 0.0])


# --------------------------------------------------------------------------
# block-wise time-varying filtering
# --------------------------------------------------------------------------

class TimeVaryingSOS:
    """Runs a cascade of second-order sections whose coefficients change over
    time, by processing in short blocks and carrying the filter state across
    block boundaries.

    Block sizes of 32-128 samples put the coefficient update rate well above
    the fastest formant transitions, so there is no audible zipper noise.
    """

    def __init__(self, n_sections: int):
        self.n_sections = n_sections
        self.zi = np.zeros((n_sections, 2))

    def process(self, x: np.ndarray, sos_per_block: list[np.ndarray],
                block: int) -> np.ndarray:
        out = np.empty_like(x)
        for i, sos in enumerate(sos_per_block):
            s, e = i * block, min((i + 1) * block, len(x))
            if s >= e:
                break
            seg, self.zi = signal.sosfilt(sos, x[s:e], zi=self.zi)
            out[s:e] = seg
        return out


def n_blocks(n: int, block: int) -> int:
    return int(np.ceil(n / block))


def blockify(ctrl: np.ndarray, block: int) -> np.ndarray:
    """Down-sample a per-sample control signal to one value per block."""
    nb = n_blocks(len(ctrl), block)
    idx = np.minimum(np.arange(nb) * block + block // 2, len(ctrl) - 1)
    return ctrl[idx]


# --------------------------------------------------------------------------
# delay lines
# --------------------------------------------------------------------------

def comb_feedback(x: np.ndarray, delay: int, fb: float,
                  damp: float = 0.0) -> np.ndarray:
    """Feedback comb  y[n] = x[n] + fb * lp(y[n-delay]).

    Vectorised by processing one delay-length block at a time, which is exact
    because samples inside a block never depend on each other.
    """
    delay = max(1, int(delay))
    n = len(x)
    y = np.zeros(n + delay)
    xx = np.concatenate([x, np.zeros(delay)])
    damp = float(np.clip(damp, 0.0, 0.95))
    zi = np.zeros(1)
    db, da = [1.0 - damp], [1.0, -damp]
    for s in range(0, n, delay):
        e = min(s + delay, n)
        prev = y[s: s + (e - s)]              # already-written tail = y[n-delay]
        if damp > 0.0:
            prev, zi = signal.lfilter(db, da, prev, zi=zi)
        y[s + delay: e + delay] = xx[s:e] + fb * prev
    return y[delay:delay + n]


def allpass(x: np.ndarray, delay: int, g: float) -> np.ndarray:
    """Schroeder allpass: y[n] = -g*x[n] + x[n-D] + g*y[n-D]."""
    delay = max(1, int(delay))
    n = len(x)
    xx = np.concatenate([np.zeros(delay), x])
    y = np.zeros(n + delay)
    for s in range(0, n, delay):
        e = min(s + delay, n)
        y[s + delay: e + delay] = (-g * xx[s + delay: e + delay]
                                   + xx[s:e]
                                   + g * y[s: s + (e - s)])
    return y[delay:delay + n]


def fractional_delay_read(x: np.ndarray, idx: np.ndarray) -> np.ndarray:
    """Linear-interpolated read of ``x`` at fractional positions ``idx``."""
    idx = np.clip(idx, 0.0, len(x) - 1.000001)
    i0 = idx.astype(np.int64)
    frac = idx - i0
    return x[i0] * (1.0 - frac) + x[i0 + 1] * frac


# --------------------------------------------------------------------------
# noise
# --------------------------------------------------------------------------

def white(n: int, rng: np.random.Generator) -> np.ndarray:
    return rng.standard_normal(n)


def pink(n: int, rng: np.random.Generator) -> np.ndarray:
    """Voss-McCartney-ish pink noise via a 3-pole filter approximation."""
    w = rng.standard_normal(n)
    b = [0.049922035, -0.095993537, 0.050612699, -0.004408786]
    a = [1.0, -2.494956002, 2.017265875, -0.522189400]
    return signal.lfilter(b, a, w)


# --------------------------------------------------------------------------
# STFT helpers (phase vocoder style processing)
# --------------------------------------------------------------------------

def stft(x: np.ndarray, n_fft: int, hop: int) -> tuple[np.ndarray, np.ndarray]:
    win = np.hanning(n_fft + 1)[:-1]
    pad = n_fft
    xp = np.concatenate([np.zeros(pad), x, np.zeros(pad + n_fft)])
    frames = 1 + (len(xp) - n_fft) // hop
    idx = np.arange(n_fft)[None, :] + hop * np.arange(frames)[:, None]
    return np.fft.rfft(xp[idx] * win, axis=1), win


def istft(spec: np.ndarray, n_fft: int, hop: int, win: np.ndarray,
          length: int) -> np.ndarray:
    frames = np.fft.irfft(spec, n=n_fft, axis=1) * win
    out_len = (spec.shape[0] - 1) * hop + n_fft
    out = np.zeros(out_len)
    wsum = np.zeros(out_len)
    w2 = win ** 2
    for i in range(spec.shape[0]):
        s = i * hop
        out[s:s + n_fft] += frames[i]
        wsum[s:s + n_fft] += w2
    out /= np.maximum(wsum, 1e-8)
    return out[n_fft:n_fft + length]
