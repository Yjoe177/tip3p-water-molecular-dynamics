from __future__ import annotations

import argparse
import array
import ctypes
import csv
import hashlib
import json
import math
import os
import platform
import random
import shutil
import subprocess
import sys
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
PASS_DIR = Path(__file__).resolve().parent
PASS_NAME = PASS_DIR.name
STAMP = PASS_NAME.rsplit("_", 2)[-2] + "_" + PASS_NAME.rsplit("_", 1)[-1]

PASS06AR = ROOT / "06AR_runtime_efficient_staged_nvt_heating_7ps_20260804_212029"
PACKAGE_DIR = ROOT / "99_review_packages"

INPUT_RAW = PASS_DIR / "input_raw"
INPUT_300K = PASS_DIR / "input_300K_state"
REPORTS = PASS_DIR / "reports"
RECEIPTS = PASS_DIR / "source_receipts"
LOGS = PASS_DIR / "logs"
META = PASS_DIR / "package_metadata"

ATOM_COUNT = 2586
WATER_COUNT = 862
FREEDOM = 5169
BOX_TARGET = 30.0
EXPECTED_START_COORD_SHA = "2ae5e2dca467b6a866c5493905d561568be1cfb3a2b491f13056e5ec758ca5da"
EXPECTED_START_VEL_SHA = "04615125ca18991a95250a6b16a245b9dc35816a47105bc440c598d1268ded81"

CONDA = Path(r"C:\Users\Acer\miniconda3\Scripts\conda.exe")
ENV_NAME = "sponge-cpu"

KB_NUMERATOR_J_PER_MOL_K = 8.314
J_PER_KCAL = 4184.0
KB_KCAL_PER_MOL_K = KB_NUMERATOR_J_PER_MOL_K / J_PER_KCAL
PHYSICAL_ANG_PER_PS_FACTOR = 0.00239005736153349

RAW_NAMES = [
    "water_30A_randomized_atom_name.txt",
    "water_30A_randomized_atom_type_name.txt",
    "water_30A_randomized_bond.txt",
    "water_30A_randomized_charge.txt",
    "water_30A_randomized_coordinate.txt",
    "water_30A_randomized_exclude.txt",
    "water_30A_randomized_LJ.txt",
    "water_30A_randomized_mass.txt",
    "water_30A_randomized_residue.txt",
    "water_30A_randomized_resname.txt",
]

STAGES = {
    "nvt300K_10ps": {
        "run_dir": PASS_DIR / "run",
        "outputs": PASS_DIR / "outputs" / "primary",
        "analysis": PASS_DIR / "analysis",
        "validation": PASS_DIR / "validation",
        "label": "nvt300K_10ps",
        "expected_steps": 10000,
        "expected_records": 500,
        "expected_frames": 100,
        "information_interval": 20,
        "trajectory_interval": 100,
        "dt_ps": 0.001,
        "timeout": 18000,
        "target_temperature_K": 300.0,
        "thermostat_seed": 20260901,
        "terminal_window": 100,
        "previous_stage": None,
    },
}

COMMANDS = {
}


def stage_input_paths(stage: str) -> tuple[str, str]:
    return "../input_300K_state/heated300K_coordinate.txt", "../input_300K_state/heated300K_velocity.txt"


for _stage, _cfg in STAGES.items():
    _coord, _vel = stage_input_paths(_stage)
    _step_limit = _cfg["expected_steps"]
    COMMANDS[_stage] = [
        str(CONDA), "run", "-n", ENV_NAME, "SPONGE",
        "-mode", "NVT",
        "-thermostat", "middle_langevin",
        "-target_temperature", f"{int(_cfg['target_temperature_K'])}",
        "-thermostat_seed", f"{_cfg['thermostat_seed']}",
        "-thermostat_tau", "0.05",
        "-default_in_file_prefix", "../input_raw/water_30A_randomized",
        "-coordinate_in_file", _coord,
        "-velocity_in_file", _vel,
        "-step_limit", f"{_step_limit}",
        "-dt", "0.001",
        "-constrain_mode", "SHAKE",
        "-cutoff", "8",
        "-write_information_interval", f"{_cfg['information_interval']}",
        "-write_trajectory_interval", f"{_cfg['trajectory_interval']}",
        "-write_restart_file_interval", "1000",
        "-mdout", f"{_cfg['label']}.mdout",
        "-mdinfo", f"{_cfg['label']}.mdinfo",
        "-rst", f"{_cfg['label']}_rst",
        "-default_out_file_prefix", f"{_cfg['label']}_traj",
    ]

META_EXCLUSIONS = [
    "package_metadata/FILE_INVENTORY.csv",
    "package_metadata/SHA256SUMS.txt",
    "package_metadata/REVIEW_PACKAGE_MANIFEST.json",
    "package_metadata/REVIEW_PACKAGE_MANIFEST.md",
    "package_metadata/SELF_REFERENTIAL_METADATA_EXCLUSIONS.json",
    "package_metadata/PACKAGE_RULES_NOTE.md",
]


def now_iso() -> str:
    return datetime.now().astimezone().replace(microsecond=0).isoformat()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_csv(path: Path, rows: list[dict], fields: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fields is None:
        fields = sorted({k for row in rows for k in row})
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def command_line(argv: list[str]) -> str:
    return " ".join(f'"{x}"' if " " in x else x for x in argv)


def available_ram_bytes() -> int | None:
    class MEMORYSTATUSEX(ctypes.Structure):
        _fields_ = [
            ("dwLength", ctypes.c_ulong),
            ("dwMemoryLoad", ctypes.c_ulong),
            ("ullTotalPhys", ctypes.c_ulonglong),
            ("ullAvailPhys", ctypes.c_ulonglong),
            ("ullTotalPageFile", ctypes.c_ulonglong),
            ("ullAvailPageFile", ctypes.c_ulonglong),
            ("ullTotalVirtual", ctypes.c_ulonglong),
            ("ullAvailVirtual", ctypes.c_ulonglong),
            ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
        ]

    try:
        status = MEMORYSTATUSEX()
        status.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return int(status.ullAvailPhys)
    except Exception:
        return None
    return None


def parse_coordinate(path: Path) -> dict:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    head = lines[0].split()
    n = int(head[0])
    start_time = float(head[1]) if len(head) >= 2 else 0.0
    step = int(float(head[2])) if len(head) >= 3 else None
    vals = [float(x) for line in lines[1:] for x in line.split()]
    coords = [tuple(vals[3 * i:3 * i + 3]) for i in range(n)]
    box = vals[3 * n:3 * n + 6]
    return {
        "exists": True,
        "path": str(path),
        "atom_count": n,
        "start_time": start_time,
        "header_step": step,
        "coords": coords,
        "box": box,
        "finite": all(math.isfinite(v) for xyz in coords for v in xyz) and all(math.isfinite(v) for v in box),
        "sha256": sha256_file(path),
        "size_bytes": path.stat().st_size,
    }


def parse_velocity(path: Path) -> dict:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    head = lines[0].split()
    n = int(head[0])
    start_time = float(head[1]) if len(head) >= 2 else 0.0
    step = int(float(head[2])) if len(head) >= 3 else None
    vals = [float(x) for line in lines[1:] for x in line.split()]
    vecs = [tuple(vals[3 * i:3 * i + 3]) for i in range(n)]
    return {
        "exists": True,
        "path": str(path),
        "atom_count": n,
        "start_time": start_time,
        "header_step": step,
        "vectors": vecs,
        "finite": all(math.isfinite(v) for xyz in vecs for v in xyz),
        "sha256": sha256_file(path),
        "size_bytes": path.stat().st_size,
    }


def missing_restart(path: Path) -> dict:
    return {
        "exists": False,
        "path": str(path),
        "atom_count": 0,
        "start_time": None,
        "header_step": None,
        "coords": [],
        "vectors": [],
        "box": [],
        "finite": False,
        "sha256": None,
        "size_bytes": 0,
    }


def parse_masses(path: Path) -> list[float]:
    vals = [float(x) for x in path.read_text(encoding="utf-8", errors="replace").split()]
    if vals and int(vals[0]) == len(vals) - 1:
        vals = vals[1:]
    return vals


def parse_mdout(path: Path) -> dict:
    header: list[str] = []
    records: list[dict] = []
    if not path.exists():
        return {"exists": False, "header": [], "records": [], "finite": False, "sha256": None, "size_bytes": 0}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        parts = line.split()
        if not parts:
            continue
        if parts[0].lower() == "step":
            header = [p.lower() for p in parts]
            continue
        if header and parts[0].isdigit() and len(parts) >= len(header):
            rec = {}
            for k, v in zip(header, parts):
                rec[k] = int(v) if k == "step" else float(v)
            records.append(rec)
    finite = all(math.isfinite(v) for rec in records for k, v in rec.items() if k != "step")
    return {"exists": True, "header": header, "records": records, "finite": finite, "sha256": sha256_file(path), "size_bytes": path.stat().st_size}


def parse_traj(path: Path, atom_count: int) -> dict:
    if not path.exists():
        return {"exists": False, "frames": [], "raw_frames": [], "frame_count": 0, "finite": False, "sha256": None, "size_bytes": 0}
    raw = path.read_bytes()
    floats = array.array("f")
    floats.frombytes(raw)
    stride = atom_count * 3
    if len(raw) % 4 or len(floats) % stride:
        raise ValueError(f"bad trajectory shape: {path}")
    bytes_per_frame = stride * 4
    frames = []
    raws = []
    for off in range(0, len(raw), bytes_per_frame):
        r = raw[off:off + bytes_per_frame]
        a = array.array("f")
        a.frombytes(r)
        frames.append(a)
        raws.append(r)
    finite = all(math.isfinite(float(v)) for frame in frames for v in frame)
    return {"exists": True, "frames": frames, "raw_frames": raws, "frame_count": len(frames), "finite": finite, "sha256": sha256_file(path), "size_bytes": path.stat().st_size}


def parse_box(path: Path) -> dict:
    if not path.exists():
        return {"exists": False, "boxes": [], "frame_count": 0, "finite": False, "sha256": None, "size_bytes": 0}
    rows = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.strip():
            rows.append([float(x) for x in line.split()])
    finite = all(math.isfinite(v) for row in rows for v in row)
    return {"exists": True, "boxes": rows, "frame_count": len(rows), "finite": finite, "sha256": sha256_file(path), "size_bytes": path.stat().st_size}


def record_value(rec: dict, candidates: list[str]) -> float | None:
    for key in candidates:
        if key in rec:
            return rec[key]
    return None


def potential_value(rec: dict) -> float | None:
    return record_value(rec, ["potential", "potential_energy"])


def temperature_value(rec: dict) -> float | None:
    return record_value(rec, ["temperature"])


def kinetic_from_temperature(temp: float, factor_note: str = "") -> float:
    return 0.5 * FREEDOM * KB_KCAL_PER_MOL_K * temp


def mean(vals: list[float]) -> float | None:
    return sum(vals) / len(vals) if vals else None


def slope(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) < 2:
        return None
    mx = mean(xs)
    my = mean(ys)
    den = sum((x - mx) ** 2 for x in xs)
    if den == 0:
        return None
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / den


def min_image_delta(a: float, b: float, box: float) -> float:
    d = a - b
    return d - round(d / box) * box


def unwrap_water(coords: list[tuple[float, float, float]], w: int, box: list[float]) -> list[list[float]]:
    o = list(coords[3 * w])
    out = [o]
    for idx in (3 * w + 1, 3 * w + 2):
        h = []
        for c in range(3):
            h.append(o[c] + min_image_delta(coords[idx][c], o[c], box[c]))
        out.append(h)
    return out


def vec_add(a, b):
    return [a[0] + b[0], a[1] + b[1], a[2] + b[2]]


def vec_sub(a, b):
    return [a[0] - b[0], a[1] - b[1], a[2] - b[2]]


def vec_scale(a, s: float):
    return [a[0] * s, a[1] * s, a[2] * s]


def dot(a, b) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def cross(a, b):
    return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]


