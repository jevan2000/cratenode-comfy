"""Font registry: which file a family name means, and whether the job may use it.

Search order (first match wins for a family):
1. configured font folders (recursive),
2. the fonts bundled with the pack (OFL),
3. the system's installed fonts (looked up on demand).

Licence data comes from font catalogs: JSON lists of
``{path, commercial_ok, licensed_for, license_note}``; a ``catalog.json`` at the
top of a configured folder is read automatically. A font used outside its
licence scope produces a warning, never an error.
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from pathlib import Path

import skia

from . import config as cfg

FONT_EXTS = {".ttf", ".otf", ".ttc"}


@dataclass(frozen=True)
class Licence:
    status: str  # free | scoped | restricted | unknown | system | bundled
    licensed_for: tuple[str, ...] = ()
    note: str = ""


@dataclass
class Face:
    family: str
    weight: int
    italic: bool
    path: Path | None
    source: str  # folder | bundled | system
    licence: Licence
    _typeface: skia.Typeface | None = field(default=None, repr=False)

    def typeface(self) -> skia.Typeface:
        if self._typeface is None and self.path is not None:
            self._typeface = skia.Typeface.MakeFromFile(str(self.path))
        return self._typeface


def _key(path: str | Path) -> str:
    return str(path).strip().replace("/", "\\").lower()


def _read_catalog(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict):
        data = data.get("fonts", [])
    return [e for e in data if isinstance(e, dict) and e.get("path")]


def _weight_cost(want: int, have: int) -> int:
    """CSS font-weight matching: lower is better."""
    if want == have:
        return 0
    if want < 400:
        return want - have if have < want else 1000 + have - want
    if want > 500:
        return have - want if have > want else 1000 + want - have
    if want < have <= 500:
        return have - want
    return 500 + want - have if have < want else 1000 + have - want


class FontRegistry:
    def __init__(self, conf: cfg.Config | None = None):
        conf = conf or cfg.load()
        self.config = conf
        self.problems: list[str] = []
        self.faces: list[Face] = []
        records = self._load_catalogs(conf)
        folders = [(p, "folder") for p in conf.font_folders] + [(cfg.BUNDLED_FONTS, "bundled")]
        for folder, source in folders:
            if not folder.is_dir():
                if source == "folder":
                    self.problems.append(f"font folder {folder} does not exist")
                continue
            for p in sorted(folder.rglob("*")):
                if p.suffix.lower() not in FONT_EXTS:
                    continue
                tf = skia.Typeface.MakeFromFile(str(p))
                if tf is None:
                    continue
                style = tf.fontStyle()
                self.faces.append(
                    Face(
                        family=tf.getFamilyName(),
                        weight=int(style.weight()),
                        italic=style.slant() != skia.FontStyle.kUpright_Slant,
                        path=p,
                        source=source,
                        licence=self._licence(p, source, records),
                        _typeface=tf,
                    )
                )
        self._system = skia.FontMgr() if conf.system_fonts else None
        self._lock = threading.Lock()
        self._collections: dict = {}

    def _load_catalogs(self, conf: cfg.Config) -> dict[str, dict]:
        paths = [f / "catalog.json" for f in conf.font_folders if (f / "catalog.json").is_file()]
        paths += list(conf.font_catalogs)
        records: dict[str, dict] = {}
        for p in paths:
            try:
                for e in _read_catalog(p):
                    r = records.setdefault(_key(e["path"]), {"commercial_ok": None, "licensed_for": [], "note": ""})
                    if e.get("commercial_ok") is True or r["commercial_ok"] is None:
                        r["commercial_ok"] = e.get("commercial_ok", r["commercial_ok"])
                    for s in e.get("licensed_for") or []:
                        if s.lower() not in (x.lower() for x in r["licensed_for"]):
                            r["licensed_for"].append(s)
                    note = (e.get("license_note") or "").strip()
                    if len(note) > len(r["note"]):
                        r["note"] = note
            except (OSError, ValueError) as err:
                self.problems.append(f"font catalog {p}: {err}")
        return records

    @staticmethod
    def _licence(path: Path, source: str, records: dict[str, dict]) -> Licence:
        if source == "bundled":
            return Licence("bundled", (), "SIL Open Font License")
        r = records.get(_key(path))
        if r is None:
            return Licence("unknown", (), "not in a font catalog")
        if r["commercial_ok"] is True:
            status = "free"
        elif r["licensed_for"]:
            status = "scoped"
        elif r["commercial_ok"] is False:
            status = "restricted"
        else:
            status = "unknown"
        return Licence(status, tuple(r["licensed_for"]), r["note"])

    # ---- lookup ----

    def families(self) -> list[str]:
        """Folder and bundled families, sorted (system fonts are looked up on demand)."""
        return sorted({f.family for f in self.faces}, key=str.lower)

    def resolve(self, family: str, weight: int = 400, italic: bool = False) -> Face | None:
        want = family.strip().lower()
        cands = [f for f in self.faces if f.family.lower() == want]
        if cands:
            best = min(f.source == "bundled" for f in cands)  # folder before bundled
            cands = [f for f in cands if (f.source == "bundled") == best]
            styled = [f for f in cands if f.italic == italic] or cands
            return min(styled, key=lambda f: (_weight_cost(weight, f.weight), str(f.path)))
        if self._system is not None:
            slant = skia.FontStyle.kItalic_Slant if italic else skia.FontStyle.kUpright_Slant
            tf = self._system.matchFamilyStyle(family, skia.FontStyle(weight, skia.FontStyle.kNormal_Width, slant))
            if tf is not None and tf.getFamilyName().lower() == want:
                st = tf.fontStyle()
                return Face(
                    family=tf.getFamilyName(),
                    weight=int(st.weight()),
                    italic=st.slant() != skia.FontStyle.kUpright_Slant,
                    path=None,
                    source="system",
                    licence=Licence("system"),
                    _typeface=tf,
                )
        return None

    def require(self, family: str, weight: int = 400, italic: bool = False) -> Face:
        face = self.resolve(family, weight, italic)
        if face is None:
            raise ValueError(f"font {family!r} is not installed (folders, bundled fonts or system)")
        return face

    def licence_warning(self, face: Face, scope: str | None) -> str | None:
        lic = face.licence
        name = f"{face.family} {face.weight}"
        if lic.status in ("free", "system", "bundled"):
            return None
        if lic.status == "scoped":
            if scope and any(s.lower() == scope.strip().lower() for s in lic.licensed_for):
                return None
            where = repr(scope) if scope else "not set"
            return f"{name} is licensed for {', '.join(lic.licensed_for)} only; licence scope is {where}"
        if lic.status == "restricted":
            return f"{name} is not licensed for commercial use"
        return f"{name} has no confirmed licence (check the font catalog)"

    def font_collection(self, faces: list[Face]) -> skia.textlayout.FontCollection:
        """A collection where each face's family name maps to exactly that face file."""
        key = tuple(id(f) for f in faces)
        with self._lock:
            if key not in self._collections:
                provider = skia.textlayout.TypefaceFontProvider()
                for f in faces:
                    provider.registerTypeface(f.typeface(), f.family)
                fc = skia.textlayout.FontCollection()
                fc.setDefaultFontManager(provider)
                self._collections[key] = fc
            return self._collections[key]


_registry: FontRegistry | None = None
_registry_lock = threading.Lock()


def registry() -> FontRegistry:
    global _registry
    with _registry_lock:
        if _registry is None:
            _registry = FontRegistry()
        return _registry
