#Requires -Version 5.1
<#
.SYNOPSIS
    4 ps NPT production Segment 02 from the synchronized 6000-step restart.
.DESCRIPTION
    Fresh continuation of the 11A NPT production from the synchronized
    coordinate/velocity restart at production-local step 6000 (108.620 ps).
    Runs 4000 additional steps at dt = 0.001 ps to reach 112.620 ps absolute
    simulation time, completing the practical 10 ps production target.

    Uses a new documented thermostat seed and the same NPT ensemble settings
    as the 11A production. Output intervals are set to:
      - write_information_interval 100
      - write_trajectory_interval 500
      - write_restart_file_interval 1000

    The unsynchronized steps 6100, 6200, and 6300 from 11A are deliberately excluded. Step 6000 is the accepted synchronized restart endpoint.
.PARAMETER PreflightOnly
    When set, performs all readiness checks, writes the preflight report, and exits
    without launching SPONGE.
#>

[CmdletBinding()]
param(
    [switch]$PreflightOnly
)

$ErrorActionPreference = "Stop"

$passRoot     = Resolve-Path (Join-Path $PSScriptRoot "..")
$inputRaw     = Join-Path $passRoot "input_raw"
$inputRestart = Join-Path $passRoot "input_restart"
$runDir       = Join-Path $passRoot "run"
$probeDir     = Join-Path $runDir "npt_production_segment02_4ps"
$condaRoot    = "C:\Users\Acer\miniconda3"
$condaExe     = Join-Path $condaRoot "Scripts\conda.exe"

$coordIn = Join-Path $inputRestart "restart_6000_coordinate.txt"
$velIn   = Join-Path $inputRestart "restart_6000_velocity.txt"

$EXPECTED_COORD_HASH = "B4AC947DF619322B15C6F2FF4728E77664348C29CC741B94F012D7271074477D"
$EXPECTED_VEL_HASH   = "FCD42A09943905EF22877E4AC1E92AE0ACD13FF330304E1CD0D02E9F8711667A"
$EXPECTED_HEADER     = "2586 108.6200000000 5999"

$ACCEPTED_BOX = @(29.8043995, 29.8043842, 29.8044262, 90.0, 90.0, 90.0)
$ATOM_COUNT = 2586
$START_TIME_PS = 108.620
$DT_PS = 0.001
$STEP_LIMIT = 4000
$INFO_INTERVAL = 100
$TRAJ_INTERVAL = 500
$RST_INTERVAL = 1000
$THERMOSTAT_SEED = 20260815
$EXPECTED_MDOUT_RECORDS = [math]::Floor($STEP_LIMIT / $INFO_INTERVAL)
$EXPECTED_TRAJ_FRAMES = [math]::Floor($STEP_LIMIT / $TRAJ_INTERVAL)
$EXPECTED_BOX_FRAMES = [math]::Floor($STEP_LIMIT / $TRAJ_INTERVAL)
$EXPECTED_FINAL_STEP = $STEP_LIMIT
$EXPECTED_FINAL_TIME_PS = $START_TIME_PS + ($STEP_LIMIT * $DT_PS)
$TRJ_BYTES_PER_FRAME = $ATOM_COUNT * 3 * 4

function Get-FileSha256 {
    param([string]$Path)
    $stream = [System.IO.File]::OpenRead($Path)
    try {
        $sha = [System.Security.Cryptography.SHA256]::Create()
        $bytes = $sha.ComputeHash($stream)
        return ([BitConverter]::ToString($bytes) -replace "-", "").ToUpper()
    }
    finally { $stream.Dispose() }
}

function Get-RestartHeaderParts {
    param([string]$Path)
    $first = Get-Content -TotalCount 1 -Path $Path
    $parts = $first.Trim() -split '\s+'
    return @{ atom_count = [int]$parts[0]; time_ps = [double]$parts[1]; label = [int]$parts[2]; raw = $first.Trim() }
}

function Get-LastLine {
    param([string]$Path)
    $lines = (Get-Content -Path $Path) | Where-Object { $_.Trim() -ne "" }
    if ($lines.Count -eq 0) { return $null }
    return $lines[$lines.Count - 1]
}

