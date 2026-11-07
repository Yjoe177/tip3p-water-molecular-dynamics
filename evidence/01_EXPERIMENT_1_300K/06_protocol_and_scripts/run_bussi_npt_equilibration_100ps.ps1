#Requires -Version 5.1
<#
.SYNOPSIS
    Foreground runner for Pass 10B 100 ps Bussi-NPT pre-production equilibration.
.DESCRIPTION
    Runs 100 ps of NPT equilibration from the accepted 08ARRR NPT state using
    the Bussi barostat and middle_langevin thermostat. Uses conda run in an
    interactive PowerShell foreground session.

    IMPORTANT:
    - Intended to be run directly by the user in an interactive PowerShell window.
    - Blocks until SPONGE exits.
    - Never deletes existing attempt evidence.
    - Starts from the original accepted NPT state, NOT from the Pass 10A probe endpoint.
    - SPONGE overwrites restart files at each interval; only the final restart pair is expected.
    - On success the runner classifies only output-contract completion; full
      stationarity assessment is performed separately after the run.
#>

[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"

# -----------------------------------------------------------------------------
# Paths and frozen constants
# -----------------------------------------------------------------------------
$passRoot     = Resolve-Path (Join-Path $PSScriptRoot "..")
$inputRaw     = Join-Path $passRoot "input_raw"
$inputRestart = Join-Path $passRoot "input_restart"
$runDir       = Join-Path $passRoot "run"
$probeDir     = Join-Path $runDir "bussi_npt_equilibration_100ps"
$condaRoot    = "C:\Users\Acer\miniconda3"
$condaExe     = Join-Path $condaRoot "Scripts\conda.exe"

$coordIn = Join-Path $inputRestart "accepted_npt_coordinate.txt"
$velIn   = Join-Path $inputRestart "accepted_npt_velocity.txt"

$expectedCoordHash = "b43cc97c3d2006be7e43d60e78cdc17694e92a295916051ade88f0db88ffa076"
$expectedVelHash   = "2220f704411c99b0e5bc6fa621b19efbc13691481e08a099f909fd34ccfe8cf2"

$ACCEPTED_BOX = @(29.9968719, 29.9968643, 29.9968872, 90.0, 90.0, 90.0)
$ATOM_COUNT = 2586
$START_TIME_PS = 22.62
$DT_PS = 0.001
$STEP_LIMIT = 100000
$INFO_INTERVAL = 100
$TRAJ_INTERVAL = 1000
$RST_INTERVAL = 10000
$EXPECTED_MDOUT_RECORDS = 1000
$EXPECTED_TRAJ_FRAMES = 100
$EXPECTED_BOX_FRAMES = 100
$EXPECTED_FINAL_STEP = 100000
$EXPECTED_FINAL_TIME_PS = 122.62
$TRJ_BYTES_PER_FRAME = $ATOM_COUNT * 3 * 4  # 31032

# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
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

function Get-LastLine {
    param([string]$Path)
    $lines = Get-NonEmptyLines -Path $Path
    if ($lines.Count -eq 0) { return $null }
    return $lines[$lines.Count - 1]
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

function Test-ApproxEqual {
    param([double]$Actual, [double]$Expected, [double]$Tolerance = 1e-4)
    return [math]::Abs($Actual - $Expected) -le $Tolerance
}

function Test-IsFinite {
    param([double]$Value)
    return -not ([double]::IsNaN($Value) -or [double]::IsInfinity($Value))
}

function Test-AllFinite {
    param([double[]]$Values)
    foreach ($v in $Values) {
        if (-not (Test-IsFinite -Value $v)) {
            return $false
        }
    }
    return $true
}

function Get-NPTBoxReport {
    param(
        [string]$BoxLine,
        [double[]]$ReferenceBox = $ACCEPTED_BOX,
        [double]$AngleTolerance = 1e-6,
        [double]$IsotropyTolerance = 1e-4
    )
    $parts = $BoxLine.Trim() -split '\s+' | ForEach-Object { [double]$_ }
    if ($parts.Count -ne 6) {
        return @{ passed = $false; reason = "Box line does not contain exactly 6 values"; report = $null }
    }

    $refLengths = $ReferenceBox[0..2]
    $lengths = $parts[0..2]
    $angles = $parts[3..5]

    $finite = Test-AllFinite -Values $parts
    $positiveLengths = ($lengths | ForEach-Object { $_ -gt 0 }) -notcontains $false
    $validAngles = ($angles | ForEach-Object { $_ -gt 0 -and $_ -lt 180 }) -notcontains $false
    $angles90 = ($angles | ForEach-Object { [math]::Abs($_ - 90.0) -le $AngleTolerance }) -notcontains $false

    # Explicit element-wise scalar arithmetic to avoid PowerShell 5.1 Object[] operator errors.
    $absChanges = @()
    $fracChanges = @()
    for ($i = 0; $i -lt 3; $i++) {
        $start = [double]$refLengths[$i]
        $final = [double]$lengths[$i]
        $d = $final - $start
        $absChanges += $d
        $fracChanges += ($d / $start)
    }

    $isotropic = $true
    for ($i = 1; $i -lt 3; $i++) {
        $fc0 = [double]$fracChanges[0]
        $fcI = [double]$fracChanges[$i]
        if ([math]::Abs($fcI - $fc0) -gt $IsotropyTolerance) {
            $isotropic = $false
            break
        }
    }

    $refVolume =
        [double]$refLengths[0] *
        [double]$refLengths[1] *
        [double]$refLengths[2]
    $volume =
        [double]$lengths[0] *
        [double]$lengths[1] *
        [double]$lengths[2]
    $fracVolumeChange = ($volume - $refVolume) / $refVolume

    $passed = $finite -and $positiveLengths -and $validAngles -and $angles90
    $classification = if ($passed) { "NPT_BOX_FINITE_AND_ISOTROPIC" } else { "NPT_BOX_VALIDATION_REPAIR_REQUIRED" }

    $report = [ordered]@{
        starting_box = ($ReferenceBox -join " ")
        final_box = ($parts -join " ")
        starting_volume_A3 = $refVolume
        final_volume_A3 = $volume
        absolute_length_changes_A = $absChanges
        fractional_length_changes = $fracChanges
        fractional_volume_change = $fracVolumeChange
        isotropic_within_tolerance = $isotropic
        classification = $classification
        checks = [ordered]@{
            finite = $finite
            positive_lengths = $positiveLengths
            valid_angles = $validAngles
            angles_remain_90_degrees = $angles90
        }
    }
    return @{ passed = $passed; report = $report }
}

function Get-HashManifest {
    param([string]$Dir)
    $manifest = @{}
    foreach ($f in (Get-ChildItem -Path $Dir -File)) {
        $manifest[$f.Name] = Get-FileSha256 -Path $f.FullName
    }
    return $manifest
}

# -----------------------------------------------------------------------------
# 1. Run directory must be empty or non-existent; never delete evidence
# -----------------------------------------------------------------------------
if (Test-Path $probeDir) {
    $existing = Get-ChildItem -Path $probeDir -Recurse -Force
    if ($existing.Count -gt 0) {
        throw "EQUILIBRATION_DIRECTORY_NOT_EMPTY_NO_RUN_LAUNCHED: $probeDir contains $($existing.Count) item(s)."
    }
}
else {
    New-Item -ItemType Directory -Path $probeDir | Out-Null
}

# -----------------------------------------------------------------------------
# 2. Input preflight
# -----------------------------------------------------------------------------
if (-not (Test-Path $condaExe)) {
    throw "conda.exe not found at $condaExe"
}

if (Test-ProcessRunning -Name "SPONGE") {
    throw "A SPONGE process is already running. Stop it before running this equilibration."
}

$coordHash = Get-FileSha256 -Path $coordIn
$velHash   = Get-FileSha256 -Path $velIn
if ($coordHash -ne $expectedCoordHash) {
    throw "Coordinate hash mismatch: expected $expectedCoordHash, got $coordHash"
}
if ($velHash -ne $expectedVelHash) {
    throw "Velocity hash mismatch: expected $expectedVelHash, got $velHash"
}

$coordHeader = Get-RestartHeaderParts -Path $coordIn
$velHeader   = Get-RestartHeaderParts -Path $velIn
if ($coordHeader.atom_count -ne $ATOM_COUNT -or $velHeader.atom_count -ne $ATOM_COUNT) {
    throw "Atom count mismatch: expected $ATOM_COUNT"
}
if ($coordHeader.raw -ne "2586 22.6200000000 249" -or $velHeader.raw -ne "2586 22.6200000000 249") {
    throw "Restart header mismatch: expected '2586 22.6200000000 249' for both"
}
if ($coordHeader.raw -ne $velHeader.raw) {
    throw "Coordinate and velocity restart headers do not agree"
}

$coordLastLine = Get-LastLine -Path $coordIn
$coordStartBox = Get-NPTBoxReport -BoxLine $coordLastLine -ReferenceBox $ACCEPTED_BOX
if (-not $coordStartBox.passed) {
    throw "Starting coordinate-restart embedded box failed finite/positive/angle validation: $coordLastLine"
}

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
$inputRawHashes | ConvertTo-Json -Depth 2 | Out-File -FilePath (Join-Path $probeDir "bussi_npt_equilibration_100ps_input_raw_hashes.json") -Encoding ascii

Write-Host "Input preflight passed."

# -----------------------------------------------------------------------------
# 3. Build exact Bussi-NPT equilibration command and metadata
# -----------------------------------------------------------------------------
Set-Location $probeDir

$prefix   = "..\..\input_raw\water_30A_randomized"
$coordArg = "..\..\input_restart\accepted_npt_coordinate.txt"
$velArg   = "..\..\input_restart\accepted_npt_velocity.txt"
$mdout    = "bussi_npt_equilibration_100ps.mdout"
$mdinfo   = "bussi_npt_equilibration_100ps.mdinfo"
$rst      = "bussi_npt_equilibration_100ps_rst"
$traj     = "bussi_npt_equilibration_100ps_traj"

$commandParts = @(
    "run",
    "-n", "sponge-cpu",
    "SPONGE",
    "-mode", "NPT",
    "-thermostat", "middle_langevin",
    "-barostat", "bussi_barostat",
    "-target_temperature", "300",
    "-target_pressure", "1.0",
    "-thermostat_seed", "20260922",
    "-thermostat_tau", "1.0",
    "-barostat_tau", "1.0",
    "-barostat_update_interval", "10",
    "-barostat_isotropy", "isotropic",
    "-default_in_file_prefix", $prefix,
    "-coordinate_in_file", $coordArg,
    "-velocity_in_file", $velArg,
    "-step_limit", "100000",
    "-dt", "0.001",
    "-constrain_mode", "SHAKE",
    "-cutoff", "8",
    "-write_information_interval", "100",
    "-write_trajectory_interval", "1000",
    "-write_restart_file_interval", "10000",
    "-print_pressure", "1",
    "-mdout", $mdout,
    "-mdinfo", $mdinfo,
    "-rst", $rst,
    "-default_out_file_prefix", $traj
)

$fullCommand = "$condaExe " + ($commandParts -join " ")

$startWallTime = Get-Date -Format "ddd MMM d HH:mm:ss yyyy"
$startWallTime | Out-File -FilePath "bussi_npt_equilibration_100ps_start_wall_time.txt" -Encoding ascii -NoNewline

$prefixDir = Split-Path $prefix -Parent
$prefixName = Split-Path $prefix -Leaf
$prefixDirAbs = Resolve-Path $prefixDir
$prefixAbs = Join-Path $prefixDirAbs $prefixName
$coordArgAbs = Resolve-Path $coordArg
$velArgAbs = Resolve-Path $velArg

if (-not (Test-Path $prefixDirAbs)) {
    throw "Resolved raw input directory does not exist: $prefixDirAbs"
}
if ((Get-FileSha256 -Path $coordArgAbs) -ne $expectedCoordHash) {
    throw "Resolved coordinate file hash mismatch: $coordArgAbs"
}
if ((Get-FileSha256 -Path $velArgAbs) -ne $expectedVelHash) {
    throw "Resolved velocity file hash mismatch: $velArgAbs"
}
foreach ($f in $rawFiles) {
    $rp = Join-Path $prefixDirAbs "$prefixName_$f"
    if (-not (Test-Path $rp)) {
        throw "Resolved raw input file missing: $rp"
    }
}

$meta = [ordered]@{
    pass                          = "10B_bussi_npt_equilibration_100ps_20260808_161936"
    purpose                       = "BUSSI_NPT_PREPRODUCTION_EQUILIBRATION"
    classification                = "BUSSI_NPT_EQUILIBRATION_100PS_FOREGROUND"
    command                       = $fullCommand
    argv                          = $commandParts
    conda_exe                     = $condaExe
    working_directory             = $probeDir
    relative_input_paths          = @{
        default_in_file_prefix = $prefix
        coordinate_in_file     = $coordArg
        velocity_in_file       = $velArg
    }
    resolved_absolute_input_paths = @{
        default_in_file_prefix_dir  = $prefixDirAbs.Path
        default_in_file_prefix_stem = $prefixAbs
        coordinate_in_file            = $coordArgAbs.Path
        velocity_in_file              = $velArgAbs.Path
    }
    start_wall_time               = $startWallTime
    stop_wall_time                = $null
    exit_code                     = $null
    input_coord_hash              = $coordHash
    input_vel_hash                = $velHash
    input_coord_header            = $coordHeader.raw
    input_vel_header              = $velHeader.raw
    input_embedded_box            = $coordLastLine.Trim()
    expected_final_step           = $EXPECTED_FINAL_STEP
    expected_final_time_ps        = $EXPECTED_FINAL_TIME_PS
    expected_mdout_records        = $EXPECTED_MDOUT_RECORDS
    expected_trajectory_frames    = $EXPECTED_TRAJ_FRAMES
    expected_box_frames           = $EXPECTED_BOX_FRAMES
    restart_overwrite_note        = "SPONGE overwrites restart files at each interval; only the final synchronized pair is expected."
}
$meta | ConvertTo-Json -Depth 4 | Out-File -FilePath "bussi_npt_equilibration_100ps_meta.json" -Encoding ascii

Write-Host "Start Wall Time: $startWallTime"
Write-Host "Working directory: $probeDir"
Write-Host "Command: $fullCommand"

# -----------------------------------------------------------------------------
# 4. Run conda/SPONGE directly in the interactive PowerShell foreground
#    No Kimi timeout, no bash background task, no watcher, no runspace.
# -----------------------------------------------------------------------------
$env:PATH = "$condaRoot\envs\sponge-cpu\bin;$condaRoot\envs\sponge-cpu\Library\bin;" + $env:PATH

$transcriptStarted = $false
try {
    Start-Transcript -Path "bussi_npt_equilibration_100ps_console.log" -IncludeInvocationHeader -Force
    $transcriptStarted = $true
}
catch {
    throw "Failed to start console transcript: $_"
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

# -----------------------------------------------------------------------------
# 5. Record end wall time and exit code
# -----------------------------------------------------------------------------
$stopWallTime = Get-Date -Format "ddd MMM d HH:mm:ss yyyy"
$stopWallTime | Out-File -FilePath "bussi_npt_equilibration_100ps_stop_wall_time.txt" -Encoding ascii -NoNewline
$exitCode | Out-File -FilePath "bussi_npt_equilibration_100ps_exit_code.txt" -Encoding ascii -NoNewline

$meta.stop_wall_time = $stopWallTime
$meta.exit_code = $exitCode
$meta | ConvertTo-Json -Depth 4 | Out-File -FilePath "bussi_npt_equilibration_100ps_meta.json" -Encoding ascii

Write-Host "Stop Wall Time: $stopWallTime"
Write-Host "Exit code: $exitCode"

if ($exitCode -ne 0) {
    Write-Warning "SPONGE exited with non-zero code $exitCode. Outputs preserved in $probeDir. No post-run validation performed."
    exit $exitCode
}

# -----------------------------------------------------------------------------
# 6. Post-run output contract validation
# -----------------------------------------------------------------------------
Write-Host "Performing post-run output contract validation..."

# 6a. mdinfo contract
$mdinfoPath = Join-Path $probeDir $mdinfo
if (-not (Test-Path $mdinfoPath)) {
    throw "mdinfo file not produced: $mdinfoPath"
}
Test-ContainsNaNInf -Path $mdinfoPath
$mdinfoText = Get-Content -Raw -Path $mdinfoPath
$mdinfoChecks = [ordered]@{
    "Mode set to NPT"                  = $mdinfoText -match "Mode set to NPT"
    "dt set to 0.001000 ps"            = $mdinfoText -match "dt set to 0\.001000 ps"
    "cutoff set to 8.00 Angstrom"      = $mdinfoText -match "cutoff set to 8\.00 Angstrom"
    "middle_langevin initialized"      = $mdinfoText -match "START INITIALIZING MIDDLE LANGEVIN DYNAMICS"
    "target temperature 300 K"         = $mdinfoText -match "target temperature is 300\.00 K"
    "bussi_barostat initialized"       = ($mdinfoText -match "START INITIALIZING PRESSURE BASED BAROSTAT" -and $mdinfoText -match "The algorithm is Bussi")
    "target pressure 1 bar"            = $mdinfoText -match "The target pressure is 1\.00 bar"
    "SETTLE initialized 862"           = ($mdinfoText -match "START INITIALIZING SETTLE" -and $mdinfoText -match "rigid triangle numbers is 862")
    "SHAKE runtime not initialized"    = $mdinfoText -match "SHAKE IS NOT INITIALIZED"
    "Stop Wall Time"                   = $mdinfoText -match "Stop Wall Time"
    "Core Run Wall Time"               = $mdinfoText -match "Core Run Wall Time"
}
foreach ($check in $mdinfoChecks.GetEnumerator()) {
    if (-not $check.Value) {
        throw "mdinfo contract failed: $($check.Key)"
    }
}

# 6b. mdout contract
$mdoutPath = Join-Path $probeDir $mdout
if (-not (Test-Path $mdoutPath)) {
    throw "mdout file not produced: $mdoutPath"
}
Test-ContainsNaNInf -Path $mdoutPath
$records = Get-MdoutRecords -Path $mdoutPath
$recordCount = $records.Count
$lastRecord = $records[$records.Count - 1]
$lastStep = 0
$lastTime = 0.0
if ($lastRecord -match '^\s*(\d+)\s+([0-9.]+)') {
    $lastStep = [int]$Matches[1]
    $lastTime = [double]$Matches[2]
}
Write-Host "mdout records: $recordCount, last step: $lastStep, last time (ps): $lastTime"
if ($recordCount -ne $EXPECTED_MDOUT_RECORDS) {
    throw "mdout record count gate failed: expected $EXPECTED_MDOUT_RECORDS, got $recordCount"
}
if ($lastStep -ne $EXPECTED_FINAL_STEP) {
    throw "mdout final step gate failed: expected $EXPECTED_FINAL_STEP, got $lastStep"
}
if ($lastTime -lt ($EXPECTED_FINAL_TIME_PS - 1e-4) -or $lastTime -gt ($EXPECTED_FINAL_TIME_PS + 1e-4)) {
    throw "mdout final time gate failed: expected ~$EXPECTED_FINAL_TIME_PS ps, got $lastTime ps"
}

# 6c. Trajectory contract
$trajPath = Join-Path $probeDir "$traj.dat"
$boxPath  = Join-Path $probeDir "$traj.box"

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

# 6d. Box trajectory contract (NPT-aware)
if (-not (Test-Path $boxPath)) {
    throw "Box trajectory file not produced: $boxPath"
}
$boxLines = Get-NonEmptyLines -Path $boxPath
Write-Host "Box frames: $($boxLines.Count)"
if ($boxLines.Count -ne $EXPECTED_BOX_FRAMES) {
    throw "Box frame count gate failed: expected $EXPECTED_BOX_FRAMES, got $($boxLines.Count)"
}
$boxReports = @()
foreach ($line in $boxLines) {
    $r = Get-NPTBoxReport -BoxLine $line -ReferenceBox $ACCEPTED_BOX
    $boxReports += $r.report
    if (-not $r.passed) {
        throw "Box trajectory frame failed finite/positive/angle validation: $line"
    }
}
$boxReports | ConvertTo-Json -Depth 4 | Out-File -FilePath "bussi_npt_equilibration_100ps_box_report.json" -Encoding ascii

# 6e. Final restart contract
$coordRst = Join-Path $probeDir "${rst}_coordinate.txt"
$velRst   = Join-Path $probeDir "${rst}_velocity.txt"

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
if ($coordRstParts.time_ps -lt ($EXPECTED_FINAL_TIME_PS - 1e-4) -or $coordRstParts.time_ps -gt ($EXPECTED_FINAL_TIME_PS + 1e-4)) {
    throw "Final restart time gate failed: expected ~$EXPECTED_FINAL_TIME_PS ps, got $($coordRstParts.time_ps) ps"
}

$coordRstBox = Get-LastLine -Path $coordRst
$coordRstBoxReport = Get-NPTBoxReport -BoxLine $coordRstBox -ReferenceBox $ACCEPTED_BOX
$coordRstBoxReport.report | ConvertTo-Json -Depth 4 | Out-File -FilePath "bussi_npt_equilibration_100ps_restart_box_report.json" -Encoding ascii
if (-not $coordRstBoxReport.passed) {
    throw "Final coordinate restart embedded box failed finite/positive/angle validation: $coordRstBox"
}

# -----------------------------------------------------------------------------
# 7. Output-contract result classification
# -----------------------------------------------------------------------------
$decision = [ordered]@{
    classification = "BUSSI_NPT_EQUILIBRATION_100PS_OUTPUT_CONTRACT_PASS"
    status         = "output_contract_pass"
    probe_dir      = $probeDir
    box_report     = $coordRstBoxReport.report
    note           = "100 ps Bussi-NPT equilibration completed the output contract. Stationarity and production readiness must be assessed separately by post-run analysis."
}
$decision | ConvertTo-Json -Depth 2 | Out-File -FilePath "bussi_npt_equilibration_100ps_decision.json" -Encoding ascii

Write-Host "BUSSI_NPT_EQUILIBRATION_100PS_OUTPUT_CONTRACT_PASS"
Write-Host "Outputs preserved in $probeDir"
Write-Host "Next: run the post-run analysis script to assess stationarity."
