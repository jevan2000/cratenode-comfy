"""Where the smart helpers compute: CPU, or the GPU when a gate says it is free.

The GPU modes run plain tensor maths (no models). Before touching the card they ask
an optional GPU gate: any HTTP endpoint returning JSON with ``"ok": true|false`` (and
optionally ``"reasons"``). Set it with ``gpu_gate`` in the config or the
``CRATENODE_GPU_GATE`` environment variable. Without a gate the GPU is used when CUDA
is available. When the gate says no, the work runs on the CPU and the report says why.
"""

from __future__ import annotations

import json
import os
import urllib.request

MODES = ["cpu", "gpu when free"]


def gate_url(config=None) -> str:
    env = os.environ.get("CRATENODE_GPU_GATE", "").strip()
    if env:
        return env
    return (getattr(config, "gpu_gate", "") or "").strip()


def ask_gate(url: str, timeout: float = 3.0) -> tuple[bool, str]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            d = json.loads(r.read().decode("utf-8"))
    except Exception as e:  # an unreachable gate means "not cleared"
        return False, f"GPU gate unreachable ({type(e).__name__})"
    if d.get("ok"):
        return True, "GPU gate: ok"
    reasons = d.get("reasons") or []
    return False, "GPU gate said no: " + ("; ".join(map(str, reasons)) or "busy")


def pick(mode: str, config=None, cuda_available: bool | None = None, gate=ask_gate):
    """(torch.device, note). Never raises: falls back to the CPU."""
    import torch

    if mode != "gpu when free":
        return torch.device("cpu"), "cpu"
    if cuda_available is None:
        cuda_available = torch.cuda.is_available()
    if not cuda_available:
        return torch.device("cpu"), "cpu (no CUDA)"
    url = gate_url(config)
    if url:
        ok, why = gate(url)
        if not ok:
            return torch.device("cpu"), f"cpu ({why})"
    try:
        import comfy.model_management as mm  # inside ComfyUI: the card ComfyUI runs on

        dev = mm.get_torch_device()
    except Exception:
        dev = torch.device("cuda")
    return dev, f"gpu ({dev})"
