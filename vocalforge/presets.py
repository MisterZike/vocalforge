"""Preset storage.

Factory presets ship read-only inside the package; user presets live in
``~/.config/vocalforge/presets`` so they survive updates.  A preset is a JSON
object with ``name``, ``description``, optional ``text``/``melody`` and a
``params`` map of the keys that differ from the defaults.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from . import params

FACTORY_DIR = Path(__file__).parent / "presets"
USER_DIR = Path.home() / ".config" / "vocalforge" / "presets"

_SAFE = re.compile(r"[^a-z0-9_-]+")


def slugify(name: str) -> str:
    s = _SAFE.sub("_", name.strip().lower()).strip("_")
    return s or "preset"


def _read(path: Path) -> dict[str, Any] | None:
    try:
        d = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(d, dict):
        return None
    d.setdefault("name", path.stem)
    d.setdefault("params", {})
    d.setdefault("macros", {})
    d["id"] = path.stem
    return d


def list_presets() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for src, d in (("user", USER_DIR), ("factory", FACTORY_DIR)):
        if not d.is_dir():
            continue
        for f in sorted(d.glob("*.json")):
            pr = _read(f)
            if pr and pr["id"] not in seen:
                pr["source"] = src
                seen.add(pr["id"])
                out.append(pr)
    out.sort(key=lambda x: (x["source"] != "factory", x["name"].lower()))
    return out


def load(name: str) -> dict[str, Any] | None:
    slug = slugify(name)
    for d in (USER_DIR, FACTORY_DIR):
        f = d / f"{slug}.json"
        if f.is_file():
            return _read(f)
    for pr in list_presets():           # fall back to a case-insensitive name
        if pr["name"].lower() == name.strip().lower():
            return pr
    return None


def save(name: str, values: dict[str, Any], description: str = "",
         text: str = "", only_changed: bool = True,
         macro_values: dict[str, float] | None = None) -> Path:
    """Persist a user preset.  By default only non-default values are stored,
    so a preset keeps working when new parameters are added later.

    ``macro_values`` records where the macro knobs were left.  Parameters stay
    authoritative for the sound; this only restores the knob positions exactly,
    which matters because some macros read back through an integer parameter
    and would otherwise snap to the nearest step.
    """
    USER_DIR.mkdir(parents=True, exist_ok=True)
    full = params.normalize_params(values)
    defaults = params.defaults()
    stored = {k: v for k, v in full.items()
              if not only_changed or k not in defaults or defaults[k] != v}
    payload = {"name": name.strip() or "Untitled",
               "description": description, "text": text, "params": stored,
               "version": 1}
    if macro_values:
        payload["macros"] = {k: round(float(v), 4)
                             for k, v in macro_values.items()}
    path = USER_DIR / f"{slugify(name)}.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True))
    return path


def delete(name: str) -> bool:
    f = USER_DIR / f"{slugify(name)}.json"
    if f.is_file():
        f.unlink()
        return True
    return False


def apply(preset: dict[str, Any] | None, base: dict[str, Any] | None = None
          ) -> dict[str, Any]:
    p = params.normalize_params(base)
    if preset:
        for k, v in (preset.get("params") or {}).items():
            p[k] = params.coerce(k, v) if k in params.BY_KEY else v
    return p
