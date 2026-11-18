"""Where CrateNode-Comfy finds fonts, catalogs and private data.

Settings come from, in order:
1. the JSON file named by the environment variable ``CRATENODE_COMFY_CONFIG``;
2. ``config.local.json`` next to this package's root folder (git-ignored);
3. built-in defaults (bundled fonts plus system fonts).

Example ``config.local.json``::

    {
      "font_folders": ["D:/fonts"],
      "font_catalogs": ["D:/fonts/catalog.json"],
      "system_fonts": true,
      "data_dir": "D:/design-data"
    }

Licensed fonts, ICC profiles and brand assets belong in these folders, never in
the package itself.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
BUNDLED_FONTS = PACKAGE_ROOT / "fonts"
LOCAL_CONFIG = PACKAGE_ROOT / "config.local.json"
BUNDLED_TEMPLATES = PACKAGE_ROOT / "templates"  # public example templates
BUNDLED_BRANDS = PACKAGE_ROOT / "brand"  # public example brand kit


@dataclass
class Config:
    font_folders: list[Path] = field(default_factory=list)
    font_catalogs: list[Path] = field(default_factory=list)
    system_fonts: bool = True
    data_dir: Path | None = None
    gpu_gate: str = ""  # optional URL answering {"ok": true|false}; see devices.py
    cmyk_profile: str = ""  # ICC output profile for print PDFs (never bundled)
    licence_scope: str = ""  # who the designs are for; scoped font licences are checked against it
    source: str = "defaults"

    @staticmethod
    def from_dict(d: dict, source: str) -> "Config":
        paths = lambda key: [Path(p) for p in d.get(key, []) if str(p).strip()]
        data_dir = d.get("data_dir")
        return Config(
            font_folders=paths("font_folders"),
            font_catalogs=paths("font_catalogs"),
            system_fonts=bool(d.get("system_fonts", True)),
            data_dir=Path(data_dir) if data_dir else None,
            gpu_gate=str(d.get("gpu_gate", "") or ""),
            cmyk_profile=str(d.get("cmyk_profile", "") or ""),
            licence_scope=str(d.get("licence_scope", "") or ""),
            source=source,
        )

    def template_folders(self) -> list[Path]:
        """Private templates (data_dir/templates) first, then the bundled examples."""
        own = [self.data_dir / "templates"] if self.data_dir else []
        return own + [BUNDLED_TEMPLATES]

    def brand_folders(self) -> list[Path]:
        """Private brand kits (data_dir/brand) first, then the bundled example."""
        own = [self.data_dir / "brand"] if self.data_dir else []
        return own + [BUNDLED_BRANDS]

    def resolve_data_path(self, p: str) -> Path:
        """A path as given, or relative to data_dir when it is relative and data_dir is set."""
        path = Path(p.strip().strip('"'))
        if not path.is_absolute() and self.data_dir and (self.data_dir / path).exists():
            return self.data_dir / path
        return path


def load() -> Config:
    env = os.environ.get("CRATENODE_COMFY_CONFIG")
    for candidate in ([Path(env)] if env else []) + [LOCAL_CONFIG]:
        if candidate.is_file():
            with open(candidate, encoding="utf-8") as f:
                return Config.from_dict(json.load(f), str(candidate))
    return Config()
