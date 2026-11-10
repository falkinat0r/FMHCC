# HCC QA-Pipeline (R1, Agent 5) -- Windows-Spiegel von run-qa.sh.
#
# Aufruf:
#   powershell -ExecutionPolicy Bypass -File scripts\qa\run-qa.ps1
#
# Exit-Code: 0 = alle Gates bestanden, 1 = FAILED, 2 = nur BLOCKED.
# Siehe run-qa.sh fuer die Gate-Definition und die BLOCKED-Semantik.
#
# HINWEIS: Diese Datei muss ASCII-only bleiben: Windows PowerShell 5.1
# dekodiert BOM-loese UTF-8-Dateien als cp1252, und z. B. der Em-Dash
# (Byte 0x94 = Recht-Quote) wuerde Strings aufbrechen (Parser-Error).
#
# PS-5.1-Fallen, die dieses Skript vermeidet:
# - Niemals `exit` in einem per `&`-aufruf ausgefuehrten Scriptblock
#   (beendet das ganze Eltern-Skript) -- Logik-Gates schreiben daher
#   $script:GateResultCode.
# - Operatorenpraesedenz: `-not A -contains B` wird als
#   `(-not A) -contains B` gelesen -- Klammern setzen wir explizit.

$ErrorActionPreference = "SilentlyContinue"
$Root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Set-Location $Root

$FailedGates = [System.Collections.Generic.List[string]]::new()
$BlockedGates = [System.Collections.Generic.List[string]]::new()
$script:GateResultCode = $null

function Invoke-Gate {
    param(
        [string]$Name,
        [scriptblock]$Script,
        [switch]$BlockedOnCode2
    )
    Write-Host ""
    Write-Host "==> GATE: $Name"
    $script:GateResultCode = $null
    & $Script
    $rc = $LASTEXITCODE
    if ($null -ne $script:GateResultCode) {
        $rc = [int]$script:GateResultCode
        $script:GateResultCode = $null
    }
    if ($rc -eq 0) {
        Write-Host "    GATE OK: $Name"
    }
    elseif ($rc -eq 2 -and $BlockedOnCode2) {
        Write-Host "    GATE BLOCKED (keine belastbare Aussage): $Name"
        $BlockedGates.Add($Name)
    }
    else {
        Write-Host "    GATE FAILED: $Name (exit $rc)"
        $FailedGates.Add($Name)
    }
}

function Get-PythonCmd {
    # uv-Venv bevorzugt (reproduzierbar), dann System-Python.
    # Immer ein echtes Array rueckgeben (Komma operiert: verhindert
    # das Aufrollen eines 1-elementigen Arrays zu einer String).
    $uv = Get-Command uv -ErrorAction SilentlyContinue
    if ($uv) {
        return , @("uv", "run", "--project", "backend", "python")
    }
    foreach ($c in @("python3", "python")) {
        if (Get-Command $c -ErrorAction SilentlyContinue) { return , @($c) }
    }
    return $null
}

$PyCmd = Get-PythonCmd

function Invoke-Python {
    # PS-5.1-Falle: `& $Array` als Kommando funktioniert nicht --
    # daher explizit: erst-Element als Kommando, Rest als Argumente.
    param([string[]]$ExtraArgs)
    & $PyCmd[0] @($PyCmd[1..($PyCmd.Count - 1)]) @ExtraArgs
}

# --- Gate 1: Secret-Scan ---------------------------------------------------------
if ($PyCmd) {
    Invoke-Gate -Name "Secret-Scan" -Script {
        Invoke-Python -ExtraArgs @("scripts/qa/scan_secrets.py")
    }
} else {
    Write-Host "==> GATE: Secret-Scan"
    Write-Host "    GATE BLOCKED: kein Python gefunden"
    $BlockedGates.Add("Secret-Scan")
}

# --- Gates 2-5: Backend + OpenAPI + QA-Suite -------------------------------------
$uv = Get-Command uv -ErrorAction SilentlyContinue
if ($uv) {
    Invoke-Gate -Name "Backend-Lint (ruff)" -Script {
        uv run --project backend ruff check backend
    }
    Invoke-Gate -Name "Backend-Unit-Tests (pytest)" -Script {
        uv run --project backend python -m pytest backend -q
    }
    Invoke-Gate -Name "OpenAPI-Drift (Contract-Snapshot)" -BlockedOnCode2 -Script {
        uv run --project backend python scripts/qa/check_openapi_drift.py
    }
    Invoke-Gate -Name "QA-Suite (pytest tests/)" -Script {
        uv run --project backend python -m pytest tests -q
    }
} else {
    foreach ($g in @(
        "Backend-Lint (ruff)",
        "Backend-Unit-Tests (pytest)",
        "OpenAPI-Drift (Contract-Snapshot)",
        "QA-Suite (pytest tests/)"
    )) {
        Write-Host "==> GATE: $g"
        Write-Host "    GATE BLOCKED: uv nicht installiert"
        $BlockedGates.Add($g)
    }
}

