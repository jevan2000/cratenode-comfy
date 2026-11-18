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
    data_roots: list[Path] = field(default_factory=list)  # extra folders Data Rows / Load Template may read
    allowed_hosts: list[str] = field(default_factory=list)  # extra hosts Copy Writer may call (loopback always)
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
            data_roots=paths("data_roots"),
            allowed_hosts=[str(h).strip().lower() for h in d.get("allowed_hosts", []) if str(h).strip()],
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

    def resolve_data_path(self, p: str, extra_roots: list | None = None) -> Path:
        """A file a workflow asked to read: as given, or relative to data_dir. Only files
        inside the data folder, the package, ComfyUI's input folder (``extra_roots``) or
        ``data_roots`` from the config are allowed, so a workflow shared by someone else
        can't read files elsewhere on the machine."""
        path = Path(p.strip().strip('"'))
        if not path.is_absolute() and self.data_dir and (self.data_dir / path).exists():
            path = self.data_dir / path
        roots = self.read_roots(extra_roots)
        real = Path(os.path.realpath(path))
        if not any(_inside(real, r) for r in roots):
            raise PermissionError(
                f"{path} is outside the folders workflows may read ({', '.join(str(r) for r in roots)}). "
                f"Move the file there, or add its folder to data_roots in the CrateNode-Comfy config.")
        return path

    def read_roots(self, extra_roots: list | None = None) -> list[Path]:
        roots = ([self.data_dir] if self.data_dir else []) + [PACKAGE_ROOT] + list(self.data_roots)
        return [Path(os.path.realpath(r)) for r in roots + list(extra_roots or [])]


def _inside(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def load() -> Config:
    env = os.environ.get("CRATENODE_COMFY_CONFIG")
    for candidate in ([Path(env)] if env else []) + [LOCAL_CONFIG]:
        if candidate.is_file():
            with open(candidate, encoding="utf-8") as f:
                return Config.from_dict(json.load(f), str(candidate))
    return Config()
