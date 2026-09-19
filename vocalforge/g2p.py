"""English grapheme-to-phoneme conversion.

Three sources, in priority order:

1. an explicit phoneme escape in the lyric --  ``/AY L AH V/``  or ``[AY]``
2. an exception lexicon of common irregular English words
3. a context-sensitive letter-rule engine in the style of the NRL / Elovitz
   text-to-phoneme rules

``espeak-ng`` is used instead of 2+3 when it is installed and
``prefer_espeak`` is set, but nothing depends on it -- VocalForge is fully
self-contained.

Context symbols used in the rule table
    #  one or more vowels          ^  exactly one consonant
    :  zero or more consonants     +  a front vowel (E, I, Y)
    .  a voiced consonant          %  a common suffix (E, ES, ED, ER, ING, ELY)
    _  a word boundary
"""
from __future__ import annotations

import re
import shutil
import subprocess

VOWEL_LETTERS = set("AEIOUY")
CONSONANTS = set("BCDFGHJKLMNPQRSTVWXZ")
VOICED = set("BDGJLMNRVWZ")
FRONT = set("EIY")

# --------------------------------------------------------------------------
# exception lexicon -- the words English rules reliably get wrong, plus the
# vocabulary that actually turns up in song lyrics.
# --------------------------------------------------------------------------
LEXICON: dict[str, str] = {w.split(None, 1)[0]: w.split(None, 1)[1] for w in """
A AX
ABOUT AX B AW T
AGAIN AX G EH N
ALL AO L
ALONE AX L OW N
ALRIGHT AO L R AY T
ALWAYS AO L W EY Z
AM AE M
AN AE N
AND AE N D
ANY EH N IY
ARE AA R
AS AE Z
AWAY AX W EY
BABY B EY B IY
BE B IY
BEAUTIFUL B Y UW T AX F AH L
BECAUSE B IH K AO Z
BEEN B IH N
BEFORE B IH F AO R
BODY B AA D IY
BOTH B OW TH
BOY B OY
BREAK B R EY K
BREATHE B R IY DH
BURN B ER N
BUT B AH T
BY B AY
CALL K AO L
CAME K EY M
CAN K AE N
CANT K AE N T
CITY S IH T IY
CLOSE K L OW S
COLD K OW L D
COME K AH M
COULD K UH D
CRAZY K R EY Z IY
DANCE D AE N S
DARK D AA R K
DID D IH D
DO D UW
DOES D AH Z
DONE D AH N
DONT D OW N T
DOWN D AW N
DREAM D R IY M
EACH IY CH
EVERY EH V R IY
EYES AY Z
FALL F AO L
FEEL F IY L
FIRE F AY ER
FIRST F ER S T
FLY F L AY
FOR F AO R
FOREVER F ER EH V ER
FRIEND F R EH N D
FROM F R AH M
GIRL G ER L
GIVE G IH V
GO G OW
GOING G OW IH NG
GONE G AO N
GONNA G AA N AX
GOOD G UH D
GOT G AA T
HAD HH AE D
HANDS HH AE N D Z
HAS HH AE Z
HAVE HH AE V
HE HH IY
HEAD HH EH D
HEAR HH IY R
HEART HH AA R T
HER HH ER
HERE HH IY R
HIGH HH AY
HIM HH IH M
HIS HH IH Z
HOLD HH OW L D
HOME HH OW M
HOW HH AW
I AY
IF IH F
IM AY M
IN IH N
INTO IH N T UW
IS IH Z
IT IH T
ITS IH T S
JUST JH AH S T
KNOW N OW
LEAVE L IY V
LET L EH T
LIFE L AY F
LIGHT L AY T
LIKE L AY K
LITTLE L IH T AH L
LIVE L IH V
LONELY L OW N L IY
LONG L AO NG
LOOK L UH K
LOSE L UW Z
LOVE L AH V
MADE M EY D
MAKE M EY K
MANY M EH N IY
ME M IY
MIND M AY N D
MINE M AY N
MORE M AO R
MOVE M UW V
MUSIC M Y UW Z IH K
MUST M AH S T
MY M AY
NEVER N EH V ER
NEW N UW
NIGHT N AY T
NO N OW
NOT N AA T
NOTHING N AH TH IH NG
NOW N AW
OF AH V
OFF AO F
OH OW
OK OW K EY
ON AA N
ONCE W AH N S
ONE W AH N
ONLY OW N L IY
OTHER AH DH ER
OUR AW ER
OUT AW T
OVER OW V ER
OWN OW N
PEOPLE P IY P AH L
PLACE P L EY S
PUT P UH T
REAL R IY L
RIGHT R AY T
RUN R AH N
SAID S EH D
SAY S EY
SEE S IY
SHE SH IY
SHOULD SH UH D
SHOW SH OW
SKY S K AY
SO S OW
SOME S AH M
SOMEBODY S AH M B AA D IY
SOMEONE S AH M W AH N
SOMETHING S AH M TH IH NG
SOON S UW N
SOUL S OW L
SOUND S AW N D
STAY S T EY
STILL S T IH L
SUN S AH N
TAKE T EY K
TELL T EH L
THAN DH AE N
THAT DH AE T
THE DH AX
THEIR DH EH R
THEM DH EH M
THEN DH EH N
THERE DH EH R
THESE DH IY Z
THEY DH EY
THING TH IH NG
THINK TH IH NG K
THIS DH IH S
THOSE DH OW Z
THOUGH DH OW
THROUGH TH R UW
TIME T AY M
TO T UW
TOGETHER T AX G EH DH ER
TONIGHT T AX N AY T
TOO T UW
TOUCH T AH CH
TWO T UW
UP AH P
US AH S
VERY V EH R IY
WANNA W AA N AX
WANT W AA N T
WAS W AH Z
WATER W AO T ER
WAY W EY
WE W IY
WERE W ER
WHAT W AH T
WHEN W EH N
WHERE W EH R
WHO HH UW
WHY W AY
WILD W AY L D
WILL W IH L
WITH W IH DH
WITHOUT W IH DH AW T
WOMAN W UH M AX N
WORD W ER D
WORK W ER K
WORLD W ER L D
WOULD W UH D
YEAH Y EH AX
YES Y EH S
YOU Y UW
YOUNG Y AH NG
YOUR Y AO R
""".strip().splitlines()}

