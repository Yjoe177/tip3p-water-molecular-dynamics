"""Independent fail-closed validator for the presentation MSD R1 repair."""
from __future__ import annotations

import csv
import hashlib
import json
import math
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
WORK = HERE.parent
PKG = WORK / "FINAL_TIP3P_WATER_300K_273K_PROJECT_PACKAGE_FINAL"
ZIP = WORK / "FINAL_TIP3P_WATER_300K_273K_PROJECT_PACKAGE_FINAL.zip"
OLD = WORK / "13_PRESENTATION_DISTRIBUTIONS_AND_MSD"
OUT = HERE / "outputs"
RESULT = HERE / "PRESENTATION_DISTRIBUTIONS_AND_MSD_R1_RESULTS.json"
EXPECTED_ZIP = "82B687D8DCD423E7AFC4121DB5E6F15C7C28D3C40D60B6B2DE7B14314D29AFCB"
EXPECTED_HB = "2D84D077B9067BACD7170A6CBB7FB524144FE6F4519DE9DDBFCFE5A7A4DCB58F"
DT, N_ATOMS, N_WATERS = 0.05, 2586, 862
WINDOWS = [(0.50, 1.50), (0.75, 1.75), (1.00, 2.00),
           (1.25, 2.25), (1.50, 2.50), (1.75, 2.75)]


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1048576), b""):
            h.update(block)
    return h.hexdigest().upper()


checks = []


def check(name, condition, detail=""):
    if not bool(condition):
        raise AssertionError(f"{name}: {detail}")
    checks.append({"name": name, "pass": True, "detail": detail})


def parse_header_driven(path):
    tokens = [line.split() for line in path.read_text(encoding="utf-8").splitlines() if line.split()]
    header, rows = tokens[0], tokens[1:]
    check(f"mdout rectangular {path.name}", all(len(row) == len(header) for row in rows), str(len(rows)))
    output = {}
    for field in ("temperature", "pressure", "potential", "density"):
        candidates = [i for i, value in enumerate(header) if value.casefold() == field]
        numeric = []
        for index in candidates:
            try:
                numeric.append(np.asarray([float(row[index]) for row in rows], dtype=float))
            except ValueError:
                pass
        check(f"unique numeric header field {field} in {path.name}", len(numeric) == 1, f"numeric candidates={len(numeric)}")
        output[field] = numeric[0]
    return output


def load_traj(path, frames):
    raw = np.fromfile(path, dtype=np.float32)
    check(f"trajectory size {path.name}", raw.size == frames * N_ATOMS * 3, f"frames={frames}")
    return raw.reshape(frames, N_ATOMS, 3).astype(float)[:, ::3, :]


def load_box(path, frames):
    box = np.loadtxt(path, usecols=(0, 1, 2), ndmin=2)
    check(f"box records {path.name}", box.shape == (frames, 3), str(box.shape))
    return box


def unwrap_cart(wrapped, boxes):
    value = np.empty_like(wrapped)
    value[0] = wrapped[0]
    for i in range(1, len(wrapped)):
        length = (boxes[i] + boxes[i - 1]) / 2
        increment = wrapped[i] - wrapped[i - 1]
        increment = increment - length * np.rint(increment / length)
        value[i] = value[i - 1] + increment
    return value


def unwrap_fractional(wrapped, boxes):
    fractional = wrapped / boxes[:, None, :]
    value = np.empty_like(wrapped)
    value[0] = wrapped[0]
    for i in range(1, len(wrapped)):
        ds = fractional[i] - fractional[i - 1]
        ds -= np.rint(ds)
        value[i] = value[i - 1] + ds * (boxes[i] + boxes[i - 1]) / 2
    return value


def correct(unwrapped):
    drift = unwrapped.mean(axis=1) - unwrapped[0].mean(axis=0)
    return unwrapped - drift[:, None, :], drift


def msd(segments):
    result = []
    for lag in range(max(map(len, segments))):
        values = []
        counts = []
        for segment in segments:
            count = max(0, len(segment) - lag)
            counts.append(count)
            if count:
                delta = segment[lag:] - segment[:count]
                values.extend(np.mean(np.sum(delta * delta, axis=2), axis=1))
        a = np.asarray(values)
        sd = a.std(ddof=1) if len(a) > 1 else 0.0
        result.append([lag * DT, a.mean(), sd, sd / math.sqrt(len(a)) if len(a) > 1 else 0.0, len(a), len(a) * N_WATERS, *counts])
    return np.asarray(result, dtype=float)


