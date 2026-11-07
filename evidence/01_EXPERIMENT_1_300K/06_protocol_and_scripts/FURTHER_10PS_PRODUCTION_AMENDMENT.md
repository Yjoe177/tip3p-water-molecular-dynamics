# Further 10 ps NPT Production Amendment (R6 annotated)

**Amendment ID:** `11B_FURTHER_10PS_PRODUCTION_AMENDMENT`  
**Pass:** `11B_npt_production_segment02_4ps_20260815_100551`  
**Type:** Runtime-driven practical production shortening  
**Status:** `EXECUTED / ACCEPTED`

## 1. Why this further amendment is required

The previously amended 50 ps NPT production target was still estimated to take approximately 106 hours (~4.4 days) of wall time on the available CPU hardware. The original 200 ps production was already reduced to 50 ps in `11A`. This amendment shortens the practical production further, from 50 ps to **10 ps total**, by accepting the already-completed 6 ps Segment 01 and adding only a fresh **4 ps Segment 02**.

## 2. Final execution facts

| Item | Value |
|---|---|
| Total conceptual completed production steps | 10000 |
| Segment 01 completed steps | 6000 |
| Segment 02 local completed steps | 4000 |
| Segment 01 final restart header | `2586 108.6200000000 5999` |
| Segment 02 actual final restart header | `2586 112.6200000000 3999` |
| Total practical production duration | 6 ps + 4 ps = **10 ps** |

**IMPORTANT:** The original planning document stated that Segment 02 would end with a local restart label of `9999`. That was a **pre-run conceptual expectation** based on a non-reset counter. The actual Segment 02 execution reset its local counter and ended with restart label `3999` (step 4000). The actual header `2586 112.6200000000 3999` is the authoritative final state.

## 3. Segment 02 settings

- `-mode NPT`
- `-thermostat middle_langevin`
- `-barostat bussi_barostat`
- `-target_temperature 300`
- `-target_pressure 1.0`
- `-thermostat_tau 1.0`
- `-barostat_tau 1.0`
- `-barostat_update_interval 10`
- `-barostat_isotropy isotropic`
- `-constrain_mode SHAKE` (runtime initialized SETTLE)
- `-cutoff 8`
- `-step_limit 4000`
- `-dt 0.001`
- Output intervals: mdout every 100 steps, trajectory every 500 steps, restart every 1000 steps

## 4. Analysis windows

- Burn-in: 102.720 – 107.620 ps (50 records)
- Primary: 107.720 – 112.620 ps (50 records)
- The 6100–6300 unsynchronized tail from Segment 01 is excluded.

## 5. Limitations

- 10 ps is a short practical production.
- No claim of long-timescale convergence or full equilibrium.
- Pressure and RDF estimates are noisy/illustrative only.
- The production is segmented because of a laptop/system restart.

---

*The untouched historical original of this amendment is preserved in*
`06_protocol_and_scripts/historical_superseded/protocol_documents/FURTHER_10PS_PRODUCTION_AMENDMENT_ORIGINAL.md`.
*This annotated copy is the authoritative final version for the R6 package.*
