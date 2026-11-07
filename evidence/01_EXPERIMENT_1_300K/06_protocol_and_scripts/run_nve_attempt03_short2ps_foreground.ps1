#Requires -Version 5.1
<#
.SYNOPSIS
    Foreground runner for Pass 09A short NVE diagnostic (Attempt 03, 2 ps).
.DESCRIPTION
    Runs the amended 2 ps / 2,000-step NVE diagnostic from the accepted 08ARRR
    NPT state in an interactive PowerShell foreground session. Uses conda run
    with the same relative-path method as the final NPT continuation.

    IMPORTANT:
    - Intended to be run directly by the user in an interactive PowerShell window.
    - Blocks until SPONGE exits.
    - Never deletes existing attempt evidence.
    - Intermediate 1,000-step restart archival is intentionally NOT performed;
      only the final 2,000-step restart is required for this short stability
      diagnostic.
    - Classifies only NVE_ATTEMPT_03_COMPLETED_SHORT_DIAGNOSTIC_OUTPUT_CONTRACT_PASS
      on success; full scientific acceptance is reviewed separately after analysis.
    - This 2 ps diagnostic is NOT equivalent to the original 20 ps NVE diagnostic.
#>

[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"

# ---------------------------------------------------------------------------
# Paths and frozen constants from the runtime amendment
# ---------------------------------------------------------------------------
$passRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$inputRaw     = Join-Path $passRoot "input_raw"
$inputRestart = Join-Path $passRoot "input_restart"
$runDir       = Join-Path $passRoot "run"
$attemptDir   = Join-Path $runDir "attempt_03_short2ps"
$condaRoot    = "C:\Users\Acer\miniconda3"
$condaExe     = Join-Path $condaRoot "Scripts\conda.exe"

$coordIn = Join-Path $inputRestart "accepted_npt_coordinate.txt"
$velIn   = Join-Path $inputRestart "accepted_npt_velocity.txt"

$expectedCoordHash = "b43cc97c3d2006be7e43d60e78cdc17694e92a295916051ade88f0db88ffa076"
$expectedVelHash   = "2220f704411c99b0e5bc6fa621b19efbc13691481e08a099f909fd34ccfe8cf2"

$ACCEPTED_BOX = @(29.9968719, 29.9968643, 29.9968872, 90.0, 90.0, 90.0)
$ATOM_COUNT = 2586
$DT_PS = 0.001
$STEP_LIMIT = 2000
$INFO_INTERVAL = 50
$TRAJ_INTERVAL = 200
$RST_INTERVAL = 1000
$EXPECTED_MDOUT_RECORDS = 40
$EXPECTED_TRAJ_FRAMES = 10
$EXPECTED_FINAL_STEP = 2000
$EXPECTED_FINAL_TIME_PS = 24.62
$START_TIME_PS = 22.62

$TRJ_BYTES_PER_FRAME = $ATOM_COUNT * 3 * 4  # 31032

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
function Get-FileSha256 {
    param([string]$Path)
    $stream = [System.IO.File]::OpenRead($Path)
    try {
        $sha = [System.Security.Cryptography.SHA256]::Create()
        $bytes = $sha.ComputeHash($stream)
        return ([BitConverter]::ToString($bytes) -replace "-", "").ToLower()
    }
    finally {
        $stream.Dispose()
    }
}

function Test-ProcessRunning {
    param([string]$Name)
    return (Get-Process -Name $Name -ErrorAction SilentlyContinue) -ne $null
}

function Test-ContainsNaNInf {
    param([string]$Path)
    if (-not (Test-Path $Path)) { return }
    $text = Get-Content -Raw -Path $Path -ErrorAction SilentlyContinue
    if ($text -match "\bNaN\b|\bInf\b|\bInfinity\b|\bnan\b|\binf\b") {
        throw "Found NaN/Inf in $Path"
    }
}

function Get-NonEmptyLines {
    param([string]$Path)
    if (-not (Test-Path $Path)) { return @() }
    return (Get-Content -Path $Path) | Where-Object { $_.Trim() -ne "" }
}

function Get-MdoutRecords {
    param([string]$Path)
    try {
        $records = (Get-Content -Path $Path -ErrorAction SilentlyContinue) | Where-Object { $_ -match '^\s*\d+\s+[0-9.]+\s+[-+0-9.eE]+' }
        return $records
    }
    catch {
        return @()
    }
}

function Get-MdoutRecordCount {
    param([string]$Path)
    return (Get-MdoutRecords -Path $Path).Count
}

function Get-MdoutLastStep {
    param([string]$Path)
    $records = Get-MdoutRecords -Path $Path
    if ($records.Count -eq 0) { return -1 }
    if ($records[$records.Count - 1] -match '^\s*(\d+)') {
        return [int]$Matches[1]
    }
    return -1
}

function Get-MdoutLastTime {
    param([string]$Path)
    $records = Get-MdoutRecords -Path $Path
    if ($records.Count -eq 0) { return $null }
    if ($records[$records.Count - 1] -match '^\s*\d+\s+([0-9.]+)') {
        return [double]$Matches[1]
    }
    return $null
}

function Test-ApproxEqual {
    param([double]$Actual, [double]$Expected, [double]$Tolerance = 1e-4)
    return [math]::Abs($Actual - $Expected) -le $Tolerance
}

function Test-BoxConsistent {
    param([string]$BoxLine, [double]$Tolerance = 1e-4)
    $parts = $BoxLine.Trim() -split '\s+' | ForEach-Object { [double]$_ }
    if ($parts.Count -ne 6) { return $false }
    for ($i = 0; $i -lt 6; $i++) {
        if (-not (Test-ApproxEqual -Actual $parts[$i] -Expected $ACCEPTED_BOX[$i] -Tolerance $Tolerance)) {
            return $false
        }
    }
    return $true
}

function Get-LastLine {
    param([string]$Path)
    $lines = Get-NonEmptyLines -Path $Path
    if ($lines.Count -eq 0) { return $null }
    return $lines[$lines.Count - 1]
}

function Get-RestartHeaderParts {
    param([string]$Path)
    $first = Get-Content -TotalCount 1 -Path $Path
    $parts = $first.Trim() -split '\s+'
    return @{
        atom_count = [int]$parts[0]
        time_ps    = [double]$parts[1]
        label      = [int]$parts[2]
        raw        = $first.Trim()
    }
}

function Get-HashManifest {
    param([string]$Dir)
    $manifest = @{}
    foreach ($f in (Get-ChildItem -Path $Dir -File)) {
        $manifest[$f.Name] = Get-FileSha256 -Path $f.FullName
    }
    return $manifest
}

# ---------------------------------------------------------------------------
# 1. Attempt directory must be empty or non-existent; never delete evidence
# ---------------------------------------------------------------------------
if (Test-Path $attemptDir) {
    $existing = Get-ChildItem -Path $attemptDir -Recurse -Force
    if ($existing.Count -gt 0) {
        throw "ATTEMPT_03_DIRECTORY_NOT_EMPTY_NO_RUN_LAUNCHED: $attemptDir contains $($existing.Count) item(s)."
    }
}
else {
    New-Item -ItemType Directory -Path $attemptDir | Out-Null
}

# ---------------------------------------------------------------------------
# 2. Input preflight
# ---------------------------------------------------------------------------

# 2a. Required conda executable
if (-not (Test-Path $condaExe)) {
    throw "conda.exe not found at $condaExe"
}

# 2b. No active SPONGE process
if (Test-ProcessRunning -Name "SPONGE") {
    throw "A SPONGE process is already running. Stop it before running this script."
}

# 2c. Accepted coordinate and velocity hashes
$coordHash = Get-FileSha256 -Path $coordIn
$velHash   = Get-FileSha256 -Path $velIn
if ($coordHash -ne $expectedCoordHash) {
    throw "Coordinate hash mismatch: expected $expectedCoordHash, got $coordHash"
}
if ($velHash -ne $expectedVelHash) {
    throw "Velocity hash mismatch: expected $expectedVelHash, got $velHash"
}

# 2d. Coordinate and velocity headers must agree
$coordHeaderParts = Get-RestartHeaderParts -Path $coordIn
$velHeaderParts   = Get-RestartHeaderParts -Path $velIn
if ($coordHeaderParts.atom_count -ne $ATOM_COUNT -or $velHeaderParts.atom_count -ne $ATOM_COUNT) {
    throw "Atom count mismatch: expected $ATOM_COUNT"
}
if ($coordHeaderParts.raw -ne "2586 22.6200000000 249" -or $velHeaderParts.raw -ne "2586 22.6200000000 249") {
    throw "Restart header mismatch: expected '2586 22.6200000000 249' for both"
}
if ($coordHeaderParts.raw -ne $velHeaderParts.raw) {
    throw "Coordinate and velocity restart headers do not agree"
}

# 2e. Embedded coordinate-restart box
$coordLastLine = Get-LastLine -Path $coordIn
if (-not (Test-BoxConsistent -BoxLine $coordLastLine -Tolerance 1e-4)) {
    throw "Coordinate-restart embedded box inconsistent with accepted fixed box: $coordLastLine"
}

# 2f. Required raw input files exist and hash manifest
$rawFiles = @(
    "water_30A_randomized_LJ.txt",
    "water_30A_randomized_atom_name.txt",
    "water_30A_randomized_atom_type_name.txt",
    "water_30A_randomized_bond.txt",
    "water_30A_randomized_charge.txt",
    "water_30A_randomized_coordinate.txt",
    "water_30A_randomized_exclude.txt",
    "water_30A_randomized_mass.txt",
    "water_30A_randomized_residue.txt",
    "water_30A_randomized_resname.txt"
)
foreach ($f in $rawFiles) {
    $p = Join-Path $inputRaw $f
    if (-not (Test-Path $p)) {
        throw "Missing raw input file: $p"
    }
}
$inputRawHashes = Get-HashManifest -Dir $inputRaw
$inputRawHashes | ConvertTo-Json -Depth 2 | Out-File -FilePath (Join-Path $attemptDir "input_raw_hashes.json") -Encoding ascii

Write-Host "Input preflight passed."

# ---------------------------------------------------------------------------
# 3. Build exact amended NVE command and metadata
# ---------------------------------------------------------------------------
Set-Location $attemptDir

$prefix   = "..\..\input_raw\water_30A_randomized"
$coordArg = "..\..\input_restart\accepted_npt_coordinate.txt"
$velArg   = "..\..\input_restart\accepted_npt_velocity.txt"
$mdout    = "nve_diagnostic_2ps.mdout"
$mdinfo   = "nve_diagnostic_2ps.mdinfo"
$rst      = "nve_diagnostic_2ps_rst"
$traj     = "nve_diagnostic_2ps_traj"

$commandParts = @(
    "run",
    "-n", "sponge-cpu",
    "SPONGE",
    "-mode", "NVE",
    "-default_in_file_prefix", $prefix,
    "-coordinate_in_file", $coordArg,
    "-velocity_in_file", $velArg,
    "-step_limit", "$STEP_LIMIT",
    "-dt", "$DT_PS",
    "-constrain_mode", "SHAKE",
    "-cutoff", "8",
    "-write_information_interval", "$INFO_INTERVAL",
    "-write_trajectory_interval", "$TRAJ_INTERVAL",
    "-write_restart_file_interval", "$RST_INTERVAL",
    "-mdout", $mdout,
    "-mdinfo", $mdinfo,
    "-rst", $rst,
    "-default_out_file_prefix", $traj
)

$fullCommand = "$condaExe " + ($commandParts -join " ")

$startWallTime = Get-Date -Format "ddd MMM d HH:mm:ss yyyy"
$startWallTime | Out-File -FilePath "nve_start_wall_time.txt" -Encoding ascii -NoNewline

$meta = [ordered]@{
    attempt                     = "03"
    classification              = "NVE_ATTEMPT_03_SHORT2PS_FOREGROUND"
    command                     = $fullCommand
    argv                        = $commandParts
    conda_exe                   = $condaExe
    working_directory           = $attemptDir
    start_wall_time             = $startWallTime
    stop_wall_time              = $null
    exit_code                   = $null
    constrain_mode_command      = "SHAKE"
    constrain_mode_runtime_note = "SPONGE is expected to initialize SETTLE for the 862 rigid TIP3P waters despite -constrain_mode SHAKE"
    input_coord_hash            = $coordHash
    input_vel_hash              = $velHash
    input_coord_header          = $coordHeaderParts.raw
    input_vel_header            = $velHeaderParts.raw
    input_embedded_box          = $coordLastLine.Trim()
    runtime_amendment           = "09A_SHORT_NVE_RUNTIME_AMENDMENT"
    scientific_scope            = "SHORT_NUMERICAL_STABILITY_DIAGNOSTIC"
    intermediate_restart_policy = "No 1,000-step restart backup is required; only the final 2,000-step restart is preserved."
}
$meta | ConvertTo-Json -Depth 4 | Out-File -FilePath "nve_attempt03_meta.json" -Encoding ascii

Write-Host "Start Wall Time: $startWallTime"
Write-Host "Working directory: $attemptDir"
Write-Host "Command: $fullCommand"

# ---------------------------------------------------------------------------
# 4. Run conda/SPONGE directly in the interactive PowerShell foreground
#    No Kimi timeout, no bash background task, no watcher, no runspace.
# ---------------------------------------------------------------------------
$env:PATH = "$condaRoot\envs\sponge-cpu\bin;$condaRoot\envs\sponge-cpu\Library\bin;" + $env:PATH

$transcriptStarted = $false
try {
    Start-Transcript -Path "nve_console.log" -IncludeInvocationHeader -Force
    $transcriptStarted = $true
}
catch {
    throw "Failed to start console transcript for nve_console.log: $_"
}

try {
    # Direct foreground invocation; blocks until SPONGE exits.
    & $condaExe @commandParts
    $exitCode = $LASTEXITCODE
}
finally {
    if ($transcriptStarted) {
        Stop-Transcript
    }
}

# ---------------------------------------------------------------------------
# 5. Record end wall time and exit code
# ---------------------------------------------------------------------------
$stopWallTime = Get-Date -Format "ddd MMM d HH:mm:ss yyyy"
$stopWallTime | Out-File -FilePath "nve_stop_wall_time.txt" -Encoding ascii -NoNewline
$exitCode | Out-File -FilePath "nve_exit_code.txt" -Encoding ascii -NoNewline

$meta.stop_wall_time = $stopWallTime
$meta.exit_code = $exitCode
$meta | ConvertTo-Json -Depth 4 | Out-File -FilePath "nve_attempt03_meta.json" -Encoding ascii

Write-Host "Stop Wall Time: $stopWallTime"
Write-Host "Exit code: $exitCode"

if ($exitCode -ne 0) {
    Write-Warning "SPONGE exited with non-zero code $exitCode. Outputs preserved in $attemptDir. No post-run validation performed."
    exit $exitCode
}

# ---------------------------------------------------------------------------
# 6. Post-run validation
# ---------------------------------------------------------------------------
Write-Host "Performing post-run validation..."

# 6a. mdinfo contract
$mdinfoPath = Join-Path $attemptDir $mdinfo
if (-not (Test-Path $mdinfoPath)) {
    throw "mdinfo file not produced: $mdinfoPath"
}
$mdinfoText = Get-Content -Raw -Path $mdinfoPath
$mdinfoChecks = @{
    "Mode set to NVE"              = $mdinfoText -match "Mode set to NVE"
    "dt set to 0.001000 ps"        = $mdinfoText -match "dt set to 0\.001000 ps"
    "cutoff set to 8.00 Angstrom" = $mdinfoText -match "cutoff set to 8\.00 Angstrom"
    "SETTLE initialized 862"       = ($mdinfoText -match "START INITIALIZING SETTLE" -and $mdinfoText -match "rigid triangle numbers is 862")
    "Stop Wall Time"               = $mdinfoText -match "Stop Wall Time"
    "Core Run Wall Time"           = $mdinfoText -match "Core Run Wall Time"
    "No thermostat or barostat init" = (
        $mdinfoText -notmatch "MIDDLE LANGEVIN DYNAMICS" -and
        $mdinfoText -notmatch "BERENDSEN" -and
        $mdinfoText -notmatch "PRESSURE BASED BAROSTAT" -and
        $mdinfoText -notmatch "target temperature" -and
        $mdinfoText -notmatch "target pressure"
    )
}
foreach ($check in $mdinfoChecks.GetEnumerator()) {
    if (-not $check.Value) {
        throw "mdinfo contract failed: $($check.Key)"
    }
}

# 6b. mdout contract
$mdoutPath = Join-Path $attemptDir $mdout
if (-not (Test-Path $mdoutPath)) {
    throw "mdout file not produced: $mdoutPath"
}
Test-ContainsNaNInf -Path $mdoutPath
$recordCount = Get-MdoutRecordCount -Path $mdoutPath
$lastStep = Get-MdoutLastStep -Path $mdoutPath
$lastTime = Get-MdoutLastTime -Path $mdoutPath
Write-Host "mdout records: $recordCount, last step: $lastStep, last time (ps): $lastTime"

if ($recordCount -ne $EXPECTED_MDOUT_RECORDS) {
    throw "mdout record count gate failed: expected $EXPECTED_MDOUT_RECORDS, got $recordCount"
}
if ($lastStep -ne $EXPECTED_FINAL_STEP) {
    throw "mdout final step gate failed: expected $EXPECTED_FINAL_STEP, got $lastStep"
}
if ($lastTime -lt 24.619 -or $lastTime -gt 24.621) {
    throw "mdout final time gate failed: expected ~$EXPECTED_FINAL_TIME_PS ps, got $lastTime ps"
}

# 6c. Trajectory contract
$trajPath = Join-Path $attemptDir "$traj.dat"
$boxPath  = Join-Path $attemptDir "$traj.box"

if (-not (Test-Path $trajPath)) {
    throw "Trajectory file not produced: $trajPath"
}
$trajSize = (Get-Item $trajPath).Length
if ($trajSize % $TRJ_BYTES_PER_FRAME -ne 0) {
    throw "Trajectory size $trajSize is not a multiple of $TRJ_BYTES_PER_FRAME bytes per frame"
}
$trajFrameCount = [int]($trajSize / $TRJ_BYTES_PER_FRAME)
Write-Host "Trajectory frames: $trajFrameCount (size: $trajSize bytes)"
if ($trajFrameCount -ne $EXPECTED_TRAJ_FRAMES) {
    throw "Trajectory frame count gate failed: expected $EXPECTED_TRAJ_FRAMES, got $trajFrameCount"
}

# 6d. Box trajectory contract (if produced)
if (Test-Path $boxPath) {
    $boxLines = Get-NonEmptyLines -Path $boxPath
    $boxFrameCount = $boxLines.Count
    Write-Host "Box frames: $boxFrameCount"
    if ($boxFrameCount -ne $EXPECTED_TRAJ_FRAMES) {
        throw "Box frame count gate failed: expected $EXPECTED_TRAJ_FRAMES, got $boxFrameCount"
    }
    foreach ($line in $boxLines) {
        if (-not (Test-BoxConsistent -BoxLine $line -Tolerance 1e-4)) {
            throw "Box trajectory frame inconsistent with accepted fixed box: $line"
        }
    }
}
else {
    Write-Host "No .box trajectory file produced; skipping optional box-frame check."
}

# 6e. Final restart contract (2,000-step only)
$coordRst = Join-Path $attemptDir "${rst}_coordinate.txt"
$velRst   = Join-Path $attemptDir "${rst}_velocity.txt"

if (-not (Test-Path $coordRst)) { throw "Final coordinate restart missing: $coordRst" }
if (-not (Test-Path $velRst))   { throw "Final velocity restart missing: $velRst" }

Test-ContainsNaNInf -Path $coordRst
Test-ContainsNaNInf -Path $velRst

$coordRstParts = Get-RestartHeaderParts -Path $coordRst
$velRstParts   = Get-RestartHeaderParts -Path $velRst

Write-Host "Final coordinate restart header: $($coordRstParts.raw)"
Write-Host "Final velocity restart header: $($velRstParts.raw)"

if ($coordRstParts.atom_count -ne $ATOM_COUNT -or $velRstParts.atom_count -ne $ATOM_COUNT) {
    throw "Restart atom count gate failed: expected $ATOM_COUNT"
}
if ($coordRstParts.raw -ne $velRstParts.raw) {
    throw "Final coordinate and velocity restart headers do not agree"
}
if ($coordRstParts.time_ps -lt 24.619 -or $coordRstParts.time_ps -gt 24.621) {
    throw "Final restart time gate failed: expected ~$EXPECTED_FINAL_TIME_PS ps, got $($coordRstParts.time_ps) ps"
}

$coordRstBox = Get-LastLine -Path $coordRst
if (-not (Test-BoxConsistent -BoxLine $coordRstBox -Tolerance 1e-4)) {
    throw "Final coordinate restart embedded box inconsistent with accepted fixed box: $coordRstBox"
}

# ---------------------------------------------------------------------------
# 7. Copy successful outputs to run/ for existing analysis scripts
#    Does not delete or overwrite attempt_03 evidence.
# ---------------------------------------------------------------------------
$runFiles = @($mdout, $mdinfo, "$traj.dat", "$traj.box",
              "${rst}_coordinate.txt", "${rst}_velocity.txt",
              "nve_start_wall_time.txt", "nve_stop_wall_time.txt",
              "nve_exit_code.txt", "nve_console.log", "nve_attempt03_meta.json",
              "input_raw_hashes.json")
foreach ($f in $runFiles) {
    $src = Join-Path $attemptDir $f
    $dst = Join-Path $runDir $f
    if (Test-Path $src) {
        Copy-Item -Path $src -Destination $dst -Force
    }
}

# ---------------------------------------------------------------------------
# 8. Final runner-only classification
# ---------------------------------------------------------------------------
$decision = [ordered]@{
    classification = "NVE_ATTEMPT_03_COMPLETED_SHORT_DIAGNOSTIC_OUTPUT_CONTRACT_PASS"
    status         = "output_contract_pass"
    attempt_dir    = $attemptDir
    note           = "This is a 2 ps short numerical-stability diagnostic only; it is not equivalent to the original 20 ps NVE diagnostic and cannot establish production readiness. Full scientific acceptance must be reviewed separately after analysis."
}
$decision | ConvertTo-Json -Depth 2 | Out-File -FilePath (Join-Path $attemptDir "nve_attempt03_decision.json") -Encoding ascii

Write-Host "NVE_ATTEMPT_03_COMPLETED_SHORT_DIAGNOSTIC_OUTPUT_CONTRACT_PASS"
Write-Host "Outputs preserved in $attemptDir and copied to $runDir"
Write-Host "Next: run python scripts\analyze_nve.py for full energy-drift, temperature, geometry, and contact analysis."
