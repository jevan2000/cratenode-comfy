"""Write docs/nodes.md: every CrateNode-Comfy node with its inputs, defaults and outputs,
from a running ComfyUI's /object_info (so it always matches the code).

    python tools/gen_node_docs.py [--server http://127.0.0.1:8195]
"""

from __future__ import annotations

import argparse
import json
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PREFIX = "CrateNode-Comfy"


def _type(spec) -> str:
    t = spec[0]
    if isinstance(t, list) or t == "COMBO":
        return "choice"
    return {"CN_SCENE": "scene", "CN_FILL": "fill", "CN_ROW": "data row", "CN_PALETTE": "palette"}.get(t, t.lower())


def _default(spec) -> str:
    opts = spec[1] if len(spec) > 1 else {}
    if "default" not in opts:
        return ""
    d = opts["default"]
    if isinstance(d, str):
        d = d.replace("\n", " / ")
        return f"`{d[:40]}{'…' if len(d) > 40 else ''}`" if d else '`""`'
    return f"`{json.dumps(d)}`"


def _cell(s: str) -> str:
    return (s or "").replace("|", "\\|").replace("\n", " ")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--server", default="http://127.0.0.1:8195")
    a = ap.parse_args()
    with urllib.request.urlopen(f"{a.server}/object_info", timeout=60) as r:
        info = json.loads(r.read())
    nodes = {k: v for k, v in info.items() if str(v.get("category", "")).startswith(PREFIX)}
    groups: dict[str, list] = {}
    for k, v in nodes.items():
        groups.setdefault(v["category"].split("/", 1)[-1], []).append((k, v))
    lines = ["# Node reference", "",
             f"All {len(nodes)} nodes, generated from the node definitions by `tools/gen_node_docs.py`.",
             "Types: *scene* is a design (`CN_SCENE`), *fill* a gradient, *data row* one CSV/JSON row, "
             "*palette* a named colour palette.", ""]
    lines += [f"- [{g}](#{g.lower().replace(' ', '-')})" for g in sorted(groups)] + [""]
    for g in sorted(groups):
        lines += [f"## {g}", ""]
        for k, v in sorted(groups[g], key=lambda kv: kv[1]["display_name"]):
            lines += [f"### {v['display_name']}", "", f"`{k}`. {_cell(v.get('description', ''))}", ""]
            req, opt = v["input"].get("required", {}), v["input"].get("optional", {})
            order = v.get("input_order") or {"required": list(req), "optional": list(opt)}
            rows = []
            for name in order.get("required", []) + order.get("optional", []):
                spec = req.get(name) or opt.get(name)
                if spec is None:
                    continue
                tip = (spec[1] if len(spec) > 1 else {}).get("tooltip", "")
                rows.append(f"| `{name}` | {_type(spec)}{' (optional)' if name in opt else ''} | "
                            f"{_default(spec)} | {_cell(tip)} |")
            if rows:
                lines += ["| Input | Type | Default | Notes |", "|---|---|---|---|"] + rows + [""]
            outs = [f"`{n}` ({_type([t])}{', list' if lst else ''})" for n, t, lst in
                    zip(v.get("output_name") or v["output"], v["output"],
                        v.get("output_is_list") or [False] * len(v["output"]))]
            if outs:
                lines += ["Outputs: " + ", ".join(outs), ""]
    (ROOT / "docs" / "nodes.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"docs/nodes.md: {len(nodes)} nodes in {len(groups)} groups")


if __name__ == "__main__":
    main()
