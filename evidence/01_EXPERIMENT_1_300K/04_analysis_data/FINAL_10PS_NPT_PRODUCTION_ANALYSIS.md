# Final 10 ps NPT Production Analysis

**Pass:** `11B_npt_production_segment02_4ps_20260815_100551`  
**Analysis date:** 2026-08-17T08:13:22.498363+00:00  
**Final classification:** `FINAL_10PS_PRACTICAL_NPT_PRODUCTION_ANALYSIS_ACCEPTED_WITH_SHORT_SAMPLING_LIMITATION`

## 1. Production validation

This is a **segmented, practical 10 ps NPT production** composed of:
- **Segment 01**: accepted synchronized production from `11A` up to local step 6000 (6 ps). The segment was interrupted by an **unexpected laptop/system restart**, not a native SPONGE/runtime failure.
- **Segment 02**: fresh 4 ps continuation from the synchronized 6000-step restart.

The unsynchronized 6100–6300 tail from Segment 01 (steps 6100, 6200, 6300) was **excluded** from analysis. The laptop-restart segmentation means stochastic continuity is **not** claimed; only ensemble-level practical analysis is reported.

| Item | Status |
|---|---|
| atom_names_exists | True |
| residue_exists | True |
| seg01_box_exists | True |
| seg01_mdout_exists | True |
| seg01_rst_coord_exists | True |
| seg01_rst_vel_exists | True |
| seg01_traj_exists | True |
| seg02_box_exists | True |
| seg02_mdout_exists | True |
| seg02_rst_coord_exists | True |
| seg02_rst_vel_exists | True |
| seg02_traj_exists | True |
| powershell_transcript_exists | True |
| full_console_output_exists | False |
| nan_or_inf_in_key_columns | False |

### 1.2 Restart headers/hashes

| File | Header | SHA256 |
|---|---|---|
| Segment 01 coordinate | `2586 108.6200000000 5999` | B4AC947DF619322B15C6F2FF4728E77664348C29CC741B94F012D7271074477D |
| Segment 01 velocity | `2586 108.6200000000 5999` | FCD42A09943905EF22877E4AC1E92AE0ACD13FF330304E1CD0D02E9F8711667A |
| Segment 02 coordinate | `2586 112.6200000000 3999` | E6DDAF9DEB248D5076B2AD783843456AB697D8456B1E42B85130D82A57DFAA81 |
| Segment 02 velocity | `2586 112.6200000000 3999` | E43EA18C0569294A4FD644C80479AAF855D1737DCE8EA6808FDCBF6D2C71277B |

### 1.3 Record/frame counts and continuity

- Segment 01 accepted mdout records: 60 (accepted through step 6000; excluded diagnostic tail: 6100, 6200, 6300)
- Segment 02 mdout records: 40
- Segment 01 trajectory frames: 6 (expected 6)
- Segment 02 trajectory frames: 8 (expected 8)
- Segment 01 last time: 108.620 ps
- Segment 02 first time: 108.720 ps
- Time continuity gap: 0.100 ps
- NaN/Inf in key columns: False

## 2. Thermodynamic analysis

### 2.1 Full 10 ps, burn-in (102.720–107.620 ps), and primary (107.720–112.620 ps) windows

The frozen primary analysis window is **107.720–112.620 ps** (50 records). The record at 107.620 ps belongs to the burn-in window, not the primary window.

| Window | Records | Time range (ps) | T (K) mean ± SD | P (bar) mean ± SD | ρ (g/cm³) mean ± SD | U (kcal/mol) mean ± SD |
|---|---|---|---|---|---|---|
| full_10ps | 100 | 102.720–112.620 | 299.3675 ± 5.7190  (n=100, min=283.1300, max=312.3100) | -7.4379 ± 427.8098  (n=100, min=-1335.1200, max=873.5500) | 0.9755 ± 0.0018  (n=100, min=0.9726, max=0.9798) | -8212.3229 ± 37.1111  (n=100, min=-8280.8200, max=-8135.6000) |
| burn_in_0_5ps | 50 | 102.720–107.620 | 298.3488 ± 5.6288  (n=50, min=283.1300, max=311.9700) | -24.2448 ± 367.8755  (n=50, min=-739.9800, max=728.3900) | 0.9768 ± 0.0013  (n=50, min=0.9744, max=0.9798) | -8221.1232 ± 38.2282  (n=50, min=-8280.8200, max=-8141.3300) |
| primary_5_10ps | 50 | 107.720–112.620 | 300.3862 ± 5.6816  (n=50, min=287.4700, max=312.3100) | 9.3690 ± 483.5997  (n=50, min=-1335.1200, max=873.5500) | 0.9742 ± 0.0010  (n=50, min=0.9726, max=0.9762) | -8203.5226 ± 34.1046  (n=50, min=-8272.1900, max=-8135.6000) |

