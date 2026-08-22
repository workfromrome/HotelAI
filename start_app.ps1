# Avvia il backend FastAPI e il frontend React/Vite in due finestre separate,
# poi apre il browser sull'app. Chiudere le due finestre per fermare l'app.

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$venvPython = Join-Path $root ".venv\Scripts\python.exe"

Write-Host "==> Avvio HotelAI" -ForegroundColor Cyan

if (-not (Test-Path $venvPython)) {
    Write-Host "Ambiente virtuale non trovato in .venv. Eseguire prima il setup (vedi README.md)." -ForegroundColor Red
    Read-Host "Premere INVIO per chiudere"
    exit 1
}

if (-not (Test-Path (Join-Path $root "frontend\node_modules"))) {
    Write-Host "Dipendenze frontend non installate. Eseguo 'npm install'..." -ForegroundColor Yellow
    Push-Location (Join-Path $root "frontend")
    npm install
    Pop-Location
}

Write-Host "==> Avvio backend (http://localhost:8000)..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList @(
    "-NoExit", "-Command",
    "cd `"$root`"; `$env:PYTHONPATH = 'src'; & `"$venvPython`" -m uvicorn api.main:app --reload --reload-dir src --port 8000"
) -WindowStyle Normal

Write-Host "==> Avvio frontend (http://localhost:5173)..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList @(
    "-NoExit", "-Command",
    "cd `"$root\frontend`"; npm run dev"
) -WindowStyle Normal

Write-Host "==> Attendo che il backend risponda..." -ForegroundColor Cyan
$ready = $false
for ($i = 0; $i -lt 30; $i++) {
    Start-Sleep -Seconds 1
    try {
        $resp = Invoke-WebRequest -Uri "http://localhost:8000/api/health" -UseBasicParsing -TimeoutSec 2
        if ($resp.StatusCode -eq 200) { $ready = $true; break }
    } catch {}
}

if ($ready) {
    Write-Host "==> Backend pronto. Apro il browser..." -ForegroundColor Green
} else {
    Write-Host "==> Il backend non ha risposto entro 30s, apro comunque il browser (potrebbe servire qualche secondo in piu)." -ForegroundColor Yellow
}

Start-Sleep -Seconds 2
Start-Process "http://localhost:5173"

Write-Host ""
Write-Host "App avviata! Due finestre PowerShell sono ora attive (backend e frontend)." -ForegroundColor Green
Write-Host "Per fermare l'app, chiudere semplicemente quelle due finestre." -ForegroundColor Green
