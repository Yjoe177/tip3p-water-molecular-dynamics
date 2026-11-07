"""Create the T5R1 read-only provenance receipt.

This script only reads the hash-pinned T1/T4 source files.  It never invokes
SPONGE and never writes outside this new T5R1 analysis directory.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent
ATOM_COUNT = 2586
FRAME_BYTES = ATOM_COUNT * 3 * 4

SOURCES = {
    "300K": {
        "trajectory_files": [PROJECT / "02_300K_reference/run/tempcomp_300K_reference/tempcomp_300K_reference_traj.dat"],
        "box_files": [PROJECT / "02_300K_reference/run/tempcomp_300K_reference/tempcomp_300K_reference_traj.box"],
        "mdout_files": [PROJECT / "02_300K_reference/run/tempcomp_300K_reference/tempcomp_300K_reference.mdout"],
        "start_time_ps": 112.62,
        "structural_times_ps": [112.67, 117.62],
        "thermo_records_expected": 100,
    },
    "273K": {
        "trajectory_files": [
            PROJECT / "07_273K_production_5ps/run/tempcomp_273K_production_5ps/tempcomp_273K_production_5ps_traj.dat",
            PROJECT / "07_273K_production_5ps/run/tempcomp_273K_production_5ps_resume/tempcomp_273K_production_5ps_resume_traj.dat",
        ],
        "box_files": [
            PROJECT / "07_273K_production_5ps/run/tempcomp_273K_production_5ps/tempcomp_273K_production_5ps_traj.box",
            PROJECT / "07_273K_production_5ps/run/tempcomp_273K_production_5ps_resume/tempcomp_273K_production_5ps_resume_traj.box",
        ],
        "mdout_files": [
            PROJECT / "07_273K_production_5ps/run/tempcomp_273K_production_5ps/tempcomp_273K_production_5ps.mdout",
            PROJECT / "07_273K_production_5ps/run/tempcomp_273K_production_5ps_resume/tempcomp_273K_production_5ps_resume.mdout",
        ],
        "start_time_ps": 124.62,
        "structural_times_ps": [124.67, 129.62],
        "thermo_records_expected": 99,
        "known_missing_thermo_record": "Step-3000 mdout record was buffered/lost at laptop restart; it is not fabricated.",
    },
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def nonblank_lines(path: Path) -> int:
    return sum(bool(line.strip()) for line in path.read_text().splitlines())


def mdout_records(path: Path) -> int:
    lines = path.read_text().splitlines()
    header = next(i for i, line in enumerate(lines)
                  if "temperature" in line.split() and "step" in line.split())
    width = len(lines[header].split())
    return sum(len(line.split()) >= width for line in lines[header + 1:])


def row(path: Path) -> dict:
    if not path.is_file():
        raise FileNotFoundError(path)
    return {"path": str(path.resolve()), "bytes": path.stat().st_size, "sha256": sha256(path)}


def main() -> None:
    datasets = {}
    for tag, spec in SOURCES.items():
        trajectory = [row(p) for p in spec["trajectory_files"]]
        boxes = [row(p) for p in spec["box_files"]]
        mdout = [row(p) for p in spec["mdout_files"]]
        frame_count = sum(Path(x["path"]).stat().st_size // FRAME_BYTES for x in trajectory)
        if any(Path(x["path"]).stat().st_size % FRAME_BYTES for x in trajectory):
            raise ValueError(f"Non-integral trajectory frame in {tag}")
        box_count = sum(nonblank_lines(Path(x["path"])) for x in boxes)
        thermo_count = sum(mdout_records(Path(x["path"])) for x in mdout)
        if frame_count != 100 or box_count != 100 or thermo_count != spec["thermo_records_expected"]:
            raise ValueError(f"Unexpected source counts for {tag}: {frame_count}, {box_count}, {thermo_count}")
        datasets[tag] = {
            "trajectory_files": trajectory,
            "box_files": boxes,
            "mdout_files": mdout,
            "structural_frame_count": frame_count,
            "box_record_count": box_count,
            "mdout_record_count": thermo_count,
            "start_time_ps": spec["start_time_ps"],
            "structural_times_ps": spec["structural_times_ps"],
            **({"known_missing_thermo_record": spec["known_missing_thermo_record"]}
               if "known_missing_thermo_record" in spec else {}),
        }
    receipt = {
        "pass": "T5R1_matched_deep_analysis_repair",
        "scope": "Analysis only; source MD files are read-only and SPONGE is never launched.",
        "source_policy": "Same seven hash-pinned T1/T4 files as T5; no trajectory is copied into this branch.",
        "datasets": datasets,
    }
    (HERE / "PROVENANCE_AUDIT_RECEIPT.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print("Wrote PROVENANCE_AUDIT_RECEIPT.json for 7 hash-pinned source files.")


if __name__ == "__main__":
    main()
