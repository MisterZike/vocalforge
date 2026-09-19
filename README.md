# VocalForge

A synthetic singing-voice generator for music production. Type a phrase, give it
a melody, and shape the result with 153 parameters — from semi-realistic sung
vocals through to Daft Punk vocoder robots and Vocaloid-style leads.

Runs entirely offline on your machine. No account, no API, no model downloads,
no cost. The only dependencies are `numpy` and `scipy`.

```
./setup.sh          # one-time: creates .venv and installs numpy + scipy
./vf ui             # open the web interface
```

---

## How it works

VocalForge is not a text-to-speech wrapper. It is a **source–filter singing
synthesiser** written from scratch, which is what makes deep parameter control
possible — there is no pretrained model to fight with, so every acoustic
property of the voice is a knob.

```
  text ──► G2P ──► syllables ──┐
                               ├──► articulation plan (phonemes anchored to notes)
  melody ──► note timeline ────┘                │
                                                ▼
   pitch contour            glottal source ──► nasal branch ──► 5-formant
   (vibrato, portamento,    (Rosenberg pulse,    (pole/zero)     cascade
    drift, jitter, snap) ──► breath, shimmer,                       │
                             growl, wave blend)                     ▼
                                                              lip radiation
   fricative noise ──► 3-band parallel resonators ──────────────►  (+)
                                                                    │
      vocoder ─► harmony ─► unison ─► gate ─► EQ ─► de-ess ─► comp ─┤
                                                                    │
      saturation ─► chorus ─► phaser ─► delay ─► reverb ─► width ─► out
```

Formant frequencies, bandwidths, voicing, breath and noise are all continuous
per-sample control tracks, and the resonators are re-tuned every 64 samples, so
the voice *moves* between phonemes rather than crossfading between static frames.

---

## The interface

`./vf ui` serves a local page at <http://127.0.0.1:8765>. It is one page, and it
reads top to bottom as the workflow: **content → instrument → notation → output**.

```
  VOCALFORGE                    LIVE   [name this voice] SAVE RESET │ PARAMETERS
 ────────────────────────────────────────────────────────────────────────────────
  we are the robots tonight                                    ← type a line
  W IY · AA R · DH AX · R OW B AA T S              8 SYL · 18 PHON
 ────────────────────────────────────────────────────────────────────────────────
  ┌ screen ─────────┐   (o) (o) (o) (o) (o)   BODY AIR TONE GRIT LIFE
  │ BODY         33 │   (o) (o) (o) (o) (o)   MOTION DICTION ROBOT THICK SPACE
  │ TINY ───── HUGE │                                        RANDOM  RESET
  │ ▸ Tract length  │
  │ ∿∿ scope ∿∿     │
  └─────────────────┘
  KEEP WORDS │ BREATHY DIVA · DAFT ROBOT · SYNTH DIVA · 8-BIT DROID …
 ────────────────────────────────────────────────────────────────────────────────
  BPM KEY SCALE SWING │ GRID ZOOM │ OCT │ LEN │ FIT CLEAR      melody A4 A4 C5…
  ┌───────────────── piano roll ────────────────────────────────────────────────┐
  │ syllable lane · phoneme lane · beat ruler                                   │
  └─────────────────────────────────────────────────────────────────────────────┘
  [ RENDER ] (▶) ▏▂▄█▆▃▁▂▅█▇▄▂▏ 0:01.4 / 0:03.9  ⭳
```

The chassis is monochrome — warm near-black, bone type, one signal orange for
*something is happening right now*. The only colour in the whole app comes from
the ten macro knobs, and the phoneme lanes share their palette, so a colour
always means "this changes the sound".

- **Lyric** — plain English, one line. Punctuation becomes breaths. Wrap
  phonemes in slashes to override pronunciation: `/M IY K UW/`. The strip
  underneath shows exactly what will be sung; hover a phoneme to inspect it.
- **The screen** narrates whatever your cursor is on — a knob and every
  parameter it is moving, a preset and its demo line, a phoneme and its
  duration, or the last render's stats when you are not touching anything.
  Clicking a parameter row in it opens that parameter in the drawer.
- **PARAMETERS** (or <kbd>Ctrl</kbd>+<kbd>K</kbd>) slides out a drawer with all
  150 of them, searchable by name, key or help text. It overlays only the right
  third, so the knobs stay visible and keep moving as you edit underneath them.
  A dot on the button means something in there is off its default.
