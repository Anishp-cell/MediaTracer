# Start the MediaTrace API on http://127.0.0.1:8000 using the project virtual environment.
# Usage (from the repository root):  .\scripts\start-backend.ps1 [-Reload]
param([switch]$Reload)

$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    Write-Error "Virtual environment not found at $python. See README.md > Installation."
    exit 1
}
# Local-first: when the model is already in the Hugging Face cache, run fully offline
# (otherwise huggingface_hub checks the Hub for a newer model revision at load time).
$hfHome = if ($env:HF_HOME) { $env:HF_HOME } else { Join-Path $env:USERPROFILE ".cache\huggingface" }
$snapshots = Join-Path $hfHome "hub\models--google--embeddinggemma-2\snapshots"
if (-not $env:HF_HUB_OFFLINE -and (Test-Path $snapshots) -and (Get-ChildItem $snapshots -Directory).Count -gt 0) {
    $env:HF_HUB_OFFLINE = "1"
    Write-Host "Model found in local cache - running offline (HF_HUB_OFFLINE=1)."
} elseif (-not $env:HF_HUB_OFFLINE) {
    Write-Host "Model not cached yet - it will be downloaded once from Hugging Face (~1.5 GB)."
}
$uvicornArgs = @("-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000")
if ($Reload) { $uvicornArgs += @("--reload", "--reload-dir", "app") }
Push-Location (Join-Path $root "backend")
try {
    & $python @uvicornArgs
} finally {
    Pop-Location
}
