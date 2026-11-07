# Publication audit

This note distinguishes the archived project's own validation claims from checks performed while preparing this public repository.

## Selection and scope

- The source `First Experiment/` workspace contains 18,268 files (about 1.85 GB), including dated attempts, repairs, virtual environments, cached dependencies, source audits, and repeated final ZIPs. It is preserved locally and not published wholesale.
- The published `evidence/` directory contains the accepted `FINAL_TIP3P_WATER_300K_273K_PROJECT_PACKAGE_COMPLETE/` package: 452 files (53.3 MB). Only the enclosing directory was shortened for Windows path compatibility; all internal relative paths and bytes are unchanged. The report PDF and presentation PDF/PPTX come from the separately supplied `Final report and presentation/` folder. Only their public filenames were normalized; their bytes are unchanged.
- The package documents that its assembly combined a frozen 300 K/273 K base, accepted MSD/presentation analysis, and accepted hydrogen-bond visualization. Its own validation record reports 7/7 assembly checks. That historical record is included as provenance, not presented as a fresh MD rerun.

## Checks performed for this publication

- Independently compared the package's 451 manifest rows with every actual non-manifest file. Inventory, byte sizes, and SHA-256 hashes matched.
- Parsed all 19 packaged Python files as syntax and all 55 JSON files. This does not validate numerical correctness or portability.
- Checked the supplied report has 24 A4 pages; the presentation has 75 PDF pages and 75 PowerPoint slides. The PowerPoint has no macro parts or external relationships. Inspected representative report and result-slide renderings.
- Compared the report's main temperature, density, hydrogen-bond, and MSD values with the accepted package summary. The report preserves the stated limits on correlated frames, related simulation lineages, short production, the 273 K restart, and diffusion claims.
- Scanned the packaged text for common private-key and token patterns. No matches were found; historical local Windows paths remain in provenance and run logs. This scan is a publication check, not a guarantee that every possible sensitive string was identified.
- Ran [`scripts/verify_package.py`](scripts/verify_package.py) on the assembled public copy.

## Limitations and presentation note

- No SPONGE simulation or full scientific analysis was rerun here. The package's earlier validators and their reports are historical evidence; this audit independently checks file integrity and selected consistency only.
- The report and presentation discuss **apparent short-time** MSD-derived estimates, but the accepted result is a relative mobility comparison. No common fit window met the stated criteria for a converged bulk diffusion coefficient.
- The 300 K and 273 K trajectories are related, about 5 ps each, and densely sampled. Reported standard deviations describe these trajectories, not independent-replicate uncertainty.
- The report's discussion on page 22 contains a duplicated word/phrase after the matched 3.5 Å coordination comparison (`... reorganization) neighbours)`). The supplied final PDF was preserved unchanged so its provenance and source hash remain intact.
- Several historical scripts and provenance records contain absolute paths from the original Windows workstation. Reusing them elsewhere requires inspecting inputs and adapting paths; do not run old stage scripts as a verification command because some launch SPONGE.

## Source artifact SHA-256

| Published file | SHA-256 |
| --- | --- |
| `report/MD_Research_Experiment_Report.pdf` | `5cd982fe633d980977ce91143fb295cb007410d44d681da8531c36bfa3efa8ba` |
| `presentation/MD_Research_Experiment_Presentation.pdf` | `120cbdf2edd0b054323d2e3d979bd4008e8dd9833cf4eade975c859853f3599c` |
| `presentation/MD_Research_Experiment_Presentation.pptx` | `adb3a8bd3ee6ae3b8ea31528704d917ab445e228e8c07e72e9fa8ec7ad60ed38` |