- <kbd>Ctrl</kbd>+<kbd>Enter</kbd> renders, <kbd>Space</kbd> plays,
  <kbd>Ctrl</kbd>+<kbd>S</kbd> saves a preset, <kbd>Esc</kbd> closes the drawer.

### The melody editor

The Melody tab is where the note timing lives.

- **Click** empty space to add a note, **drag** its body to move it, **drag its
  right edge** to change how long it sounds, **right-click** to delete it.
- Arrow keys nudge the selected note; `Delete` removes it.
- The **wheel** scrolls the pitch range, **ctrl+wheel** zooms, **shift+wheel**
  scrolls through time.
- **Grid** sets the snap (down to 1/16, and triplet values 1/3 and 1/6).
- The toolbar transposes, halves or doubles every note value, and has
  **legato** (extend each note to the next) and **staccato** (halve each
  sounding length). **Fit to syllables** lays out one note per syllable.

A note has two independent durations: the **step** it occupies, and the
**length** it actually sounds. Drawing a note shorter than the gap to the next
one is what makes staccato — the pitch is held through the silence, so the
next note still glides from the right place. **Note length** in the Timing
panel does the same thing to every note at once.

The melody is still plain text — `pitch.melody` in presets, `-m` on the command
line, and a read-out at the right of the roll toolbar that you can copy from or
paste into. The roll and that text stay in sync both ways:

```
NAME[octave][:step[:length]]     C4      one beat, legato
                                 Eb4:2   two beats
                                 G4:1:1/2  one-beat step, sounds for half of it
R[:beats]                        R:0.5   a half-beat rest
```

The octave carries over from the previous note. More notes than syllables gives
melisma (one syllable held across several notes); fewer subdivides each note
between the syllables that share it.

### The alignment view

Underneath the roll, two lanes show what the synthesiser actually did:

- **syl** — each syllable, shaded by which note it landed on
- **phon** — every phoneme, coloured by class (vowels teal, fricatives amber,
  stops red, nasals purple, and so on)

The dashed vertical lines mark **vowel onsets**, and they line up with note
starts because that is the rule the articulation planner follows: consonants
are placed *before* the beat so the vowel lands *on* it, which is how singers
actually phrase. The yellow curve over the roll is the pitch that was really
sung — portamento glides, vibrato, scoops and scale snapping all visible
against the notes you wrote.

It updates as you edit (no audio render needed — the alignment is computed in
about a millisecond), and refreshes to the full-resolution pitch track after
each render.

### Auditioning presets

**keep my words & melody** (above the preset list, on by default) means a
preset changes the *voice* and nothing else — your lyric, melody, tempo, key,
scale and swing all stay put. So you can write your line once and click down
the preset list to hear it as a robot, a diva, a monster.

With the lock off, a preset loads its own demo lyric and melody too. To hear
one preset's demo without turning the lock off, **alt-click** it. Hovering a
preset shows the demo line it would load. **Reset** follows the same rule: it
resets the voice and keeps your content while the lock is on.

The command line does the same with `--voice-only`:

```bash
./vf render "my own words" -p daft_robot --voice-only -m "D4 F4 A4:2 G4" -b 96
```

Presets you save appear at the top of the list tagged `mine`; right-click one
to delete it. They are stored as JSON in `~/.config/vocalforge/presets/`, and
only record what you changed from the defaults, so they keep working when new
parameters are added.

---

## Command line

```bash
./vf render "we are the robots" -p daft_robot -o out/robot.wav --play
./vf render "take me higher" -p trance_angel -m "A4 A4 C5 E5 D5" -b 138
./vf render "stab stab stab" -m "C4:1:1/4 C4:1:1/4 G4:2:1"   # per-note lengths
./vf render "hello" -s voice.tract_length=0.7 -s voc.mix=1 -s voc.bands=8
./vf render "my sound" --save-preset "My Sound" --description "what it is"
./vf render "my words" -p daft_robot --voice-only -m "D4 F4 A4"  # preset's voice only

./vf presets                  # list presets
./vf params vocoder -v        # every vocoder parameter, with help text
./vf phonemes "digital love"  # check pronunciation before rendering
./vf ui --port 9000           # web interface on another port
```

`-s KEY=VALUE` is repeatable and reaches every one of the 153 parameters.
Output format follows the file extension — `.wav` natively, anything else
(`.mp3`, `.flac`, `.ogg`) via `ffmpeg` if it is installed.

---

## Getting the sound you want

