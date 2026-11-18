# Security

## What the pack can touch

Workflows are often shared, so CrateNode-Comfy limits what a workflow can make it do:

- **Reading files:** Data Rows, Load Template and Brand Kit read only from your data
  folder (`data_dir`), ComfyUI's `input` folder, this package, and folders you list
  in `data_roots` in the config. Anything else is refused, including through `..`
  or symlinks.
- **Writing files:** every save node writes inside ComfyUI's `output` folder
  (Save as Template may also write to `data_dir/templates`). Names taken from data
  rows are cleaned, so a value can't add folders.
- **Network:** Copy Writer talks to an Ollama server on this machine only, unless you
  add its host to `allowed_hosts`. The optional GPU gate URL comes only from your
  config or the `CRATENODE_GPU_GATE` environment variable, never from a workflow.
- **Programs:** ffmpeg is run with an argument list (no shell). Templates are plain
  JSON read into known types (no pickle, no code).
- **Live previews:** `/cratenode/preview` renders only the listed design nodes from
  plain values, with size limits. It is served by ComfyUI, so it is reachable where
  ComfyUI is (by default only this machine).
- **Metadata:** Export Image embeds the workflow in PNG and WebP files, as ComfyUI's
  Save Image does. Turn `embed_workflow` off for files you share if the workflow
  holds anything private (prompts, file names).

Nothing private belongs in this repository: no licensed fonts or colour profiles,
no client assets, no tokens. Your fonts, templates, brand kits and profiles live in
folders you configure (`config.local.json` is git-ignored).

## Reporting a problem

Please report security issues privately through GitHub's "Report a vulnerability"
(Security tab of the repository) rather than in a public issue.
