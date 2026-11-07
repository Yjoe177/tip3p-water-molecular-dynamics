# Final Accepted Protocol

## System

- 862 TIP3P water molecules (2586 atoms)
- Initial 30 Å cubic box
- SPONGE runtime v2.0.0 2026-02-16 Spring Festive

## Major accepted stages

1. **System preparation / energy minimization (04H)**
   - Accepted 7600 steps total.
   - Endpoint: `02_accepted_stage_states/energy_minimization/`
   - The **coordinate** from this endpoint was used as the coordinate component of the 05ARR `quench_10K` start state.
   - The **velocity** from the 04H minimisation endpoint was **not** used as the low-temperature starting velocity; the 05AR generated 50 K seed velocity was used instead.

2. **Mixed-origin 05ARR start inputs**
   - Coordinate source: `04H_continuous_minimisation_5000_20260803_211028/outputs/primary/continuous5000_rst_coordinate.txt`
     - SHA-256: `255035EA24B59ABED88A6846D9974A84B5A12091386D6CD17038562CA314E65E`
   - Velocity source: `05AR_velocity_initialisation_conditioning_repair_20260804_104636/velocity_generation/generated/physical_50K_velocity.txt`
     - SHA-256: `C89EB95C26260FBF8B05DCB5451A7164B4099F4FE077CA6C47452FE251E028A4`
   - These two files, from different origins, were the actual inputs consumed by the first accepted 05ARR low-temperature stage (`quench_10K`).
   - The combined start state is archived in `02_accepted_stage_states/05ARR_start_inputs/`.

3. **05ARR quench_10K**
   - 200 steps at 10 K target, dt = 0.0001 ps, total 0.02 ps.
   - Endpoint: `02_accepted_stage_states/quench_10K_transition/`
   - Direct input for: 05ARR `warm_25K`.
   - The command for `warm_25K` explicitly references `../../quench_10K/run/quench0200_rst_coordinate.txt` and `../../quench_10K/run/quench0200_rst_velocity.txt` (verified by source-exact runner and path-resolution proof).

4. **05ARR warm_25K / low-temperature relaxation**
   - 400 steps at 25 K target, 0.00025 ps timestep, 0.1 ps total.
   - Endpoint: `02_accepted_stage_states/warm_25K_continuation/`
   - **Classification:** read from archived `PASS05ARR_REVIEW_RECLASSIFICATION.json` as `PASS_SAFE_LOW_TEMPERATURE_RELAXATION_CONTINUE_TO_50K`.
   - Exact 25 K equilibrium was **not demonstrated** (`NOT_DEMONSTRATED`); the state is accepted only as the input for the 50 K conditioning stage.
   - Used as input for: 05ARRR `condition_50K`.

5. **Low-temperature conditioning (05ARRR condition_50K)**
   - 50 K NVT conditioning, 600 steps, 0.3 ps, starting from the accepted 05ARR warm state.
   - Endpoint: `02_accepted_stage_states/low_temperature_conditioning/`
   - Used as input for: heating-ready 50 K preflight.

6. **Heating-ready 50 K preflight (05ARRR preflight_1fs_nvt)**
   - 200 steps, dt = 0.001 ps, 0.2 ps total, NVT at 50 K.
   - Endpoint: `02_accepted_stage_states/heating_ready_50K_preflight/`
   - This exact coordinate/velocity pair was the input to 06AR heating.

7. **Heating (06AR)**
   - Staged NVT heating from ~50 K to 300 K, 7 ps total.
   - 5 ps ramp + 2 ps 300 K hold, middle_langevin thermostat, dt = 0.001 ps.
   - Endpoint: `02_accepted_stage_states/heating_300K/`
   - Used as input for 300 K NVT stabilization.

8. **300 K NVT stabilization (07A)**
   - 10 ps NVT at 300 K.
   - Endpoint: `02_accepted_stage_states/nvt_10ps/`

9. **Practical NPT density relaxation (08ARRR)**
   - Short practical NPT relaxation producing the accepted NPT state.
   - Endpoint: `02_accepted_stage_states/practical_npt_5ps/`
   - Used as input for the Bussi-NPT equilibration (and for the NVE diagnostic branch).

10. **Short NVE numerical-stability diagnostic (09A)**
   - 2 ps NVE diagnostic run.
   - Endpoint: `02_accepted_stage_states/nve_2ps_diagnostic/`
   - **DIAGNOSTIC ONLY — NOT USED AS PRODUCTION INPUT.**
   - Total-energy drift was not available from the installed output format.

11. **Bussi-NPT equilibration (10B)**
   - 100 ps Bussi-NPT attempted; accepted scientific endpoint is **80 ps**.
   - Endpoint: `02_accepted_stage_states/bussi_npt_80ps/`
   - Restart header: `2586 102.6200000000 79999`
   - Used as input for production Segment 01.

12. **Final NPT production**
    - **Segment 01 (11A)**: 200 ps production attempted, interrupted at 6 ps by an unexpected **laptop/system restart**.
      - Accepted: 0–6000 steps (102.720–108.620 ps).
      - Endpoint: `02_accepted_stage_states/production_segment01_6ps/`
    - **Segment 02 (11B)**: 4 ps fresh continuation from the synchronized 6000-step restart.
      - Endpoint: `02_accepted_stage_states/final_production_10ps/`
      - Final header: `2586 112.6200000000 3999`
    - **Total accepted production**: 6 ps + 4 ps = **10 ps**.
    - The unsynchronized steps **6100, 6200, and 6300** from Segment 01 are excluded from analysis. Step **6000** is the accepted synchronized endpoint.

13. **Thermodynamic / structural analysis**
    - Primary analysis window: 107.720–112.620 ps (50 records).
    - Per-frame PBC minimum image used for TIP3P geometry.
    - Intermolecular RDF normalized with per-frame box volumes, atom-axis counts, and correct same-molecule exclusions.
    - All analysis outputs are regenerated by `06_protocol_and_scripts/reproduce_final_analysis_from_package.py`.

## Key settings for final Bussi-NPT equilibration and production

- Thermostat: middle_langevin, tau = 1.0 ps
- Barostat: bussi_barostat, tau = 1.0 ps, isotropic
- Target temperature: 300 K
- Target pressure: 1.0 bar
- Cutoff: 8 Å
- Water constraints: SETTLE initialized at runtime (command requested SHAKE)

## Important branch logic

The final production starts from the **accepted NPT state** (Bussi-NPT 80 ps), not from the NVE diagnostic endpoint. The NVE run is retained only as diagnostic evidence.

## Important caveats

- The production is segmented due to a laptop/system restart.
- Stochastic continuity across the restart is not claimed.
- Only ensemble-level practical analysis is reported.
- Total production is only 10 ps; all statistics are limited by short sampling.
- The final accepted intermolecular RDF is `04_analysis_data/rdf_intermolecular_normalized.csv`.
