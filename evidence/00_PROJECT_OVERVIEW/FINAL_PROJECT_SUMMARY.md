# Final TIP3P Water 300 K / 273 K Project Package — COMPLETE

Assembly date: 2026-09-22. **Assembly only — no SPONGE run, no MD rerun, no
scientific recomputation.** Every content file is byte-identical to its
accepted source package (per-file sha256 verified during copy; see
`SOURCE_PROVENANCE.json` and `FINAL_PACKAGE_MANIFEST_SHA256.csv`).

## Sections

| section | origin | files |
|---|---|---|
| `00_PROJECT_OVERVIEW/` | base package `00_PROJECT_OVERVIEW/` (unchanged) + base root bookkeeping archived with `BASE_PACKAGE_` prefix + base summary archived as `BASE_PACKAGE_FINAL_PROJECT_SUMMARY.md` + this updated `FINAL_PROJECT_SUMMARY.md` | 8 |
| `01_EXPERIMENT_1_300K/` | base `01_EXPERIMENT_1_ORIGINAL_300K/` (byte-identical) | 108 |
| `02_EXPERIMENT_2_300K_vs_273K/` | base `02_EXPERIMENT_2_TEMPERATURE_COMPARISON/` (byte-identical) | 220 |
| `03_FINAL_DEEP_ANALYSIS/` | base `03_FINAL_RESULTS/` (byte-identical; section renamed, files untouched) | 4 |
| `04_REPRODUCIBILITY/` | base `04_REPRODUCIBILITY/` (byte-identical) | 10 |
| `05_MSD_AND_MOBILITY_ANALYSIS/` | full contents of `PRESENTATION_DISTRIBUTIONS_AND_MSD_FINAL.zip` (accepted MSD/presentation analysis; clean — no caches/wheels/nested zips) | 46 |
| `06_HBOND_NETWORK_VISUALIZATION/` | full contents of `HBOND_NETWORK_VISUALIZATION_FINAL_PACKAGE.zip` (accepted H-bond network visualization, branch 15R; scripts, PDBs, pair lists, provenance, README, validation, FINAL_DECISION, PNGs) | 32 |
| `07_PRESENTATION_ASSETS/` | presentation-ready subset: the 13 `fig_*.png` from (2) + the 4 H-bond render PNGs from (3) + README; 05/06 hold the full analyses, 07 holds the presentation subset | 23 |

Source packages (hashes re-verified at assembly):

1. `FINAL_TIP3P_WATER_300K_273K_PROJECT_PACKAGE_FINAL.zip` — 25,090,778 B, sha256 `82b687d8dcd423e7afc4121db5e6f15c7c28d3c40d60b6b2de7b14314d29afcb` (frozen base; not modified)
2. `PRESENTATION_DISTRIBUTIONS_AND_MSD_FINAL.zip` — 3,917,725 B, sha256 `433f7ae5178005726638256425780df6817cc58e9433240d5baa207993cc7983`
3. `15R_HBOND_NETWORK_VISUALIZATION_PRESENTATION_REPAIR_20260922_181921/HBOND_NETWORK_VISUALIZATION_FINAL_PACKAGE.zip` — 1,280,777 B, sha256 `30fd73bd6d7a5abd71c1643810c917bd50b5f8db092e24b4142c086a2a9d5307`

Section-name mapping from the base package (names only; all file contents
byte-identical): `01_EXPERIMENT_1_ORIGINAL_300K` → `01_EXPERIMENT_1_300K`,
`02_EXPERIMENT_2_TEMPERATURE_COMPARISON` → `02_EXPERIMENT_2_300K_vs_273K`,
`03_FINAL_RESULTS` → `03_FINAL_DEEP_ANALYSIS`. The base package's own root-level
`README.md`, `FINAL_PACKAGE_MANIFEST_SHA256.csv`, and `FINAL_PACKAGE_VALIDATION.json`
are preserved byte-identical in `00_PROJECT_OVERVIEW/` with a `BASE_PACKAGE_`
prefix; the base summary is preserved byte-identical as
`00_PROJECT_OVERVIEW/BASE_PACKAGE_FINAL_PROJECT_SUMMARY.md`. This summary
replaces the base summary at `00_PROJECT_OVERVIEW/FINAL_PROJECT_SUMMARY.md`
(the only base-path file not byte-identical, by instruction; the original is
archived and remains in the frozen base zip).

Not included (by design): superseded/repair branches, the base zip itself,
development/review packages, venvs, caches, wheels, temp files.

## Accepted conclusions added by this package

**MSD / short-time mobility (section 05, accepted package 2):**
300 K shows higher short-time oxygen mobility than 273 K. Mean squared
displacement at 1 ps: **3.414 Å² (300 K) vs 2.380 Å² (273 K)**; at 2 ps:
**6.436 Å² (300 K) vs 4.345 Å² (273 K)**. No converged bulk diffusion
coefficient is claimed.

**H-bond network visualization (section 06, accepted package 3):**
representative frames — frame 7 at 300 K (whole-frame H-bonds: 1109) and
frame 52 at 273 K (whole-frame H-bonds: 1196). The rendered local clusters
are illustrative only; quantitative conclusions (e.g. 2.775±0.040 vs
2.572±0.039 H-bonds/water) come from the full 100-frame analysis. No ice
claim is made.
