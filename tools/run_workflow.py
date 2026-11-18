"""Run an API-format workflow on a ComfyUI server headless and download its outputs.

    python tools/run_workflow.py examples/spike/scene_thumbnail.api.json
        [--server http://127.0.0.1:8195] [--out out/run] [--set 5.text="A longer title"]

- Images named by LoadImage nodes are uploaded from examples/assets first.
- ``--set NODE.INPUT=VALUE`` overrides an input (JSON values allowed: 120, true, "text").
- Outputs (images, and text such as saved PDF paths) are saved under --out, with
  ``run.json`` describing the run (prompt id, seconds, files).

Standard library only, so it runs with any Python.
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import time
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "examples" / "assets"


def http(method: str, url: str, data: bytes | None = None, headers: dict | None = None, timeout=60):
    req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def upload(server: str, path: Path) -> None:
    boundary = uuid.uuid4().hex
    ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    body = b"".join([
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"image\"; filename=\"{path.name}\"\r\n"
        f"Content-Type: {ctype}\r\n\r\n".encode(),
        path.read_bytes(),
        f"\r\n--{boundary}\r\nContent-Disposition: form-data; name=\"overwrite\"\r\n\r\ntrue\r\n--{boundary}--\r\n".encode(),
    ])
    http("POST", f"{server}/upload/image", body, {"Content-Type": f"multipart/form-data; boundary={boundary}"})


def apply_sets(wf: dict, sets: list[str]) -> None:
    for s in sets:
        target, _, raw = s.partition("=")
        node, _, inp = target.partition(".")
        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            value = raw
        if node not in wf:
            raise SystemExit(f"--set: no node {node!r} in the workflow")
        wf[node]["inputs"][inp] = value


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("workflow")
    ap.add_argument("--server", default="http://127.0.0.1:8195")
    ap.add_argument("--out", default=None)
    ap.add_argument("--set", action="append", default=[])
    ap.add_argument("--timeout", type=float, default=600)
    a = ap.parse_args()

    wf_path = Path(a.workflow)
    wf = json.loads(wf_path.read_text(encoding="utf-8"))
    apply_sets(wf, a.set)
    out = Path(a.out or ROOT / "out" / wf_path.stem)
    out.mkdir(parents=True, exist_ok=True)

    for node in wf.values():
        if node.get("class_type") == "LoadImage":
            asset = ASSETS / str(node["inputs"].get("image", ""))
            if asset.is_file():
                upload(a.server, asset)

    started = time.time()
    resp = json.loads(http("POST", f"{a.server}/prompt",
                           json.dumps({"prompt": wf, "client_id": uuid.uuid4().hex}).encode(),
                           {"Content-Type": "application/json"}))
    if resp.get("node_errors"):
        raise SystemExit(f"workflow rejected: {json.dumps(resp['node_errors'], indent=1)}")
    pid = resp["prompt_id"]
    while True:
        hist = json.loads(http("GET", f"{a.server}/history/{pid}")).get(pid)
        if hist and hist.get("status", {}).get("completed") is not None:
            break
        if time.time() - started > a.timeout:
            raise SystemExit(f"timed out after {a.timeout}s (prompt {pid})")
        time.sleep(0.25)
    seconds = round(time.time() - started, 2)
    status = hist["status"]
    files = []
    for node_id, outputs in hist.get("outputs", {}).items():
        for img in outputs.get("images", []):
            q = urllib.parse.urlencode({k: img[k] for k in ("filename", "subfolder", "type")})
            dest = out / f"{node_id}_{img['filename']}"
            dest.write_bytes(http("GET", f"{a.server}/view?{q}"))
            files.append(str(dest))
        for t in outputs.get("text", []):
            files.append(f"text from node {node_id}: {t}")
    report = {"prompt_id": pid, "ok": status.get("status_str") == "success", "seconds": seconds, "files": files}
    if not report["ok"]:
        report["messages"] = [m for m in status.get("messages", []) if m[0] == "execution_error"]
    (out / "run.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    if not report["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