function Test-IsFinite {
    param([double]$Value)
    return -not ([double]::IsNaN($Value) -or [double]::IsInfinity($Value))
}

function Test-AllFinite {
    param([double[]]$Values)
    foreach ($v in $Values) { if (-not (Test-IsFinite -Value $v)) { return $false } }
    return $true
}

function Test-ProcessRunning {
    param([string]$Name)
    return (Get-Process -Name $Name -ErrorAction SilentlyContinue) -ne $null
}

function Get-NPTBoxReport {
    param([string]$BoxLine, [double[]]$ReferenceBox = $ACCEPTED_BOX)
    $parts = $BoxLine.Trim() -split '\s+' | ForEach-Object { [double]$_ }
    if ($parts.Count -ne 6) { return @{ passed = $false; reason = "Box line does not contain exactly 6 values" } }
    $lengths = $parts[0..2]; $angles = $parts[3..5]
    $finite = Test-AllFinite -Values $parts
    $positiveLengths = ($lengths | ForEach-Object { $_ -gt 0 }) -notcontains $false
    $validAngles = ($angles | ForEach-Object { $_ -gt 0 -and $_ -lt 180 }) -notcontains $false
    return @{
        passed         = ($finite -and $positiveLengths -and $validAngles)
        classification = if ($finite -and $positiveLengths -and $validAngles) { "NPT_BOX_FINITE" } else { "NPT_BOX_VALIDATION_REPAIR_REQUIRED" }
        reason         = if ($finite -and $positiveLengths -and $validAngles) { "All box lengths finite and positive; angles in (0, 180)" } else { "Failed finite/positive/angle validation" }
        lengths        = $lengths
        angles         = $angles
    }
}

function New-RunDirectory {
    param([string]$Path)
    if (Test-Path $Path) {
        throw "Run directory already exists (attempt must be fresh): $Path"
    }
    New-Item -ItemType Directory -Path $Path | Out-Null
}

# === Preflight checks ===
$preflight = [ordered]@{
    pass                  = "11B_npt_production_segment02_4ps_20260815_100551"
    purpose               = "NPT_PRODUCTION_SEGMENT02_4PS_FROM_SYNCHRONIZED_6000_STEP_RESTART"
    classification        = "PREFLIGHT_IN_PROGRESS"
    checks                = [ordered]@{}
    parser_errors_count   = $null
    exact_indexed_argv    = @()
}

if (Test-ProcessRunning -Name "SPONGE") { throw "A SPONGE process is already running." }
$preflight.checks["active_sponge_count"] = 0

$coordHash = Get-FileSha256 -Path $coordIn
$velHash   = Get-FileSha256 -Path $velIn
$preflight.checks["coordinate_hash_match"] = ($coordHash -eq $EXPECTED_COORD_HASH)
$preflight.checks["velocity_hash_match"]   = ($velHash -eq $EXPECTED_VEL_HASH)
if (-not $preflight.checks["coordinate_hash_match"]) { throw "Coordinate hash mismatch: $coordHash" }
if (-not $preflight.checks["velocity_hash_match"])   { throw "Velocity hash mismatch: $velHash" }

$coordHeader = Get-RestartHeaderParts -Path $coordIn
$velHeader   = Get-RestartHeaderParts -Path $velIn
$preflight.checks["coordinate_header"] = $coordHeader.raw
$preflight.checks["velocity_header"]   = $velHeader.raw
$preflight.checks["headers_synchronized"] = ($coordHeader.raw -eq $velHeader.raw)
$preflight.checks["coordinate_header_exact"] = ($coordHeader.raw -eq $EXPECTED_HEADER)
$preflight.checks["velocity_header_exact"]   = ($velHeader.raw -eq $EXPECTED_HEADER)
if ($coordHeader.raw -ne $EXPECTED_HEADER -or $velHeader.raw -ne $EXPECTED_HEADER) {
    throw "Restart header mismatch. Expected '$EXPECTED_HEADER', got coord='$($coordHeader.raw)', vel='$($velHeader.raw)'"
}
if ($coordHeader.atom_count -ne $ATOM_COUNT -or $velHeader.atom_count -ne $ATOM_COUNT) {
    throw "Atom count mismatch: coord=$($coordHeader.atom_count), vel=$($velHeader.atom_count)"
}