# --- Gate 6: Frontend (Node.js) ------------------------------------------------------
# Lokale Node-Installation (tools/) oder HCC_NODE_BIN oder PATH.
$NodeDir = $env:HCC_NODE_BIN
if (-not $NodeDir) {
    $candidates = Get-ChildItem -Path (Join-Path $Root "tools") -Filter "node-*" -Directory -ErrorAction SilentlyContinue
    if ($candidates) { $NodeDir = $candidates[0].FullName }
}
if ($NodeDir -and -not ($env:PATH.Split(";") -contains $NodeDir)) {
    $env:PATH = "$NodeDir;$env:PATH"
}
$node = Get-Command node -ErrorAction SilentlyContinue
$npm  = Get-Command npm  -ErrorAction SilentlyContinue
if ($node -and $npm) {
    Invoke-Gate -Name "Frontend-Typecheck (tsc)" -Script {
        Set-Location (Join-Path $Root "frontend")
        npx tsc -b --noEmit
    }
    Invoke-Gate -Name "Frontend-Build (vite)" -Script {
        Set-Location (Join-Path $Root "frontend")
        npm run build
    }
    Invoke-Gate -Name "Frontend-Tests (vitest)" -Script {
        Set-Location (Join-Path $Root "frontend")
        npx vitest run
    }
    Invoke-Gate -Name "Frontend-Lint (eslint)" -Script {
        Set-Location (Join-Path $Root "frontend")
        npm run lint
    }
} else {
    Write-Host "==> GATE: Frontend (tsc/build/vitest/lint)"
    Write-Host "    GATE BLOCKED: node/npm nicht installiert (HCC_NODE_BIN setzen?)"
    $BlockedGates.Add("Frontend (tsc/build/vitest/lint)")
}
Set-Location $Root

# --- Gate 7: Dependency-Audits (Netzwerk) ---------------------------------------------
# Semantik: 0=clean, 1=vulnerable, 2=blocked (Netzwerk/Tool-Fehler).
# Ein Audit ohne belastbares Ergebnis ist NICHT gruen (R1-Regel).
if ($uv) {
    Invoke-Gate -Name "Dependency-Audit (Python, uv audit)" -BlockedOnCode2 -Script {
        $out = (& uv audit --project backend 2>&1 | Out-String)
        $nativeRc = $LASTEXITCODE
        Write-Host $out
        if ($nativeRc -eq 0) {
            $script:GateResultCode = 0
            return
        }
        if ($out -match "(?i)(cve-|vulnerab)") {
            $script:GateResultCode = 1
            return
        }
        Write-Host "    (Audit-Ausfuehrung fehlgeschlagen -- als BLOCKED gewertet)"
        $script:GateResultCode = 2
    }
} else {
    Write-Host "==> GATE: Dependency-Audit (Python, uv audit)"
    Write-Host "    GATE BLOCKED: uv nicht installiert"
    $BlockedGates.Add("Dependency-Audit (Python, uv audit)")
}
if ($npm) {
    Invoke-Gate -Name "Dependency-Audit (npm, prod-Abhaengigkeiten)" -BlockedOnCode2 -Script {
        Set-Location (Join-Path $Root "frontend")
        $out = (& npm audit --omit=dev 2>&1 | Out-String)
        $nativeRc = $LASTEXITCODE
        Set-Location $Root
        Write-Host $out
        if ($nativeRc -eq 0) {
            $script:GateResultCode = 0
            return
        }
        if ($nativeRc -eq 1) {
            $script:GateResultCode = 1
            return
        }
        $script:GateResultCode = 2
    }
} else {
    Write-Host "==> GATE: Dependency-Audit (npm, prod-Abhaengigkeiten)"
    Write-Host "    GATE BLOCKED: npm nicht installiert"
    $BlockedGates.Add("Dependency-Audit (npm, prod-Abhaengigkeiten)")
}

# --- Gate 8: Deploy-Invarianten ----------------------------------------------------------
Invoke-Gate -Name "Deploy-Invarianten (systemd/nginx/deploy-lxc.sh)" -BlockedOnCode2 -Script {
    if ($null -eq $PyCmd) {
        $script:GateResultCode = 2
        return
    }
    Invoke-Python -ExtraArgs @("scripts/qa/check_deploy_artifacts.py")
    $script:GateResultCode = $LASTEXITCODE
}

# --- Fazit -------------------------------------------------------------------------------
Write-Host ""
Write-Host "================================================================"
if ($FailedGates.Count -gt 0) {
    Write-Host "Fazit: FAILED -- $($FailedGates.Count) Gate(s) bestanden nicht:"
    $FailedGates | ForEach-Object { Write-Host "  - $_" }
    Write-Host "Exit 1"
    exit 1
}
if ($BlockedGates.Count -gt 0) {
    Write-Host "Fazit: GREEN-MIT-RESERVE -- $($BlockedGates.Count) Gate(s) BLOCKED:"
    $BlockedGates | ForEach-Object { Write-Host "  - $_" }
    Write-Host "Exit 2"
    exit 2
}
Write-Host "Fazit: ALLE GATES BESTANDEN. Exit 0"
exit 0
