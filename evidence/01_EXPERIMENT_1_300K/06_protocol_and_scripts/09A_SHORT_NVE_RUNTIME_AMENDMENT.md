# 09A Short NVE Runtime Amendment

## Amendment identifier

`09A_SHORT_NVE_RUNTIME_AMENDMENT`

## Scientific scope

`SHORT_NUMERICAL_STABILITY_DIAGNOSTIC`

## Rationale

The original 03BR frozen protocol calls for a 20 ps / 20,000-step NVE diagnostic
following the accepted 08ARRR NPT state. Attempt 02 of Pass 09A was launched in
the interactive PowerShell foreground using the same conda/SPONGE relative-path
method that succeeded for the final NPT continuation. The user stopped the run
because the CPU-only runtime on the laptop makes the full 20 ps diagnostic
impractical.

This amendment replaces the original duration with a short diagnostic that is
still long enough to reveal short-time numerical instability, structural instability, finite temperature/potential behavior, and potential-energy behavior; quantitative TOTAL-ENERGY drift is NOT available from the installed SPONGE output format.

## Original frozen protocol

| Setting | Value | Source |
|---------|-------|--------|
| duration | 20 ps | 03BR command_templates/14_nve_diagnostic.txt |
| step_limit | 20000 | 03BR command_templates/14_nve_diagnostic.txt |
| dt | 0.001 ps | 03BR command_templates/14_nve_diagnostic.txt |

Source SHA-256: `3bb7270d0a1dcece5cf64f5488446d5bca34385205a1aa90f9b058bd1b87f9aa`

## Amended protocol

| Setting | Value |
|---------|-------|
| duration | 2 ps |
| step_limit | 2000 |
| dt | 0.001 ps |
| constrain_mode | SHAKE (SPONGE runtime routes this to SETTLE for the 862 TIP3P waters) |
| cutoff | 8 Å |
| write_information_interval | 50 steps |
| write_trajectory_interval | 200 steps |
| write_restart_file_interval | 1000 steps |
| thermostat | omitted |
| barostat | omitted |
| seed | none |
| mode | NVE |

## Expected output contract

- 40 numeric mdout records (steps 50, 100, ..., 2000)
- 10 trajectory frames
- Final simulation time approximately 24.620 ps (22.620 + 2.000)
- 2,000-step final restart preserved

## Intermediate restart policy

Intermediate 1,000-step restart archival was removed from the amended
diagnostic because it is not required for the scientific short-time
stability assessment and avoiding asynchronous restart-copy logic makes
the evidence path simpler and more robust.

## Input state

- Coordinate: `input_restart/accepted_npt_coordinate.txt`
  - SHA-256: `b43cc97c3d2006be7e43d60e78cdc17694e92a295916051ade88f0db88ffa076`
- Velocity: `input_restart/accepted_npt_velocity.txt`
  - SHA-256: `2220f704411c99b0e5bc6fa621b19efbc13691481e08a099f909fd34ccfe8cf2`
- Start time: 22.620 ps
- Label: 249

## Important limitations

- This amended run is **not equivalent** to the original 20 ps NVE diagnostic.
- It is intended only to detect obvious integration instability, short-time numerical instability, structural instability, finite temperature/potential behavior, and potential-energy behavior; quantitative TOTAL-ENERGY drift is NOT available from the installed SPONGE output format.
- It **cannot** establish long-timescale energy conservation and does not provide quantitative total-energy drift.
- No production-readiness threshold may be invented from this short diagnostic.

## Classification constraint

The runner must classify a successful short diagnostic only as
`NVE_ATTEMPT_03_COMPLETED_SHORT_DIAGNOSTIC_OUTPUT_CONTRACT_PASS`. Full
scientific acceptance for production must be reviewed separately against the
measured results and the documented protocol limitations.
