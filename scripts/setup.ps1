<#
.SYNOPSIS
  One-time setup for the Intelligent Route Planning System on Windows.

.DESCRIPTION
  1. Creates a Python virtual environment in .venv and installs dependencies.
  2. Creates .env from .env.example with a freshly generated SECRET_KEY (if .env is missing).
  3. Starts the PostgreSQL container with Docker Compose (unless -SkipDocker is given).
  4. Creates and initialises the application database (schema, seed data, ten views).

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
  powershell -ExecutionPolicy Bypass -File scripts\setup.ps1 -SkipDocker   # using your own PostgreSQL
  powershell -ExecutionPolicy Bypass -File scripts\setup.ps1 -Dev          # also install test tools
#>
param(
    [switch]$SkipDocker,
    [switch]$Dev
)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

function Step($msg) { Write-Host "`n==> $msg" -ForegroundColor Cyan }

Step "Checking Python"
$py = Get-Command py -ErrorAction SilentlyContinue
if ($py) { $pyExe = "py"; $pyArgs = @("-3") } else { $pyExe = "python"; $pyArgs = @() }
& $pyExe @pyArgs --version
if ($LASTEXITCODE -ne 0) { throw "Python 3.10+ is required (https://www.python.org/downloads/)." }

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Step "Creating virtual environment (.venv)"
    & $pyExe @pyArgs -m venv .venv
}
$venvPy = Join-Path $Root ".venv\Scripts\python.exe"

Step "Installing Python dependencies"
& $venvPy -m pip install --upgrade pip --quiet
if ($Dev) { & $venvPy -m pip install -r requirements-dev.txt --quiet } else { & $venvPy -m pip install -r requirements.txt --quiet }
if ($LASTEXITCODE -ne 0) { throw "pip install failed." }
if ($Dev) {
    Step "Installing Chromium for Playwright browser tests"
    & $venvPy -m playwright install chromium
}

if (-not (Test-Path ".env")) {
    Step "Creating .env from .env.example"
    $secret = & $venvPy -c "import secrets; print(secrets.token_hex(32))"
    (Get-Content ".env.example") -replace '^SECRET_KEY=.*', "SECRET_KEY=$secret" | Set-Content ".env" -Encoding utf8
} else {
    Write-Host ".env already exists - leaving it unchanged."
}

if (-not $SkipDocker) {
    Step "Starting PostgreSQL with Docker Compose"
    $docker = Get-Command docker -ErrorAction SilentlyContinue
    if (-not $docker) { throw "Docker was not found. Install Docker Desktop, or re-run with -SkipDocker and set DATABASE_URL in .env to your own PostgreSQL." }
    docker compose up -d
    if ($LASTEXITCODE -ne 0) { throw "docker compose failed. Is Docker Desktop running?" }
    Write-Host "Waiting for PostgreSQL to accept connections..."
    for ($i = 0; $i -lt 30; $i++) {
        $state = docker inspect --format "{{.State.Health.Status}}" route-planner-db 2>$null
        if ($state -eq "healthy") { break }
        Start-Sleep -Seconds 2
    }
}

Step "Initialising the database (schema, seed data, ten views)"
& $venvPy scripts\init_db.py
if ($LASTEXITCODE -ne 0) { throw "Database initialisation failed - check DATABASE_URL in .env." }

Write-Host "`nSetup complete. Start the app with:  powershell -ExecutionPolicy Bypass -File scripts\run.ps1" -ForegroundColor Green
