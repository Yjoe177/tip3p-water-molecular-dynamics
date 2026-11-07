"""External-review R1 repair: analysis only; never invokes SPONGE or MD."""
from __future__ import annotations

import csv
import hashlib
import json
import math
import shutil
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
WORK = HERE.parent
OLD = WORK / "13_PRESENTATION_DISTRIBUTIONS_AND_MSD"
PKG = WORK / "FINAL_TIP3P_WATER_300K_273K_PROJECT_PACKAGE_FINAL"
ZIP = WORK / "FINAL_TIP3P_WATER_300K_273K_PROJECT_PACKAGE_FINAL.zip"
OUT = HERE / "outputs"
EXPECTED_ZIP = "82B687D8DCD423E7AFC4121DB5E6F15C7C28D3C40D60B6B2DE7B14314D29AFCB"
EXPECTED_HB = "2D84D077B9067BACD7170A6CBB7FB524144FE6F4519DE9DDBFCFE5A7A4DCB58F"
DT = 0.05
N_ATOMS = 2586
N_WATERS = 862
WINDOWS = [(0.50, 1.50), (0.75, 1.75), (1.00, 2.00),
           (1.25, 2.25), (1.50, 2.50), (1.75, 2.75)]

# Prospective common-window rule, defined before any result is selected.
RULE = {
    "positive_slope": True,
    "minimum_R2": 0.995,
    "alpha_range_inclusive": [0.90, 1.10],
    "maximum_curvature_ratio": 0.10,
    "maximum_local_slope_CV": 0.20,
    "minimum_lag_points": 21,
    "minimum_273K_valid_origins_at_any_lag": 20,
    "require_both_273K_segments_contribute_through_window": True,
    "selection": "Choose the earliest common candidate passing every rule for both temperatures; never maximize R2."
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest().upper()


def write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_csv(path: Path, header, rows) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(rows)


def source_map():
    provenance = json.loads((PKG / "00_PROJECT_OVERVIEW/SOURCE_PROVENANCE.json").read_text(encoding="utf-8"))
    verified = {}
    roles = {}
    for temp, entries in provenance["immutable_deep_raw_sources"].items():
        verified[temp] = []
        roles[temp] = {"trajectory": [], "box": [], "mdout": []}
        for entry in entries:
            path = PKG / entry["package_relative_current_path"]
            actual = sha256(path)
            if actual != entry["sha256"].upper():
                raise RuntimeError(f"Frozen input hash mismatch: {path}")
            verified[temp].append({**entry, "verified_sha256": actual})
            roles[temp][entry["role"]].append(path)
    return verified, roles


def parse_mdout(path: Path):
    lines = [line.split() for line in path.read_text(encoding="utf-8").splitlines() if line.split()]
    if len(lines) < 2:
        raise RuntimeError(f"Empty mdout: {path}")
    header, rows = lines[0], lines[1:]
    if any(len(row) != len(header) for row in rows):
        raise RuntimeError(f"Inconsistent mdout row width: {path}")

    def resolve(name: str):
        candidates = [i for i, field in enumerate(header) if field.casefold() == name.casefold()]
        numeric = []
        for index in candidates:
            try:
                numeric.append((index, np.asarray([float(row[index]) for row in rows], dtype=float)))
            except ValueError:
                pass
        if len(numeric) != 1:
            raise RuntimeError(f"Required mdout field {name!r} is absent or duplicated ambiguously in {path}; numeric candidates={len(numeric)}")
        return numeric[0]

    fields = {}
    indices = {}
    for name in ("temperature", "pressure", "potential", "density"):
        index, values = resolve(name)
        fields[name] = values
        indices[name] = index
    return fields, {"header": header, "resolved_zero_based_indices": indices, "record_count": len(rows),
                    "duplicate_pressure_resolution": "Selected the unique pressure-named column numeric in every row; the other pressure-named column contains nonnumeric overflow markers."}


def load_traj(path: Path, frames: int):
    raw = np.fromfile(path, dtype=np.float32)
    expected = frames * N_ATOMS * 3
    if raw.size != expected:
        raise RuntimeError(f"Trajectory size mismatch for {path}: {raw.size} != {expected}")
    return raw.reshape(frames, N_ATOMS, 3).astype(np.float64)[:, ::3, :]


def load_box(path: Path, frames: int):
    box = np.loadtxt(path, usecols=(0, 1, 2), ndmin=2)
    if box.shape != (frames, 3):
        raise RuntimeError(f"Box shape mismatch for {path}: {box.shape}")
    return box


def unwrap_cartesian(wrapped, boxes):
    unwrapped = np.empty_like(wrapped)
    unwrapped[0] = wrapped[0]
    for frame in range(1, len(wrapped)):
        length = 0.5 * (boxes[frame] + boxes[frame - 1])
        delta = wrapped[frame] - wrapped[frame - 1]
        delta -= length * np.rint(delta / length)
        unwrapped[frame] = unwrapped[frame - 1] + delta
    return unwrapped


def unwrap_fractional_deaffined(wrapped, boxes):
    fractional = wrapped / boxes[:, None, :]
    unwrapped = np.empty_like(wrapped)
    unwrapped[0] = wrapped[0]
    for frame in range(1, len(wrapped)):
        ds = fractional[frame] - fractional[frame - 1]
        ds -= np.rint(ds)
        length = 0.5 * (boxes[frame] + boxes[frame - 1])
        unwrapped[frame] = unwrapped[frame - 1] + ds * length
    return unwrapped


def remove_centroid_drift(unwrapped):
    drift_vectors = unwrapped.mean(axis=1) - unwrapped[0].mean(axis=0)
    corrected = unwrapped - drift_vectors[:, None, :]
    return corrected, drift_vectors


def curve(segments):
    rows = []
    for lag in range(max(len(segment) for segment in segments)):
        origin_means = []
        origins_by_segment = []
        for segment in segments:
            count = max(0, len(segment) - lag)
            origins_by_segment.append(count)
            if count:
                displacement = segment[lag:] - segment[:count]
                origin_means.extend(np.mean(np.sum(displacement * displacement, axis=2), axis=1))
        values = np.asarray(origin_means, dtype=float)
        sd = float(values.std(ddof=1)) if len(values) > 1 else 0.0
        rows.append([lag * DT, float(values.mean()), sd,
                     float(sd / math.sqrt(len(values))) if len(values) > 1 else 0.0,
                     len(values), len(values) * N_WATERS, *origins_by_segment])
    return np.asarray(rows, dtype=float)


def save_curve(name, data, segment_labels):
    header = ["lag_ps", "MSD_A2", "SD_across_time_origin_means_A2",
              "naive_SE_across_correlated_time_origins_A2", "valid_time_origins",
              "oxygen_displacement_samples"] + [f"valid_origins_{label}" for label in segment_labels]
    write_csv(OUT / name, header, data)


def diagnostic(msd, start, end, segment_lengths=None):
    chosen = msd[(msd[:, 0] >= start - 1e-12) & (msd[:, 0] <= end + 1e-12)]
    x, y = chosen[:, 0], chosen[:, 1]
    slope, intercept = np.polyfit(x, y, 1)
    predicted = slope * x + intercept
    residual = y - predicted
    ss_res = float(np.sum(residual ** 2))
    ss_tot = float(np.sum((y - y.mean()) ** 2))
    r2 = 1.0 - ss_res / ss_tot
    alpha, log_intercept = np.polyfit(np.log(x), np.log(y), 1)
    quadratic = np.polyfit(x, y, 2)
    curvature = abs(float(quadratic[0]) * (end - start) / slope)
    interval_slopes = np.diff(y) / np.diff(x)
    local_cv = float(interval_slopes.std(ddof=1) / abs(interval_slopes.mean()))
    dw = float(np.sum(np.diff(residual) ** 2) / ss_res) if ss_res else 2.0
    result = {
        "start_ps": start, "end_ps": end, "n_lag_points": len(x),
        "slope_A2_per_ps": float(slope), "intercept_A2": float(intercept),
        "D_A2_per_ps": float(slope / 6.0), "D_cm2_per_s": float(slope / 6.0e4),
        "R2": float(r2), "residual_RMSE_A2": float(math.sqrt(ss_res / len(x))),
        "Durbin_Watson_descriptive_only": dw,
        "alpha_loglog": float(alpha), "loglog_intercept": float(log_intercept),
        "curvature_ratio": curvature, "local_interval_slope_CV": local_cv,
        "valid_origin_count_range": [int(chosen[:, 4].min()), int(chosen[:, 4].max())],
        "strong_lag_to_lag_residual_correlation": bool(dw < 1.0),
    }
    if segment_lengths:
        origin_ranges = []
        for length in segment_lengths:
            counts = [max(0, length - int(round(t / DT))) for t in x]
            origin_ranges.append([min(counts), max(counts)])
        result["valid_origin_count_ranges_by_273K_segment"] = origin_ranges
        result["both_273K_segments_contribute_through_window"] = bool(origin_ranges[1][0] > 0)
    return result


def passes(item, is_273=False):
    checks = {
        "positive_slope": bool(item["slope_A2_per_ps"] > 0),
        "R2": bool(item["R2"] >= RULE["minimum_R2"]),
        "alpha": bool(RULE["alpha_range_inclusive"][0] <= item["alpha_loglog"] <= RULE["alpha_range_inclusive"][1]),
        "curvature": bool(item["curvature_ratio"] <= RULE["maximum_curvature_ratio"]),
        "local_slope_plateau": bool(item["local_interval_slope_CV"] <= RULE["maximum_local_slope_CV"]),
        "lag_points": bool(item["n_lag_points"] >= RULE["minimum_lag_points"]),
        "valid_origins": bool(item["valid_origin_count_range"][0] >= RULE["minimum_273K_valid_origins_at_any_lag"]),
    }
    if is_273:
        checks["both_273K_segments"] = item["both_273K_segments_contribute_through_window"]
    item["prospective_checks"] = checks
    item["passes_prospective_rule"] = all(checks.values())
    return item


def interpolate(msd, lag):
    return float(np.interp(lag, msd[:, 0], msd[:, 1]))


def copy_accepted_distributions():
    names = ["temperature", "density", "potential", "box_volume", "pressure", "hbond_count", "hbonds_per_water"]
    copied = []
    for name in names:
        for suffix in ("raw_values.csv", "distribution.csv"):
            source = OLD / "outputs" / f"{name}_{suffix}"
            shutil.copy2(source, OUT / source.name)
            copied.append(source.name)
        source = OLD / "outputs" / f"fig_{name}_distribution.png"
        shutil.copy2(source, OUT / source.name)
        copied.append(source.name)
    return names, copied


def accepted_distribution_verification(thermo300, thermo273, box300, box273, hb):
    old = json.loads((OLD / "PRESENTATION_DISTRIBUTIONS_AND_MSD_RESULTS.json").read_text(encoding="utf-8"))
    arrays = {
        "temperature": (thermo300["temperature"], thermo273["temperature"]),
        "density": (thermo300["density"], thermo273["density"]),
        "potential": (thermo300["potential"], thermo273["potential"]),
        "box_volume": (np.prod(box300, axis=1), np.prod(box273, axis=1)),
        "pressure": (thermo300["pressure"], thermo273["pressure"]),
        "hbond_count": (hb["N_HB_300K"], hb["N_HB_273K"]),
        "hbonds_per_water": (hb["HB_per_water_300K"], hb["HB_per_water_273K"]),
    }
    report = {}
    for name, (a, b) in arrays.items():
        expected = old["distributions"][name]
        values = {"n": {"300K": len(a), "273K": len(b)},
                  "mean": {"300K": float(a.mean()), "273K": float(b.mean())},
                  "sd": {"300K": float(a.std(ddof=1)), "273K": float(b.std(ddof=1))}}
        for category in ("n", "mean", "sd"):
            for temp in ("300K", "273K"):
                if not np.isclose(values[category][temp], expected[category][temp], rtol=0, atol=1e-12):
                    raise RuntimeError(f"Accepted distribution changed: {name} {category} {temp}")
        report[name] = values
    return report


def plot_results(msd300, msd273, fit300, fit273, common_selected,
                 common_fit300, common_fit273, seg1, seg2,
                 uncorrected300, uncorrected273, fractional300, fractional273,
                 concatenated273):
    common_max = 2.95
    fig, ax = plt.subplots(figsize=(7.4, 4.8))
    for data, color, label in [(msd300, "red", "300 K"), (msd273, "blue", "273 K restart-safe")]:
        mask = data[:, 0] <= common_max + 1e-12
        ax.plot(data[mask, 0], data[mask, 1], color=color, linewidth=2.2, label=label)
    if common_selected is not None:
        for fit, color, yplace in [(common_fit300, "darkred", 0.98), (common_fit273, "navy", 0.77)]:
            x = np.asarray([fit["start_ps"], fit["end_ps"]])
            ax.plot(x, fit["slope_A2_per_ps"] * x + fit["intercept_A2"], "--", color=color, linewidth=2)
            label = (f"{color.replace('darkred','300 K').replace('navy','273 K')}: {fit['start_ps']:.2f}-{fit['end_ps']:.2f} ps\n"
                     f"slope={fit['slope_A2_per_ps']:.3f} Å²/ps, apparent D={fit['D_cm2_per_s']:.3e} cm²/s\nR²={fit['R2']:.5f}")
            ax.text(0.03, yplace, label, transform=ax.transAxes, va="top", color=color, fontsize=8.5)
    ax.set(xlabel="Lag time (ps)", ylabel="Oxygen MSD (Å²)", xlim=(0, common_max))
    ax.grid(alpha=0.18); ax.legend(frameon=False, loc="lower right"); fig.tight_layout()
    fig.savefig(OUT / "fig_msd_comparison_repaired.png", dpi=220); plt.close(fig)

    fig, axes = plt.subplots(2, 2, figsize=(10, 7.5))
    starts = [x[0] for x in WINDOWS]
    for diagnostics, color, label in [(fit300, "red", "300 K"), (fit273, "blue", "273 K")]:
        axes[0, 0].plot(starts, [x["slope_A2_per_ps"] for x in diagnostics], "o-", color=color, label=label)
        axes[0, 1].plot(starts, [x["alpha_loglog"] for x in diagnostics], "o-", color=color)
        axes[1, 0].plot(starts, [x["local_interval_slope_CV"] for x in diagnostics], "o-", color=color)
        axes[1, 1].plot(starts, [x["curvature_ratio"] for x in diagnostics], "o-", color=color)
    axes[0, 0].set_ylabel("Slope (Å²/ps)"); axes[0, 0].legend(frameon=False)
    axes[0, 1].set_ylabel("Log-log exponent α"); axes[0, 1].axhspan(0.9, 1.1, color="gray", alpha=0.12)
    axes[1, 0].set_ylabel("Local-slope CV"); axes[1, 0].axhline(0.2, color="gray", linestyle="--")
    axes[1, 1].set_ylabel("Curvature ratio"); axes[1, 1].axhline(0.1, color="gray", linestyle="--")
    for ax in axes.flat: ax.set_xlabel("Candidate-window start lag (ps)"); ax.grid(alpha=0.18)
    fig.tight_layout(); fig.savefig(OUT / "fig_msd_fit_diagnostics_repaired.png", dpi=220); plt.close(fig)

    def simple_plot(filename, curves, xmax=2.95):
        fig, ax = plt.subplots(figsize=(7.4, 4.8))
        for data, style, label in curves:
            mask = data[:, 0] <= xmax + 1e-12
            ax.plot(data[mask, 0], data[mask, 1], style, linewidth=2, label=label)
        ax.set(xlabel="Lag time (ps)", ylabel="Oxygen MSD (Å²)", xlim=(0, xmax))
        ax.grid(alpha=0.18); ax.legend(frameon=False); fig.tight_layout(); fig.savefig(OUT / filename, dpi=220); plt.close(fig)

    simple_plot("fig_msd_273K_segment_consistency.png", [(seg1, "b-", "273 K segment 1"), (seg2, "c--", "273 K segment 2")], 1.95)
    simple_plot("fig_msd_COM_drift_sensitivity.png", [(msd300, "r-", "300 K COM-corrected"), (uncorrected300, "r--", "300 K uncorrected"), (msd273, "b-", "273 K COM-corrected"), (uncorrected273, "b--", "273 K uncorrected")])
    simple_plot("fig_msd_NPT_box_scaling_sensitivity.png", [(msd300, "r-", "300 K Cartesian"), (fractional300, "m--", "300 K de-affined"), (msd273, "b-", "273 K Cartesian"), (fractional273, "c--", "273 K de-affined")])
    simple_plot("fig_msd_273K_restart_sensitivity_repaired.png", [(msd273, "b-", "Segmented primary"), (concatenated273, "m--", "Concatenated sensitivity")])


def main():
    if OUT.exists():
        raise RuntimeError(f"Refusing to overwrite existing output directory: {OUT}")
    if sha256(ZIP) != EXPECTED_ZIP:
        raise RuntimeError("Frozen FINAL ZIP hash mismatch")
    OUT.mkdir(parents=True)
    verified, roles = source_map()
    old_manifest = {p.relative_to(OLD).as_posix(): sha256(p) for p in sorted(OLD.rglob("*")) if p.is_file()}

    thermo300, parse300 = parse_mdout(roles["300K"]["mdout"][0])
    parsed273 = [parse_mdout(path) for path in roles["273K"]["mdout"]]
    thermo273 = {name: np.concatenate([item[0][name] for item in parsed273]) for name in thermo300}
    box300 = load_box(roles["300K"]["box"][0], 100)
    box1 = load_box(roles["273K"]["box"][0], 60)
    box2 = load_box(roles["273K"]["box"][1], 40)
    box273 = np.vstack([box1, box2])
    hbpath = PKG / "02_EXPERIMENT_2_TEMPERATURE_COMPARISON/04_FINAL_DEEP_ANALYSIS/outputs/hbond_timeseries.csv"
    if sha256(hbpath) != EXPECTED_HB:
        raise RuntimeError("Frozen H-bond source hash mismatch")
    hb = np.genfromtxt(hbpath, delimiter=",", names=True)
    distribution_check = accepted_distribution_verification(thermo300, thermo273, box300, box273, hb)
    distribution_names, copied_distributions = copy_accepted_distributions()

    wrapped300 = load_traj(roles["300K"]["trajectory"][0], 100)
    wrapped1 = load_traj(roles["273K"]["trajectory"][0], 60)
    wrapped2 = load_traj(roles["273K"]["trajectory"][1], 40)

    u300 = unwrap_cartesian(wrapped300, box300)
    u1 = unwrap_cartesian(wrapped1, box1)
    u2 = unwrap_cartesian(wrapped2, box2)
    c300, drift300 = remove_centroid_drift(u300)
    c1, drift1 = remove_centroid_drift(u1)
    c2, drift2 = remove_centroid_drift(u2)
    f300u, _ = remove_centroid_drift(unwrap_fractional_deaffined(wrapped300, box300))
    f1u, _ = remove_centroid_drift(unwrap_fractional_deaffined(wrapped1, box1))
    f2u, _ = remove_centroid_drift(unwrap_fractional_deaffined(wrapped2, box2))

    primary300 = curve([c300])
    primary273 = curve([c1, c2])
    uncorrected300 = curve([u300])
    uncorrected273 = curve([u1, u2])
    fractional300 = curve([f300u])
    fractional273 = curve([f1u, f2u])
    segment1 = curve([c1])
    segment2 = curve([c2])

    wrappedcat = np.concatenate([wrapped1, wrapped2])
    boxcat = np.vstack([box1, box2])
    ccat, driftcat = remove_centroid_drift(unwrap_cartesian(wrappedcat, boxcat))
    concatenated273 = curve([ccat])

    save_curve("msd_300K_COM_corrected_primary.csv", primary300, ["300K"])
    save_curve("msd_273K_segmented_COM_corrected_primary.csv", primary273, ["273K_segment1", "273K_segment2"])
    save_curve("msd_300K_uncorrected_sensitivity.csv", uncorrected300, ["300K"])
    save_curve("msd_273K_segmented_uncorrected_sensitivity.csv", uncorrected273, ["273K_segment1", "273K_segment2"])
    save_curve("msd_300K_fractional_deaffined_sensitivity.csv", fractional300, ["300K"])
    save_curve("msd_273K_fractional_deaffined_sensitivity.csv", fractional273, ["273K_segment1", "273K_segment2"])
    save_curve("msd_273K_segment1_COM_corrected.csv", segment1, ["273K_segment1"])
    save_curve("msd_273K_segment2_COM_corrected.csv", segment2, ["273K_segment2"])
    save_curve("msd_273K_concatenated_COM_corrected_sensitivity.csv", concatenated273, ["273K_concatenated"])
    np.savez_compressed(OUT / "msd_intermediate_COM_corrected_oxygen.npz",
                        COM_corrected_300K=c300, COM_corrected_273K_segment1=c1,
                        COM_corrected_273K_segment2=c2, drift_300K=drift300,
                        drift_273K_segment1=drift1, drift_273K_segment2=drift2)

    fits300 = [passes(diagnostic(primary300, *window)) for window in WINDOWS]
    fits273 = [passes(diagnostic(primary273, *window, segment_lengths=[60, 40]), True) for window in WINDOWS]
    common_table = []
    for a, b in zip(fits300, fits273):
        common_table.append({
            "start_ps": a["start_ps"], "end_ps": a["end_ps"],
            "300K": a, "273K": b, "D300_over_D273": a["D_A2_per_ps"] / b["D_A2_per_ps"],
            "common_pass": bool(a["passes_prospective_rule"] and b["passes_prospective_rule"]),
            "273K_second_segment_note": "Segment 2 contributes throughout this window." if b["both_273K_segments_contribute_through_window"] else "Segment 2 does not contribute at lags >= 2.00 ps; after 1.95 ps only segment 1 contributes."
        })
    passing = [row for row in common_table if row["common_pass"]]
    selected = passing[0] if passing else None

    selected_window = tuple((selected["start_ps"], selected["end_ps"])) if selected else (0.75, 1.75)
    segment_fit1 = diagnostic(segment1, *selected_window)
    segment_fit2 = diagnostic(segment2, *selected_window)
    segment_difference = abs(segment_fit1["slope_A2_per_ps"] - segment_fit2["slope_A2_per_ps"])
    segment_relative = segment_difference / ((segment_fit1["slope_A2_per_ps"] + segment_fit2["slope_A2_per_ps"]) / 2)

    fractional_fits300 = diagnostic(fractional300, *selected_window)
    fractional_fits273 = diagnostic(fractional273, *selected_window, segment_lengths=[60, 40])
    cart_fits300 = diagnostic(primary300, *selected_window)
    cart_fits273 = diagnostic(primary273, *selected_window, segment_lengths=[60, 40])

    comparison_lags = [1.0, 2.0, 2.95]
    drift_effect = {}
    repaired_values = {}
    for lag in comparison_lags:
        repaired_values[str(lag)] = {"300K_A2": interpolate(primary300, lag), "273K_A2": interpolate(primary273, lag)}
        drift_effect[str(lag)] = {
            "300K_uncorrected_minus_corrected_A2": interpolate(uncorrected300, lag) - interpolate(primary300, lag),
            "273K_uncorrected_minus_corrected_A2": interpolate(uncorrected273, lag) - interpolate(primary273, lag),
        }

    plot_results(primary300, primary273, fits300, fits273,
                 selected, selected["300K"] if selected else None, selected["273K"] if selected else None,
                 segment1, segment2, uncorrected300, uncorrected273,
                 fractional300, fractional273, concatenated273)

    npt = {
        "method_A": "Cartesian frame-to-frame minimum-image increments using arithmetic-mean consecutive box lengths, followed by segment-local oxygen-centroid drift removal.",
        "method_B": "Wrapped coordinates converted with each frame box to fractional coordinates; fractional increments minimum-imaged and converted using arithmetic-mean consecutive box lengths, followed by segment-local oxygen-centroid drift removal.",
        "comparison_window_ps": list(selected_window),
        "300K": {"cartesian_slope_A2_per_ps": cart_fits300["slope_A2_per_ps"], "fractional_slope_A2_per_ps": fractional_fits300["slope_A2_per_ps"],
                 "absolute_slope_difference_A2_per_ps": fractional_fits300["slope_A2_per_ps"] - cart_fits300["slope_A2_per_ps"],
                 "relative_slope_difference": (fractional_fits300["slope_A2_per_ps"] - cart_fits300["slope_A2_per_ps"]) / cart_fits300["slope_A2_per_ps"]},
        "273K": {"cartesian_slope_A2_per_ps": cart_fits273["slope_A2_per_ps"], "fractional_slope_A2_per_ps": fractional_fits273["slope_A2_per_ps"],
                 "absolute_slope_difference_A2_per_ps": fractional_fits273["slope_A2_per_ps"] - cart_fits273["slope_A2_per_ps"],
                 "relative_slope_difference": (fractional_fits273["slope_A2_per_ps"] - cart_fits273["slope_A2_per_ps"]) / cart_fits273["slope_A2_per_ps"]},
        "MSD_difference_at_lags_A2": {str(lag): {"300K_fractional_minus_cartesian": interpolate(fractional300, lag) - interpolate(primary300, lag),
                                                        "273K_fractional_minus_cartesian": interpolate(fractional273, lag) - interpolate(primary273, lag)} for lag in comparison_lags}
    }
    restart = {"max_common_lag_ps": 2.95,
               "difference_at_max_lag_A2": interpolate(concatenated273, 2.95) - interpolate(primary273, 2.95),
               "relative_difference_at_max_lag": (interpolate(concatenated273, 2.95) - interpolate(primary273, 2.95)) / interpolate(primary273, 2.95)}

    results = {
        "scope": "Analysis-only external-review R1 repair; frozen package and branch 13 unchanged.",
        "prospective_acceptance_rule": RULE,
        "authoritative_package": {"path": ZIP.name, "sha256": EXPECTED_ZIP},
        "source_hashes": verified,
        "hbond_source": {"path": hbpath.relative_to(PKG).as_posix(), "sha256": EXPECTED_HB},
        "mdout_header_driven_parsing": {"300K": parse300, "273K": [item[1] for item in parsed273]},
        "records": {"trajectory_300K": 100, "box_300K": 100, "trajectory_273K_segments": [60, 40], "box_273K_segments": [60, 40], "thermo_300K": len(thermo300["temperature"]), "thermo_273K": len(thermo273["temperature"])},
        "accepted_distributions": {"status": "independently source-recomputed and numerically unchanged", "statistics": distribution_check, "names": distribution_names, "copied_files": copied_distributions},
        "COM_drift": {"definition": "Euclidean magnitude of the all-oxygen centroid displacement relative to frame 0, computed independently per continuous segment.",
                      "300K_final_A": float(np.linalg.norm(drift300[-1])), "273K_segment1_final_A": float(np.linalg.norm(drift1[-1])), "273K_segment2_final_A": float(np.linalg.norm(drift2[-1])),
                      "MSD_uncorrected_minus_corrected": drift_effect},
        "repaired_primary_MSD_at_lags_A2": repaired_values,
        "common_window_fits": common_table,
        "common_window_decision": {"exists": bool(selected), "selected_window_ps": [selected["start_ps"], selected["end_ps"]] if selected else None,
                                   "selection_reason": "Earliest common candidate passing the prospective rule for both temperatures; R2 was not maximized." if selected else "No candidate passed the prospective common-window rule for both temperatures.",
                                   "accepted_apparent_D": {"300K": selected["300K"] if selected else None, "273K": selected["273K"] if selected else None}},
        "273K_segment_consistency": {"fit_window_ps": list(selected_window), "segment1": segment_fit1, "segment2": segment_fit2,
                                     "absolute_slope_difference_A2_per_ps": segment_difference, "relative_slope_difference": segment_relative},
        "NPT_box_scaling_sensitivity": npt,
        "273K_restart_sensitivity": restart,
        "scientific_decision": {
            "robust_result": "300 K water has higher short-time oxygen mobility than 273 K water.",
            "conditional_result": "A numerical fit is labelled an apparent short-time oxygen self-mobility / effective diffusion estimate under the simulated conditions only when the prospective diagnostics pass.",
            "not_claimed": ["converged bulk self-diffusion coefficient", "experimental diffusion coefficient", "long-time transport convergence", "statistically independent uncertainty", "causal transport coefficient free of thermostat or finite-size effects"]},
        "limitations": ["Trajectories are only about 5 ps.", "Adjacent lag points are correlated.", "Overlapping time origins are correlated; SD is descriptive and naive SE is not inferential.", "The periodic box is only about 30 Å.", "No finite-size hydrodynamic correction is applied.", "Dynamics use the same Middle-Langevin/NPT setup; thermostat and friction can affect transport.", "Fitted values are not converged bulk self-diffusion constants."],
    }
    write_json(HERE / "PRESENTATION_DISTRIBUTIONS_AND_MSD_R1_RESULTS.json", results)
    write_json(HERE / "INPUT_PROVENANCE_R1.json", {"FINAL_zip_sha256": EXPECTED_ZIP, "raw_inputs": verified, "hbond_sha256": EXPECTED_HB, "immutable_branch_13_manifest": old_manifest})

    if selected:
        dtext = (f"The earliest common window passing the prospective rule is {selected['start_ps']:.2f}-{selected['end_ps']:.2f} ps. "
                 f"The resulting conditional estimates are {selected['300K']['D_cm2_per_s']:.6g} cm²/s at 300 K and {selected['273K']['D_cm2_per_s']:.6g} cm²/s at 273 K.")
    else:
        dtext = "No common window passes the prospective rule, so no primary numerical diffusion estimate is claimed."
    interpretation = f"""# Presentation MSD R1 scientific interpretation

## Presentation-ready wording

**Robust result:** 300 K water has higher short-time oxygen mobility than 273 K water over matched lag times in these trajectories.

**Conditional result:** {dtext} These values must be labelled **apparent short-time oxygen self-mobility / effective diffusion estimates under the simulated conditions**. The candidate window is an approximately linear short-time regime, not a proven long-time diffusive regime.

**Not claimed:** converged bulk self-diffusion coefficients, experimental diffusion coefficients, long-time transport convergence, statistically independent uncertainty, or transport coefficients free of thermostat and finite-size effects.

## Method and diagnostics

Oxygen coordinates were minimum-image unwrapped within each continuous segment. The frame-wise mean displacement of all 862 unwrapped oxygen references relative to segment frame 0 was then subtracted from every oxygen. The 273 K correction was applied independently to the 60-frame and 40-frame segments. No primary displacement crosses the restart boundary. The concatenated curve remains a structural sensitivity only and makes no RNG-continuity claim.

All six matched candidate windows were evaluated prospectively using positive slope, R² ≥ {RULE['minimum_R2']}, α in [{RULE['alpha_range_inclusive'][0]}, {RULE['alpha_range_inclusive'][1]}], curvature ratio ≤ {RULE['maximum_curvature_ratio']}, local interval-slope CV ≤ {RULE['maximum_local_slope_CV']}, 21 lag points, at least 20 valid 273 K origins, and contribution from both 273 K segments throughout the window. R² was not used alone. Durbin-Watson values are descriptive only: strong lag-to-lag residual correlation is expected because adjacent MSD points are correlated.

After 1.95 ps the 40-frame 273 K segment cannot contribute to longer-lag MSD points; this is why later candidate windows fail the both-segments rule.

## Limitations

The trajectories are only about 5 ps. Adjacent lag points are correlated, and overlapping time origins are also correlated. SD across origin means is a descriptive spread; `naive_SE_across_correlated_time_origins_A2` is not an independent-sample uncertainty. The periodic box is only about 30 Å and no finite-size hydrodynamic correction is applied. Both dynamics were generated under the same Middle-Langevin/NPT setup, and thermostat/friction can affect dynamical transport. Therefore, fitted values are not converged bulk self-diffusion constants and must not be compared directly with experiment without separate authorization.
"""
    (HERE / "PRESENTATION_DISTRIBUTIONS_AND_MSD_R1_INTERPRETATION.md").write_text(interpretation, encoding="utf-8")
    print("R1 analysis generated; run independent validator.")


if __name__ == "__main__":
    main()