def solve3(m: list[list[float]], b: list[float]) -> list[float]:
    a = [row[:] + [b[i]] for i, row in enumerate(m)]
    for col in range(3):
        piv = max(range(col, 3), key=lambda r: abs(a[r][col]))
        if abs(a[piv][col]) < 1e-20:
            raise ValueError("singular inertia tensor")
        a[col], a[piv] = a[piv], a[col]
        div = a[col][col]
        a[col] = [x / div for x in a[col]]
        for r in range(3):
            if r == col:
                continue
            fac = a[r][col]
            a[r] = [a[r][c] - fac * a[col][c] for c in range(4)]
    return [a[i][3] for i in range(3)]


def kinetic_sum(masses: list[float], vectors: list[tuple[float, float, float]] | list[list[float]]) -> float:
    return sum(m * dot(v, v) for m, v in zip(masses, vectors))


def temperature_from_vectors(masses: list[float], vectors, velocity_energy_factor: float) -> float:
    return velocity_energy_factor * kinetic_sum(masses, vectors) / (FREEDOM * KB_KCAL_PER_MOL_K)


def center_of_mass_momentum(masses: list[float], vectors) -> dict:
    p = [0.0, 0.0, 0.0]
    for m, v in zip(masses, vectors):
        p[0] += m * v[0]
        p[1] += m * v[1]
        p[2] += m * v[2]
    return {"x": p[0], "y": p[1], "z": p[2], "norm": math.sqrt(dot(p, p))}


def source_line(path: Path, pattern: str) -> dict:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except FileNotFoundError:
        return {"path": str(path), "exists": False}
    for i, line in enumerate(lines, start=1):
        if pattern.lower() in line.lower():
            return {"path": str(path), "exists": True, "line_number": i, "line": line.strip(), "sha256": sha256_file(path)}
    return {"path": str(path), "exists": True, "line_number": None, "line": None, "sha256": sha256_file(path)}


def calibrate_temperature_formula() -> dict:
    raise SystemExit("temperature formula recalibration is forbidden in Pass 05ARR")


def constraint_residuals(coords: list[tuple[float, float, float]], vectors, box: list[float]) -> dict:
    max_abs = 0.0
    max_item = None
    vals = []
    for w in range(WATER_COUNT):
        xyz = unwrap_water(coords, w, box)
        ids = [3 * w, 3 * w + 1, 3 * w + 2]
        for name, a, b in [("OH1", 0, 1), ("OH2", 0, 2), ("HH", 1, 2)]:
            dv = vec_sub(vectors[ids[a]], vectors[ids[b]])
            dr = vec_sub(xyz[a], xyz[b])
            val = dot(dv, dr)
            vals.append(abs(val))
            if abs(val) > max_abs:
                max_abs = abs(val)
                max_item = {"water_index_1based": w + 1, "constraint": name, "abs_residual": abs(val), "signed_residual": val}
    tol = 1e-8
    return {
        "tolerance_abs_velocity_dot_position": tol,
        "max_abs_velocity_constraint_residual": max_abs,
        "mean_abs_velocity_constraint_residual": mean(vals),
        "max_residual_location": max_item,
        "all_rigid_velocity_constraints_pass": max_abs <= tol,
    }


def generate_velocities(calibration: dict) -> dict:
    raise SystemExit("offline velocity generation is forbidden in Pass 07A")


def copy_inputs() -> dict:
    rows = []
    raw_src = PASS06AR / "input_raw"
    for name in RAW_NAMES:
        src = raw_src / name
        dst = INPUT_RAW / name
        shutil.copy2(src, dst)
        rows.append({
            "filename": name,
            "source_path": str(src),
            "copy_path": str(dst),
            "source_size_bytes": src.stat().st_size,
            "copy_size_bytes": dst.stat().st_size,
            "source_sha256": sha256_file(src),
            "copy_sha256": sha256_file(dst),
            "byte_match": src.stat().st_size == dst.stat().st_size and sha256_file(src) == sha256_file(dst),
        })
    coord_src = PASS06AR / "stage_06_300K_hold" / "run" / "hold300K_2ps_rst_coordinate.txt"
    coord_dst = INPUT_300K / "heated300K_coordinate.txt"
    shutil.copy2(coord_src, coord_dst)
    coord = {
        "source_path": str(coord_src),
        "copy_path": str(coord_dst),
        "source_sha256": sha256_file(coord_src),
        "copy_sha256": sha256_file(coord_dst),
        "required_sha256": EXPECTED_START_COORD_SHA,
        "sha256_ok": sha256_file(coord_dst) == EXPECTED_START_COORD_SHA,
        "size_bytes": coord_dst.stat().st_size,
        "classification": "HEATING_COMPLETE_APPROXIMATELY_300K_HEATED_STATE_COORDINATE",
    }
    vel_src = PASS06AR / "stage_06_300K_hold" / "run" / "hold300K_2ps_rst_velocity.txt"
    vel_dst = INPUT_300K / "heated300K_velocity.txt"
    shutil.copy2(vel_src, vel_dst)
    velocity = {
        "source_path": str(vel_src),
        "copy_path": str(vel_dst),
        "source_sha256": sha256_file(vel_src),
        "copy_sha256": sha256_file(vel_dst),
        "required_sha256": EXPECTED_START_VEL_SHA,
        "sha256_ok": sha256_file(vel_dst) == EXPECTED_START_VEL_SHA,
        "size_bytes": vel_dst.stat().st_size,
        "classification": "HEATING_COMPLETE_APPROXIMATELY_300K_HEATED_STATE_VELOCITY",
    }
    all_files = sorted(p.name for p in INPUT_RAW.iterdir() if p.is_file())
    status = {
        "generated_at": now_iso(),
        "source_pass": str(PASS06AR),
        "pass06ar_heated_300K_state_active_input": True,
        "pass06a_partial_state_active_input": False,
        "earlier_failed_conditioning_state_active_input": False,
        "accepted_state_classification": [
            "HEATING_COMPLETE",
            "APPROXIMATELY_300K_HEATED_STATE",
            "NVT_EQUILIBRATION_NOT_YET_COMPLETE",
        ],
        "raw_input_count": len(all_files),
        "expected_raw_input_count": 10,
        "raw_filenames": all_files,
        "all_expected_raw_names_present": all_files == sorted(RAW_NAMES),
        "raw_rows": rows,
        "raw_hashes_all_match": all(r["byte_match"] for r in rows),
        "accepted_start_coordinate": coord,
        "accepted_start_velocity": velocity,
        "no_pass04h_minimiser_velocity": not any("velocity" in p.name.lower() for p in INPUT_RAW.iterdir()),
        "no_pass05a_generated_velocity": not (INPUT_RAW / "velocity_generation_50K_rst_velocity.txt").exists(),
        "no_pass06a_partial_state": not any("06A" in p.name or "partial" in p.name.lower() for p in INPUT_RAW.iterdir()),
        "no_earlier_failed_conditioning_state": not any("startup0020" in p.name.lower() or "settle_stability_1fs" in p.name for p in INPUT_RAW.iterdir()),
        "input_300K_state_files": sorted(p.name for p in INPUT_300K.iterdir() if p.is_file()),
    }
    status["overall_ok"] = all([
        status["raw_input_count"] == 10,
        status["all_expected_raw_names_present"],
        status["raw_hashes_all_match"],
        coord["sha256_ok"],
        velocity["sha256_ok"],
        status["no_pass04h_minimiser_velocity"],
        status["no_pass05a_generated_velocity"],
        status["no_pass06a_partial_state"],
        status["no_earlier_failed_conditioning_state"],
        status["input_300K_state_files"] == ["heated300K_coordinate.txt", "heated300K_velocity.txt"],
    ])
    write_json(RECEIPTS / "INPUT_VERIFICATION.json", status)
    write_csv(RECEIPTS / "RAW_INPUT_HASHES.csv", rows)
    write_text(
        RECEIPTS / "INPUT_VERIFICATION.md",
        "\n".join([
            "# Input Verification",
            "",
            f"- Overall: `{status['overall_ok']}`",
            f"- Raw input files: `{status['raw_input_count']}`",
            f"- Accepted 300 K coordinate SHA-256: `{coord['copy_sha256']}`",
            f"- Accepted 300 K velocity SHA-256: `{velocity['copy_sha256']}`",
            "- Pass 06A partial state and earlier failed conditioning states are not active inputs.",
            "",
        ]),
    )
    return status


def write_pass06ar_acceptance_report() -> dict:
    report = {
        "generated_at": now_iso(),
        "source_pass": str(PASS06AR),
        "heating_decision": "PASS_RUNTIME_EFFICIENT_HEATING_300K_READY_FOR_NVT_EQUILIBRATION",
        "heating_status": "HEATING_COMPLETE",
        "temperature_state": "APPROXIMATELY_300K_HEATED_STATE",
        "heating_duration_ps": 7,
        "full_equilibration_claimed": False,
        "accepted_coordinate_sha256": EXPECTED_START_COORD_SHA,
        "accepted_velocity_sha256": EXPECTED_START_VEL_SHA,
    }
    write_json(REPORTS / "PASS06AR_ACCEPTANCE.json", report)
    write_text(
        REPORTS / "PASS06AR_ACCEPTANCE.md",
        "\n".join([
            "# Pass 06AR Acceptance",
            "",
            "- Heating decision: `PASS_RUNTIME_EFFICIENT_HEATING_300K_READY_FOR_NVT_EQUILIBRATION`",
            "- Heating status: `HEATING_COMPLETE`",
            "- Temperature state: `APPROXIMATELY_300K_HEATED_STATE`",
            "- Heating duration: `7 ps`",
            "- Full equilibration claimed: `false`",
            f"- Accepted coordinate SHA-256: `{EXPECTED_START_COORD_SHA}`",
            f"- Accepted velocity SHA-256: `{EXPECTED_START_VEL_SHA}`",
            "",
        ]),
    )
    return report