$coordLastLine = Get-LastLine -Path $coordIn
$coordStartBox = Get-NPTBoxReport -BoxLine $coordLastLine -ReferenceBox $ACCEPTED_BOX
$preflight.checks["starting_box_report"] = $coordStartBox
if (-not $coordStartBox.passed) {
    throw "Starting box failed finite/positive/angle validation: $coordLastLine"
}

$rawFiles = @(
    "water_30A_randomized_LJ.txt", "water_30A_randomized_atom_name.txt", "water_30A_randomized_atom_type_name.txt",
    "water_30A_randomized_bond.txt", "water_30A_randomized_charge.txt", "water_30A_randomized_coordinate.txt",
    "water_30A_randomized_exclude.txt", "water_30A_randomized_mass.txt", "water_30A_randomized_residue.txt",
    "water_30A_randomized_resname.txt"
)
foreach ($f in $rawFiles) {
    $p = Join-Path $inputRaw $f
    $preflight.checks["raw_file_$f"] = Test-Path $p
    if (-not (Test-Path $p)) { throw "Missing raw input file: $p" }
}

$condaExeTest = Test-Path $condaExe
$preflight.checks["conda_exe_exists"] = $condaExeTest
if (-not $condaExeTest) { throw "conda.exe not found at $condaExe" }

$parserErrors = @()
[System.Management.Automation.PSParser]::Tokenize((Get-Content -Raw -Path $PSCommandPath), [ref]$parserErrors) | Out-Null
$preflight.parser_errors_count = $parserErrors.Count
if ($parserErrors.Count -gt 0) { throw "PowerShell parser errors detected: $($parserErrors.Count)" }

New-RunDirectory -Path $probeDir
$preflight.checks["output_directory_status"] = "fresh_directory_created"

$prefix   = "..\..\input_raw\water_30A_randomized"
$coordArg = "..\..\input_restart\restart_6000_coordinate.txt"
$velArg   = "..\..\input_restart\restart_6000_velocity.txt"
$mdout    = "npt_production_segment02_4ps.mdout"
$mdinfo   = "npt_production_segment02_4ps.mdinfo"
$rst      = "npt_production_segment02_4ps_rst"
$traj     = "npt_production_segment02_4ps_traj"

$commandParts = @(
    "run", "-n", "sponge-cpu", "SPONGE",
    "-mode", "NPT",
    "-thermostat", "middle_langevin",
    "-barostat", "bussi_barostat",
    "-target_temperature", "300",
    "-target_pressure", "1.0",
    "-thermostat_seed", [string]$THERMOSTAT_SEED,
    "-thermostat_tau", "1.0",
    "-barostat_tau", "1.0",
    "-barostat_update_interval", "10",
    "-barostat_isotropy", "isotropic",
    "-default_in_file_prefix", $prefix,
    "-coordinate_in_file", $coordArg,
    "-velocity_in_file", $velArg,
    "-step_limit", [string]$STEP_LIMIT,
    "-dt", "0.001",
    "-constrain_mode", "SHAKE",
    "-cutoff", "8",
    "-write_information_interval", [string]$INFO_INTERVAL,
    "-write_trajectory_interval", [string]$TRAJ_INTERVAL,
    "-write_restart_file_interval", [string]$RST_INTERVAL,
    "-print_pressure", "1",
    "-mdout", $mdout,
    "-mdinfo", $mdinfo,
    "-rst", $rst,
    "-default_out_file_prefix", $traj
)

$indexedArgv = for ($i = 0; $i -lt $commandParts.Count; $i++) {
    @{ index = $i; value = $commandParts[$i] }
}
$preflight.exact_indexed_argv = $indexedArgv
$preflight.checks["command_parts_count"] = $commandParts.Count

