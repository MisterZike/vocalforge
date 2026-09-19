"""Command line interface."""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

from . import audio, g2p, macros, params, presets, render


def _apply_sets(p: dict, assignments: list[str]) -> dict:
    for a in assignments or []:
        if "=" not in a:
            print(f"! ignoring '{a}' (expected key=value)", file=sys.stderr)
            continue
        k, v = a.split("=", 1)
        k = k.strip()
        if k not in params.BY_KEY:
            near = [x for x in params.BY_KEY if k.lower() in x.lower()][:4]
            hint = f"  did you mean: {', '.join(near)}" if near else ""
            print(f"! unknown parameter '{k}'{hint}", file=sys.stderr)
            continue
        p[k] = params.coerce(k, v.strip())
    return p


def _play(path: Path) -> None:
    for cmd in (["pw-play"], ["paplay"], ["aplay"], ["ffplay", "-nodisp", "-autoexit",
                                                     "-loglevel", "error"]):
        if shutil.which(cmd[0]):
            subprocess.run(cmd + [str(path)])
            return
    print("! no audio player found (tried pw-play, paplay, aplay, ffplay)",
          file=sys.stderr)


# What belongs to the song rather than the voice.  --voice-only drops these
# from a preset so it can be auditioned against a melody you already have.
CONTENT_KEYS = ("pitch.melody", "pitch.bpm", "pitch.root", "pitch.scale",
                "pitch.swing", "pitch.note_length", "pitch.auto_style")


def cmd_render(a: argparse.Namespace) -> int:
    base = {}
    if a.preset:
        pr = presets.load(a.preset)
        if not pr:
            print(f"! no preset named '{a.preset}'. Try: vf presets", file=sys.stderr)
            return 2
        base = presets.apply(pr)
        if a.voice_only:
            defaults = params.defaults()
            for k in CONTENT_KEYS:
                base[k] = defaults[k]
        elif not a.text and pr.get("text"):
            a.text = pr["text"]
    p = params.normalize_params(base)
    if a.melody is not None:
        p["pitch.melody"] = a.melody
    if a.bpm is not None:
        p["pitch.bpm"] = a.bpm
    if a.seed is not None:
        p["render.seed"] = a.seed
    for spec in a.macro or []:
        if "=" not in spec:
            print(f"! ignoring '{spec}' (expected name=0..1)", file=sys.stderr)
            continue
        k, v = spec.split("=", 1)
        k = k.strip().lower()
        if k not in macros.BY_KEY:
            print(f"! unknown macro '{k}'. Available: "
                  f"{', '.join(macros.BY_KEY)}", file=sys.stderr)
            continue
        try:
            macros.apply(p, k, float(v))
        except ValueError:
            print(f"! macro '{k}' needs a number between 0 and 1", file=sys.stderr)
    _apply_sets(p, a.set)

    text = a.text or "hello world"
    bar_state = {"last": ""}

    def prog(stage, frac):
        if a.quiet:
            return
        n = int(frac * 28)
        line = f"\r  [{'#' * n}{'.' * (28 - n)}] {stage:<18}"
        sys.stderr.write(line)
        sys.stderr.flush()
        bar_state["last"] = line

    x, sr, info = render.render(text, p, prog)
    if not a.quiet:
        sys.stderr.write("\r" + " " * 60 + "\r")

    out = Path(a.output) if a.output else Path("out") / "vocalforge.wav"
    audio.export(out, x, sr, int(p["render.bits"]))
    if not a.quiet:
        print(f"  {out}")
        print(f"  {info['duration']:.2f}s @ {sr} Hz, {info['peak_db']} dBFS peak, "
              f"rendered in {info['render_time']}s")
        print(f"  phonemes: {info['phonemes']}")
    if a.save_preset:
        path = presets.save(a.save_preset, p, a.description or "", text)
        print(f"  preset saved: {path}")
    if a.play:
        _play(out)
    return 0


def cmd_presets(a: argparse.Namespace) -> int:
    rows = presets.list_presets()
    if a.json:
        print(json.dumps(rows, indent=2))
        return 0
    for pr in rows:
        tag = "user" if pr["source"] == "user" else "    "
        print(f"  {tag} {pr['id']:18} {pr['name']}")
        if pr.get("description"):
            print(f"       {pr['description']}")
    return 0


