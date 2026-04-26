#!/usr/bin/env pwsh
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

function Resolve-PythonInvocation {
    $launcher = Get-Command py -ErrorAction SilentlyContinue
    if ($launcher) {
        return @{ Exe = $launcher.Source; Args = @("-3") }
    }

    $candidates = @(Get-Command python -All -ErrorAction SilentlyContinue)
    foreach ($candidate in $candidates) {
        if ($candidate.Source -like "*MySQL*") { continue }
        return @{ Exe = $candidate.Source; Args = @() }
    }

    return $null
}

$Python = Resolve-PythonInvocation
if (-not $Python) {
    [Console]::Error.WriteLine("Error: a usable Python 3 was not found on PATH.")
    [Console]::Error.WriteLine("Install Python from https://www.python.org/downloads/ (which provides the 'py' launcher),")
    [Console]::Error.WriteLine("or ensure a real python.exe is on PATH (the MySQL Shell bundled python.exe is not usable).")
    exit 1
}

if (-not (Test-Path "requirements.txt")) {
    [Console]::Error.WriteLine("Error: requirements.txt not found in $ScriptDir")
    exit 1
}

$VenvPython = Join-Path $ScriptDir ".venv\Scripts\python.exe"

if (-not (Test-Path ".venv")) {
    Write-Host "[setup] Creating virtual environment..."
    & $Python.Exe @($Python.Args) -m venv .venv
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

    Write-Host "[setup] Upgrading pip..."
    & $VenvPython -m pip install --upgrade pip
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

    Write-Host "[setup] Installing dependencies..."
    & $VenvPython -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

if (-not $env:TCL_LIBRARY -or -not $env:TK_LIBRARY) {
    $BasePrefix = & $VenvPython -c "import sys; print(sys.base_prefix)"
    if ($LASTEXITCODE -eq 0 -and $BasePrefix) {
        $TclDir = Join-Path $BasePrefix "tcl\tcl8.6"
        $TkDir = Join-Path $BasePrefix "tcl\tk8.6"
        if ((Test-Path (Join-Path $TclDir "init.tcl")) -and (Test-Path (Join-Path $TkDir "tk.tcl"))) {
            if (-not $env:TCL_LIBRARY) { $env:TCL_LIBRARY = $TclDir }
            if (-not $env:TK_LIBRARY) { $env:TK_LIBRARY = $TkDir }
        }
    }
}

Write-Host "[run] Launching PMCompare UI..."
& $VenvPython pm_compare.py --ui
exit $LASTEXITCODE
