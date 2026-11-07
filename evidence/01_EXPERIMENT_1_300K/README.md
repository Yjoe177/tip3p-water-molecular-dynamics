# Final MD Project Package R6

Repaired reproducibility/data package for the internship MD project.

## System

- 862 TIP3P water molecules (2586 atoms)
- Verified atom order: O, H1, H2 repeated for each water
- Initial 30 Å cubic box (fluctuating under NPT)
- SPONGE runtime: v2.0.0 2026-02-16 Spring Festive
- Conda package metadata: 2.0.0_alpha
- Force field: TIP3P water with encoded LJ/charge tables, SETTLE water constraints at runtime

## Folder structure

| Folder | Contents |
|---|---|
| `01_system_and_forcefield/` | Raw SPONGE/Xponge input files. See `SYSTEM_INPUT_MANIFEST.md`. |
| `02_final_state/` | Final accepted coordinate and velocity restart at the end of Segment 02 (step 3999, time 112.620 ps). |
| `02_accepted_stage_states/` | Compact set of accepted endpoint states for each major stage, including the 05ARR `warm_25K_continuation` state. |
| `03_preproduction_equilibration_80ps/` | Accepted 80 ps Bussi-NPT equilibration raw data and restart. |
| `03_production_trajectory/segment01_6ps/` | Accepted 6 ps Segment 01 production; interrupted by laptop/system restart. |
| `03_production_trajectory/segment02_4ps/` | Accepted 4 ps Segment 02 production continuation. |
| `04_analysis_data/` | Regenerated analysis outputs (CSV/JSON/MD). |
| `05_figures/` | Report-ready figures. |
| `06_protocol_and_scripts/` | Accepted runners, protocol docs, and the authoritative package-local analysis reproducer. Superseded historical documents are in `historical_superseded/`. |
| `FILE_MANIFEST_SHA256.csv` | Recursive file manifest (excludes itself). |
| `PACKAGE_INTERNAL_VALIDATION.json` | Internal scientific and package validation results. |

## Inputs, raw results, and analysis outputs

- **Inputs**: `01_system_and_forcefield/` files.
- **Raw results**: trajectory `.dat`/`.box`, `.mdout`, `.mdinfo`, restart `.txt` files in `02_final_state/`, `02_accepted_stage_states/`, `03_preproduction_equilibration_80ps/`, and `03_production_trajectory/`.
- **Analysis outputs**: CSV/PNG/JSON/MD files in `04_analysis_data/` and `05_figures/`.

## Corrected low-temperature provenance chain

The explicit accepted input chain is:

- `04H energy minimization endpoint coordinate` (SHA-256: `255035EA24B59ABED88A6846D9974A84B5A12091386D6CD17038562CA314E65E`)
- **plus** `05AR valid rigid-water 50 K seed velocity` (SHA-256: `C89EB95C26260FBF8B05DCB5451A7164B4099F4FE077CA6C47452FE251E028A4`)
  → `05ARR_start_inputs`
- → `05ARR quench_10K` (200 steps, 10 K target, dt = 0.0001 ps, total 0.02 ps)
- → `05ARR warm_25K` (400 steps, 25 K target, dt = 0.00025 ps, total 0.1 ps)
- → `05ARRR condition_50K`
- → `05ARRR heating-ready 50 K preflight`
- → `06AR heating_300K`
- → `07A nvt_10ps`
- → `08ARRR practical_npt_5ps`

From `practical_npt_5ps` the chain branches explicitly:

**Diagnostic branch (NOT used as production input):**

`practical_npt_5ps` → `09A nve_2ps_diagnostic` — DIAGNOSTIC ONLY

**Production branch:**

`practical_npt_5ps` → `10B bussi_npt_80ps` → `11A production_segment01_6ps` → `11B final_production_10ps`

The 04H energy-minimization **velocity** was **not** used as the low-temperature starting velocity; the 05AR generated 50 K seed velocity was used instead. The 04H velocity is archived for provenance only.

