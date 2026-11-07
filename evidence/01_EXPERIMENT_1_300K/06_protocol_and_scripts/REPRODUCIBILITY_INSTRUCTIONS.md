# Reproducibility Instructions

From the package root, run:

```bash
python 06_protocol_and_scripts/reproduce_final_analysis_from_package.py
```

This regenerates all analysis outputs and all 8 report figures using only files
contained in the package. No SPONGE is launched. The script is the authoritative
final post-processing script; older scripts in `06_protocol_and_scripts/historical_superseded/`
are retained only for provenance and must not be used for final analysis.

## Manifest staleness warning

Running the reproducer rewrites derived files in `04_analysis_data/` and `05_figures/`.
For archive preservation, keep the original ZIP frozen and extract or copy the package
to a working directory before running the reproducer. After regeneration, the package's
`FILE_MANIFEST_SHA256.csv` will no longer describe those rewritten derived files
byte-for-byte because of timestamps, plotting-library metadata, and tiny environment-specific
floating formatting. Scientific numerical agreement should be validated separately.
