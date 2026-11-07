# 15R — H-bond network visualization: presentation repair

Presentation-only repair of `15_HBOND_NETWORK_VISUALIZATION_20260922_104453`.
No MD was rerun, the selected frames are unchanged (300 K frame 7, N_HB=1109;
273 K frame 52, N_HB=1196), and no accepted scientific result was modified.
READ-ONLY on all source data; SPONGE never run.

## What changed vs branch 15

1. **Dashes now connect donor-H to acceptor-O.** In branch 15 the dashed
   H-bond indicators ran donor-O→acceptor-O. Here, for each accepted
   intra-cluster H-bond event the specific donor-water hydrogen satisfying the
   angle criterion was recomputed from the raw trajectory, and dashes run from
   that H atom to the acceptor O. If both donor hydrogens satisfied the
   criterion, the one with the larger angle would be drawn (this did not occur:
   0 dual-H events in both frames). The original O···O pair lists are archived
   unchanged in `provenance/archive_original_pairs/`.
2. **Tighter framing** — the cluster fills more of the canvas (zoom buffer 0.1;
   identical policy for both panels, same orientation policy as before:
   `orient` + fixed rotation turn x 20 / y −15, centred on the central oxygen).
3. **Captions corrected** to report whole-frame counts:
   "300 K — frame 7, t = 113.020 ps — Whole-frame H-bonds: 1109" /
   "273 K — frame 52, t = 127.270 ps — Whole-frame H-bonds: 1196", plus a footer
   on every panel and the side-by-side: "Illustrative local snapshots;
   quantitative conclusions use all 100 frames."

## H-bond criterion (verbatim)

> donor–acceptor O···O distance < 3.5 Å AND angle O_donor–H···O_acceptor > 150°
> (vertex at H), acceptor on a different molecule than donor.

## Explicit connectivity disclaimer

The **drawn local clusters have 15 drawn H-bonds at 300 K and 14 at 273 K** —
the 273 K snapshot cluster is *not* more connected, and nothing in these images
should be read as showing that. The quantitative statement that the 273 K branch
has a more populated geometric H-bond network comes from the full 100-frame
accepted analysis (2.775±0.040 vs 2.572±0.039 H-bonds/water; 1195.9±17.2 vs
1108.7±17.0 H-bonds/frame), not from these single frames. Cluster membership
depends on the highest-degree water in the frame, not on a matched statistic.

## Disclaimers (unchanged from branch 15)

- **No ice-formation claim** is made or implied.
- A single snapshot per temperature carries **no statistical representativeness**.
- Adjacent frames are correlated (0.05 ps spacing); the selected frames are
  illustrative picks (count closest to the branch mean), not independent samples.
- Qualitative/local visualization only, supporting the accepted quantitative
  H-bond analysis of closure branch
  `12_TEMPERATURE_COMPARISON_300K_273K/11_T5R1R2_FINAL_EXTERNAL_REVIEW_CLOSURE`.

## Renderer

PyMOL open source 3.2.0a0 (PyPI wheel) from the branch-15 local venv
(`../15_HBOND_NETWORK_VISUALIZATION_20260922_104453/venv`), which was created
because VMD is not installed and the user approved PyMOL on 2026-09-22. The
wheel's missing native DLLs live in that venv's `pymol_dlls/` (see branch-15
README); this repair reuses that venv unchanged.

## Reproduce

```bash
cd 15R_HBOND_NETWORK_VISUALIZATION_PRESENTATION_REPAIR_20260922_181921
/c/Users/Acer/miniconda3/envs/sponge-cpu/python.exe scripts/derive_h2o_pairs.py
OLDV=../15_HBOND_NETWORK_VISUALIZATION_20260922_104453/venv/Scripts/python.exe
$OLDV scripts/render.py
$OLDV scripts/label_and_compose.py
$OLDV validation/validate_repair.py
```

## File inventory

- `scripts/derive_h2o_pairs.py` — donor-H→acceptor-O pair derivation (frozen sponge-cpu python)
- `scripts/render.py` — PyMOL renderer (branch-15 venv)
- `scripts/label_and_compose.py` — captions/footer/side-by-side (Pillow)
- `analysis/selection_results.json` — carried over unchanged from branch 15
- `analysis/cluster_{300K,273K}.pdb` — carried over unchanged
- `analysis/hbonds_{300K,273K}.txt` — original O···O lists (carried over, unchanged)
- `analysis/hbonds_{300K,273K}_HtoO.txt` — new donor-H→acceptor-O lists
- `analysis/h2o_pairs_report.json` — per-event H assignment, angles, counts
- `provenance/` — input hashes, branch-15 provenance, archived original pair lists
- `renders/` — final PNGs (main, zoom, labeled, side-by-side)
- `validation/validate_repair.py` + `validation/VALIDATION.json` — PASS
- `HBOND_NETWORK_VISUALIZATION_FINAL_PACKAGE/` + `.zip` + manifest + sha256
- `FINAL_DECISION.json`
