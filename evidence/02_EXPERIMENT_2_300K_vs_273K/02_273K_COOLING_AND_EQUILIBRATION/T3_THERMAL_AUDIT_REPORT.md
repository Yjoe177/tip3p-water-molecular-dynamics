# T3 Thermal Audit — 273 K NPT Equilibration (checkpoint 2 trailing T ≈ 278.9 K vs target 273 K)

Date: 2026-08-28. Scope: audit only; no SPONGE launch; no production; no physics changes.

## Verdict

**NO_CONFIGURATION_PROBLEM__1PS_EXTENSION_RECOMMENDED**

## 1. Target temperature verification (all accepted 273 K segments)

`target temperature is 273.00 K` appears in the mdinfo of all four segments
(stage03_273K, checkpoint01, checkpoint02, checkpoint02_resume — 4/4), and the
recorded Terminal Commands / runner scripts pass `-target_temperature 273`
throughout (`RUN_273K_COOLING.ps1`, `RUN_273K_EQUILIBRATION_CHECKPOINT.ps1`,
`RUN_273K_EQUILIBRATION_CHECKPOINT02.ps1`, `RUN_273K_EQUILIBRATION_CHECKPOINT02_RESUME.ps1`).
The thermostat was at 273 K for the entire accepted 273 K chain (t = 118.62 → 123.620 ps).

## 2. mdout parsing

The validator (`05_273K_equilibration_checkpoint02/validate_273K_equilibration_checkpoint02_segmented.py`)
locates the header line, builds a column-name → index map, and reads
`temperature` by name (column 3), not by fixed offset. Re-parsing all 99 records
independently reproduces the reported trailing statistics:
last 1 ps = 278.96 ± 2.93 K (n = 19), last 0.5 ps = 278.45 ± 2.76 K (n = 10).
Parsing is correct.

## 3. SPONGE temperature / DoF treatment (source check, SPONGE 1.2 branch, Xia-Yijie/SPONGE)

- Reported temperature: `T = 2·Σ(½m·v²) / (kB · freedom)` (`MD_core.cu`, `Get_Atom_Temperature`).
- `freedom = 3·N_atoms` minus `constrain_pair_numbers` (`constrain.cu`, `Initial_Constrain`).
  mdinfo shows `constrain pair number is 2586` (= 3 per water), so
  `freedom = 7758 − 2586 = 5172 = 6 dof per rigid water` — the correct
  constrained count for SETTLE TIP3P. SETTLE.cu does not modify `freedom`.
- Any DoF misdefinition would shift the reported T by a large factor
  (e.g. 3N vs 3N−3N_mol gives 182 K or 409 K), not a 2% offset, and the sign of
  any realistic miscount is opposite to the observed upward bias.
- The middle-Langevin thermostat applies per-atom Ornstein–Uhlenbeck noise
  (`sart_gamma = sqrt((1−exp(−2γdt))·T·kB)`, `Middle_Langevin_MD.cu`); its
  fluctuation–dissipation balance targets 273 K per Cartesian component with no
  DoF-count dependence.

Caveat: source audit is against the public 1.2 branch; the installed binary is
SPONGE v2.0.0 (2026-02-16). The matching mdinfo fields (`constrain pair number`,
`target temperature`) are consistent with this behaviour. No evidence of a
temperature-definition offset.

## 4. Chronological 0.5 ps block means (all 99 accepted 273 K records)

| block (ps)        | n  | T mean (K) | PE mean (kcal/mol) | density (g/cm³) |
|-------------------|----|-----------|--------------------|-----------------|
| 118.62–119.12     | 10 | 286.75    | −8346.0            | 0.9744 |
| 119.12–119.62     | 10 | 282.26    | −8375.4            | 0.9748 |
| 119.62–120.12     | 10 | 279.59    | −8420.8            | 0.9745 |
| 120.12–120.62     | 10 | 278.42    | −8430.9            | 0.9750 |
| 120.62–121.12     | 10 | 280.85    | −8459.9            | 0.9751 |
| 121.12–121.62     | 10 | 283.57    | −8457.6            | 0.9752 |
| 121.62–122.12     | 10 | 277.30    | −8470.7            | 0.9745 |
| 122.12–122.62     | 10 | 276.68    | −8467.1            | 0.9748 |
| 122.62–123.12     |  9 | 279.53    | −8452.5            | 0.9748 |
| 123.12–123.62     | 10 | 278.45    | −8496.3            | 0.9743 |

Post-transient (t ≥ 119.62 ps) trends on block means:
- Temperature: −0.51 K/ps, t = −0.73 (n = 8) — NOT significant; statistically plateaued at ≈ 278–279 K.
- Potential energy: −16.0 kcal/mol/ps, t = −3.70 — significant continuing downward drift.
- Density: ≈ 0 drift (0.9743–0.9752), t = −0.98 — flat (NPT).

## 5. Interpretation

Temperature is not still relaxing downward (statistically flat), but potential
energy is still decreasing significantly and roughly linearly (~ −16 kcal/mol/ps).
The system is still structurally relaxing; that relaxation continuously releases
heat, which the γ = 1 ps⁻¹ Langevin bath dissipates. The observed ~6 K elevation
is consistent with a quasi-steady-state balance between relaxation heating and
thermostat dissipation, not with a configuration, parser, or temperature-definition
error. The correct remedy is more sampling at unchanged physics — not forcing
T down via tau/field/constraint/timestep changes.

## 6. Prepared action (not executed)

`06_273K_equilibration_extension_1ps/RUN_273K_EQUILIBRATION_EXTENSION_1PS.ps1`
(T3E1): 1 ps (1000 × 0.001 ps) NPT continuation at 273 K, identical physics and
intervals, fresh documented seed 20260905, from the validated synchronized
restart pair `2586 123.6200000000 499` (SHA-pinned, read-only source). Fail-closed;
supports `-PreflightOnly`. NOT launched. SPONGE was not started during this audit.