# open-syllable vocalese that producers actually type
LEXICON.update({
    "AAH": "AA", "AH": "AA", "OOH": "UW", "OOOH": "UW", "OH": "OW",
    "EH": "EH", "AY": "EY", "LA": "L AA", "NA": "N AA", "DA": "D AA",
    "HEY": "HH EY", "WOO": "W UW", "WHOA": "W OW", "UH": "AH",
    "MM": "M", "MMM": "M", "HMM": "HH M", "SHH": "SH",
})

# words whose spelling fights the letter rules
LEXICON.update({
    "GET": "G EH T", "GETS": "G EH T S", "GETTING": "G EH T IH NG",
    "GIFT": "G IH F T", "GIVEN": "G IH V AX N", "GIVING": "G IH V IH NG",
    "BEGIN": "B IH G IH N", "FORGET": "F ER G EH T", "GUESS": "G EH S",
    "TOGETHER": "T AX G EH DH ER", "ANGEL": "EY N JH AX L",
    "TIGHT": "T AY T", "MIGHT": "M AY T", "FIGHT": "F AY T",
    "HIGHER": "HH AY ER", "FIRE": "F AY ER", "DESIRE": "D IH Z AY ER",
    "ELECTRIC": "IH L EH K T R IH K", "NEON": "N IY AA N",
    "CYBER": "S AY B ER", "DIGITAL": "D IH JH AX T AX L",
    "PARADISE": "P EH R AX D AY S", "MIDNIGHT": "M IH D N AY T",
    "STARLIGHT": "S T AA R L AY T", "RHYTHM": "R IH DH AX M",
    "BASS": "B EY S", "SYNTH": "S IH N TH", "ROBOT": "R OW B AA T",
    "ROBOTS": "R OW B AA T S", "HUMAN": "HH Y UW M AX N",
    "MACHINE": "M AX SH IY N", "FUTURE": "F Y UW CH ER",
    "LOVER": "L AH V ER", "DIAMOND": "D AY M AX N D", "HIGHEST": "HH AY AX S T",
})