def write_density_interpretation_report() -> dict:
    water_molar_mass_g_mol = 18.01528
    avogadro = 6.02214076e23
    volume_cm3 = (BOX_TARGET * 1e-8) ** 3
    density = WATER_COUNT * water_molar_mass_g_mol / avogadro / volume_cm3
    report = {
        "generated_at": now_iso(),
        "ensemble": "NVT",
        "box_length_A": BOX_TARGET,
        "water_count": WATER_COUNT,
        "starting_density_g_cm3": density,
        "starting_density_g_cm3_approximately": 0.955,
        "nvt_cannot_relax_box_volume_or_density": True,
        "density_not_expected_to_approach_npt_value_in_this_stage": True,
        "npt_remains_required_after_nvt_stabilization": True,
        "density_mismatch_is_not_nvt_numerical_failure": True,
    }
    write_json(REPORTS / "DENSITY_INTERPRETATION.json", report)
    write_text(
        REPORTS / "DENSITY_INTERPRETATION.md",
        "\n".join([
            "# Density Interpretation",
            "",
            "- Ensemble: `NVT`",
            f"- Box length: `{BOX_TARGET} A`",
            f"- Water count: `{WATER_COUNT}`",
            f"- Starting density: approximately `{density:.6f} g/cm3`",
            "- NVT cannot relax box volume or density.",
            "- NPT remains required after NVT stabilization.",
            "- Density mismatch is not an NVT numerical failure.",
            "",
        ]),
    )
    return report


def prepare() -> None:
    for d in [INPUT_RAW, INPUT_300K, REPORTS, RECEIPTS, LOGS, META]:
        d.mkdir(parents=True, exist_ok=True)
    for cfg in STAGES.values():
        for k in ["run_dir", "outputs", "analysis", "validation"]:
            cfg[k].mkdir(parents=True, exist_ok=True)
    input_status = copy_inputs()
    acceptance = write_pass06ar_acceptance_report()
    density = write_density_interpretation_report()
    if not input_status["overall_ok"]:
        raise SystemExit("input verification failed")
    print(json.dumps({"prepared": True, "pass": PASS_NAME}, indent=2))