def fit(data, lo, hi, lengths=None):
    q = data[(data[:, 0] >= lo - 1e-12) & (data[:, 0] <= hi + 1e-12)]
    x, y = q[:, 0], q[:, 1]
    slope, intercept = np.polyfit(x, y, 1)
    residual = y - (slope * x + intercept)
    ss = np.sum(residual ** 2)
    r2 = 1 - ss / np.sum((y - y.mean()) ** 2)
    alpha = np.polyfit(np.log(x), np.log(y), 1)[0]
    curvature = abs(np.polyfit(x, y, 2)[0] * (hi - lo) / slope)
    local = np.diff(y) / np.diff(x)
    result = {"slope": slope, "intercept": intercept, "D": slope / 6e4, "R2": r2,
              "RMSE": math.sqrt(ss / len(x)), "alpha": alpha, "curvature": curvature,
              "local_CV": local.std(ddof=1) / abs(local.mean()),
              "origins": [int(q[:, 4].min()), int(q[:, 4].max())], "n": len(x)}
    if lengths:
        result["segment_ranges"] = [[min(max(0, length - round(t / DT)) for t in x),
                                     max(max(0, length - round(t / DT)) for t in x)] for length in lengths]
    return result


def read_curve(name):
    with (OUT / name).open(newline="", encoding="utf-8") as f:
        return np.asarray([[float(x) for x in row] for row in list(csv.reader(f))[1:]])


def close(a, b, atol=1e-10):
    return np.allclose(a, b, rtol=1e-10, atol=atol)