The 05ARR `warm_25K` state is **not** a demonstrated 25 K equilibrium; it is accepted only as the input for the 50 K conditioning stage. The reviewed classification and the `NOT_DEMONSTRATED` exact-25K-equilibration assessment are read directly from the archived `PASS05ARR_REVIEW_RECLASSIFICATION.json` evidence.

## Package-local reproducer

Run the package-local reproducer from the package root:

```bash
python 06_protocol_and_scripts/reproduce_final_analysis_from_package.py
```

This regenerates **all 8 final report figures** and all analysis outputs in `04_analysis_data/` and `05_figures/` using only files contained in the package.

## Final state

- Coordinate: `02_final_state/npt_production_segment02_4ps_rst_coordinate.txt`
- Velocity: `02_final_state/npt_production_segment02_4ps_rst_velocity.txt`
- Header: `2586 112.6200000000 3999`
- Coordinate SHA256: `E6DDAF9DEB248D5076B2AD783843456AB697D8456B1E42B85130D82A57DFAA81`
- Velocity SHA256: `E43EA18C0569294A4FD644C80479AAF855D1737DCE8EA6808FDCBF6D2C71277B`

## Accepted production

- **Segment 01**: 6 ps accepted from `11A` (local steps 100-6000, time 102.720-108.620 ps). The segment was interrupted by an **unexpected laptop/system restart**, not a native SPONGE/runtime failure.
- **Segment 02**: 4 ps fresh continuation from the synchronized 6000-step restart (time 108.720-112.620 ps).
- **Total accepted production**: 6 ps + 4 ps = **10 ps**.
- Step **6000** is the accepted synchronized endpoint. The unsynchronized steps **6100, 6200, and 6300** from Segment 01 are preserved as diagnostic evidence only and excluded from analysis.

## Preproduction equilibration

- Accepted 80 ps Bussi-NPT equilibration from `10B` (steps 0-80,000, time 22.720-102.620 ps).
- The raw data are in `03_preproduction_equilibration_80ps/`.
- Unsynchronized 80,100-80,900 tail excluded.
- This provides the restart used for production Segment 01.
- The packaged console artifact is a **PowerShell transcript wrapper**, not a full SPONGE step log. A full 80 ps SPONGE console output was not found on disk.

## Primary analysis window

The final frozen primary analysis window is **107.720–112.620 ps** (50 records). The record at 107.620 ps belongs to the burn-in window, not the primary window. The primary box window includes the 108.620 ps Segment 01 frame plus all eight Segment 02 frames (9 frames total).

## Correct TIP3P geometry

All intramolecular geometry is computed with the minimum-image convention using the fluctuating per-frame box. The final values are in `04_analysis_data/structure.csv` and the final report.

## Correct RDF result

Use only `04_analysis_data/rdf_intermolecular_normalized.csv` and `05_figures/rdf_intermolecular_normalized.png` for the intermolecular RDF. The first-local-peak analysis is corrected; the O–H intermolecular first local peak is at ~1.85 Å, while a later broader maximum is near ~3.25 Å.

The deprecated folder `04_analysis_data/deprecated_unnormalized_plots/` contains old visualization artifacts. The audit folder `04_analysis_data/audit_history_deprecated_rdfs/` contains the all-pairs RDF (including intramolecular pairs) for reference only.

## Console log distinction

Segment 02 is preserved with a 24-line PowerShell transcript (`npt_production_segment02_4ps_powershell_transcript.log`), not a full SPONGE step console log. Completion evidence is provided by the mdinfo file, the mdout ending at 4000 / 112.620 ps, the synchronized final restart hashes, and the meta.json `exit_code = 0`. A full console output was not found on disk.

## Limitations

- 10 ps total production is very short for liquid water.
- The production is segmented; stochastic continuity is not claimed.
- Pressure estimates are noisy on this timescale.
- RDFs are illustrative only due to only 14 accepted trajectory frames.
- No equilibrium/convergence claims are made.