### 2.2 Box / volume statistics

| Window | Frames | Time range (ps) | Volume (Å³) mean ± SD |
|---|---|---|---|---|
| full_10ps | 14 | 103.620–112.620 | 26448.9439 ± 45.2645  (n=14, min=26339.3255, max=26496.8124) |
| burn_in_0_5ps | 5 | 103.620–107.620 | 26413.3300 ± 45.6121  (n=5, min=26339.3255, max=26461.7005) |
| primary_5_10ps | 9 | 108.620–112.620 | 26468.7294 ± 32.4972  (n=9, min=26412.9723, max=26496.8124) |

The primary box window includes the 108.620 ps Segment 01 frame and all eight Segment 02 frames; it is **not** defined as Segment 02 only.

### 2.3 Linear trends in primary window

- Temperature slope: -1.7866 K/ps
- Pressure slope: 45.8714 bar/ps
- Density slope: 0.000059 g/cm³/ps
- Potential slope: -16.9147 kcal/mol/ps

## 3. TIP3P intramolecular geometry

All intramolecular geometry calculations use the **minimum-image convention** with the fluctuating per-frame box. These values are averaged over all 14 accepted trajectory frames (Segment 01 + Segment 02).

| Quantity | Mean ± SD | Min | Max | N |
|---|---|---|---|---|
| O–H distance (Å) | 0.957197 ± 0.000047 | 0.957102 | 0.957275 | 24136 |
| H–H distance (Å) | 1.513595 ± 0.000074 | 1.513447 | 1.513717 | 12068 |
| H–O–H angle (°) | 104.490602 ± 0.000091 | 104.490179 | 104.491071 | 12068 |

| Structural check | Observed value | Threshold status |
|---|---:|---|
| Minimum intermolecular O–O distance | 2.457 Å | threshold check: PASS (>2.0 Å) |
| Minimum intermolecular H–H distance | 1.522 Å | threshold check: PASS (>1.0 Å) |
| Minimum intermolecular O–H distance | 1.518 Å | threshold check: PASS (>0.5 Å) |
| H–O–H angle range | 104.490–104.491 ° | threshold check: PASS (90–120°) |

## 4. Radial distribution functions (intermolecular-only)

The intermolecular RDFs are normalized using:
- atom-axis species counts (`coords_a.shape[1]`, `coords_b.shape[1]`),
- per-frame box volumes,
- same-molecule exclusion for O–H and H–H,
- valid target partner counts: O–O = 861, O–H intermolecular = 1722, H–H intermolecular = 1722.

These are **illustrative** due to only 14 accepted trajectory frames.

| Species | First local peak r (Å) | g(r) | First minimum r (Å) | g(r) |
|---|---|---|---|---|
| O–O | 2.75 | 2.607 | 3.45 | 0.931 |
| O–H intermolecular | 1.85 | 1.242 | 2.45 | 0.284 |
| H–H intermolecular | 2.45 | 1.247 | 2.95 | 0.840 |

The O–H intermolecular curve also has a later, broader maximum near **3.25 Å** with g(r) ≈ 1.445. This is labelled as a later/second maximum, not the first local peak.

Large-r (8–10 Å) mean g(r):
- O–O: 0.99970
- O–H: 0.99957
- H–H: 0.99986

Large-r values approach 1 within the tolerance |mean−1| < 0.1: **True**.

## 5. Generated outputs

All analysis outputs and figures are generated by `06_protocol_and_scripts/reproduce_final_analysis_from_package.py` using only files contained in this package. Package-relative paths are used so the package remains understandable after being moved.

## 6. Limitations and caveats

- 10 ps total production is very short for liquid water.
- The production is segmented due to a laptop/system restart; stochastic continuity is not claimed.
- Pressure estimates are noisy on this timescale.
- RDFs are illustrative only due to only 14 accepted trajectory frames.
- No equilibrium/convergence claims are made.
- The 80 ps Bussi-NPT equilibration and the 10 ps production are the accepted scientific endpoints; earlier attempts and superseded planning documents are retained only for provenance.
