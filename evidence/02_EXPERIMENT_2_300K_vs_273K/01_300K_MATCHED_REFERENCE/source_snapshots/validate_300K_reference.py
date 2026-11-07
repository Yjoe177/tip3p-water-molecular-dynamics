#!/usr/bin/env python3
"""Post-run validator for the 5 ps 300 K reference production
(branch 12_TEMPERATURE_COMPARISON_300K_273K, pass T1).

Run AFTER the user has manually executed RUN_300K_REFERENCE.ps1.
This script never fabricates results: if run outputs are absent it reports
RUN_OUTPUTS_NOT_FOUND and fails.

Usage:
    python validate_300K_reference.py
"""
import json
import math
import os
import struct
import sys
import hashlib

PASS_ROOT = os.path.dirname(os.path.abspath(__file__))
BRANCH_ROOT = os.path.dirname(PASS_ROOT)
RUN_DIR = os.path.join(PASS_ROOT, "run", "tempcomp_300K_reference")
INPUT_DIR = os.path.join(PASS_ROOT, "input")
COMMON_DIR = os.path.join(BRANCH_ROOT, "01_common_start_state")
OUT_JSON = os.path.join(BRANCH_ROOT, "11_validation", "T1_300K_REFERENCE_POSTRUN_VALIDATION.json")

EXPECTED_COORD_HASH = "E6DDAF9DEB248D5076B2AD783843456AB697D8456B1E42B85130D82A57DFAA81"
EXPECTED_VEL_HASH = "E43EA18C0569294A4FD644C80479AAF855D1737DCE8EA6808FDCBF6D2C71277B"
EXPECTED_HEADER = "2586 112.6200000000 3999"
ATOM_COUNT = 2586
DT_PS = 0.001
STEP_LIMIT = 5000
TRAJ_INTERVAL = 50
INFO_INTERVAL = 50
START_TIME_PS = 112.620
# Frame-count semantics inherited from the validated R7R runner:
# frames = floor(step_limit / write_trajectory_interval) = 100.
# The box file is written by the same trajectory writer at the same cadence.
EXPECTED_FRAMES = STEP_LIMIT // TRAJ_INTERVAL
EXPECTED_MDOUT_RECORDS = STEP_LIMIT // INFO_INTERVAL
BYTES_PER_FRAME = ATOM_COUNT * 3 * 4  # float32 xyz, SPONGE .dat trajectory

META = os.path.join(RUN_DIR, "tempcomp_300K_reference_meta.json")
MDOUT = os.path.join(RUN_DIR, "tempcomp_300K_reference.mdout")
MDINFO = os.path.join(RUN_DIR, "tempcomp_300K_reference.mdinfo")
TRAJ_DAT = os.path.join(RUN_DIR, "tempcomp_300K_reference_traj.dat")
TRAJ_BOX = os.path.join(RUN_DIR, "tempcomp_300K_reference_traj.box")
RST_COORD = os.path.join(RUN_DIR, "tempcomp_300K_reference_rst_coordinate.txt")
RST_VEL = os.path.join(RUN_DIR, "tempcomp_300K_reference_rst_velocity.txt")


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest().upper()


def is_finite(x):
    return not (math.isnan(x) or math.isinf(x))


checks = {}
def check(name, ok, detail=""):
    checks[name] = {"passed": bool(ok), "detail": str(detail)}
    return ok


