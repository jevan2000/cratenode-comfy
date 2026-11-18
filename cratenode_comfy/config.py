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


@dataclass
class Config:
    font_folders: list[Path] = field(default_factory=list)
    font_catalogs: list[Path] = field(default_factory=list)
    system_fonts: bool = True
    data_dir: Path | None = None
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
            source=source,
        )


def load() -> Config:
    env = os.environ.get("CRATENODE_COMFY_CONFIG")
    for candidate in ([Path(env)] if env else []) + [LOCAL_CONFIG]:
        if candidate.is_file():
            with open(candidate, encoding="utf-8") as f:
                return Config.from_dict(json.load(f), str(candidate))
    return Config()
