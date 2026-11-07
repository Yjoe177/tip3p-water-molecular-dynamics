# Build Provenance for FINAL_MD_PROJECT_PACKAGE_R7

## Source

R7 was built from the accepted, scientifically frozen R6 package:

- Source package: `C:\Users\Acer\Desktop\Chemistry Research Intern\First Experiment\FINAL_MD_PROJECT_PACKAGE_R6`
- Source ZIP: `C:\Users\Acer\Desktop\Chemistry Research Intern\First Experiment\FINAL_MD_PROJECT_PACKAGE_R6.zip`
- Source ZIP SHA-256: `4833405121E30D830F7056F366583C2F2382A5965FA6B5DC356FC6B3EABF3D83`
- Source ZIP CRC test: PASS
- Source manifest rows: 142
- Source manifest mismatches: 0
- Source scientific values verified: YES

## Builder

The canonical R7 builder is `build_final_package_r7.py` in the project root.
A byte-identical copy is archived inside the R7 package at:

`06_protocol_and_scripts/build_final_package_r7.py`

It is a **standalone** script that copies R6, applies only documentation and
provenance fixes, verifies scientific immutability, and regenerates validation.

## Historical development patches

The previous `patch_r*.py` and `patch_r6_*.py` files and the R2-R6 builders are
preserved in this package under:

`06_protocol_and_scripts/historical_superseded/development_patches/`

They are **historical development intermediates only** and are **not** the
canonical method for reproducing R7. The canonical method is to run the
standalone `build_final_package_r7.py` from the project root.

## R6 patch replay status

The R6 final builder was developed through a sequence of patch files. Those
patches are archived for transparency, but the final authoritative R6 builder
is the file `build_final_package_r6.py` whose SHA-256 is recorded above. R7 does
not depend on replaying those patches; it depends only on the accepted R6 package.

## Changes from R6 to R7

R7 makes **no scientific changes**. The only changes are:

1. Corrected low-temperature provenance description in `README.md` and
   `FINAL_ACCEPTED_PROTOCOL.md` to show the explicit mixed-origin 05ARR start
   inputs, the `quench_10K` stage, and the NVE diagnostic branch.
2. Added explicit root provenance transition in
   `06_protocol_and_scripts/PROVENANCE_CHAIN_VALIDATION.json`.
3. Added explicit warm_25K command/path-resolution validation.
4. Added `BUILD_PROVENANCE.md` and `R6_TO_R7_SCIENTIFIC_IMMUTABILITY.json`.
5. Archived R2-R6 builders and development patches under
   `historical_superseded/development_patches/`.
6. Regenerated `R7_ZIP_VALIDATION.json`, `PACKAGE_INTERNAL_VALIDATION.json`,
   `FILE_MANIFEST_SHA256.csv`, and the ZIP sidecar.

Generated: 2026-08-17T08:12:27.477512+00:00


## R7R correction note

R7R was created from the accepted R7 package because the R7 manifest was generated
before `PACKAGE_INTERNAL_VALIDATION.json` was updated, leaving one stale manifest row.
R7R finalizes all package files before regenerating the manifest, then verifies every
row against both the on-disk file and the ZIP bytes. No scientific file or analysis
output was changed.

R7R canonical builder: `06_protocol_and_scripts/build_final_package_r7r.py`.
Corrected R7 canonical builder: `06_protocol_and_scripts/build_final_package_r7.py`.

R7R built at: 2026-08-17T08:56:18.015019+00:00