def main():
    if not os.path.isdir(RUN_DIR) or not os.path.isfile(META):
        result = {
            "status": "RUN_OUTPUTS_NOT_FOUND",
            "detail": "No run outputs found. Execute RUN_300K_REFERENCE.ps1 first. No results were fabricated.",
            "expected_run_dir": RUN_DIR,
        }
        os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
        json.dump(result, open(OUT_JSON, "w"), indent=2)
        print(json.dumps(result, indent=2))
        sys.exit(1)

    meta = json.load(open(META))

    # 1. SPONGE exit code
    exit_code = meta.get("exit_code")
    check("sponge_exit_code_zero", exit_code == 0, f"exit_code={exit_code}")

    # 2. Final restart exists, atom count, numeric finiteness
    for label, path in (("coordinate", RST_COORD), ("velocity", RST_VEL)):
        exists = os.path.isfile(path)
        check(f"final_restart_{label}_exists", exists, path)
        if not exists:
            continue
        lines = [l for l in open(path).read().splitlines() if l.strip()]
        header = lines[0].strip()
        hp = header.split()
        check(f"final_{label}_atom_count", int(hp[0]) == ATOM_COUNT, header)
        body = lines[1:1 + ATOM_COUNT]
        check(f"final_{label}_line_count", len(body) == ATOM_COUNT,
              f"{len(body)} data lines")
        vals = []
        oknum = True
        for l in body:
            parts = l.split()
            if len(parts) != 3:
                oknum = False
                break
            try:
                v = [float(x) for x in parts]
            except ValueError:
                oknum = False
                break
            if not all(is_finite(x) for x in v):
                oknum = False
                break
            vals.append(v)
        check(f"final_{label}_finite_values", oknum and len(vals) == ATOM_COUNT)

    # 3. Trajectory frames: binary .dat must be an exact multiple of frame size
    if os.path.isfile(TRAJ_DAT):
        size = os.path.getsize(TRAJ_DAT)
        n_frames = size // BYTES_PER_FRAME
        check("trajectory_dat_exact_frame_multiple", size % BYTES_PER_FRAME == 0,
              f"{size} bytes, {BYTES_PER_FRAME} bytes/frame, remainder {size % BYTES_PER_FRAME}")
        check("trajectory_frame_count", n_frames == EXPECTED_FRAMES,
              f"{n_frames} frames, expected {EXPECTED_FRAMES} "
              f"(floor({STEP_LIMIT}/{TRAJ_INTERVAL}) per accepted R7R runner convention)")
        # finite values across the whole trajectory (sampled scan of all floats)
        allfinite = True
        with open(TRAJ_DAT, "rb") as f:
            while True:
                buf = f.read(1 << 20)
                if not buf:
                    break
                n = len(buf) // 4
                for x in struct.unpack(f"<{n}f", buf[: n * 4]):
                    if not is_finite(x):
                        allfinite = False
                        break
                if not allfinite:
                    break
        check("trajectory_all_finite", allfinite)
    else:
        check("trajectory_dat_exists", False, TRAJ_DAT)

    # 4. Box frames: one 6-value record per frame, finite, positive lengths
    if os.path.isfile(TRAJ_BOX):
        box_lines = [l for l in open(TRAJ_BOX).read().splitlines() if l.strip()]
        ok_box = True
        for l in box_lines:
            p = l.split()
            if len(p) != 6:
                ok_box = False
                break
            try:
                v = [float(x) for x in p]
            except ValueError:
                ok_box = False
                break
            if not all(is_finite(x) for x in v) or not all(x > 0 for x in v[:3]):
                ok_box = False
                break
        check("box_records_wellformed_finite", ok_box, f"{len(box_lines)} box records")
        check("box_frame_count_matches_trajectory",
              os.path.isfile(TRAJ_DAT) and len(box_lines) == os.path.getsize(TRAJ_DAT) // BYTES_PER_FRAME,
              f"box={len(box_lines)} traj={os.path.getsize(TRAJ_DAT) // BYTES_PER_FRAME if os.path.isfile(TRAJ_DAT) else 'NA'}")
        if box_lines:
            vols = []
            for l in box_lines:
                v = [float(x) for x in l.split()]
                vols.append(v[0] * v[1] * v[2])
            check("box_volume_finite_positive", all(is_finite(v) and v > 0 for v in vols),
                  f"mean volume {sum(vols)/len(vols):.2f} A^3")
    else:
        check("trajectory_box_exists", False, TRAJ_BOX)

    # 5. Structural spacing: interval 50 * dt 0.001 ps = 0.05 ps between frames
    check("structural_spacing_ps", abs(TRAJ_INTERVAL * DT_PS - 0.05) < 1e-12,
          f"{TRAJ_INTERVAL * DT_PS} ps between saved frames")

    # 6. mdout thermodynamic records: finite, temperature centered near 300 K
    #
    # REPAIR (attempt 2): attempt 1 hard-coded temperature = column index 3.
    # The actual SPONGE mdout layout (see the header line in the file itself) is
    #   step time temperature pressure Pxx Pyy Pzz Pxy Pxz Pyz potential density ...
    # so index 3 is *pressure*, which is why attempt 1 reported
    # "mean T = -75.25 K" — that value was the mean pressure in bar.
    # The parser below is driven by the explicit header labels, not positions.
    if os.path.isfile(MDOUT):
        raw_lines = open(MDOUT).read().splitlines()
        header_idx = None
        for i, l in enumerate(raw_lines):
            if "temperature" in l.split() and "step" in l.split():
                header_idx = i
                break
        check("mdout_header_found", header_idx is not None,
              f"header at line {header_idx + 1}" if header_idx is not None else "no labelled header found")
        if header_idx is not None:
            labels = raw_lines[header_idx].split()
            # first occurrence wins (the label "pressure" appears twice;
            # the second column is printed as "****" by SPONGE and is unusable)
            col = {}
            for i, lab in enumerate(labels):
                col.setdefault(lab, i)
            REQUIRED = ["step", "time", "temperature", "pressure", "potential", "density"]
            missing = [k for k in REQUIRED if k not in col]
            check("mdout_required_labels_present", not missing,
                  f"missing={missing}" if missing else f"column map: { {k: col[k] for k in REQUIRED} }")

            records = []
            numeric_ok = True
            for l in raw_lines[header_idx + 1:]:
                if not l.strip() or l.lstrip().startswith("#"):
                    continue
                cols = l.split()
                if len(cols) < len(labels):
                    continue
                rec = {}
                for lab in set(REQUIRED):
                    tok = cols[col[lab]]
                    if tok == "****":  # SPONGE overflow sentinel
                        rec[lab] = float("nan")
                        continue
                    try:
                        rec[lab] = float(tok)
                    except ValueError:
                        numeric_ok = False
                        rec[lab] = float("nan")
                records.append(rec)
            check("mdout_finite", numeric_ok and all(
                all(is_finite(r[k]) for k in REQUIRED) for r in records),
                f"{len(records)} data records")
            check("mdout_record_count", len(records) == EXPECTED_MDOUT_RECORDS,
                  f"{len(records)} records, expected {EXPECTED_MDOUT_RECORDS}")

            # Explicit first / middle / final record verification
            n = len(records)
            probe_idx = [0, n // 2, n - 1]
            exp_steps = [INFO_INTERVAL * (i + 1) for i in probe_idx]
            probes_ok = True
            probe_detail = []
            for pi, es in zip(probe_idx, exp_steps):
                r = records[pi]
                ok = (r["step"] == es and
                      abs(r["time"] - (START_TIME_PS + r["step"] * DT_PS)) < 1e-6 and
                      all(is_finite(r[k]) for k in REQUIRED))
                probes_ok = probes_ok and ok
                probe_detail.append(
                    f"record[{pi}]: step={int(r['step'])} (exp {es}), time={r['time']:.3f} ps, "
                    f"T={r['temperature']:.2f} K, P={r['pressure']:.2f} bar, "
                    f"Epot={r['potential']:.2f}, density={r['density']:.4f}")
            check("mdout_first_middle_final_records_correct", probes_ok, " | ".join(probe_detail))

            def mean_sd(key):
                vals = [r[key] for r in records]
                m = sum(vals) / len(vals)
                sd = math.sqrt(sum((v - m) ** 2 for v in vals) / (len(vals) - 1))
                return m, sd

            stats = {}
            for key in ("temperature", "pressure", "density", "potential"):
                m, sd = mean_sd(key)
                stats[key] = {"mean": round(m, 4), "sample_sd": round(sd, 4), "n": n}
            mean_t = stats["temperature"]["mean"]
            check("temperature_centered_near_300K", abs(mean_t - 300.0) < 10.0,
                  f"mean T = {mean_t:.2f} K, sample SD = {stats['temperature']['sample_sd']:.2f} K "
                  f"over {n} records (loose |mean-300|<10 K check)")
            # Pressure over a 5 ps window is reported honestly but is NOT a
            # pass/fail equilibration criterion.
            checks["thermo_stats"] = {
                "passed": True,
                "detail": json.dumps(stats),
                "note": ("Pressure mean/SD reported for information only; short 5 ps NPT "
                         "windows are not expected to centre on the 1 bar target."),
            }
    else:
        check("mdout_exists", False, MDOUT)

    # 7. Duration consistency from mdinfo if available
    if os.path.isfile(MDINFO):
        info = open(MDINFO, errors="replace").read()
        check("mdinfo_present", True, f"{len(info)} chars")
    # Steps executed: derived from trajectory frames * interval
    if os.path.isfile(TRAJ_DAT):
        steps_done = (os.path.getsize(TRAJ_DAT) // BYTES_PER_FRAME) * TRAJ_INTERVAL
        check("simulation_length_5ps", steps_done == STEP_LIMIT,
              f"{steps_done} steps = {steps_done * DT_PS:.3f} ps, expected {STEP_LIMIT} steps = 5.0 ps")

    # 8. Input provenance unchanged (run inputs + immutable common start state)
    check("run_input_coordinate_hash_unchanged",
          sha256(os.path.join(INPUT_DIR, "tempcomp_300K_reference_start_coordinate.txt")) == EXPECTED_COORD_HASH)
    check("run_input_velocity_hash_unchanged",
          sha256(os.path.join(INPUT_DIR, "tempcomp_300K_reference_start_velocity.txt")) == EXPECTED_VEL_HASH)
    check("common_start_coordinate_hash_unchanged",
          sha256(os.path.join(COMMON_DIR, "common_start_coordinate.txt")) == EXPECTED_COORD_HASH)
    check("common_start_velocity_hash_unchanged",
          sha256(os.path.join(COMMON_DIR, "common_start_velocity.txt")) == EXPECTED_VEL_HASH)
    hdr = open(os.path.join(COMMON_DIR, "common_start_coordinate.txt")).readline().strip()
    check("common_start_header_unchanged", hdr == EXPECTED_HEADER, hdr)

    all_ok = all(c["passed"] for c in checks.values())
    result = {
        "status": "T1_300K_REFERENCE_POSTRUN_PASS" if all_ok else "T1_300K_REFERENCE_POSTRUN_FAIL",
        "frame_count_semantics": (
            "Expected frames = floor(step_limit / write_trajectory_interval) = "
            "floor(5000/50) = 100, the exact convention used and validated by the "
            "accepted R7R production runner. The .box file is written by the same "
            "trajectory writer at the same cadence, so coordinate and box frame "
            "counts must be identical. If SPONGE deviates from this convention, "
            "record the actual count and investigate before accepting."
        ),
        "checks": checks,
    }
    os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
    json.dump(result, open(OUT_JSON, "w"), indent=2)
    print(json.dumps(result, indent=2))
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
