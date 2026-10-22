# Index the demo corpus into the running MediaTrace backend (files are indexed in place, never copied or modified).
# Usage (from the repository root, with the backend running):  .\scripts\seed-demo.ps1
# Build the corpus first if needed:  .\.venv\Scripts\python scripts\make_demo_corpus.py
param([string]$Api = "http://127.0.0.1:8000/api")

$root = Split-Path -Parent $PSScriptRoot
$corpus = Join-Path $root "data\demo_corpus"
if (-not (Test-Path $corpus)) {
    Write-Error "Demo corpus not found at $corpus. Run: .\.venv\Scripts\python scripts\make_demo_corpus.py"
    exit 1
}

Write-Host "Waiting for the embedding model..."
do {
    try { $health = Invoke-RestMethod "$Api/health" -TimeoutSec 5 } catch { $health = $null }
    if ($health -and $health.model.state -eq "error") { Write-Error "Model failed to load: $($health.model.error)"; exit 1 }
    if (-not $health -or $health.model.state -ne "ready") { Start-Sleep -Seconds 2 }
} until ($health -and $health.model.state -eq "ready")
Write-Host "Model ready on $($health.model.device) ($($health.model.dtype)); modalities: $($health.model.modalities -join ', ')"

$body = @{ paths = @($corpus); recursive = $true } | ConvertTo-Json
$reg = Invoke-RestMethod "$Api/index/local" -Method Post -ContentType "application/json" -Body $body
$files = @($reg.files)
foreach ($group in ($files | Group-Object action)) { Write-Host ("  {0,-10} {1}" -f $group.Name, $group.Count) }
if (-not $reg.job_id) { Write-Host "Nothing new to index (all files unchanged)."; exit 0 }

do {
    Start-Sleep -Milliseconds 800
    $job = Invoke-RestMethod "$Api/jobs/$($reg.job_id)"
    Write-Host ("`r  {0,3:N0}%  {1}" -f ($job.progress * 100), $job.message) -NoNewline
} while ($job.status -in @("queued", "running"))
Write-Host ""
Write-Host "Job $($job.status): $($job.message)"
foreach ($e in @($job.errors)) { if ($e) { Write-Warning "$($e.filename): $($e.error)" } }
