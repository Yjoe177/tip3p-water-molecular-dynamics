# Script status

## Current package-local runnable validators/utilities

- `validate_final_tip3p_water_project_package_final.py`: global standalone validator; no-argument operation is strictly read-only.
- `validate_final_deep_analysis_subset.py`: read-only final deep-analysis subset validator.
- `validate_packaged_T1_reference.py`: read-only packaged T1 validator.
- `package_final_tip3p_water_project_final.py`: validates, manifests, packages, and audits R3RF.

## Exact historical apparatus/method snapshots

- `01_300K_MATCHED_REFERENCE/source_snapshots/`: exact T1 apparatus; not package-local validators.
- `04_FINAL_DEEP_ANALYSIS/method_snapshot/`: exact retained method scripts.
- `04_FINAL_DEEP_ANALYSIS/source_snapshots/`: exact old interpretation source snapshot; not user-facing.
- Experiment-1 R7R stage runner scripts are retained byte-identically as authority evidence.

## Scripts that launch SPONGE and must not be run for verification

Historical stage/T1 runner scripts may launch SPONGE and are evidence only. `01_EXPERIMENT_1_ORIGINAL_300K/06_protocol_and_scripts/reproduce_final_analysis_from_package.py` is separately retained as package-local post-processing apparatus; it is not part of final verification.
