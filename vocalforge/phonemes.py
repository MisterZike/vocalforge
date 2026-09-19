"""Phoneme inventory with acoustic targets.

Formant values follow the classic Peterson & Barney / Klatt tables for a
neutral adult vocal tract.  The synthesiser scales them at render time via the
``voice.formant_shift`` and ``voice.tract_length`` parameters, so one table
covers everything from a deep male to a Miku-style hyper-soprano.

Each entry carries:
    cls      phoneme class, drives the articulation model
    voiced   whether the glottal source runs
    f/b      five formant frequencies and bandwidths (the steady target)
    f2/b2    optional second target -- diphthongs glide from f to f2
    nasal    couples the nasal pole/zero branch
    noise    list of (centre_hz, bandwidth_hz, gain) fricative noise bands
    amp      relative loudness
    dur      nominal duration in ms at speed 1.0
    open_q   glottal open-quotient bias (breathier / tenser articulation)
"""
from __future__ import annotations

from dataclasses import dataclass, field

VOWEL = "vowel"
DIPHTHONG = "diphthong"
NASAL = "nasal"
STOP = "stop"
FRICATIVE = "fricative"
AFFRICATE = "affricate"
APPROXIMANT = "approximant"
SILENCE = "silence"

# classes that can carry a musical note
SYLLABIC = {VOWEL, DIPHTHONG}
# classes that sustain pitch (a held note can stretch these)
SUSTAINABLE = {VOWEL, DIPHTHONG, NASAL, APPROXIMANT}

_DEFAULT_B = (60.0, 90.0, 150.0, 200.0, 260.0)


@dataclass
class Phone:
    name: str
    cls: str
    voiced: bool = True
    f: tuple = (500.0, 1500.0, 2500.0, 3300.0, 3850.0)
    b: tuple = _DEFAULT_B
    f2: tuple | None = None
    b2: tuple | None = None
    nasal: float = 0.0
    noise: list = field(default_factory=list)
    amp: float = 1.0
    dur: float = 110.0
    open_q: float = 0.0
    burst: float = 0.0          # stop release burst strength
    closure: float = 0.0        # fraction of duration that is silent closure

    def target_a(self):
        return self.f, self.b

    def target_b(self):
        return (self.f2 or self.f), (self.b2 or self.b)


def _v(name, f1, f2_, f3, dur=140.0, b=None, amp=1.0, oq=0.0):
    return Phone(name, VOWEL, True, (f1, f2_, f3, 3300.0, 3850.0),
                 b or _DEFAULT_B, amp=amp, dur=dur, open_q=oq)


def _d(name, a, b_, dur=210.0):
    """Diphthong built from two vowel entries."""
    return Phone(name, DIPHTHONG, True, a.f, a.b, b_.f, b_.b, dur=dur)


# ---------------------------------------------------------------- vowels ---
_IY = _v("IY", 270, 2290, 3010, dur=150)
_IH = _v("IH", 390, 1990, 2550, dur=110)
_EH = _v("EH", 530, 1840, 2480, dur=125)
_AE = _v("AE", 660, 1720, 2410, dur=165)
_AA = _v("AA", 730, 1090, 2440, dur=165)
_AO = _v("AO", 570, 840, 2410, dur=160)
_UH = _v("UH", 440, 1020, 2240, dur=110)
_UW = _v("UW", 300, 870, 2240, dur=150)
_AH = _v("AH", 640, 1190, 2390, dur=115)
_AX = _v("AX", 500, 1500, 2400, dur=75, amp=0.8)   # schwa
_ER = _v("ER", 490, 1350, 1690, dur=155)

