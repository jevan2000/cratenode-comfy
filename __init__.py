"""CrateNode-Comfy: a design suite of custom nodes for ComfyUI."""

import importlib.util as _util
import os as _os
import sys as _sys

# Say plainly what is missing (ComfyUI otherwise only reports "IMPORT FAILED").
_MISSING = [pkg for mod, pkg in (("skia", "skia-python"), ("pypdf", "pypdf"), ("numpy", "numpy"))
            if _util.find_spec(mod) is None]
if _MISSING:
    _req = _os.path.join(_os.path.dirname(__file__), "requirements.txt")
    raise ImportError(
        f"CrateNode-Comfy needs {', '.join(_MISSING)} in ComfyUI's Python. Install with:\n"
        f'    "{_sys.executable}" -m pip install -r "{_req}"\n'
        "then restart ComfyUI. (ComfyUI-Manager does this automatically when it installs the pack.)")

from .cratenode_comfy.extension import comfy_entrypoint  # noqa: F401,E402

WEB_DIRECTORY = "./web"  # live previews on the nodes (web/live_preview.js)