def cmd_params(a: argparse.Namespace) -> int:
    q = (a.filter or "").lower()
    group = None
    for e in params.SCHEMA:
        if q and q not in e["key"].lower() and q not in e["label"].lower():
            continue
        if e["group"] != group:
            group = e["group"]
            print(f"\n{group.upper()}")
        rng = ""
        if e["kind"] in ("f", "i"):
            rng = f"[{e['lo']} .. {e['hi']}]"
        elif e["kind"] == "e":
            rng = "{" + ", ".join(str(c) for c in e["choices"]) + "}"
        elif e["kind"] == "b":
            rng = "{true, false}"
        print(f"  {e['key']:26} {str(e['default']):>12}  {e['unit']:<6} {rng}")
        if e["help"] and a.verbose:
            print(f"    {e['help']}")
    return 0


def cmd_phonemes(a: argparse.Namespace) -> int:
    words = g2p.text_to_phones(a.text, a.espeak)
    print("  " + " | ".join(" ".join(w) for w in words))
    if a.syllables:
        for w in words:
            print("   ", " - ".join("".join(s) for s in g2p.syllabify(w)))
    return 0


def cmd_macros(a: argparse.Namespace) -> int:
    for m in macros.MACROS:
        print(f"\n  {m['label']:<9} {m['lo']} -> {m['hi']}")
        print(f"    {m['blurb']}")
        if a.verbose:
            for t, pts in m["targets"].items():
                lo = macros.eval_curve(pts, 0.0)
                hi = macros.eval_curve(pts, 1.0)
                star = " *" if t == m["probe"] else "  "
                print(f"    {star} {t:24} {lo} .. {hi}")
    print("\n  (* = the parameter a preset is read back through)")
    return 0


def cmd_ui(a: argparse.Namespace) -> int:
    from . import server
    server.serve(a.host, a.port, open_browser=not a.no_browser)
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="vf", description="VocalForge - synthetic vocal samples for music production.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("render", help="render a vocal sample to a file")
    r.add_argument("text", nargs="?", help="the phrase to sing")
    r.add_argument("-p", "--preset")
    r.add_argument("-o", "--output")
    r.add_argument("-m", "--melody", help="e.g. 'C4 Eb4 G4:2'")
    r.add_argument("-b", "--bpm", type=float)
    r.add_argument("--seed", type=int)
    r.add_argument("-M", "--macro", action="append", metavar="NAME=0..1",
                   help="turn a macro knob (body, air, tone, grit, life, "
                        "motion, diction, robot, thick, space); repeatable")
    r.add_argument("-s", "--set", action="append", metavar="KEY=VALUE",
                   help="override any parameter; repeatable")
    r.add_argument("--voice-only", action="store_true",
                   help="take only the voice from the preset, not its melody, "
                        "tempo or key")
    r.add_argument("--save-preset", metavar="NAME")
    r.add_argument("--description", default="")
    r.add_argument("--play", action="store_true")
    r.add_argument("-q", "--quiet", action="store_true")
    r.set_defaults(func=cmd_render)

    pl = sub.add_parser("presets", help="list available presets")
    pl.add_argument("--json", action="store_true")
    pl.set_defaults(func=cmd_presets)

    pp = sub.add_parser("params", help="list every parameter")
    pp.add_argument("filter", nargs="?")
    pp.add_argument("-v", "--verbose", action="store_true", help="include help text")
    pp.set_defaults(func=cmd_params)

    ph = sub.add_parser("phonemes", help="show how text is pronounced")
    ph.add_argument("text")
    ph.add_argument("--espeak", action="store_true")
    ph.add_argument("--syllables", action="store_true")
    ph.set_defaults(func=cmd_phonemes)

    mc = sub.add_parser("macros", help="list the macro knobs")
    mc.add_argument("-v", "--verbose", action="store_true",
                    help="show the parameters each macro drives")
    mc.set_defaults(func=cmd_macros)

    u = sub.add_parser("ui", help="start the web interface")
    u.add_argument("--host", default="127.0.0.1")
    u.add_argument("--port", type=int, default=8765)
    u.add_argument("--no-browser", action="store_true")
    u.set_defaults(func=cmd_ui)
    return ap


def main(argv: list[str] | None = None) -> int:
    ap = build_parser()
    a = ap.parse_args(argv)
    try:
        return a.func(a)
    except KeyboardInterrupt:
        print()
        return 130


if __name__ == "__main__":
    sys.exit(main())