def main():
    data = json.loads(RESULT.read_text(encoding="utf-8"))
    check("FINAL ZIP SHA-256", sha(ZIP) == EXPECTED_ZIP, EXPECTED_ZIP)
    provenance = json.loads((PKG / "00_PROJECT_OVERVIEW/SOURCE_PROVENANCE.json").read_text(encoding="utf-8"))
    roles = {}
    for temp, entries in provenance["immutable_deep_raw_sources"].items():
        roles[temp] = {"trajectory": [], "box": [], "mdout": []}
        for entry in entries:
            path = PKG / entry["package_relative_current_path"]
            check(f"raw source hash {temp} {entry['role']} {path.name}", sha(path) == entry["sha256"].upper())
            roles[temp][entry["role"]].append(path)
    check("nine frozen raw sources", sum(len(v) for group in roles.values() for v in group.values()) == 9)
    hbpath = PKG / "02_EXPERIMENT_2_TEMPERATURE_COMPARISON/04_FINAL_DEEP_ANALYSIS/outputs/hbond_timeseries.csv"
    check("H-bond source hash", sha(hbpath) == EXPECTED_HB)

    manifest = json.loads((HERE / "INPUT_PROVENANCE_R1.json").read_text(encoding="utf-8"))["immutable_branch_13_manifest"]
    check("branch 13 file set unchanged", set(manifest) == {p.relative_to(OLD).as_posix() for p in OLD.rglob("*") if p.is_file()})
    check("branch 13 hashes unchanged", all(sha(OLD / name) == digest for name, digest in manifest.items()))

    th300 = parse_header_driven(roles["300K"]["mdout"][0])
    thparts = [parse_header_driven(path) for path in roles["273K"]["mdout"]]
    th273 = {key: np.concatenate([part[key] for part in thparts]) for key in th300}
    check("thermo record counts 100 and 99", len(th300["temperature"]) == 100 and len(th273["temperature"]) == 99)
    box300 = load_box(roles["300K"]["box"][0], 100)
    box1 = load_box(roles["273K"]["box"][0], 60)
    box2 = load_box(roles["273K"]["box"][1], 40)

    hb = np.genfromtxt(hbpath, delimiter=",", names=True)
    distributions = {
        "temperature": (th300["temperature"], th273["temperature"]), "density": (th300["density"], th273["density"]),
        "potential": (th300["potential"], th273["potential"]), "pressure": (th300["pressure"], th273["pressure"]),
        "box_volume": (np.prod(box300, axis=1), np.prod(np.vstack([box1, box2]), axis=1)),
        "hbond_count": (hb["N_HB_300K"], hb["N_HB_273K"]), "hbonds_per_water": (hb["HB_per_water_300K"], hb["HB_per_water_273K"])}
    for name, (a, b) in distributions.items():
        raw = np.genfromtxt(OUT / f"{name}_raw_values.csv", delimiter=",", names=True)
        va = raw["value_300K"][~np.isnan(raw["value_300K"])]
        vb = raw["value_273K"][~np.isnan(raw["value_273K"])]
        check(f"distribution source values {name}", close(va, a) and close(vb, b))
        hist = np.genfromtxt(OUT / f"{name}_distribution.csv", delimiter=",", names=True)
        widths = hist["bin_right"] - hist["bin_left"]
        check(f"common histogram bins and unit integrals {name}",
              close(hist["bin_center"], (hist["bin_left"] + hist["bin_right"]) / 2) and
              abs(np.sum(hist["density_300K"] * widths) - 1) < 1e-12 and abs(np.sum(hist["density_273K"] * widths) - 1) < 1e-12)

    w300 = load_traj(roles["300K"]["trajectory"][0], 100)
    w1 = load_traj(roles["273K"]["trajectory"][0], 60)
    w2 = load_traj(roles["273K"]["trajectory"][1], 40)
    check("oxygen count 862", w300.shape[1] == w1.shape[1] == w2.shape[1] == N_WATERS)
    u300, u1, u2 = unwrap_cart(w300, box300), unwrap_cart(w1, box1), unwrap_cart(w2, box2)
    c300, d300 = correct(u300); c1, d1 = correct(u1); c2, d2 = correct(u2)
    reported_drift = data["COM_drift"]
    check("COM drift independently recomputed", close([np.linalg.norm(d300[-1]), np.linalg.norm(d1[-1]), np.linalg.norm(d2[-1])],
                                                        [reported_drift["300K_final_A"], reported_drift["273K_segment1_final_A"], reported_drift["273K_segment2_final_A"]]))
    check("COM-corrected centroids stationary", max(np.abs(c300.mean(axis=1) - c300[0].mean(axis=0)).max(),
                                                      np.abs(c1.mean(axis=1) - c1[0].mean(axis=0)).max(),
                                                      np.abs(c2.mean(axis=1) - c2[0].mean(axis=0)).max()) < 1e-11)
    m300, m273, m1, m2 = msd([c300]), msd([c1, c2]), msd([c1]), msd([c2])
    check("primary 300K MSD independently recomputed", close(m300, read_curve("msd_300K_COM_corrected_primary.csv")))
    check("primary 273K MSD independently recomputed", close(m273, read_curve("msd_273K_segmented_COM_corrected_primary.csv")))
    check("273K segment-specific MSD independently recomputed", close(m1, read_curve("msd_273K_segment1_COM_corrected.csv")) and close(m2, read_curve("msd_273K_segment2_COM_corrected.csv")))
    check("no primary 273K restart crossing", np.array_equal(m273[:, 4], m273[:, 6] + m273[:, 7]) and m273[-1, 7] == 0)

    f300 = correct(unwrap_fractional(w300, box300))[0]
    f1 = correct(unwrap_fractional(w1, box1))[0]
    f2 = correct(unwrap_fractional(w2, box2))[0]
    fm300, fm273 = msd([f300]), msd([f1, f2])
    check("NPT de-affined MSD independently recomputed", close(fm300, read_curve("msd_300K_fractional_deaffined_sensitivity.csv")) and close(fm273, read_curve("msd_273K_fractional_deaffined_sensitivity.csv")))

    for index, ((lo, hi), reported) in enumerate(zip(WINDOWS, data["common_window_fits"])):
        a, b = fit(m300, lo, hi), fit(m273, lo, hi, [60, 40])
        check(f"common fit table window {index + 1}", close([a["slope"], a["D"], a["R2"], a["RMSE"], b["slope"], b["D"], b["R2"], b["RMSE"]],
                                                               [reported["300K"]["slope_A2_per_ps"], reported["300K"]["D_cm2_per_s"], reported["300K"]["R2"], reported["300K"]["residual_RMSE_A2"], reported["273K"]["slope_A2_per_ps"], reported["273K"]["D_cm2_per_s"], reported["273K"]["R2"], reported["273K"]["residual_RMSE_A2"]]))
        check(f"alpha and slope diagnostics window {index + 1}", close([a["alpha"], a["curvature"], a["local_CV"], b["alpha"], b["curvature"], b["local_CV"]],
                                                                       [reported["300K"]["alpha_loglog"], reported["300K"]["curvature_ratio"], reported["300K"]["local_interval_slope_CV"], reported["273K"]["alpha_loglog"], reported["273K"]["curvature_ratio"], reported["273K"]["local_interval_slope_CV"]]))
        check(f"origin ranges window {index + 1}", a["origins"] == reported["300K"]["valid_origin_count_range"] and b["origins"] == reported["273K"]["valid_origin_count_range"] and b["segment_ranges"] == reported["273K"]["valid_origin_count_ranges_by_273K_segment"])
        check(f"slope to D conversion window {index + 1}", abs(reported["300K"]["D_cm2_per_s"] - reported["300K"]["slope_A2_per_ps"] / 6e4) < 1e-15 and abs(reported["273K"]["D_cm2_per_s"] - reported["273K"]["slope_A2_per_ps"] / 6e4) < 1e-15)

    passing = [row for row in data["common_window_fits"] if row["common_pass"]]
    selected = data["common_window_decision"]
    check("prospective selection faithfully applied", (not passing and not selected["exists"] and selected["accepted_apparent_D"] == {"300K": None, "273K": None}) or (passing and selected["selected_window_ps"] == [passing[0]["start_ps"], passing[0]["end_ps"]]))
    check("273K second segment cutoff explicit", all(row["273K"]["valid_origin_count_ranges_by_273K_segment"][1][0] == max(0, 40 - round(row["end_ps"] / DT)) for row in data["common_window_fits"]))

    text = (HERE / "PRESENTATION_DISTRIBUTIONS_AND_MSD_R1_INTERPRETATION.md").read_text(encoding="utf-8")
    check("scientific label present", "apparent short-time oxygen self-mobility / effective diffusion estimates under the simulated conditions" in text)
    check("limitations wording complete", all(phrase in text for phrase in ["only about 5 ps", "lag points are correlated", "overlapping time origins", "about 30 Å", "finite-size hydrodynamic correction", "Middle-Langevin/NPT", "thermostat/friction", "not converged bulk self-diffusion constants"]))
    check("no accepted D when common rule fails", "no primary numerical diffusion estimate is claimed" in text)
    check("UTF-8 text files", all(path.read_bytes().decode("utf-8") is not None for path in HERE.glob("*.py")) and all(path.read_bytes().decode("utf-8") is not None for path in HERE.glob("*.json")) and all(path.read_bytes().decode("utf-8") is not None for path in HERE.glob("*.md")) and all(path.read_bytes().decode("utf-8") is not None for path in OUT.glob("*.csv")))

    required = ["fig_msd_comparison_repaired.png", "fig_msd_fit_diagnostics_repaired.png", "fig_msd_273K_segment_consistency.png", "fig_msd_COM_drift_sensitivity.png", "fig_msd_NPT_box_scaling_sensitivity.png", "fig_msd_273K_restart_sensitivity_repaired.png"]
    required += [f"fig_{name}_distribution.png" for name in distributions]
    check("all required figures exist", all((OUT / name).is_file() and (OUT / name).stat().st_size > 1000 for name in required), ", ".join(required))
    check("all source hashes remain unchanged at validation end", sha(ZIP) == EXPECTED_ZIP and all(sha(PKG / entry["package_relative_current_path"]) == entry["sha256"].upper() for entries in provenance["immutable_deep_raw_sources"].values() for entry in entries) and sha(hbpath) == EXPECTED_HB)

    validation = {"verdict": "PRESENTATION_DISTRIBUTIONS_AND_MSD_R1_VALIDATED", "passed": len(checks), "failed": 0, "checks": checks}
    (HERE / "PRESENTATION_DISTRIBUTIONS_AND_MSD_R1_VALIDATION.json").write_text(json.dumps(validation, indent=2) + "\n", encoding="utf-8")
    print(f"{validation['verdict']} ({len(checks)}/{len(checks)})")


if __name__ == "__main__":
    main()