**Robot / vocoder (Daft Punk, Kraftwerk)** — the character comes from the
vocoder, not the voice. Set `voc.mix` to 1, pick a bright carrier
(`supersaw`, `saw`), and stack a chord with `voc.chord` (`0 12` for octaves,
`0 3 7` for minor). Fewer `voc.bands` is more obviously robotic; more is more
intelligible. Then remove every human cue: `pitch.quantize` 1.0,
`pitch.portamento` 0, `pitch.vibrato_depth` 0, `voice.pitch_jitter` 0,
`voice.shimmer` 0. Keep `voc.sibilance` around 0.4 so consonants survive.

**Vocaloid / Miku** — a small bright tract rather than a vocoder. Lower
`voice.tract_length` to ~0.8, raise `voice.formant_shift` a couple of
semitones, raise `voice.formant_q` for tighter resonance, and keep breath low.
Machine-steady pitch with vibrato that only arrives late
(`pitch.vibrato_delay` ~320 ms) is the giveaway.

**Semi-realistic singing** — realism lives in the imperfections. Raise
`voice.open_quotient` (0.65–0.75), `voice.breathiness` (0.3–0.5),
`voice.shimmer` and `voice.pitch_jitter` (~0.05 each), `pitch.drift`, and add
`pitch.scoop` so notes are approached from below. Keep `pitch.quantize` at 0
and `pitch.portamento` around 70 ms.

**Deep / monstrous** — `voice.tract_length` above 1.3 with negative
`voice.formant_shift`, plus `voice.growl` for period-doubling.

**Dancefloor** — `gate.depth` with `gate.division` 16 for a trance gate,
`uni.voices` for width, `harm.intervals` for stacked thirds and fifths.

Two controls change more than anything else: **`voice.tract_length`** (who is
singing) and **`voc.mix`** (human or machine).

---

## Pronunciation

The built-in G2P uses an irregular-word lexicon plus context-sensitive letter
rules. It handles ordinary lyrics well, but English spelling will occasionally
beat it. Two escape hatches:

- Spell it phonetically in the lyric: `/D IY JH AX T AX L/`
- Install `espeak-ng` (`sudo pacman -S espeak-ng`) and enable
  **Articulation → Use espeak-ng**. It is optional; nothing depends on it.

Check with `./vf phonemes "your lyric"`.

---

## Reproducibility

`render.seed` drives all randomness — jitter, shimmer, breath noise, unison
phases. A non-zero seed gives byte-identical output every render. Seed `0`
means "new randomness each time", which is useful for generating several takes
of the same line to layer.

---

## Deploying it

The repo is set up for Vercel (Hobby works). `api/index.py` re-uses the same
request handler the local server uses, `public/` is served statically, and
`vercel.json` rewrites `/api/*` onto the function.

1. <https://vercel.com/new> → import this repository
2. Framework preset: **Other**. Leave build and output settings empty.
3. Deploy.

**A hosted deployment is not identical to running it locally.** Serverless
functions are stateless and have no writable disk, so two things change, and
the app detects this at boot via `/api/env`:

| | local | hosted |
|---|---|---|
| audio | streamed from `/audio/<id>.wav` | returned inline, played from a blob URL |
| user presets | `~/.config/vocalforge/presets/*.json` | your browser's localStorage |

Factory presets, rendering, the knobs, the roll and export all behave the same.

Worth knowing before you rely on it: numpy and scipy come to ~150 MB, which
fits inside the 250 MB function limit but makes cold starts slow — the first
render after an idle period can take several seconds. Renders themselves are
0.1–1.5 s. `maxDuration` is set to 60 s in `vercel.json` to leave headroom.
Running it locally stays the better experience; hosting is for sharing.

## Layout

```
vocalforge/
  dsp.py         filters, delay lines, envelopes, STFT
  phonemes.py    phoneme inventory with formant targets
  g2p.py         text -> phonemes
  melody.py      note parsing, scales, pitch contour
  synth.py       articulation planning + source-filter render
  vocoder.py     channel vocoder and carrier oscillator
  effects.py     the effect rack
  params.py      the parameter schema (single source of truth)
  macros.py      macro knobs: curves over groups of parameters
  presets.py     preset storage
  render.py      the full pipeline
  server.py      local web UI
  cli.py         command line
api/index.py     Vercel serverless entry point
public/          theme.js  palette bridge for the canvases
                 macros.js knobs and their ten animated graphics
                 melody.js piano roll + alignment lanes
                 app.js    screen, drawer, toolbar, transport
vercel.json      routes and function limits
out/             rendered samples
```

Adding a parameter means adding one line to `params.py` — the CLI, the preset
format and the web UI all pick it up automatically.
