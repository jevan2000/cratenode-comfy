# Copy this checkout into a ComfyUI custom_nodes folder.
#   .\tools\install_sandbox.ps1 -ComfyRoot D:\ComfyUI -Python D:\ComfyUI\venv\Scripts\python.exe
# Defaults come from the environment variables COMFYUI_ROOT and COMFYUI_PYTHON.
# Copies, never links, so a half-edited checkout can't break a running ComfyUI.
# Restart ComfyUI afterwards (only when it is idle).
param(
  [string]$ComfyRoot = $env:COMFYUI_ROOT,
  [string]$Python = $env:COMFYUI_PYTHON
)
$ErrorActionPreference = 'Stop'
if (-not $ComfyRoot -or -not $Python) { throw "give -ComfyRoot and -Python, or set COMFYUI_ROOT and COMFYUI_PYTHON" }
$src = Split-Path -Parent $PSScriptRoot
$dst = Join-Path $ComfyRoot "custom_nodes\cratenode-comfy"
robocopy $src $dst /MIR /XD .git out __pycache__ .pytest_cache /XF *.pyc /NFL /NDL /NJH /NJS | Out-Null
if ($LASTEXITCODE -ge 8) { throw "robocopy failed ($LASTEXITCODE)" }
# skia's Paragraph looks for ICU data next to the base python.exe (venvs share it).
$base = & $Python -c "import sys; print(sys.base_prefix)"
$icu = Join-Path $base "icudtl.dat"
if (-not (Test-Path $icu)) {
  $site = & $Python -c "import sysconfig; print(sysconfig.get_paths()['purelib'])"
  Copy-Item (Join-Path $site "icudtl.dat") $icu
  "copied icudtl.dat to $base"
}
# The example workflows' Load Image / Load Video nodes read these from ComfyUI's input folder.
$inputDir = Join-Path $ComfyRoot "input"  # not $input: that name is reserved in PowerShell
if (Test-Path $inputDir) {
  Get-ChildItem (Join-Path $src "api_examples\assets") -File | ForEach-Object {
    $t = Join-Path $inputDir $_.Name
    if (-not (Test-Path $t)) { Copy-Item $_.FullName $t }
  }
}
"installed to $dst"
