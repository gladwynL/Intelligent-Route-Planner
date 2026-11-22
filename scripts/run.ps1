<#
.SYNOPSIS
  Start the Intelligent Route Planning System at http://127.0.0.1:8000
.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\run.ps1
#>
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$venvPy = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPy)) { throw "Run scripts\setup.ps1 first (virtual environment not found)." }
& $venvPy run.py