$fullCommand = "$condaExe " + ($commandParts -join " ")
$startWallTime = Get-Date -Format "ddd MMM d HH:mm:ss yyyy"

$preflight.classification = "PREFLIGHT_PASS"
$preflight.checks["start_wall_time"] = $startWallTime
$preflight.checks["working_directory"] = $probeDir
$preflight.checks["full_command"] = $fullCommand
$preflight.checks["expected_final_time_ps"] = $EXPECTED_FINAL_TIME_PS
$preflight.checks["expected_final_step"] = $EXPECTED_FINAL_STEP

$preflightPath = Join-Path $probeDir "PREFLIGHT_REPORT.json"
$preflight | ConvertTo-Json -Depth 5 | Out-File -FilePath $preflightPath -Encoding ascii

$reportPath = Join-Path (Join-Path $passRoot "validation") "PREFLIGHT_VALIDATION_REPORT.json"
$preflight | ConvertTo-Json -Depth 5 | Out-File -FilePath $reportPath -Encoding ascii

Write-Host "Preflight passed. Report written to $preflightPath"
Write-Host "Start Wall Time: $startWallTime"
Write-Host "Working directory: $probeDir"
Write-Host "Command: $fullCommand"

if ($PreflightOnly) {
    Write-Host "PreflightOnly switch set; SPONGE will NOT be launched."
    exit 0
}

# === Launch ===
$meta = [ordered]@{
    pass                    = $preflight.pass
    purpose                 = $preflight.purpose
    classification          = "NPT_PRODUCTION_SEGMENT02_4PS_FROM_SYNCHRONIZED_6000_STEP_RESTART"
    command                 = $fullCommand
    argv                    = $commandParts
    conda_exe               = $condaExe
    working_directory       = $probeDir
    start_wall_time         = $startWallTime
    stop_wall_time          = $null
    exit_code               = $null
    input_coord_hash        = $coordHash
    input_vel_hash          = $velHash
    input_coord_header      = $coordHeader.raw
    input_vel_header        = $velHeader.raw
    input_embedded_box      = $coordLastLine.Trim()
    expected_final_step     = $EXPECTED_FINAL_STEP
    expected_final_time_ps  = $EXPECTED_FINAL_TIME_PS
    expected_mdout_records  = $EXPECTED_MDOUT_RECORDS
    expected_traj_frames    = $EXPECTED_TRAJ_FRAMES
    expected_box_frames     = $EXPECTED_BOX_FRAMES
    restart_interval_steps  = $RST_INTERVAL
    note                    = "4 ps Segment 02 continuation from synchronized 6000-step (108.620 ps) 11A restart. New thermostat seed 20260815. Completes practical 10 ps production target."
}
$meta | ConvertTo-Json -Depth 4 | Out-File -FilePath (Join-Path $probeDir "npt_production_segment02_4ps_meta.json") -Encoding ascii

$env:PATH = "$condaRoot\envs\sponge-cpu\bin;$condaRoot\envs\sponge-cpu\Library\bin;" + $env:PATH

try {
    Start-Transcript -Path "npt_production_segment02_4ps_console.log" -IncludeInvocationHeader -Force
}
catch { throw "Failed to start transcript: $_" }

try {
    Set-Location $probeDir
    & $condaExe @commandParts
    $exitCode = $LASTEXITCODE
}
finally {
    Stop-Transcript
}

$stopWallTime = Get-Date -Format "ddd MMM d HH:mm:ss yyyy"
$meta.stop_wall_time = $stopWallTime
$meta.exit_code = $exitCode
$meta | ConvertTo-Json -Depth 4 | Out-File -FilePath (Join-Path $probeDir "npt_production_segment02_4ps_meta.json") -Encoding ascii

Write-Host "Stop Wall Time: $stopWallTime"
Write-Host "Exit code: $exitCode"

if ($exitCode -ne 0) {
    Write-Warning "SPONGE exited with non-zero code $exitCode. Outputs preserved in $probeDir."
    exit $exitCode
}

Write-Host "4 ps Segment 02 production run completed."
