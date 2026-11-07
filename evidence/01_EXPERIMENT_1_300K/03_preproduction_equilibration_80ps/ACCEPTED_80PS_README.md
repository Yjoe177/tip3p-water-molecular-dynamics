# Accepted 80 ps Bussi-NPT Equilibration

This folder contains the accepted scientific data from the 10B 80 ps Bussi-NPT
pre-production equilibration.

- Classification: `BUSSI_NPT_EQUILIBRATION_SEGMENT01_80PS_ACCEPTED_RUNTIME_STALL_AFTER_RESTART`
- Accepted steps: 0 – 80,000 (80 ps)
- Accepted mdout records: 800 (step 100 through 80,000)
- Absolute time range: 22.720 – 102.620 ps (production starts at cumulative 102.620 ps)
- Restart at step 80,000: `restart_80000_coordinate.txt` / `restart_80000_velocity.txt`
- Restart header: `2586 102.6200000000 79999`
- Coordinate SHA256: `7AB6E6C7EFFF0BE8E5518D67993C40ACE8CEB5C4B9A1477A96F8C607FD3155BA`
- Velocity SHA256: `B4D10C5061547E6E6B9960C4BC2559A3F0A0544174C4F30E6C6634744C0766DC`

The unsynchronized 80,100–80,900 tail (9 mdout records) is preserved only in the
_full_evidence.mdout file and must NOT be used as scientific data.

These data are sufficient to regenerate the 80 ps equilibration density and
temperature plots in `05_figures/`.

The packaged `bussi_npt_equilibration_segment01_80ps_powershell_transcript.log` is a
PowerShell transcript wrapper, not a full SPONGE step console log. A full 80 ps
SPONGE console output was not found on disk.
