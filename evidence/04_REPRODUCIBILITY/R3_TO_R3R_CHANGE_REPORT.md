# R3 to R3R change report

R3R is a documentation/provenance/build-safety freeze polish. The following are the only intended package-internal changes relative to R3:

- `README.md` — neutral title and `Package version: R3R`.
- `00_PROJECT_OVERVIEW/FINAL_PROJECT_SUMMARY.md` — exact accepted H-H feature wording.
- `00_PROJECT_OVERVIEW/SOURCE_PROVENANCE.json` — explicit common-start, T1 input-start, and T4 step-3000 path/hash records.
- `04_REPRODUCIBILITY/build_final_tip3p_project_r3.py`, `validate_final_tip3p_water_project_package_r3.py`, `package_final_tip3p_water_project_r3.py` — removed as superseded R3 closure scripts.
- `04_REPRODUCIBILITY/build_final_tip3p_project_r3r.py`, `validate_final_tip3p_water_project_package_r3r.py`, `package_final_tip3p_water_project_r3r.py` — new strict R3R closure scripts.
- `04_REPRODUCIBILITY/R3_TO_R3R_CHANGE_REPORT.md` — this report.
- `FINAL_PACKAGE_MANIFEST_SHA256.csv` and `FINAL_PACKAGE_VALIDATION.json` — regenerated R3R metadata.

No trajectory, box, mdout, NPZ, CSV scientific output, PNG, R7R-derived evidence, T5R1R2-derived data, or accepted numerical result was changed.