PHONES: dict[str, Phone] = {p.name: p for p in [
    _IY, _IH, _EH, _AE, _AA, _AO, _UH, _UW, _AH, _AX, _ER,
    # ------------------------------------------------------ diphthongs ---
    _d("EY", _EH, _IY), _d("AY", _AA, _IY), _d("OY", _AO, _IY),
    _d("AW", _AA, _UW), _d("OW", _AO, _UW),

    # ---------------------------------------------------------- nasals ---
    Phone("M",  NASAL, True, (250, 1100, 2150, 3300, 3850),
          (90, 110, 170, 220, 280), nasal=1.0, amp=0.55, dur=80),
    Phone("N",  NASAL, True, (250, 1700, 2600, 3300, 3850),
          (90, 110, 170, 220, 280), nasal=1.0, amp=0.55, dur=75),
    Phone("NG", NASAL, True, (250, 2300, 2750, 3300, 3850),
          (90, 110, 170, 220, 280), nasal=1.0, amp=0.5, dur=85),

    # --------------------------------------------------- approximants ---
    Phone("L", APPROXIMANT, True, (380, 880, 2575, 3300, 3850),
          (60, 90, 160, 200, 260), nasal=0.25, amp=0.8, dur=75),
    Phone("R", APPROXIMANT, True, (310, 1060, 1380, 3300, 3850),
          (70, 100, 120, 200, 260), amp=0.85, dur=80),
    Phone("W", APPROXIMANT, True, (290, 610, 2150, 3300, 3850),
          (60, 80, 160, 200, 260), amp=0.8, dur=70),
    Phone("Y", APPROXIMANT, True, (260, 2070, 3020, 3300, 3850),
          (60, 90, 160, 200, 260), amp=0.8, dur=65),

    # ------------------------------------------------------ fricatives ---
    Phone("S",  FRICATIVE, False, amp=0.0, dur=115,
          noise=[(5800, 1800, 1.0), (7600, 2200, 0.7)]),
    Phone("Z",  FRICATIVE, True,  (250, 1700, 2500, 3300, 3850),
          amp=0.28, dur=95, noise=[(5600, 1800, 0.55), (7400, 2200, 0.35)]),
    Phone("SH", FRICATIVE, False, amp=0.0, dur=125,
          noise=[(2500, 900, 0.9), (4200, 1800, 1.0), (6200, 2000, 0.55)]),
    Phone("ZH", FRICATIVE, True,  (250, 1700, 2400, 3300, 3850),
          amp=0.28, dur=100, noise=[(2400, 900, 0.5), (4100, 1800, 0.55)]),
    Phone("F",  FRICATIVE, False, amp=0.0, dur=105,
          noise=[(1400, 1200, 0.18), (5200, 3500, 0.3)]),
    Phone("V",  FRICATIVE, True,  (280, 1100, 2300, 3300, 3850),
          amp=0.3, dur=80, noise=[(5000, 3500, 0.16)]),
    Phone("TH", FRICATIVE, False, amp=0.0, dur=100,
          noise=[(1700, 1400, 0.14), (6200, 3200, 0.24)]),
    Phone("DH", FRICATIVE, True,  (280, 1400, 2500, 3300, 3850),
          amp=0.32, dur=70, noise=[(6000, 3200, 0.13)]),
    Phone("HH", FRICATIVE, False, amp=0.0, dur=85,
          noise=[(700, 700, 0.3), (1800, 1600, 0.3), (3200, 2400, 0.22)]),

    # ----------------------------------------------------------- stops ---
    Phone("P", STOP, False, amp=0.0, dur=95,  closure=0.72, burst=0.55,
          noise=[(900, 900, 0.5), (2200, 2000, 0.5)]),
    Phone("B", STOP, True,  (250, 1000, 2200, 3300, 3850),
          amp=0.12, dur=80, closure=0.70, burst=0.32,
          noise=[(700, 800, 0.4), (1800, 1600, 0.35)]),
    Phone("T", STOP, False, amp=0.0, dur=95,  closure=0.70, burst=0.75,
          noise=[(3800, 1800, 0.8), (5600, 2600, 0.7)]),
    Phone("D", STOP, True,  (250, 1700, 2500, 3300, 3850),
          amp=0.12, dur=78, closure=0.68, burst=0.42,
          noise=[(3600, 1800, 0.5), (5200, 2400, 0.4)]),
    Phone("K", STOP, False, amp=0.0, dur=100, closure=0.68, burst=0.7,
          noise=[(1900, 900, 0.7), (2900, 1600, 0.7), (4400, 2400, 0.4)]),
    Phone("G", STOP, True,  (250, 2000, 2600, 3300, 3850),
          amp=0.12, dur=82, closure=0.66, burst=0.4,
          noise=[(1800, 900, 0.45), (2700, 1500, 0.45)]),

    # ------------------------------------------------------ affricates ---
    Phone("CH", AFFRICATE, False, amp=0.0, dur=150, closure=0.42, burst=0.6,
          noise=[(2500, 900, 0.85), (4200, 1900, 0.95)]),
    Phone("JH", AFFRICATE, True,  (250, 1700, 2500, 3300, 3850),
          amp=0.2, dur=135, closure=0.38, burst=0.4,
          noise=[(2400, 900, 0.5), (4100, 1800, 0.6)]),

    # ---------------------------------------------------------- silence ---
    Phone("SIL", SILENCE, False, amp=0.0, dur=120),
    Phone("SP",  SILENCE, False, amp=0.0, dur=60),   # short inter-word pause
]}

# aliases some users / dictionaries produce
ALIASES = {
    "AH0": "AX", "AXR": "ER", "IX": "IH", "UX": "UW",
    "DX": "D", "Q": "SIL", "NX": "N", "EL": "L", "EM": "M", "EN": "N",
}

VOWEL_NAMES = [n for n, p in PHONES.items() if p.cls in SYLLABIC]


def get(name: str) -> Phone:
    name = name.upper().strip()
    name = ALIASES.get(name, name.rstrip("012"))
    name = ALIASES.get(name, name)
    return PHONES.get(name, PHONES["AX"])


def is_syllabic(name: str) -> bool:
    return get(name).cls in SYLLABIC
