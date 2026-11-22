<#
.SYNOPSIS
  Run the automated test suite (database, API, external-integration and browser tests).
.DESCRIPTION
  Uses TEST_DATABASE_URL from .env (a separate database that is created and
  re-seeded automatically). Requires: scripts\setup.ps1 -Dev
.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\test.ps1            # everything
  powershell -ExecutionPolicy Bypass -File scripts\test.ps1 -NoBrowser # skip Playwright tests
#>
param([switch]$NoBrowser)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$venvPy = Join-Path $Root ".venv\Scripts\python.exe"
if ($NoBrowser) { & $venvPy -m pytest -m "not e2e" } else { & $venvPy -m pytest }
exit $LASTEXITCODE
