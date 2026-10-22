# Start the MediaTrace web UI on http://localhost:5173 (proxies /api to the backend on port 8000).
# Usage (from the repository root):  .\scripts\start-frontend.ps1
$root = Split-Path -Parent $PSScriptRoot
Push-Location (Join-Path $root "frontend")
try {
    if (-not (Test-Path "node_modules")) { npm install }
    npm run dev
} finally {
    Pop-Location
}
