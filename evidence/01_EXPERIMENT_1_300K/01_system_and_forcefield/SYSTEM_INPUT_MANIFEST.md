# System and Force-Field Input Manifest

This folder contains the exact SPONGE/Xponge system input files used for the
accepted final NPT production run. The files are copied without modification.

## System

- 862 TIP3P water molecules (2586 atoms)
- Verified atom order: O, H1, H2 repeated for each water molecule
- Initial 30 Å cubic box, fluctuating under NPT

## Files

| File | Purpose |
|---|---|
| `water_30A_randomized_atom_name.txt` | Per-atom names: O, H1, H2 in water order. |
| `water_30A_randomized_atom_type_name.txt` | Lennard-Jones atom type names for each atom. |
| `water_30A_randomized_bond.txt` | Bond / constraint geometry parameters. At runtime the production simulation initialized 862 rigid water triangles via SETTLE. |
| `water_30A_randomized_charge.txt` | SPONGE/Xponge encoded partial charge values (O ≈ -15.1974, H ≈ +7.5987). These are the encoded form of the TIP3P partial charges; they correspond to physical -0.834 e / +0.417 e through the SPONGE charge encoding. |
| `water_30A_randomized_coordinate.txt` | Reference / initial atomic coordinates in the 30 Å box. |
| `water_30A_randomized_exclude.txt` | Nonbonded exclusion list (1-2 and 1-3 pairs). |
| `water_30A_randomized_LJ.txt` | SPONGE/Xponge encoded Lennard-Jones coefficient tables for the 2 LJ types plus per-atom LJ type indices. |
| `water_30A_randomized_mass.txt` | Atomic masses used for thermostat and kinetic energy. |
| `water_30A_randomized_residue.txt` | Residue-size / topology structure: header "2586 862" followed by 862 entries of 3 atoms (one water residue each). |
| `water_30A_randomized_resname.txt` | Residue names. |

## Runtime constraints

The production command requested `-constrain_mode SHAKE`, but the SPONGE runtime
initialized all 862 waters with SETTLE (rigid triangles). SHAKE was NOT initialized.
The final accepted constraint algorithm for the reported production is therefore SETTLE.

## SPONGE version

- Runtime banner: SPONGE v2.0.0 2026-02-16 Spring Festive
- Conda package metadata: 2.0.0_alpha (see repodata in the project environment audit)

## Command-line usage

SPONGE is invoked with a common prefix:

```text
-default_in_file_prefix water_30A_randomized
```

No separate PME grid or topology file is required; SPONGE reads the above text files directly.
