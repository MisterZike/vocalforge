"""The singing-voice synthesiser: articulation planning + source-filter render.

Signal model (Klatt-style, with a musical front end):

    glottal source  ->  nasal branch  ->  5-formant cascade  ->  lip radiation
    fricative noise ->  3-band parallel resonator bank  ------>  +

Every stage is driven by per-sample or per-block control tracks, so formants,
voicing, breath and noise all move continuously rather than being crossfaded
between static frames.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import signal

from . import dsp, g2p, melody
from . import phonemes as P

BLOCK = 64          # samples per filter-coefficient update


@dataclass
class Segment:
    phone: P.Phone
    start: float            # seconds
    end: float
    note: float | None = None
    syl: int = -1           # index into the syllable list
    role: str = ""          # onset | nucleus | coda | silence
    note_idx: int = -1      # index into the note list
    word: int = -1

    @property
    def dur(self) -> float:
        return max(self.end - self.start, 1e-4)


@dataclass
class Syllable:
    onset: list[str]
    nucleus: str | None
    coda: list[str]
    word: int = -1
    text: str = ""          # the source word, for display

    @property
    def phones(self) -> list[str]:
        return self.onset + ([self.nucleus] if self.nucleus else []) + self.coda


# --------------------------------------------------------------------------
# articulation planning
# --------------------------------------------------------------------------

def split_syllables(words: list[list[str]], sources: list[str] | None = None
                    ) -> tuple[list[Syllable], list[int]]:
    """Flatten words into syllables; also return indices where a word ends."""
    sylls: list[Syllable] = []
    breaks: list[int] = []
    src = sources or [""] * len(words)
    for wi, w in enumerate(words):
        if len(w) == 1 and P.get(w[0]).cls == P.SILENCE:
            sylls.append(Syllable([], None, [w[0]], wi, src[wi]))
            breaks.append(len(sylls) - 1)
            continue
        parts = g2p.syllabify(w)
        for pi, chunk in enumerate(parts):
            nuc = next((i for i, ph in enumerate(chunk) if P.is_syllabic(ph)), None)
            label = src[wi] if len(parts) == 1 else f"{src[wi]}({pi + 1})"
            if nuc is None:
                # consonant-only chunk (e.g. "mm") -- treat a nasal as the nucleus
                sylls.append(Syllable([], chunk[0], chunk[1:], wi, label))
            else:
                sylls.append(Syllable(chunk[:nuc], chunk[nuc], chunk[nuc + 1:],
                                      wi, label))
        breaks.append(len(sylls) - 1)
    return sylls, breaks


def assign_notes(sylls: list[Syllable], notes: list[melody.Note]
                 ) -> list[tuple[float, float, float | None, int]]:
    """Give every singable syllable a (start, end, midi) span.

    More notes than syllables -> melisma (a syllable holds a run of notes).
    More syllables than notes -> the note is subdivided between them.
    """
    singable = [i for i, s in enumerate(sylls) if s.nucleus is not None]
    voiced = [nt for nt in notes if nt.midi is not None]
    spans: list[tuple[float, float, float | None, int]] = \
        [(0.0, 0.0, None, -1)] * len(sylls)
    if not singable or not voiced:
        return spans
    index_of = {id(nt): i for i, nt in enumerate(notes)}

    S, N = len(singable), len(voiced)
    if N >= S:
        for k, si in enumerate(singable):
            a, b = k * N // S, max((k + 1) * N // S, k * N // S + 1)
            spans[si] = (voiced[a].start, voiced[min(b, N) - 1].end,
                         voiced[a].midi, index_of[id(voiced[a])])
    else:
        groups: dict[int, list[int]] = {}
        for k, si in enumerate(singable):
            groups.setdefault(k * N // S, []).append(si)
        for j, members in groups.items():
            nt = voiced[j]
            step = (nt.end - nt.start) / len(members)
            for m, si in enumerate(members):
                spans[si] = (nt.start + m * step, nt.start + (m + 1) * step,
                             nt.midi, index_of[id(nt)])

    # silences/pauses inherit the gap between their neighbours
    for i, s in enumerate(sylls):
        if s.nucleus is None:
            prev = next((spans[j][1] for j in range(i - 1, -1, -1)
                         if sylls[j].nucleus is not None), 0.0)
            spans[i] = (prev, prev, None, -1)
    return spans


def plan(words: list[list[str]], notes: list[melody.Note], p: dict,
         sources: list[str] | None = None
         ) -> tuple[list[Segment], float, float, list[Syllable]]:
    """Lay phonemes out in time, anchoring each vowel onset to its note start.

    Returns (segments, lead_in, total, syllables).  ``lead_in`` is the
    time the first syllable's onset consonants need *before* the first beat --
    the caller shifts the note timeline by it so the vowel lands on the beat.
    """
    speed = max(float(p.get("art.speed", 1.0)), 0.05)
    c_len = max(float(p.get("art.consonant_length", 1.0)), 0.05)
    legato = float(np.clip(p.get("art.legato", 0.5), 0.0, 1.0))

    sylls, _ = split_syllables(words, sources)
    spans = assign_notes(sylls, notes)

    def cdur(name: str) -> float:
        return P.get(name).dur * 1e-3 * c_len / speed

    # ---- nominal layout ---------------------------------------------------
    # each entry carries where it came from, so the UI can draw the mapping
    nominal: list[tuple[str, float, int, str, int]] = []   # name,dur,syl,role,note
    anchors: list[tuple[float, float]] = []                # (nominal_t, wanted_t)
    t = 0.0
    lead = sum(cdur(c) for c in sylls[0].onset) if sylls else 0.0

    for si, (syl, (ns, ne, midi, ni)) in enumerate(zip(sylls, spans)):
        for c in syl.onset:
            nominal.append((c, cdur(c), si, "onset", ni))
            t += cdur(c)
        if syl.nucleus is not None:
            anchors.append((t, ns + lead))
            note_len = max(ne - ns, 0.04)
            coda_t = sum(cdur(c) for c in syl.coda)
            vlen = max(note_len - coda_t * (1.0 - legato), 0.035)
            nominal.append((syl.nucleus, vlen, si, "nucleus", ni))
            t += vlen
        for c in syl.coda:
            role = "silence" if P.get(c).cls == P.SILENCE else "coda"
            nominal.append((c, cdur(c), si, role, ni))
            t += cdur(c)

    tail = float(p.get("art.release", 120.0)) * 1e-3
    note_total = max((nt.slot_end for nt in notes), default=0.0)
    total = note_total + lead + tail
    anchors = [(0.0, 0.0)] + anchors + [(t, max(total, 1e-3))]

    # ---- monotone piecewise-linear time warp onto the anchors -------------
    xs = np.array([a[0] for a in anchors])
    ys = np.array([a[1] for a in anchors])
    order = np.argsort(xs, kind="stable")
    xs, ys = xs[order], ys[order]
    ys = np.maximum.accumulate(ys)
    keep = np.concatenate([[True], np.diff(xs) > 1e-9])
    xs, ys = xs[keep], ys[keep]

    segs: list[Segment] = []
    t = 0.0
    edges = [0.0]
    for entry in nominal:
        t += entry[1]
        edges.append(t)
    warped = np.interp(np.array(edges), xs, ys)
    # never let a segment collapse to nothing
    min_d = 0.008
    for i in range(1, len(warped)):
        if warped[i] - warped[i - 1] < min_d:
            warped[i] = warped[i - 1] + min_d

    for (name, _, si, role, ni), s, e in zip(nominal, warped[:-1], warped[1:]):
        midi = spans[si][2] if 0 <= si < len(spans) else None
        segs.append(Segment(P.get(name), float(s), float(e), midi, si, role, ni,
                            sylls[si].word if 0 <= si < len(sylls) else -1))
    if segs:
        total = max(total, segs[-1].end + tail)
    return segs, lead, total, sylls


def prepare(text: str, notes: list[melody.Note], p: dict,
            rng: np.random.Generator):
    """Everything up to (but not including) audio: phonemes, notes, timing."""
    pairs = g2p.text_to_words(text, bool(p.get("text.espeak", False)))
    if not pairs:
        pairs = [("ah", ["AA"])]
    sources = [s for s, _ in pairs]
    words = [ph for _, ph in pairs]

    sylls_probe, _ = split_syllables(words, sources)
    n_syl = max(1, sum(1 for s in sylls_probe if s.nucleus is not None))

    if not notes:
        notes = melody.auto_melody(
            n_syl, float(p.get("pitch.root", 60.0)),
            str(p.get("pitch.scale", "minor_pentatonic")),
            str(p.get("pitch.auto_style", "monotone")), rng)
    melody.build_timeline(notes, float(p.get("pitch.bpm", 120.0)),
                          float(p.get("pitch.swing", 0.0)),
                          float(p.get("pitch.note_length", 1.0)))

    segs, lead, total, sylls = plan(words, notes, p, sources)
    for nt in notes:                      # shift so vowels land on the beat
        nt.start += lead
        nt.end += lead
        nt.slot_end += lead
    return words, sources, notes, segs, lead, total, sylls


# --------------------------------------------------------------------------
# control tracks
# --------------------------------------------------------------------------

def _formant_tracks(segs: list[Segment], n: int, sr: int, p: dict):
    """Per-sample formant frequency/bandwidth tracks plus articulation gates."""
    F = np.tile(np.array(P.PHONES["AX"].f, dtype=np.float64), (n, 1))
    B = np.tile(np.array(P.PHONES["AX"].b, dtype=np.float64), (n, 1))
    nasal = np.zeros(n)
    voiced = np.zeros(n)
    vamp = np.zeros(n)
    namp = np.zeros(n)
    nbands = np.zeros((n, 3, 3))          # (centre, bw, gain) x 3
    oq_bias = np.zeros(n)

    diph = float(np.clip(p.get("art.diphthong", 1.0), 0.0, 2.0))

    for seg in segs:
        s = int(seg.start * sr)
        e = min(int(seg.end * sr), n)
        if e <= s:
            continue
        ph = seg.phone
        fa, ba = ph.target_a()
        fb, bb = ph.target_b()
        L = e - s
        if ph.cls == P.DIPHTHONG:
            # hold the first target, then glide -- that is what a sung
            # diphthong does, rather than sliding from the very first sample
            r = np.clip((np.linspace(0.0, 1.0, L) - 0.35) / 0.5, 0.0, 1.0)
            r = (3 - 2 * r) * r * r * diph
        else:
            r = np.zeros(L)
        r = r[:, None]
        F[s:e] = np.array(fa) * (1 - r) + np.array(fb) * r
        B[s:e] = np.array(ba) * (1 - r) + np.array(bb) * r
        nasal[s:e] = ph.nasal
        oq_bias[s:e] = ph.open_q

        # ---- amplitude / voicing envelopes --------------------------------
        if ph.cls == P.SILENCE:
            continue
        if ph.cls in (P.STOP, P.AFFRICATE):
            cl = int(L * ph.closure)
            burst = min(max(int(0.012 * sr), 1), max(L - cl, 1))
            if ph.voiced and cl > 0:
                vamp[s:s + cl] = ph.amp          # low-frequency voice bar
                voiced[s:s + cl] = 1.0
            bs = s + cl
            be = min(bs + burst, e)
            if be > bs:
                env = np.exp(-np.linspace(0.0, 4.0, be - bs))
                namp[bs:be] = ph.burst * env
                for k, (cf, bw, g) in enumerate(ph.noise[:3]):
                    nbands[bs:be, k] = (cf, bw, g)
            if be < e:                            # aspiration into the vowel
                env = np.exp(-np.linspace(0.0, 3.0, e - be))
                namp[be:e] = ph.burst * 0.35 * env
                for k, (cf, bw, g) in enumerate(ph.noise[:3]):
                    nbands[be:e, k] = (cf, bw * 1.6, g)
                if ph.voiced:
                    vamp[be:e] = np.linspace(ph.amp, 1.0, e - be)
                    voiced[be:e] = 1.0
            continue

        if ph.cls in (P.FRICATIVE,):
            for k, (cf, bw, g) in enumerate(ph.noise[:3]):
                nbands[s:e, k] = (cf, bw, g)
            namp[s:e] = 1.0
            if ph.voiced:
                vamp[s:e] = ph.amp
                voiced[s:e] = 1.0
            continue

        vamp[s:e] = ph.amp
        voiced[s:e] = 1.0

    return F, B, nasal, voiced, vamp, namp, nbands, oq_bias


def _shape_formants(F: np.ndarray, B: np.ndarray, p: dict, sr: int) -> tuple:
    """Apply voice-character scaling to the raw formant tracks."""
    tract = max(float(p.get("voice.tract_length", 1.0)), 0.25)
    F = F / tract
    F = F * dsp.semitones(float(p.get("voice.formant_shift", 0.0)))
    for i, key in enumerate(("voice.f1", "voice.f2", "voice.f3")):
        F[:, i] *= dsp.semitones(float(p.get(key, 0.0)))
    spread = float(p.get("voice.formant_spread", 1.0))
    if abs(spread - 1.0) > 1e-6:
        F[:, 1:] = F[:, :1] + (F[:, 1:] - F[:, :1]) * spread
    q = max(float(p.get("voice.formant_q", 1.0)), 0.1)
    B = B / q
    # vocal effort pulls F1 up and narrows its bandwidth
    effort = float(np.clip(p.get("voice.effort", 0.5), 0.0, 1.0))
    F[:, 0] *= 1.0 + 0.18 * (effort - 0.5)
    B[:, 0] *= 1.0 - 0.35 * (effort - 0.5)
    F = np.clip(F, 60.0, sr * 0.47)
    B = np.clip(B, 25.0, sr * 0.30)
    return F, B


def _sos_bank(freqs: np.ndarray, bws: np.ndarray, sr: int,
              zero: bool = False) -> np.ndarray:
    """Vectorised resonator (or anti-resonator) coefficients.

    ``freqs``/``bws`` have shape (blocks, sections); returns (blocks, sections, 6).
    """
    r = np.exp(-np.pi * bws / sr)
    th = dsp.TWO_PI * freqs / sr
    a1 = -2.0 * r * np.cos(th)
    a2 = r * r
    nb, ns = freqs.shape
    sos = np.zeros((nb, ns, 6))
    if zero:
        g = 1.0 / np.maximum(1.0 + a1 + a2, 1e-6)
        sos[..., 0] = g
        sos[..., 1] = g * a1
        sos[..., 2] = g * a2
        sos[..., 3] = 1.0
    else:
        sos[..., 0] = 1.0 + a1 + a2
        sos[..., 3] = 1.0
        sos[..., 4] = a1
        sos[..., 5] = a2
    return sos


def _run_tv(x: np.ndarray, sos: np.ndarray, block: int) -> np.ndarray:
    """Run a time-varying SOS cascade, carrying state across blocks."""
    out = np.empty_like(x)
    zi = np.zeros((sos.shape[1], 2))
    for i in range(sos.shape[0]):
        s, e = i * block, min((i + 1) * block, len(x))
        if s >= e:
            break
        out[s:e], zi = signal.sosfilt(sos[i], x[s:e], zi=zi)
    return out


# --------------------------------------------------------------------------
# glottal source
# --------------------------------------------------------------------------

def glottal_source(f0: np.ndarray, sr: int, p: dict,
                   rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray]:
    """Generate the excitation.  Returns (source, period_index)."""
    n = len(f0)
    phase = np.cumsum(f0) / sr
    period_idx = np.floor(phase).astype(np.int64)
    x = np.mod(phase, 1.0)

    oq = float(np.clip(p.get("voice.open_quotient", 0.62), 0.15, 0.95))
    sq = max(float(p.get("voice.speed_quotient", 2.2)), 1.0)
    t1 = oq * sq / (1.0 + sq)
    t2 = oq / (1.0 + sq)

    # --- Rosenberg glottal flow pulse -------------------------------------
    g = np.zeros(n)
    rise = x < t1
    fall = (x >= t1) & (x < t1 + t2)
    g[rise] = 0.5 * (1.0 - np.cos(np.pi * x[rise] / t1))
    g[fall] = np.cos(np.pi * (x[fall] - t1) / (2.0 * t2))
    g -= g.mean()

    # --- alternative waveforms for synthetic / robotic voices -------------
    blend = float(np.clip(p.get("voice.wave_blend", 0.0), 0.0, 1.0))
    if blend > 0.0:
        kind = str(p.get("voice.alt_wave", "saw"))
        pw = float(np.clip(p.get("voice.pulse_width", 0.5), 0.02, 0.98))
        if kind == "saw":
            alt = 2.0 * x - 1.0
        elif kind == "square":
            alt = np.where(x < pw, 1.0, -1.0)
        elif kind == "triangle":
            alt = 4.0 * np.abs(x - 0.5) - 1.0
        elif kind == "pulse":
            alt = np.where(x < pw * 0.25, 1.0, -0.12)
        elif kind == "supersaw":
            alt = np.zeros(n)
            for det in (-0.021, -0.009, 0.0, 0.011, 0.023):
                alt += 2.0 * np.mod(phase * (1.0 + det), 1.0) - 1.0
            alt /= 5.0
        else:
            alt = 2.0 * x - 1.0
        alt = alt - alt.mean()
        # soften the alternative so it sits at a similar level as the pulse
        gm = np.sqrt(np.mean(g ** 2)) or 1.0
        am = np.sqrt(np.mean(alt ** 2)) or 1.0
        g = g * (1.0 - blend) + alt * (gm / am) * blend

    # --- shimmer: per-period amplitude variation --------------------------
    shim = float(p.get("voice.shimmer", 0.0))
    if shim > 0.0:
        npd = int(period_idx.max()) + 2
        amps = 1.0 + shim * (rng.random(npd) - 0.5) * 2.0
        g = g * amps[period_idx]

    # --- subharmonic / growl ----------------------------------------------
    growl = float(np.clip(p.get("voice.growl", 0.0), 0.0, 1.0))
    if growl > 0.0:
        alt = 1.0 - growl * (period_idx % 2)
        g = g * alt

    # --- spectral tilt -----------------------------------------------------
    tilt = float(p.get("voice.tilt", 0.0))          # dB, negative = darker
    if abs(tilt) > 0.1:
        fc = float(np.clip(3000.0 * (10.0 ** (tilt / 26.0)), 120.0, sr * 0.45))
        g = dsp.sos_apply(dsp.biquad_lowshelf(sr, 900.0, 0.7, -tilt * 0.35), g)
        g = dsp.sos_apply(dsp.biquad_lowpass(sr, fc, 0.6), g)

    # --- aspiration (breath) ----------------------------------------------
    breath = float(np.clip(p.get("voice.breathiness", 0.12), 0.0, 1.5))
    if breath > 0.0:
        noise = dsp.white(n, rng)
        noise = dsp.sos_apply(dsp.biquad_highpass(sr, 260.0, 0.7), noise)
        # breath is loudest while the glottis is open
        gate = np.clip((x < oq).astype(np.float64) * 0.75 + 0.25, 0.0, 1.0)
        gate = dsp.smooth(gate, sr, 0.35)
        g = g + noise * gate * breath * 0.28

    return g, period_idx


# --------------------------------------------------------------------------
# main render
# --------------------------------------------------------------------------

def render_voice(text: str, notes: list[melody.Note], p: dict, sr: int,
                 rng: np.random.Generator
                 ) -> tuple[np.ndarray, list[Segment], np.ndarray, dict]:
    """Synthesise the dry mono voice.

    Returns (audio, segments, pitch_hz, detail) where ``detail`` carries the
    note list, syllables and pitch track used, for the alignment view.
    """
    words, sources, notes, segs, lead, total, sylls = prepare(text, notes, p, rng)

    n = max(int(total * sr), int(0.05 * sr))
    midi, gate = melody.contour(notes, sr, n, p, rng)
    f0 = dsp.midi_to_hz(midi)

    F, B, nasal, voiced, vamp, namp, nbands, oq_bias = _formant_tracks(segs, n, sr, p)
    F, B = _shape_formants(F, B, p, sr)

    glide = float(p.get("art.glide", 32.0))
    F = dsp.dezip(F, sr, glide)
    B = dsp.dezip(B, sr, glide * 1.5)
    nasal = dsp.dezip(nasal, sr, glide)

    # --- source -----------------------------------------------------------
    src_p = dict(p)
    src_p["voice.open_quotient"] = float(np.clip(
        float(p.get("voice.open_quotient", 0.62)) + float(np.mean(oq_bias)),
        0.15, 0.95))
    src, _ = glottal_source(f0, sr, src_p, rng)

    v_env = dsp.dezip(vamp * voiced, sr, 6.0) * dsp.dezip(gate, sr, 5.0)
    src = src * v_env

    # --- vocal tract ------------------------------------------------------
    nb = dsp.n_blocks(n, BLOCK)
    Fb = np.stack([dsp.blockify(F[:, i], BLOCK) for i in range(5)], axis=1)
    Bb = np.stack([dsp.blockify(B[:, i], BLOCK) for i in range(5)], axis=1)
    n_form = int(np.clip(p.get("voice.n_formants", 5), 2, 5))
    sos = _sos_bank(Fb[:, :n_form], Bb[:, :n_form], sr)
    voice = _run_tv(src, sos, BLOCK)

    # nasal branch: extra pole + zero, crossfaded by the nasal control track
    if float(np.max(nasal)) > 1e-3:
        nz = dsp.sos_apply(dsp.biquad_peak(sr, 270.0, 2.5, 6.0), voice)
        nz = dsp.sos_apply(dsp.biquad_peak(sr, 460.0, 3.0, -11.0), nz)
        nz = dsp.sos_apply(dsp.biquad_lowpass(sr, 3200.0, 0.7), nz)
        voice = voice * (1.0 - nasal) + nz * nasal

    # lip radiation: differentiator (+6 dB/octave)
    voice = signal.lfilter([1.0, -0.96], [1.0], voice)

    # --- fricative / burst noise branch -----------------------------------
    noise_out = np.zeros(n)
    if float(np.max(namp)) > 1e-4:
        raw = dsp.white(n, rng)
        bnb = [dsp.blockify(nbands[:, k, 0], BLOCK) for k in range(3)]
        bbw = [dsp.blockify(nbands[:, k, 1], BLOCK) for k in range(3)]
        for k in range(3):
            cf, bw = bnb[k], bbw[k]
            if float(np.max(cf)) < 1.0:
                continue
            cf = np.where(cf < 1.0, 4000.0, cf)
            bw = np.where(bw < 1.0, 1000.0, bw)
            q = np.clip(cf / np.maximum(bw, 20.0), 0.3, 12.0)
            sosk = np.zeros((len(cf), 1, 6))
            for i in range(len(cf)):
                sosk[i, 0] = dsp.biquad_bandpass(sr, cf[i], q[i])
            band = _run_tv(raw, sosk, BLOCK)
            gain = dsp.dezip(nbands[:, k, 2], sr, 4.0)
            noise_out += band * gain
        noise_out *= dsp.dezip(namp, sr, 3.0) * dsp.dezip(gate, sr, 5.0)
        noise_out *= float(p.get("art.sibilance", 1.0))
        noise_out = dsp.sos_apply(dsp.biquad_highpass(sr, 180.0, 0.7), noise_out)

    out = voice + noise_out * 0.9

    cg = float(p.get("art.consonant_gain", 1.0))
    if abs(cg - 1.0) > 1e-3:
        out = voice + noise_out * 0.9 * cg

    out = dsp.soft_limit(out * 0.9, 1.4)
    out = dsp.normalize(out, -3.0)
    detail = {"notes": notes, "syllables": sylls, "midi": midi,
              "gate": gate, "lead": lead}
    return out, segs, f0, detail
