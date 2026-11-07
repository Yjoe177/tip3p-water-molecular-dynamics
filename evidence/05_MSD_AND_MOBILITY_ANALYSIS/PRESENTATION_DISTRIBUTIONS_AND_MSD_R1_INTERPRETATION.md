# Presentation MSD R1 scientific interpretation

## Presentation-ready wording

**Robust result:** 300 K water has higher short-time oxygen mobility than 273 K water over matched lag times in these trajectories.

**Conditional result:** No common window passes the prospective rule, so no primary numerical diffusion estimate is claimed. These values must be labelled **apparent short-time oxygen self-mobility / effective diffusion estimates under the simulated conditions**. The candidate window is an approximately linear short-time regime, not a proven long-time diffusive regime.

**Not claimed:** converged bulk self-diffusion coefficients, experimental diffusion coefficients, long-time transport convergence, statistically independent uncertainty, or transport coefficients free of thermostat and finite-size effects.

## Method and diagnostics

Oxygen coordinates were minimum-image unwrapped within each continuous segment. The frame-wise mean displacement of all 862 unwrapped oxygen references relative to segment frame 0 was then subtracted from every oxygen. The 273 K correction was applied independently to the 60-frame and 40-frame segments. No primary displacement crosses the restart boundary. The concatenated curve remains a structural sensitivity only and makes no RNG-continuity claim.

All six matched candidate windows were evaluated prospectively using positive slope, R² ≥ 0.995, α in [0.9, 1.1], curvature ratio ≤ 0.1, local interval-slope CV ≤ 0.2, 21 lag points, at least 20 valid 273 K origins, and contribution from both 273 K segments throughout the window. R² was not used alone. Durbin-Watson values are descriptive only: strong lag-to-lag residual correlation is expected because adjacent MSD points are correlated.

After 1.95 ps the 40-frame 273 K segment cannot contribute to longer-lag MSD points; this is why later candidate windows fail the both-segments rule.

## Limitations

The trajectories are only about 5 ps. Adjacent lag points are correlated, and overlapping time origins are also correlated. SD across origin means is a descriptive spread; `naive_SE_across_correlated_time_origins_A2` is not an independent-sample uncertainty. The periodic box is only about 30 Å and no finite-size hydrodynamic correction is applied. Both dynamics were generated under the same Middle-Langevin/NPT setup, and thermostat/friction can affect dynamical transport. Therefore, fitted values are not converged bulk self-diffusion constants and must not be compared directly with experiment without separate authorization.