# --------------------------------------------------------------------------
# letter rules
# --------------------------------------------------------------------------
_RULES_SRC = """
A|_|A|_|AX
A|_|ARE|_|AA R
A| |AR|O|AX R
A||AR|#|EH R
A||AR||AA R
A||AIR||EH R
A||AI||EY
A||AY||EY
A||AU||AO
A||AW||AO
A||AL|_|AX L
A||ALL||AO L
A||ANG|+|EY N JH
A|_|A|^#|AX
A||A|^E_|EY
A||A|^%|EY
A||A|_|AX
A||A||AE
B||BB||B
B||B||B
C||CH||CH
C||CK||K
C||CI|#|SH
C||C|+|S
C||C||K
D||DGE||JH
D||DD||D
D||D|_|D
D||D||D
E||EE||IY
E||EA|R|IY
E||EAR|^|ER
E||EA||IY
E||EIGH||EY
E||EI||IY
E||EW||UW
E||EY||IY
E||ER|_|ER
E||ER||ER
E||E|_|
E||ED|_|D
E||E|^E_|IY
E||E||EH
F||FF||F
F||F||F
G||GH|_|
G||GHT||T
G||GG||G
G||G|+|JH
G||G||G
H||H|_|
H||H||HH
I||IGH||AY
I||IGN|_|AY N
I||ION||Y AX N
I||IE|_|IY
I||IE||IY
I||IR||ER
I||ING|_|IH NG
I||I|^E_|AY
I||I|^%|AY
I||I||IH
J||J||JH
K||KN|_|N
K||K||K
L||LL||L
L||L||L
M||MB|_|M
M||MM||M
M||M||M
N||NG|_|NG
N||NG|^|NG
N||NN||N
N||N||N
O||OO||UW
O||OU|S|AH
O||OUGH||AO
O||OU||AW
O||OW||OW
O||OI||OY
O||OY||OY
O||OA||OW
O||OR|_|AO R
O||OR||AO R
O||OE|_|OW
O||O|_|OW
O||O|^E_|OW
O||O|^%|OW
O||O|NG|AO
O||O||AA
P||PH||F
P||PP||P
P||P||P
Q||QU||K W
Q||Q||K
R||RR||R
R||R||R
S||SH||SH
S||SION||ZH AX N
S||SS||S
S||SC|+|S
S||S|_|Z
S||S||S
T||TCH||CH
T||TH||TH
T||TION||SH AX N
T||TT||T
T||T||T
U||UR||ER
U||UU||UW
U||U|_|UW
U||U|^E_|UW
U||U|^%|UW
U||U||AH
V||V||V
W||WR||R
W||WH||W
W||W||W
X||X||K S
Y||Y|_|IY
Y||YOU||Y UW
Y||Y|#|Y
Y||Y||IH
Z||ZZ||Z
Z||Z||Z
"""


def _parse_rules():
    table: dict[str, list] = {}
    for line in _RULES_SRC.strip().splitlines():
        letter, left, match, right, out = line.split("|")
        table.setdefault(letter, []).append(
            (left, match, right, out.split()))
    return table


RULES = _parse_rules()
_SUFFIXES = ("E", "ES", "ED", "ER", "ING", "ELY")


def _match_left(word: str, i: int, ctx: str) -> bool:
    for c in reversed(ctx):
        i -= 1
        if i < 0:
            return c == "_"
        ch = word[i]
        if c == "#":
            if ch not in VOWEL_LETTERS:
                return False
        elif c == "^":
            if ch not in CONSONANTS:
                return False
        elif c == "+":
            if ch not in FRONT:
                return False
        elif c == ".":
            if ch not in VOICED:
                return False
        elif c == "_":
            return False
        elif c != ch:
            return False
    return True


def _match_right(word: str, i: int, ctx: str) -> bool:
    for c in ctx:
        if c == "_":
            return i >= len(word)
        if i >= len(word):
            return False
        ch = word[i]
        if c == "#":
            if ch not in VOWEL_LETTERS:
                return False
            while i < len(word) and word[i] in VOWEL_LETTERS:
                i += 1
            continue
        if c == "^":
            if ch not in CONSONANTS:
                return False
        elif c == "+":
            if ch not in FRONT:
                return False
        elif c == ".":
            if ch not in VOICED:
                return False
        elif c == "%":
            if not any(word[i:].startswith(s) for s in _SUFFIXES):
                return False
            return True
        elif c != ch:
            return False
        i += 1
    return True


def _rule_word(word: str) -> list[str]:
    out: list[str] = []
    i = 0
    n = len(word)
    while i < n:
        ch = word[i]
        if ch not in RULES:
            i += 1
            continue
        for left, match, right, phones in RULES[ch]:
            if not word.startswith(match, i):
                continue
            if left and not _match_left(word, i, left):
                continue
            if right and not _match_right(word, i + len(match), right):
                continue
            out.extend(phones)
            i += len(match)
            break
        else:
            i += 1
    return out


def _fix_plural(word: str, phones: list[str]) -> list[str]:
    """English -s assimilation: cats -> S, dogs -> Z, buses -> IH Z."""
    if not phones or not word.endswith("S") or word.endswith("SS"):
        return phones
    prev = phones[-2] if len(phones) >= 2 else ""
    if phones[-1] in ("S", "Z"):
        if prev in ("S", "Z", "SH", "ZH", "CH", "JH"):
            phones[-1:] = ["IH", "Z"]
        elif prev in ("P", "T", "K", "F", "TH"):
            phones[-1] = "S"
        else:
            phones[-1] = "Z"
    return phones


def _espeak(text: str) -> list[str] | None:
    exe = shutil.which("espeak-ng") or shutil.which("espeak")
    if not exe:
        return None
    try:
        res = subprocess.run([exe, "-q", "-x", "--sep=_", "-v", "en-us", text],
                             capture_output=True, text=True, timeout=10)
    except Exception:
        return None
    if res.returncode != 0:
        return None
    return _from_espeak(res.stdout)