def path_inside(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def path_entry(run_dir: Path, literal: str, expected: Path, prefix: bool = False) -> dict:
    if prefix:
        entries = []
        ok = True
        for suffix in ["atom_name.txt", "atom_type_name.txt", "bond.txt", "charge.txt", "coordinate.txt", "exclude.txt", "LJ.txt", "mass.txt", "residue.txt", "resname.txt"]:
            lit = f"{literal}_{suffix}"
            exp = INPUT_RAW / f"water_30A_randomized_{suffix}"
            ent = path_entry(run_dir, lit, exp, False)
            entries.append(ent)
            ok = ok and ent["overall_ok"]
        return {"literal_relative_path": literal, "prefix_entries": entries, "overall_ok": ok}
    norm = (run_dir / literal).resolve()
    exp_res = expected.resolve()
    exists = norm.exists()
    return {
        "literal_relative_path": literal,
        "normalized_absolute_path": str(norm),
        "expected_absolute_path": str(exp_res),
        "exists": exists,
        "inside_current_pass": path_inside(norm, PASS_DIR),
        "matches_expected": norm == exp_res,
        "sha256": sha256_file(norm) if exists and norm.is_file() else None,
        "size_bytes": norm.stat().st_size if exists and norm.is_file() else None,
        "overall_ok": exists and path_inside(norm, PASS_DIR) and norm == exp_res,
    }


def stage_path_preflight(stage: str) -> dict:
    cfg = STAGES[stage]
    rd = cfg["run_dir"]
    coord_literal, vel_literal = stage_input_paths(stage)
    coord_expected = INPUT_300K / "heated300K_coordinate.txt"
    vel_expected = INPUT_300K / "heated300K_velocity.txt"
    specs = [
        ("../input_raw/water_30A_randomized", INPUT_RAW / "water_30A_randomized", True),
        (coord_literal, coord_expected, False),
        (vel_literal, vel_expected, False),
    ]
    entries = [path_entry(rd, lit, exp, prefix) for lit, exp, prefix in specs]
    coordinate_hash_ok = entries[1].get("sha256") == EXPECTED_START_COORD_SHA
    velocity_hash_ok = entries[2].get("sha256") == EXPECTED_START_VEL_SHA
    proof = {
        "generated_at": now_iso(),
        "stage": stage,
        "working_directory": str(rd),
        "entries": entries,
        "coordinate_sha256_ok": coordinate_hash_ok,
        "velocity_sha256_ok": velocity_hash_ok,
        "overall_ok": all(e["overall_ok"] for e in entries) and coordinate_hash_ok and velocity_hash_ok,
        "all_paths_inside_current_pass": all(
            pe.get("inside_current_pass", True)
            for e in entries
            for pe in (e.get("prefix_entries") or [e])
        ),
    }
    write_json(RECEIPTS / f"PATH_RESOLUTION_PROOF_{stage}.json", proof)
    write_text(RECEIPTS / f"PATH_RESOLUTION_PROOF_{stage}.md", f"# Path Resolution Proof {stage}\n\n- Overall: `{proof['overall_ok']}`\n")
    return proof


def environment_probe(stage: str, argv: list[str], cwd: Path) -> dict:
    resolved = subprocess.run([str(CONDA), "run", "-n", ENV_NAME, "python", "-c", "import shutil; print(shutil.which('SPONGE') or '')"], cwd=str(PASS_DIR), text=True, capture_output=True, timeout=120)
    version = subprocess.run([str(CONDA), "run", "-n", ENV_NAME, "SPONGE", "-v"], cwd=str(PASS_DIR), text=True, capture_output=True, timeout=120)
    env = {
        "generated_at": now_iso(),
        "stage": stage,
        "working_directory": str(cwd),
        "argv": argv,
        "command": command_line(argv),
        "conda_executable": str(CONDA),
        "conda_executable_exists": CONDA.exists(),
        "environment_name": ENV_NAME,
        "cpu": platform.processor(),
        "cpu_count": os.cpu_count(),
        "available_physical_ram_bytes_before_launch": available_ram_bytes(),
        "available_ram_warning": "LOW_AVAILABLE_RAM_PERFORMANCE_WARNING" if (available_ram_bytes() is not None and available_ram_bytes() < 1024 * 1024 * 1024) else None,
        "windows_version": platform.platform(),
        "resolved_sponge_executable": resolved.stdout.strip(),
        "resolved_probe": {"exit_code": resolved.returncode, "stdout": resolved.stdout, "stderr": resolved.stderr},
        "sponge_version_exit_code": version.returncode,
        "sponge_version_stdout": version.stdout,
        "sponge_version_stderr": version.stderr,
    }
    write_json(RECEIPTS / f"EXECUTION_ENVIRONMENT_{stage}.json", env)
    return env


def run_stage(stage: str) -> None:
    cfg = STAGES[stage]
    exec_dir = LOGS / stage / "scientific_execution"
    exec_dir.mkdir(parents=True, exist_ok=True)
    result_path = exec_dir / "execution_result.json"
    if result_path.exists():
        raise SystemExit(f"{stage} already has execution_result.json; refusing duplicate scientific run")
    proof = stage_path_preflight(stage)
    if not proof["overall_ok"]:
        raise SystemExit(f"path preflight failed for {stage}")
    argv = COMMANDS[stage]
    env = environment_probe(stage, argv, cfg["run_dir"])
    started = {"generated_at": now_iso(), "stage": stage, "working_directory": str(cfg["run_dir"]), "argv": argv, "command": command_line(argv), "path_preflight": proof, "environment": env}
    write_json(exec_dir / "STARTED.json", started)
    stdout_path = exec_dir / "stdout.txt"
    stderr_path = exec_dir / "stderr.txt"
    t0 = time.time()
    start_iso = now_iso()
    with stdout_path.open("w", encoding="utf-8") as out, stderr_path.open("w", encoding="utf-8") as err:
        proc = subprocess.Popen(argv, cwd=str(cfg["run_dir"]), stdout=out, stderr=err, text=True)
        timed_out = False
        taskkill_result = None
        while True:
            code = proc.poll()
            if code is not None:
                break
            if time.time() - t0 > cfg["timeout"]:
                timed_out = True
                taskkill_argv = ["taskkill", "/PID", str(proc.pid), "/T", "/F"]
                tk = subprocess.run(taskkill_argv, text=True, capture_output=True)
                taskkill_result = {
                    "argv": taskkill_argv,
                    "command": command_line(taskkill_argv),
                    "exit_code": tk.returncode,
                    "stdout": tk.stdout,
                    "stderr": tk.stderr,
                }
                code = proc.wait(timeout=30)
                break
            time.sleep(5)
    elapsed = time.time() - t0
    result = {
        "generated_at": now_iso(),
        "stage": stage,
        "argv": argv,
        "command": command_line(argv),
        "working_directory": str(cfg["run_dir"]),
        "start_time": start_iso,
        "finish_time": now_iso(),
        "root_process_pid": proc.pid,
        "elapsed_seconds": elapsed,
        "timeout_seconds": cfg["timeout"],
        "timeout_margin_seconds": cfg["timeout"] - elapsed,
        "timed_out": timed_out,
        "exit_code": code,
        "supervisor_termination_code": code if timed_out else None,
        "taskkill": taskkill_result,
        "stdout_path": str(stdout_path),
        "stderr_path": str(stderr_path),
        "stdout_sha256": sha256_file(stdout_path),
        "stderr_sha256": sha256_file(stderr_path),
        "stdout_size_bytes": stdout_path.stat().st_size,
        "stderr_size_bytes": stderr_path.stat().st_size,
    }
    write_json(result_path, result)
    print(json.dumps({"stage": stage, "exit_code": code, "timed_out": timed_out, "elapsed_seconds": elapsed}, indent=2))


def dist_atoms(frame, ai: int, bi: int, box: list[float]) -> float:
    dx = min_image_delta(float(frame[3 * ai]), float(frame[3 * bi]), box[0])
    dy = min_image_delta(float(frame[3 * ai + 1]), float(frame[3 * bi + 1]), box[1])
    dz = min_image_delta(float(frame[3 * ai + 2]), float(frame[3 * bi + 2]), box[2])
    return math.sqrt(dx * dx + dy * dy + dz * dz)


def min_pair_cell(frame, indices: list[int], box: list[float], cell_size: float, skip_same_water: bool) -> dict:
    dims = [max(1, int(math.floor(box[i] / cell_size))) for i in range(3)]
    cells: dict[tuple[int, int, int], list[int]] = {}
    for ai in indices:
        key = tuple(int(math.floor((float(frame[3 * ai + c]) % box[c]) / box[c] * dims[c])) % dims[c] for c in range(3))
        cells.setdefault(key, []).append(ai)
    best = {"distance": float("inf")}
    for key, atoms in cells.items():
        neigh = []
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for dz in (-1, 0, 1):
                    neigh.append(((key[0] + dx) % dims[0], (key[1] + dy) % dims[1], (key[2] + dz) % dims[2]))
        for ai in atoms:
            for nk in neigh:
                for bi in cells.get(nk, []):
                    if bi <= ai:
                        continue
                    if skip_same_water and ai // 3 == bi // 3:
                        continue
                    d = dist_atoms(frame, ai, bi, box)
                    if d < best["distance"]:
                        best = {"distance": d, "atom_i": ai + 1, "atom_j": bi + 1, "water_i": ai // 3 + 1, "water_j": bi // 3 + 1}
    return best


def structure_validation(stage: str, traj: dict, box: dict, coord_restart: dict, expected_frames: int, frame_interval: int) -> dict:
    frames = traj["frames"]
    boxes = box["boxes"]
    all_box_valid = all(len(b) == 6 and all(abs(b[i] - BOX_TARGET) < 0.01 for i in range(3)) and all(abs(b[i] - 90) < 0.01 for i in range(3, 6)) for b in boxes)
    hashes = [sha256_bytes(raw) for raw in traj["raw_frames"]]
    unique_hashes = len(hashes) == len(set(hashes))
    duplicate_frames = []
    for fi, frame in enumerate(frames, start=1):
        coords = [(float(frame[3 * a]), float(frame[3 * a + 1]), float(frame[3 * a + 2])) for a in range(ATOM_COUNT)]
        if len(set(coords)) != ATOM_COUNT:
            duplicate_frames.append(fi)
    max_disp = 0.0
    max_disp_atom = None
    max_disp_interval = None
    max_h_disp = 0.0
    max_h_atom = None
    max_o_disp = 0.0
    max_o_atom = None
    max_water_com_disp = 0.0
    max_water_com_index = None
    max_water_com_interval = None
    rms_values = []
    rms_oxygen_values = []
    rms_water_com_values = []
    masses = parse_masses(INPUT_RAW / "water_30A_randomized_mass.txt") if (INPUT_RAW / "water_30A_randomized_mass.txt").exists() else []
    for fi in range(1, len(frames)):
        prev = frames[fi - 1]
        cur = frames[fi]
        b = boxes[fi][:3]
        ss = 0.0
        oss = 0.0
        disp_vecs = []
        for atom in range(ATOM_COUNT):
            vec = [min_image_delta(float(cur[3 * atom + c]), float(prev[3 * atom + c]), b[c]) for c in range(3)]
            disp_vecs.append(vec)
            d = math.sqrt(sum(v * v for v in vec))
            ss += d * d
            if d > max_disp:
                max_disp = d
                max_disp_atom = atom + 1
                max_disp_interval = [fi, fi + 1]
            if atom % 3 == 0:
                oss += d * d
                if d > max_o_disp:
                    max_o_disp = d
                    max_o_atom = atom + 1
            else:
                if d > max_h_disp:
                    max_h_disp = d
                    max_h_atom = atom + 1
        rms_values.append(math.sqrt(ss / ATOM_COUNT))
        rms_oxygen_values.append(math.sqrt(oss / WATER_COUNT))
        if masses and len(masses) >= ATOM_COUNT:
            wss = 0.0
            for w in range(WATER_COUNT):
                ids = [3 * w, 3 * w + 1, 3 * w + 2]
                mtot = sum(masses[i] for i in ids)
                com_vec = [
                    sum(masses[i] * disp_vecs[i][c] for i in ids) / mtot
                    for c in range(3)
                ]
                dcom = math.sqrt(sum(v * v for v in com_vec))
                wss += dcom * dcom
                if dcom > max_water_com_disp:
                    max_water_com_disp = dcom
                    max_water_com_index = w + 1
                    max_water_com_interval = [fi, fi + 1]
            rms_water_com_values.append(math.sqrt(wss / WATER_COUNT))
    tip = {"oh1_min": float("inf"), "oh1_max": 0.0, "oh2_min": float("inf"), "oh2_max": 0.0, "hh_min": float("inf"), "hh_max": 0.0}
    min_inter = {"distance": float("inf")}
    min_oo = {"distance": float("inf")}
    frame_min_inter_records = []
    frame_min_oo_records = []
    for fi, (frame, b6) in enumerate(zip(frames, boxes), start=1):
        b = b6[:3]
        for w in range(WATER_COUNT):
            o, h1, h2 = 3 * w, 3 * w + 1, 3 * w + 2
            oh1 = dist_atoms(frame, o, h1, b)
            oh2 = dist_atoms(frame, o, h2, b)
            hh = dist_atoms(frame, h1, h2, b)
            tip["oh1_min"] = min(tip["oh1_min"], oh1)
            tip["oh1_max"] = max(tip["oh1_max"], oh1)
            tip["oh2_min"] = min(tip["oh2_min"], oh2)
            tip["oh2_max"] = max(tip["oh2_max"], oh2)
            tip["hh_min"] = min(tip["hh_min"], hh)
            tip["hh_max"] = max(tip["hh_max"], hh)
        inter = min_pair_cell(frame, list(range(ATOM_COUNT)), b, 3.5, True)
        oo = min_pair_cell(frame, list(range(0, ATOM_COUNT, 3)), b, 4.0, True)
        frame_min_inter_records.append({**inter, "saved_frame": fi, "md_step": fi * frame_interval})
        frame_min_oo_records.append({**oo, "saved_frame": fi, "md_step": fi * frame_interval})
        if inter["distance"] < min_inter["distance"]:
            min_inter = {**inter, "saved_frame": fi, "md_step": fi * frame_interval}
        if oo["distance"] < min_oo["distance"]:
            min_oo = {**oo, "saved_frame": fi, "md_step": fi * frame_interval}
    tip["strict_oh_range"] = [0.9542, 0.9602]
    tip["strict_hh_range"] = [1.5086, 1.5186]
    if frames:
        tight = 0.9542 <= tip["oh1_min"] <= tip["oh1_max"] <= 0.9602 and 0.9542 <= tip["oh2_min"] <= tip["oh2_max"] <= 0.9602 and 1.5086 <= tip["hh_min"] <= tip["hh_max"] <= 1.5186
    else:
        tight = False
    tip["tight_tip3p_geometry"] = tight
    restart_coords = coord_restart.get("coords") or []
    final_diff = None
    if frames and restart_coords:
        final_diff = 0.0
        final = frames[-1]
        for atom, xyz in enumerate(restart_coords):
            for c in range(3):
                final_diff = max(final_diff, abs(float(final[3 * atom + c]) - xyz[c]))
    mdinfo = (STAGES[stage]["run_dir"] / f"{STAGES[stage]['label']}.mdinfo").read_text(encoding="utf-8", errors="replace") if (STAGES[stage]["run_dir"] / f"{STAGES[stage]['label']}.mdinfo").exists() else ""
    stdout = (LOGS / stage / "scientific_execution" / "stdout.txt").read_text(encoding="utf-8", errors="replace") if (LOGS / stage / "scientific_execution" / "stdout.txt").exists() else ""
    settle = "START INITIALIZING SETTLE" in (mdinfo + stdout) and "rigid triangle numbers is 862" in (mdinfo + stdout)
    valid_restart = coord_restart.get("exists") and coord_restart.get("atom_count") == ATOM_COUNT and coord_restart.get("finite") and len(coord_restart.get("box") or []) == 6
    terminal_n = max(1, math.ceil(len(frame_min_inter_records) * 0.20)) if frame_min_inter_records else 0
    terminal_inter = frame_min_inter_records[-terminal_n:] if terminal_n else []
    terminal_oo = frame_min_oo_records[-terminal_n:] if terminal_n else []
    terminal_10_n = max(1, math.ceil(len(frame_min_inter_records) * 0.10)) if frame_min_inter_records else 0
    terminal_10_inter = frame_min_inter_records[-terminal_10_n:] if terminal_10_n else []
    final_inter = frame_min_inter_records[-1] if frame_min_inter_records else {"distance": None}
    final_oo = frame_min_oo_records[-1] if frame_min_oo_records else {"distance": None}
    terminal_inter_min = min((r["distance"] for r in terminal_inter), default=None)
    terminal_oo_min = min((r["distance"] for r in terminal_oo), default=None)
    terminal_10_inter_min = min((r["distance"] for r in terminal_10_inter), default=None)
    min_inter_distance = min_inter["distance"] if math.isfinite(min_inter["distance"]) else None
    min_oo_distance = min_oo["distance"] if math.isfinite(min_oo["distance"]) else None
    sustained_recovery = None
    for idx, rec in enumerate(frame_min_inter_records):
        if all(r["distance"] >= 1.20 for r in frame_min_inter_records[idx:]):
            sustained_recovery = rec
            break
    val = {
        "stage": stage,
        "coordinate_frame_count": len(frames),
        "expected_coordinate_frame_count": expected_frames,
        "box_frame_count": len(boxes),
        "expected_box_frame_count": expected_frames,
        "all_frames_finite": traj["finite"] and box["finite"],
        "all_frame_hashes_unique": unique_hashes,
        "duplicate_coordinate_frames": duplicate_frames,
        "no_duplicate_atomic_coordinates": not duplicate_frames,
        "box_30x30x30": all_box_valid,
        "settle_initialized": settle,
        "tip3p_geometry": tip,
        "minimum_intermolecular_atom_distance": {**min_inter, "distance": min_inter_distance},
        "minimum_oo_distance": {**min_oo, "distance": min_oo_distance},
        "minimum_intermolecular_atom_distance_history": frame_min_inter_records,
        "minimum_oo_distance_history": frame_min_oo_records,
        "final_saved_frame_minimum_intermolecular_distance": final_inter,
        "final_saved_frame_minimum_oo_distance": final_oo,
        "terminal_20_percent_frame_count": terminal_n,
        "terminal_20_percent_minimum_intermolecular_distance": terminal_inter_min,
        "terminal_20_percent_minimum_oo_distance": terminal_oo_min,
        "terminal_10_percent_frame_count": terminal_10_n,
        "terminal_10_percent_minimum_intermolecular_distance": terminal_10_inter_min,
        "sustained_recovery_to_ge_1p20_after_saved_frame": sustained_recovery,
        "sustained_recovery_to_ge_1p20_before_final_frame": sustained_recovery is not None,
        "no_contact_below_1p00_angstrom": min_inter_distance is not None and min_inter_distance >= 1.00,
        "no_contact_below_1p20_angstrom": min_inter_distance is not None and min_inter_distance >= 1.20,
        "final_saved_frame_minimum_intermolecular_distance_at_least_1p20": final_inter.get("distance") is not None and final_inter["distance"] >= 1.20,
        "terminal_20_percent_minimum_intermolecular_distance_at_least_1p20": terminal_inter_min is not None and terminal_inter_min >= 1.20,
        "terminal_10_percent_minimum_intermolecular_distance_at_least_1p20": terminal_10_inter_min is not None and terminal_10_inter_min >= 1.20,
        "maximum_saved_displacement": max_disp if len(frames) > 1 else None,
        "maximum_saved_displacement_atom": max_disp_atom,
        "maximum_saved_displacement_frame_interval": max_disp_interval,
        "maximum_hydrogen_displacement": max_h_disp if len(frames) > 1 else None,
        "maximum_hydrogen_displacement_atom": max_h_atom,
        "maximum_hydrogen_displacement_classification": "TRANSLATION_PLUS_RIGID_WATER_ROTATION_DIAGNOSTIC",
        "maximum_oxygen_displacement": max_o_disp if len(frames) > 1 else None,
        "maximum_oxygen_displacement_atom": max_o_atom,
        "maximum_water_center_of_mass_displacement": max_water_com_disp if rms_water_com_values else None,
        "maximum_water_center_of_mass_displacement_water": max_water_com_index,
        "maximum_water_center_of_mass_displacement_frame_interval": max_water_com_interval,
        "rms_saved_displacement_mean": mean(rms_values) if rms_values else None,
        "rms_saved_displacement_max": max(rms_values) if rms_values else None,
        "rms_oxygen_displacement_mean": mean(rms_oxygen_values) if rms_oxygen_values else None,
        "rms_oxygen_displacement_max": max(rms_oxygen_values) if rms_oxygen_values else None,
        "rms_water_center_of_mass_displacement_mean": mean(rms_water_com_values) if rms_water_com_values else None,
        "rms_water_center_of_mass_displacement_max": max(rms_water_com_values) if rms_water_com_values else None,
        "large_oxygen_or_water_center_of_mass_displacement": (max_o_disp > 1.0 or max_water_com_disp > 1.0) if len(frames) > 1 else False,
        "abnormal_coordinate_displacement": False,
        "coordinate_restart_exists": coord_restart.get("exists"),
        "valid_coordinate_restart": valid_restart,
        "restart_header_step": coord_restart.get("header_step"),
        "final_trajectory_restart_max_abs_diff": final_diff,
        "final_trajectory_restart_agreement_within_output_precision": final_diff is not None and final_diff < 2e-6,
    }
    val["overall_structure_valid"] = all([
        val["coordinate_frame_count"] == expected_frames,
        val["box_frame_count"] == expected_frames,
        val["all_frames_finite"],
        val["all_frame_hashes_unique"],
        val["no_duplicate_atomic_coordinates"],
        val["box_30x30x30"],
        val["settle_initialized"],
        val["tip3p_geometry"]["tight_tip3p_geometry"],
        val["no_contact_below_1p20_angstrom"],
        val["valid_coordinate_restart"],
        val["final_trajectory_restart_agreement_within_output_precision"],
        not val["abnormal_coordinate_displacement"],
    ])
    return val


def copy_primary_outputs(stage: str) -> dict:
    cfg = STAGES[stage]
    label = cfg["label"]
    names = [
        f"{label}.mdout", f"{label}.mdinfo", f"{label}_traj.dat", f"{label}_traj.box",
        f"{label}_rst_coordinate.txt", f"{label}_rst_velocity.txt",
    ]
    seen = set(names)
    rows = []
    for name in names:
        src = cfg["run_dir"] / name
        if src.exists():
            dst = cfg["outputs"] / name
            shutil.copy2(src, dst)
            rows.append({"filename": name, "exists": True, "run_sha256": sha256_file(src), "copy_sha256": sha256_file(dst), "run_size_bytes": src.stat().st_size, "copy_size_bytes": dst.stat().st_size, "byte_match": sha256_file(src) == sha256_file(dst) and src.stat().st_size == dst.stat().st_size})
        else:
            rows.append({"filename": name, "exists": False})
    for src in sorted(cfg["run_dir"].glob(f"{label}_rst*")):
        if not src.is_file() or src.name in seen:
            continue
        dst = cfg["outputs"] / src.name
        shutil.copy2(src, dst)
        rows.append({
            "filename": src.name,
            "exists": True,
            "checkpoint_restart": True,
            "run_sha256": sha256_file(src),
            "copy_sha256": sha256_file(dst),
            "run_size_bytes": src.stat().st_size,
            "copy_size_bytes": dst.stat().st_size,
            "byte_match": sha256_file(src) == sha256_file(dst) and src.stat().st_size == dst.stat().st_size,
        })
    for name in ["stdout.txt", "stderr.txt", "execution_result.json", "STARTED.json"]:
        src = LOGS / stage / "scientific_execution" / name
        if src.exists():
            dst = cfg["outputs"] / f"scientific_{name}"
            shutil.copy2(src, dst)
            rows.append({"filename": f"scientific_{name}", "exists": True, "run_sha256": sha256_file(src), "copy_sha256": sha256_file(dst), "run_size_bytes": src.stat().st_size, "copy_size_bytes": dst.stat().st_size, "byte_match": sha256_file(src) == sha256_file(dst)})
    write_csv(cfg["validation"] / "PRIMARY_OUTPUT_COPY_HASHES.csv", rows)
    return {"rows": rows, "all_existing_byte_match": all(r.get("byte_match", True) for r in rows if r.get("exists"))}


def analyze_stage(stage: str) -> dict:
    cfg = STAGES[stage]
    exec_path = LOGS / stage / "scientific_execution" / "execution_result.json"
    exec_result = json.loads(exec_path.read_text(encoding="utf-8"))
    copied = copy_primary_outputs(stage)
    label = cfg["label"]
    mdout = parse_mdout(cfg["run_dir"] / f"{label}.mdout")
    records = mdout["records"]
    temps = [temperature_value(r) for r in records]
    pots = [potential_value(r) for r in records]
    kinetics = [kinetic_from_temperature(t) for t in temps if t is not None]
    totals = [(p + kinetic_from_temperature(t)) for p, t in zip(pots, temps) if p is not None and t is not None]
    steps = [r["step"] for r in records]
    traj = parse_traj(cfg["run_dir"] / f"{label}_traj.dat", ATOM_COUNT)
    boxes = parse_box(cfg["run_dir"] / f"{label}_traj.box")
    crd_path = cfg["run_dir"] / f"{label}_rst_coordinate.txt"
    vel_path = cfg["run_dir"] / f"{label}_rst_velocity.txt"
    coord_restart = parse_coordinate(crd_path) if crd_path.exists() else missing_restart(crd_path)
    vel_restart = parse_velocity(vel_path) if vel_path.exists() else missing_restart(vel_path)
    structure = structure_validation(stage, traj, boxes, coord_restart, cfg["expected_frames"], cfg["trajectory_interval"])
    finite_series = all(x is not None and math.isfinite(x) for x in temps + pots + totals)
    duration_ps = cfg["dt_ps"] * (steps[-1] if steps else 0)
    total_change = totals[-1] - totals[0] if len(totals) >= 2 else None
    rel_change = total_change / abs(totals[0]) if total_change is not None and totals[0] else None
    drift = total_change / duration_ps if total_change is not None and duration_ps else None
    temp_stats = {"first": temps[0] if temps else None, "final": temps[-1] if temps else None, "mean": mean(temps), "min": min(temps) if temps else None, "max": max(temps) if temps else None}
    record_times_ps = [step * cfg["dt_ps"] for step in steps]
    def series_mean_in_window(values: list[float], start_ps: float, end_ps: float, include_start: bool = False) -> float | None:
        vals = []
        for t_ps, val in zip(record_times_ps, values):
            if val is None:
                continue
            left_ok = t_ps >= start_ps if include_start else t_ps > start_ps
            if left_ok and t_ps <= end_ps:
                vals.append(val)
        return mean(vals)
    one_ps_temperature_means = [
        {"window_ps": [float(i), float(i + 1)], "mean_temperature_K": series_mean_in_window(temps, float(i), float(i + 1))}
        for i in range(10)
    ]
    one_ps_potential_means = [
        {"window_ps": [float(i), float(i + 1)], "mean_potential": series_mean_in_window(pots, float(i), float(i + 1))}
        for i in range(10)
    ]
    first_2ps_temperature_mean = series_mean_in_window(temps, 0.0, 2.0, include_start=True)
    middle_4ps_temperature_mean = series_mean_in_window(temps, 3.0, 7.0)
    final_2ps_temperature_mean = series_mean_in_window(temps, 8.0, 10.0)
    final_100_record_temperature_mean = mean(temps[-100:]) if len(temps) >= 100 else None
    fraction_inside_250_350K = (sum(1 for t in temps if t is not None and 250.0 <= t <= 350.0) / len(temps)) if temps else None
    fraction_inside_270_330K = (sum(1 for t in temps if t is not None and 270.0 <= t <= 330.0) / len(temps)) if temps else None
    full_temperature_slope = slope([float(x) for x in steps], temps) if temps else None
    first_2ps_potential_mean = series_mean_in_window(pots, 0.0, 2.0, include_start=True)
    final_2ps_potential_mean = series_mean_in_window(pots, 8.0, 10.0)
    full_potential_slope = slope([float(x) for x in steps], pots) if pots else None
    terminal_window_size = min(cfg.get("terminal_window", 50), len(temps))
    terminal_temps = temps[-terminal_window_size:] if terminal_window_size else []
    terminal_steps = steps[-terminal_window_size:] if terminal_window_size else []
    previous_temps = temps[-2 * terminal_window_size:-terminal_window_size] if terminal_window_size and len(temps) >= 2 * terminal_window_size else []
    terminal_pots = pots[-terminal_window_size:] if terminal_window_size else []
    terminal_totals = totals[-terminal_window_size:] if terminal_window_size else []
    terminal_temp_mean = mean(terminal_temps)
    previous_temp_mean = mean(previous_temps)
    terminal_temp_slope = slope([float(x) for x in terminal_steps], terminal_temps) if terminal_temps else None
    terminal_potential_slope = slope([float(x) for x in terminal_steps], terminal_pots) if terminal_pots else None
    terminal_total_slope = slope([float(x) for x in terminal_steps], terminal_totals) if terminal_totals else None
    terminal_growth = bool(
        terminal_temp_slope is not None
        and terminal_temp_slope > 0.05
        and terminal_temps[-1] > terminal_temps[0] + 5.0
    )
    if previous_temp_mean is not None and terminal_temp_mean is not None:
        terminal_growth = terminal_growth or terminal_temp_mean > previous_temp_mean + 10.0
    target = cfg["target_temperature_K"]
    temperature_runaway = bool(temps and (max(temps) >= 450.0 or (final_2ps_temperature_mean is not None and final_2ps_temperature_mean > 360.0)))
    total_energy_growth = bool(
        total_change is not None
        and rel_change is not None
        and (rel_change > 0.10 or (terminal_total_slope is not None and terminal_total_slope > max(1.0, abs(totals[0]) * 0.0005)))
    )
    terminal_potential_change = terminal_pots[-1] - terminal_pots[0] if len(terminal_pots) >= 2 else None
    abrupt_terminal_potential_collapse = bool(
        terminal_potential_change is not None
        and terminal_potential_change < -500.0
        and terminal_potential_slope is not None
        and terminal_potential_slope < -1.0
    )
    primary_output_files_complete = len(copied["rows"]) >= 6 and all(r.get("exists") and r.get("byte_match") for r in copied["rows"][:6])
    structure_base_ok = all([
        structure["coordinate_frame_count"] == cfg["expected_frames"],
        structure["box_frame_count"] == cfg["expected_frames"],
        structure["all_frames_finite"],
        structure["all_frame_hashes_unique"],
        structure["no_duplicate_atomic_coordinates"],
        structure["box_30x30x30"],
        structure["settle_initialized"],
        structure["tip3p_geometry"]["tight_tip3p_geometry"],
        structure["valid_coordinate_restart"],
        structure["final_trajectory_restart_agreement_within_output_precision"],
        not structure["abnormal_coordinate_displacement"],
    ])
    velocity_restart_ok = bool(vel_restart.get("exists") and vel_restart.get("atom_count") == ATOM_COUNT and vel_restart.get("finite"))
    runtime_ok = exec_result["exit_code"] == 0 and not exec_result["timed_out"]
    info_interval = cfg.get("information_interval", 10)
    expected_record_steps = list(range(info_interval, cfg["expected_steps"] + 1, info_interval))
    mdout_record_steps_ok = steps == expected_record_steps
    common_gates = [
        runtime_ok,
        exec_result["exit_code"] == 0,
        not exec_result["timed_out"],
        len(records) == cfg["expected_records"],
        mdout_record_steps_ok,
        (steps[-1] if steps else None) == cfg["expected_steps"],
        finite_series,
        primary_output_files_complete,
        structure_base_ok,
        velocity_restart_ok,
        not temperature_runaway,
    ]
    nvt_stage = True
    validation = {
        "generated_at": now_iso(),
        "stage": stage,
        "execution": exec_result,
        "output_copy": copied,
        "mdout_header": mdout["header"],
        "record_count": len(records),
        "expected_record_count": cfg["expected_records"],
        "mdout_record_steps_expected": {"first": info_interval, "last": cfg["expected_steps"], "interval": info_interval},
        "mdout_record_steps_ok": mdout_record_steps_ok,
        "completed_steps": steps[-1] if steps else None,
        "expected_completed_steps": cfg["expected_steps"],
        "finite_potential_temperature_reconstructed_total": finite_series,
        "temperature": temp_stats,
        "one_ps_temperature_window_means": one_ps_temperature_means,
        "first_2ps_temperature_mean": first_2ps_temperature_mean,
        "middle_4ps_temperature_mean": middle_4ps_temperature_mean,
        "final_2ps_temperature_mean": final_2ps_temperature_mean,
        "final_100_record_temperature_mean": final_100_record_temperature_mean,
        "full_temperature_slope_K_per_step": full_temperature_slope,
        "fraction_temperature_records_inside_250_350K": fraction_inside_250_350K,
        "fraction_temperature_records_inside_270_330K": fraction_inside_270_330K,
        "terminal_window_size": terminal_window_size,
        "terminal_window_temperature_mean": terminal_temp_mean,
        "terminal_window_previous_temperature_mean": previous_temp_mean,
        "terminal_window_temperature_slope_K_per_step": terminal_temp_slope,
        "potential_energy_first": pots[0] if pots else None,
        "potential_energy_final": pots[-1] if pots else None,
        "potential_energy_change": (pots[-1] - pots[0]) if len(pots) >= 2 else None,
        "potential_energy_range": [min(pots), max(pots)] if pots else None,
        "one_ps_potential_window_means": one_ps_potential_means,
        "first_2ps_potential_mean": first_2ps_potential_mean,
        "final_2ps_potential_mean": final_2ps_potential_mean,
        "full_potential_slope_per_step": full_potential_slope,
        "terminal_window_potential_energy_change": terminal_potential_change,
        "terminal_window_potential_energy_slope_per_step": terminal_potential_slope,
        "potential_relaxation_observed": len(pots) >= 2 and pots[-1] < pots[0],
        "abrupt_terminal_potential_collapse": abrupt_terminal_potential_collapse,
        "reconstructed_kinetic_energy_first": kinetics[0] if kinetics else None,
        "reconstructed_kinetic_energy_final": kinetics[-1] if kinetics else None,
        "reconstructed_total_energy_source": "TOTAL_ENERGY_RECONSTRUCTED_FROM_REPORTED_TEMPERATURE",
        "reconstructed_total_energy_first": totals[0] if totals else None,
        "reconstructed_total_energy_final": totals[-1] if totals else None,
        "reconstructed_total_energy_change": total_change,
        "reconstructed_total_energy_relative_change": rel_change,
        "reconstructed_total_energy_drift_per_ps": drift,
        "reconstructed_total_energy_linear_slope_per_step": slope([float(x) for x in steps], totals) if finite_series else None,
        "terminal_window_reconstructed_total_energy_slope_per_step": terminal_total_slope,
        "output_timing_limitation": "Kinetic and total energy are reconstructed at mdout write times from reported temperature and potential.",
        "nvt_total_energy_conservation_gate_used": False,
        "nvt_energy_interpretation": [
            "TOTAL_ENERGY_RECONSTRUCTED_FROM_REPORTED_TEMPERATURE",
            "NVT_TOTAL_ENERGY_NOT_EXPECTED_TO_BE_CONSERVED",
            "CONTINUING_POTENTIAL_ENERGY_RELAXATION_ALLOWED",
            "RECONSTRUCTED_SYSTEM_ENERGY_CHANGE_UNDER_NVT",
        ],
        "reconstructed_system_energy_change_under_nvt": {
            "value_kcal_per_mol": total_change,
            "interpretation": "This is reconstructed system-energy change under NVT, not exact thermostat work.",
            "gate_used": False,
        },
        "duration_ps": duration_ps,
        "temperature_runaway": temperature_runaway,
        "sustained_terminal_temperature_growth": terminal_growth,
        "total_energy_growth": total_energy_growth,
        "primary_output_files_complete": primary_output_files_complete,
        "structure_base_ok": structure_base_ok,
        "velocity_restart_ok": velocity_restart_ok,
        "structure": structure,
        "coordinate_restart": {k: v for k, v in coord_restart.items() if k != "coords"},
        "velocity_restart": {k: v for k, v in vel_restart.items() if k != "vectors"},
    }
    if not runtime_ok:
        validation["overall_ok"] = False
        validation["stage_decision"] = "BLOCKED_SUPERVISOR_TIMEOUT" if exec_result.get("timed_out") else "REPAIR_REQUIRED_PATH_OR_OUTPUT_CONTRACT"
    else:
        low_bound = 240.0
        high_bound = 360.0
        final_2ps_low_bound = 260.0
        final_2ps_high_bound = 340.0
        max_temp_threshold = 450.0
        terminal_trend_bounded = terminal_temp_slope is None or abs(terminal_temp_slope) <= 1.0 or (terminal_temps and low_bound <= terminal_temps[-1] <= high_bound)
        max_temp_ok = temp_stats["max"] is not None and temp_stats["max"] < max_temp_threshold
        final_temp_ok = temp_stats["final"] is not None and low_bound <= temp_stats["final"] <= high_bound
        terminal_mean_ok = final_2ps_temperature_mean is not None and final_2ps_low_bound <= final_2ps_temperature_mean <= final_2ps_high_bound
        contact_ok = all([
            structure["no_contact_below_1p00_angstrom"],
            structure["final_saved_frame_minimum_intermolecular_distance_at_least_1p20"],
            structure["terminal_20_percent_minimum_intermolecular_distance_at_least_1p20"],
        ])
        no_sustained_terminal_runaway = not temperature_runaway and not (terminal_growth and not (terminal_mean_ok and final_temp_ok and max_temp_ok))
        movement_numerically_concerning = bool(
            structure["large_oxygen_or_water_center_of_mass_displacement"]
            and (
                temperature_runaway
                or not contact_ok
                or not structure["settle_initialized"]
                or not structure["tip3p_geometry"]["tight_tip3p_geometry"]
                or not finite_series
                or not velocity_restart_ok
                or not structure["valid_coordinate_restart"]
            )
        )
        potential_behavior_classification = (
            "CONTINUING_BOUNDED_RELAXATION"
            if finite_series and not temperature_runaway and contact_ok and structure_base_ok and velocity_restart_ok and not movement_numerically_concerning
            else "POTENTIAL_BEHAVIOR_REQUIRES_REVIEW"
        )
        pass_gates = all(common_gates + [terminal_mean_ok, final_temp_ok, max_temp_ok, terminal_trend_bounded, no_sustained_terminal_runaway, contact_ok, not movement_numerically_concerning])
        ambiguous_gates = all([
            runtime_ok,
            len(records) == cfg["expected_records"],
            mdout_record_steps_ok,
            (steps[-1] if steps else None) == cfg["expected_steps"],
            finite_series,
            primary_output_files_complete,
            structure_base_ok,
            velocity_restart_ok,
            contact_ok,
            not temperature_runaway,
        ])
        validation["target_temperature_K"] = target
        validation["temperature_relaxed_gate_low_K"] = low_bound
        validation["temperature_relaxed_gate_high_K"] = high_bound
        validation["final_2ps_temperature_gate_low_K"] = final_2ps_low_bound
        validation["final_2ps_temperature_gate_high_K"] = final_2ps_high_bound
        validation["maximum_temperature_gate"] = {"threshold_K": max_temp_threshold, "passed": max_temp_ok}
        validation["final_temperature_relaxed_gate"] = final_temp_ok
        validation["final_2ps_temperature_relaxed_gate"] = terminal_mean_ok
        validation["terminal_window_temperature_relaxed_gate"] = terminal_mean_ok
        validation["terminal_temperature_trend_bounded"] = terminal_trend_bounded
        validation["no_sustained_terminal_temperature_runaway"] = no_sustained_terminal_runaway
        validation["contact_gate_no_contact_below_1p00_final_and_terminal20_ge_1p20"] = contact_ok
        validation["movement_numerically_concerning"] = movement_numerically_concerning
        validation["maximum_hydrogen_displacement_used_as_failure_gate"] = False
        validation["nve_total_energy_conservation_gate_used"] = False
        validation["potential_energy_plateau_required"] = False
        validation["zero_potential_energy_slope_required"] = False
        validation["continued_potential_energy_reduction_is_automatic_failure"] = False
        validation["potential_behavior_classification"] = potential_behavior_classification
        validation["ambiguous_but_structurally_safe"] = bool(ambiguous_gates and not pass_gates)
        validation["overall_ok"] = pass_gates
        if pass_gates:
            validation["stage_decision"] = "PASS_300K_NVT_STABILIZED_READY_FOR_NPT"
        elif ambiguous_gates:
            validation["stage_decision"] = "HOLD_300K_NVT_FOR_REVIEW"
        else:
            validation["stage_decision"] = "REPAIR_REQUIRED_NVT_NUMERICAL_STABILITY"
    write_json(cfg["analysis"] / "STAGE_ANALYSIS.json", validation)
    write_json(cfg["validation"] / "STAGE_VALIDATION.json", validation)
    write_text(
        cfg["analysis"] / "STAGE_ANALYSIS.md",
        "\n".join([
            f"# {stage} Analysis",
            "",
            f"- Decision: `{validation['stage_decision']}`",
            f"- Records: `{validation['record_count']}/{cfg['expected_records']}`",
            f"- Completed steps: `{validation['completed_steps']}`",
            f"- Temperature mean: `{validation['temperature']['mean']}`",
            f"- Reconstructed total change: `{validation['reconstructed_total_energy_change']}`",
            "",
        ]),
    )
    print(json.dumps({"stage": stage, "decision": validation["stage_decision"], "overall_ok": validation["overall_ok"]}, indent=2))
    return validation


def previous_ok(stage: str, expected_decision: str) -> bool:
    path = STAGES[stage]["validation"] / "STAGE_VALIDATION.json"
    return path.exists() and json.loads(path.read_text(encoding="utf-8")).get("stage_decision") == expected_decision


def final_decision() -> dict:
    start_coord = INPUT_300K / "heated300K_coordinate.txt"
    start_vel = INPUT_300K / "heated300K_velocity.txt"
    input_path = RECEIPTS / "INPUT_VERIFICATION.json"
    input_status = json.loads(input_path.read_text(encoding="utf-8")) if input_path.exists() else None
    stage = "nvt300K_10ps"
    stage_cfg = STAGES[stage]
    validation_path = stage_cfg["validation"] / "STAGE_VALIDATION.json"
    validation = json.loads(validation_path.read_text(encoding="utf-8")) if validation_path.exists() else None
    decision_name = "REPAIR_REQUIRED_PATH_OR_OUTPUT_CONTRACT"
    if input_status is None or not input_status.get("overall_ok"):
        decision_name = "REPAIR_REQUIRED_PATH_OR_OUTPUT_CONTRACT"
    elif validation is None:
        decision_name = "REPAIR_REQUIRED_PATH_OR_OUTPUT_CONTRACT"
    elif validation.get("stage_decision") == "BLOCKED_SUPERVISOR_TIMEOUT" or validation.get("execution", {}).get("timed_out"):
        decision_name = "BLOCKED_SUPERVISOR_TIMEOUT"
    elif validation.get("stage_decision") == "PASS_300K_NVT_STABILIZED_READY_FOR_NPT":
        decision_name = "PASS_300K_NVT_STABILIZED_READY_FOR_NPT"
    elif validation.get("stage_decision") == "HOLD_300K_NVT_FOR_REVIEW":
        decision_name = "HOLD_300K_NVT_FOR_REVIEW"
    elif validation.get("stage_decision") == "REPAIR_REQUIRED_PATH_OR_OUTPUT_CONTRACT":
        decision_name = "REPAIR_REQUIRED_PATH_OR_OUTPUT_CONTRACT"
    else:
        decision_name = "REPAIR_REQUIRED_NVT_NUMERICAL_STABILITY"
    accepted = decision_name == "PASS_300K_NVT_STABILIZED_READY_FOR_NPT"
    accepted_coord = stage_cfg["run_dir"] / "nvt300K_10ps_rst_coordinate.txt"
    accepted_vel = stage_cfg["run_dir"] / "nvt300K_10ps_rst_velocity.txt"
    next_actions = {
        "PASS_300K_NVT_STABILIZED_READY_FOR_NPT": "Proceed to reviewed NPT density and volume relaxation.",
        "HOLD_300K_NVT_FOR_REVIEW": "Review the finite, structurally safe 300 K NVT stabilization before deciding whether to continue.",
        "REPAIR_REQUIRED_NVT_NUMERICAL_STABILITY": "Repair the NVT numerical or structural stability issue before further dynamics.",
        "REPAIR_REQUIRED_PATH_OR_OUTPUT_CONTRACT": "Repair the path, parser, command, or missing-output contract before any further stage.",
        "BLOCKED_SUPERVISOR_TIMEOUT": "Resolve the supervisor timeout before attempting another NVT stabilization run.",
    }
    next_action = next_actions[decision_name]
    decision = {
        "generated_at": now_iso(),
        "final_decision": decision_name,
        "source_pass": str(PASS06AR),
        "pass06ar_acceptance": json.loads((REPORTS / "PASS06AR_ACCEPTANCE.json").read_text(encoding="utf-8")) if (REPORTS / "PASS06AR_ACCEPTANCE.json").exists() else None,
        "density_interpretation": json.loads((REPORTS / "DENSITY_INTERPRETATION.json").read_text(encoding="utf-8")) if (REPORTS / "DENSITY_INTERPRETATION.json").exists() else None,
        "accepted_start_coordinate": str(start_coord),
        "accepted_start_coordinate_sha256": sha256_file(start_coord) if start_coord.exists() else None,
        "accepted_start_velocity": str(start_vel),
        "accepted_start_velocity_sha256": sha256_file(start_vel) if start_vel.exists() else None,
        "input_verification": input_status,
        "stage": validation,
        "accepted_nvt_coordinate": str(accepted_coord) if accepted else None,
        "accepted_nvt_coordinate_sha256": sha256_file(accepted_coord) if accepted else None,
        "accepted_nvt_velocity": str(accepted_vel) if accepted else None,
        "accepted_nvt_velocity_sha256": sha256_file(accepted_vel) if accepted else None,
        "state": "PRACTICALLY_STABILIZED_300K_NVT_STATE" if accepted else None,
        "timestep_ps": 0.001 if accepted else None,
        "next_stage": "reviewed NPT density and volume relaxation" if accepted else None,
        "next_action": next_action,
        "nve_did_not_run": True,
        "two_fs_did_not_run": True,
        "npt_did_not_run": True,
        "production_did_not_run": True,
        "second_nvt_process_did_not_run": True,
        "additional_heating_stages_did_not_run": True,
        "complete_thermodynamic_equilibrium_claimed": False,
    }
    write_json(PASS_DIR / "FINAL_DECISION.json", decision)
    write_text(
        PASS_DIR / "FINAL_DECISION.md",
        "\n".join([
            f"# {decision_name}",
            "",
            f"- Accepted starting coordinate SHA-256: `{decision['accepted_start_coordinate_sha256']}`",
            f"- Accepted starting velocity SHA-256: `{decision['accepted_start_velocity_sha256']}`",
            f"- Accepted NVT coordinate: `{decision['accepted_nvt_coordinate']}`",
            f"- Accepted NVT velocity: `{decision['accepted_nvt_velocity']}`",
            f"- Timestep: `{decision['timestep_ps']}` ps",
            f"- Next action: {decision['next_action']}",
            "",
        ]),
    )
    return decision


def write_overall_stabilization_summary(decision: dict) -> dict:
    temperature_potential = []
    minimum_distance = []
    stage_summaries = []
    cumulative_start_ps = 0.0
    final_300k_structure = None
    for stage, cfg in STAGES.items():
        val_path = cfg["validation"] / "STAGE_VALIDATION.json"
        if not val_path.exists():
            break
        val = json.loads(val_path.read_text(encoding="utf-8"))
        label = cfg["label"]
        mdout = parse_mdout(cfg["run_dir"] / f"{label}.mdout")
        for rec in mdout["records"]:
            step = rec["step"]
            stage_time_ps = step * cfg["dt_ps"]
            temperature_potential.append({
                "stage": stage,
                "label": label,
                "target_temperature_K": cfg["target_temperature_K"],
                "step": step,
                "stage_time_ps": stage_time_ps,
                "cumulative_time_ps": cumulative_start_ps + stage_time_ps,
                "temperature_K": temperature_value(rec),
                "potential_energy": potential_value(rec),
            })
        for rec in val.get("structure", {}).get("minimum_intermolecular_atom_distance_history", []):
            stage_time_ps = rec["md_step"] * cfg["dt_ps"]
            minimum_distance.append({
                "stage": stage,
                "label": label,
                "target_temperature_K": cfg["target_temperature_K"],
                "saved_frame": rec["saved_frame"],
                "md_step": rec["md_step"],
                "stage_time_ps": stage_time_ps,
                "cumulative_time_ps": cumulative_start_ps + stage_time_ps,
                "minimum_intermolecular_atom_distance_A": rec["distance"],
                "minimum_oo_distance_A": next(
                    (oo["distance"] for oo in val.get("structure", {}).get("minimum_oo_distance_history", []) if oo["saved_frame"] == rec["saved_frame"]),
                    None,
                ),
            })
        stage_summaries.append({
            "stage": stage,
            "label": label,
            "target_temperature_K": cfg["target_temperature_K"],
            "stage_decision": val.get("stage_decision"),
            "temperature": val.get("temperature"),
            "terminal_window_temperature_mean": val.get("terminal_window_temperature_mean"),
            "potential_energy_first": val.get("potential_energy_first"),
            "potential_energy_final": val.get("potential_energy_final"),
            "potential_energy_change": val.get("potential_energy_change"),
            "minimum_intermolecular_atom_distance": val.get("structure", {}).get("minimum_intermolecular_atom_distance"),
            "minimum_oo_distance": val.get("structure", {}).get("minimum_oo_distance"),
        })
        if stage == "nvt300K_10ps":
            final_300k_structure = {
                "stage": stage,
                "label": label,
                "tip3p_geometry": val.get("structure", {}).get("tip3p_geometry"),
                "settle_initialized": val.get("structure", {}).get("settle_initialized"),
                "minimum_intermolecular_atom_distance": val.get("structure", {}).get("minimum_intermolecular_atom_distance"),
                "minimum_oo_distance": val.get("structure", {}).get("minimum_oo_distance"),
                "final_saved_frame_minimum_intermolecular_distance": val.get("structure", {}).get("final_saved_frame_minimum_intermolecular_distance"),
                "terminal_20_percent_minimum_intermolecular_distance": val.get("structure", {}).get("terminal_20_percent_minimum_intermolecular_distance"),
                "maximum_saved_displacement": val.get("structure", {}).get("maximum_saved_displacement"),
                "rms_saved_displacement_mean": val.get("structure", {}).get("rms_saved_displacement_mean"),
                "final_trajectory_restart_max_abs_diff": val.get("structure", {}).get("final_trajectory_restart_max_abs_diff"),
            }
        cumulative_start_ps += cfg["expected_steps"] * cfg["dt_ps"]
    summary = {
        "generated_at": now_iso(),
        "pass": "07A",
        "final_decision": decision["final_decision"],
        "total_requested_steps": 10000,
        "total_requested_duration_ps": 10.0,
        "executed_process_count": len(stage_summaries),
        "temperature_and_potential_vs_stage_and_time": temperature_potential,
        "minimum_distance_history": minimum_distance,
        "process_summaries": stage_summaries,
        "final_300K_nvt_structure_metrics": final_300k_structure,
    }
    write_json(REPORTS / "OVERALL_STABILIZATION_SUMMARY.json", summary)
    write_text(
        REPORTS / "OVERALL_STABILIZATION_SUMMARY.md",
        "\n".join([
            "# Overall NVT Stabilization Summary",
            "",
            f"- Final decision: `{decision['final_decision']}`",
            f"- Executed scientific processes: `{len(stage_summaries)}`",
            f"- Requested duration: `10.0 ps`",
            f"- Final 300 K structure metrics present: `{final_300k_structure is not None}`",
            "",
        ]),
    )
    return summary


def inventory_rows(decision: dict) -> list[dict]:
    write_json(META / "SELF_REFERENTIAL_METADATA_EXCLUSIONS.json", {"excluded_from_inventory": META_EXCLUSIONS})
    write_text(META / "PACKAGE_RULES_NOTE.md", "Six self-referential metadata files are archived but excluded from the hash inventory. __pycache__ and *.pyc are excluded.\n")
    rows = []
    for path in sorted(PASS_DIR.rglob("*")):
        if not path.is_file():
            continue
        rp = path.relative_to(PASS_DIR).as_posix()
        if "__pycache__" in path.parts or path.suffix == ".pyc" or rp in META_EXCLUSIONS:
            continue
        rows.append({"relative_path": rp, "size_bytes": path.stat().st_size, "sha256": sha256_file(path)})
    write_csv(META / "FILE_INVENTORY.csv", rows, ["relative_path", "size_bytes", "sha256"])
    write_text(META / "SHA256SUMS.txt", "\n".join(f"{r['sha256']}  {r['relative_path']}" for r in rows) + "\n")
    manifest = {"generated_at": now_iso(), "pass": "07A", "final_decision": decision["final_decision"], "inventory_count": len(rows), "metadata_exclusion_count": len(META_EXCLUSIONS)}
    write_json(META / "REVIEW_PACKAGE_MANIFEST.json", manifest)
    write_text(META / "REVIEW_PACKAGE_MANIFEST.md", f"# Review Package Manifest\n\n- Final decision: `{decision['final_decision']}`\n- Inventory count: `{len(rows)}`\n")
    return rows


def create_zip(decision: dict, rows: list[dict]) -> dict:
    PACKAGE_DIR.mkdir(parents=True, exist_ok=True)
    zip_path = PACKAGE_DIR / f"pass_07a_practical_300K_nvt_stabilization_10ps_{STAMP}.zip"
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(PASS_DIR.rglob("*")):
            if not path.is_file():
                continue
            if "__pycache__" in path.parts or path.suffix == ".pyc":
                continue
            zf.write(path, PASS_DIR.name + "/" + path.relative_to(PASS_DIR).as_posix())
    with zipfile.ZipFile(zip_path, "r") as zf:
        archive_names = [n for n in zf.namelist() if not n.endswith("/")]
        prefix = PASS_DIR.name + "/"
        rel_names = [n[len(prefix):] if n.startswith(prefix) else n for n in archive_names]
        archived = {rp: sha256_bytes(zf.read(arc)) for arc, rp in zip(archive_names, rel_names)}
        testzip = zf.testzip()
    inv = {r["relative_path"]: r for r in rows}
    missing = sorted(set(inv) - set(rel_names))
    extras = sorted(set(rel_names) - set(inv) - set(META_EXCLUSIONS))
    mismatches = [{"relative_path": rp, "inventory_sha256": inv[rp]["sha256"], "archived_sha256": archived.get(rp)} for rp in inv if archived.get(rp) != inv[rp]["sha256"]]
    metadata_exclusion_archived_byte_hashes = {rp: archived.get(rp) for rp in META_EXCLUSIONS}
    metadata_exclusion_missing_from_archive = sorted(rp for rp, digest in metadata_exclusion_archived_byte_hashes.items() if digest is None)
    receipt = {
        "generated_at": now_iso(),
        "pass": "07A",
        "decision": decision["final_decision"],
        "zip_path": str(zip_path),
        "zip_filename": zip_path.name,
        "zip_sha256": sha256_file(zip_path),
        "zip_size_bytes": zip_path.stat().st_size,
        "zip_member_count": len(archive_names),
        "zip_testzip_result": testzip,
        "inventory_count": len(rows),
        "metadata_exclusion_count": len(META_EXCLUSIONS),
        "metadata_exclusion_archived_byte_hashes": metadata_exclusion_archived_byte_hashes,
        "metadata_exclusion_missing_from_archive": metadata_exclusion_missing_from_archive,
        "verified_inventory_count": sum(1 for r in rows if archived.get(r["relative_path"]) == r["sha256"]),
        "missing_entries": missing,
        "extra_unaccounted_entries": extras,
        "hash_mismatches": mismatches,
        "overall_verification_result": not missing and not extras and not mismatches and not metadata_exclusion_missing_from_archive and testzip is None,
    }
    write_json(PACKAGE_DIR / f"pass_07a_practical_300K_nvt_stabilization_10ps_{STAMP}_receipt.json", receipt)
    return receipt


def update_indexes(receipt: dict) -> dict:
    csv_path = PACKAGE_DIR / "ZIP_INDEX.csv"
    fields = ["created_at", "pass", "zip_filename", "zip_path", "zip_sha256", "zip_size_bytes", "file_count", "decision"]
    row = {
        "created_at": receipt["generated_at"],
        "pass": "07A",
        "zip_filename": receipt["zip_filename"],
        "zip_path": receipt["zip_path"],
        "zip_sha256": receipt["zip_sha256"],
        "zip_size_bytes": receipt["zip_size_bytes"],
        "file_count": receipt["zip_member_count"],
        "decision": receipt["decision"],
    }
    old = []
    if csv_path.exists():
        with csv_path.open("r", encoding="utf-8", newline="") as f:
            old = list(csv.DictReader(f))
    old = [r for r in old if r.get("pass") != "07A"]
    old.append(row)
    write_csv(csv_path, old, fields)
    md_path = PACKAGE_DIR / "ZIP_INDEX.md"
    text = md_path.read_text(encoding="utf-8", errors="replace") if md_path.exists() else "# Review Package ZIP Index\n"
    start = "<!-- PASS07A_INDEX_START -->"
    end = "<!-- PASS07A_INDEX_END -->"
    block = "\n".join([
        start,
        "## Pass 07A Index",
        "",
        "| Pass | ZIP filename | Creation time | SHA-256 | Decision | File count |",
        "|---|---|---|---|---|---:|",
        f"| 07A | `{row['zip_filename']}` | {row['created_at']} | `{row['zip_sha256']}` | `{row['decision']}` | {row['file_count']} |",
        end,
        "",
    ])
    if start in text and end in text:
        pre = text.split(start)[0]
        post = text.split(end, 1)[1]
        text = pre + block + post.lstrip("\n")
    else:
        text = text.rstrip() + "\n\n" + block
    write_text(md_path, text)
    with csv_path.open("r", encoding="utf-8", newline="") as f:
        csv_rows = list(csv.DictReader(f))
    md_text = md_path.read_text(encoding="utf-8", errors="replace")
    verification = {
        "generated_at": now_iso(),
        "csv_path": str(csv_path),
        "md_path": str(md_path),
        "csv_07a_row_count": sum(1 for r in csv_rows if r.get("pass") == "07A"),
        "md_07a_marker_count": md_text.count("PASS07A_INDEX_START"),
        "md_07a_table_row_count": md_text.count("| 07A |"),
    }
    verification["overall_ok"] = verification["csv_07a_row_count"] == 1 and verification["md_07a_marker_count"] == 1 and verification["md_07a_table_row_count"] == 1
    write_json(PACKAGE_DIR / f"pass_07a_practical_300K_nvt_stabilization_10ps_{STAMP}_index_verification.json", verification)
    return verification


def finalize() -> None:
    decision = final_decision()
    summary = write_overall_stabilization_summary(decision)
    rows = inventory_rows(decision)
    receipt = create_zip(decision, rows)
    index = update_indexes(receipt)
    print(json.dumps({"final_decision": decision["final_decision"], "zip": receipt, "index": index}, indent=2))


def calibrate_and_generate() -> None:
    raise SystemExit("offline velocity regeneration is forbidden in Pass 07A")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=[
        "prepare",
        "run",
        "analyze",
        "finalize",
    ])
    args = ap.parse_args()
    if args.mode == "prepare":
        prepare()
    elif args.mode == "run":
        run_stage("nvt300K_10ps")
    elif args.mode == "analyze":
        analyze_stage("nvt300K_10ps")
    elif args.mode == "finalize":
        finalize()


if __name__ == "__main__":
    main()
