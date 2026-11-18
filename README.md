# CrateNode-Comfy

A design suite for ComfyUI: typography, layout, shapes, effects, templates,
data-driven batches, motion and print output, as custom nodes that sit next to
your image-generation nodes.

**Status: early development.** See [docs/plan.md](docs/plan.md).

## Install (development)

Copy this folder into `ComfyUI/custom_nodes/cratenode-comfy` and install the
requirements into ComfyUI's Python:

```
python -m pip install -r requirements.txt
```

Restart ComfyUI. The nodes appear under **CrateNode-Comfy** in the node menu.

## Configuration

Fonts, private templates and brand kits are read from folders you configure, so
licensed material never has to live inside this package. See
`cratenode_comfy/config.py`.

## Licence

MIT. See [LICENSE](LICENSE). Bundled example fonts are under the SIL Open Font
License (see `fonts/`).