_ESPEAK_MAP = {
    "i:": "IY", "I": "IH", "e": "EH", "a": "AE", "A:": "AA", "0": "AO",
    "O:": "AO", "U": "UH", "u:": "UW", "V": "AH", "@": "AX", "3:": "ER",
    "3": "ER", "eI": "EY", "aI": "AY", "OI": "OY", "aU": "AW", "oU": "OW",
    "@U": "OW", "I@": "IH R", "e@": "EH R", "U@": "UH R", "i": "IY",
    "p": "P", "b": "B", "t": "T", "d": "D", "k": "K", "g": "G",
    "tS": "CH", "dZ": "JH", "f": "F", "v": "V", "T": "TH", "D": "DH",
    "s": "S", "z": "Z", "S": "SH", "Z": "ZH", "h": "HH", "m": "M",
    "n": "N", "N": "NG", "l": "L", "r": "R", "R": "R", "w": "W", "j": "Y",
}


def _from_espeak(raw: str) -> list[str]:
    out: list[str] = []
    for tok in raw.replace("\n", " ").split():
        for part in tok.split("_"):
            part = part.strip("'`,%=|")
            if not part:
                continue
            out.extend(_ESPEAK_MAP.get(part, "AX").split())
    return out


# --------------------------------------------------------------------------
# public API
# --------------------------------------------------------------------------
_ESCAPE = re.compile(r"/([^/]+)/|\[([^\]]+)\]")
_WORD = re.compile(r"[A-Za-z']+|[.,;:!?]|-")


def word_to_phones(word: str) -> list[str]:
    w = re.sub(r"[^A-Z]", "", word.upper())
    if not w:
        return []
    if w in LEXICON:
        return LEXICON[w].split()
    # try stripping a regular plural / past-tense ending against the lexicon
    for suf, add in (("S", None), ("ED", ["D"]), ("ING", ["IH", "NG"])):
        if w.endswith(suf) and w[:-len(suf)] in LEXICON:
            base = LEXICON[w[:-len(suf)]].split()
            return _fix_plural(w, base + ["S"]) if add is None else base + add
    ph = _fix_plural(w, _rule_word(w))
    if not ph:                       # e.g. a bare silent-E word
        ph = _rule_word(w + "H") or ["AX"]
    return ph


def text_to_words(text: str, prefer_espeak: bool = False
                  ) -> list[tuple[str, list[str]]]:
    """Convert a lyric into (source token, phonemes) pairs.

    Punctuation becomes an explicit SIL/SP token so phrasing survives.
    """
    words: list[tuple[str, list[str]]] = []
    pos = 0
    for m in _ESCAPE.finditer(text):
        words.extend(_plain(text[pos:m.start()], prefer_espeak))
        manual = (m.group(1) or m.group(2)).split()
        if manual:
            words.append((m.group(0), [x.upper() for x in manual]))
        pos = m.end()
    words.extend(_plain(text[pos:], prefer_espeak))
    return [(src, ph) for src, ph in words if ph]


def text_to_phones(text: str, prefer_espeak: bool = False) -> list[list[str]]:
    """Just the phonemes -- see :func:`text_to_words` for the source tokens."""
    return [ph for _, ph in text_to_words(text, prefer_espeak)]


def _plain(text: str, prefer_espeak: bool) -> list[tuple[str, list[str]]]:
    if not text.strip():
        return []
    out: list[tuple[str, list[str]]] = []
    for tok in _WORD.findall(text):
        if tok in ".,;:!?":
            out.append((tok, ["SIL" if tok in ".!?" else "SP"]))
        elif tok == "-":
            continue
        elif prefer_espeak:
            # espeak gives no word alignment with --sep, so phonemise per word
            ph = _espeak(tok)
            out.append((tok, ph if ph else word_to_phones(tok)))
        else:
            out.append((tok, word_to_phones(tok)))
    return out


def syllabify(phones: list[str]) -> list[list[str]]:
    """Split a word's phonemes into syllables, one vowel nucleus each.

    Uses maximal-onset: consonants between two nuclei attach to the following
    syllable, except the single consonant closest to the first nucleus.
    """
    from . import phonemes as P

    nuclei = [i for i, p in enumerate(phones) if P.is_syllabic(p)]
    if not nuclei:
        return [phones] if phones else []
    bounds = [0]
    for a, b in zip(nuclei, nuclei[1:]):
        gap = b - a - 1
        if gap <= 0:
            split = a + 1
        elif gap == 1:
            split = a + 1                 # V-CV
        else:
            split = a + 1 + max(1, gap - 2)   # VC-CV / VC-CCV
        bounds.append(split)
    bounds.append(len(phones))
    return [phones[s:e] for s, e in zip(bounds, bounds[1:]) if phones[s:e]]
