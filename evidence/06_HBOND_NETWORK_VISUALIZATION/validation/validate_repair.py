"""Validation for the 15R presentation repair.

Checks:
1. sha256 of all source files unchanged (vs carried-over selection_results.json).
2. Independent fresh-code-path recomputation of the whole-frame H-bond counts
   for the two selected frames equals the accepted values (1109 / 1196).
3. Each drawn dash pair (donor-H serial, acceptor-O serial from
   analysis/hbonds_<tag>_HtoO.txt) satisfies the criterion geometrically when
   recomputed from the cluster PDB coordinates with that specific H:
   O_D...O_A < 3.5 A AND angle O_D-H...O_A > 150 deg (vertex at H).
4. Dash counts equal the accepted intra-cluster counts (15 at 300 K, 14 at 273 K).
5. PNG outputs exist, valid PNG magic, PIL-openable, > 20 KB, correct dimensions.

Writes validation/VALIDATION.json.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent.parent
NATOM = 2586
FRAME_BYTES = NATOM * 3 * 4


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_frame(traj: Path, idx: int) -> np.ndarray:
    with traj.open("rb") as f:
        f.seek(idx * FRAME_BYTES)
        return np.frombuffer(f.read(FRAME_BYTES), dtype="<f4").astype(np.float64).reshape(NATOM, 3)


def load_box(box: Path, idx: int) -> np.ndarray:
    rows = [[float(x) for x in l.split()] for l in box.read_text().splitlines() if l.strip()]
    return np.array(rows[idx][:3])


def count_hbonds(pos: np.ndarray, box: np.ndarray) -> int:
    po = pos[::3]
    n = len(po)
    count = 0
    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            dv = po[i] - po[j]
            dv -= box * np.round(dv / box)
            if not (1e-12 < np.linalg.norm(dv) < 3.5):
                continue
            for hh in (1, 2):
                h = pos[3 * i + hh]
                v1 = po[i] - h
                v1 -= box * np.round(v1 / box)
                v2 = po[j] - h
                v2 -= box * np.round(v2 / box)
                c = np.dot(v1, v2) / np.linalg.norm(v1) / np.linalg.norm(v2)
                if math.degrees(math.acos(max(-1.0, min(1.0, c)))) > 150.0:
                    count += 1
    return count


def read_pdb_atoms(path: Path):
    atoms = {}
    for line in path.read_text().splitlines():
        if line.startswith(("HETATM", "ATOM")):
            serial = int(line[6:11])
            xyz = np.array([float(line[30:38]), float(line[38:46]), float(line[46:54])])
            atoms[serial] = (line[12:16].strip(), xyz)
    return atoms


def main() -> None:
    sel = json.loads((HERE / "analysis" / "selection_results.json").read_text())
    report = json.loads((HERE / "analysis" / "h2o_pairs_report.json").read_text())
    checks = {}

    # 1. source hashes
    bad = []
    for key, meta in sel["input_sha256"].items():
        actual = sha256(Path(meta["path"]))
        if actual != meta["sha256"]:
            bad.append(key)
    checks["source_sha256_unchanged"] = {"pass": not bad, "mismatches": bad}

    # 2. whole-frame recount
    rec = {}
    for tag in ("300K", "273K"):
        b = sel["branches"][tag]
        idx = b["frame_index"]
        if tag == "300K":
            traj, boxf, i2 = (Path(sel["input_sha256"]["traj_300K"]["path"]),
                              Path(sel["input_sha256"]["box_300K"]["path"]), idx)
        elif idx < 60:
            traj, boxf, i2 = (Path(sel["input_sha256"]["traj_273K_seg1"]["path"]),
                              Path(sel["input_sha256"]["box_273K_seg1"]["path"]), idx)
        else:
            traj, boxf, i2 = (Path(sel["input_sha256"]["traj_273K_seg2"]["path"]),
                              Path(sel["input_sha256"]["box_273K_seg2"]["path"]), idx - 60)
        n = count_hbonds(load_frame(traj, i2), load_box(boxf, i2))
        rec[tag] = {"recomputed": n, "expected": b["recomputed_hbond_count"], "match": n == b["recomputed_hbond_count"]}
    checks["whole_frame_hbond_recount"] = {"pass": all(v["match"] for v in rec.values()), "detail": rec}

    # 3+4. dash pair geometry with the specific H, and counts
    geom = {}
    expected_counts = {"300K": 15, "273K": 14}
    for tag in ("300K", "273K"):
        atoms = read_pdb_atoms(HERE / "analysis" / f"cluster_{tag}.pdb")
        pairs = []
        for line in (HERE / "analysis" / f"hbonds_{tag}_HtoO.txt").read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                pairs.append(tuple(int(x) for x in line.split()))
        ok_all, detail = True, []
        for hser, oser in pairs:
            hname, h = atoms[hser]
            oname, oa = atoms[oser]
            if not hname.startswith("H") or oname != "O":
                ok_all = False
                detail.append({"pair": [hser, oser], "error": f"wrong atom types {hname}/{oname}"})
                continue
            od = atoms[hser - ((hser - 1) % 3)][1] if False else None
            # donor O is the first atom of the donor water's residue (serial = 3*residx+1)
            residx = (hser - 1) // 3
            od = atoms[residx * 3 + 1][1]
            roo = float(np.linalg.norm(od - oa))
            v1, v2 = od - h, oa - h
            ang = math.degrees(math.acos(np.clip(np.dot(v1, v2) / np.linalg.norm(v1) / np.linalg.norm(v2), -1, 1)))
            ok = roo < 3.5 and ang > 150.0
            ok_all &= ok
            detail.append({"donor_H_serial": hser, "acceptor_O_serial": oser,
                           "r_OO_A": round(roo, 4), "angle_deg": round(ang, 3), "criterion_ok": ok})
        geom[tag] = {"n_pairs": len(pairs), "expected": expected_counts[tag],
                     "count_ok": len(pairs) == expected_counts[tag],
                     "report_count_match": len(pairs) == report["branches"][tag]["n_events_HtoO"],
                     "all_pairs_satisfy_criterion": ok_all, "pairs": detail}
    checks["dash_pairs_geometry_and_counts"] = {
        "pass": all(v["count_ok"] and v["all_pairs_satisfy_criterion"] and v["report_count_match"] for v in geom.values()),
        "detail": geom}

    # 5. PNGs
    from PIL import Image
    png_specs = {
        "hbond_network_300K.png": (2000, 1500), "hbond_network_273K.png": (2000, 1500),
        "hbond_network_300K_zoom.png": (2000, 1500), "hbond_network_273K_zoom.png": (2000, 1500),
        "hbond_network_300K_labeled.png": (2000, 1654), "hbond_network_273K_labeled.png": (2000, 1654),
        "hbond_network_comparison_sidebyside.png": (4008, 1654),
    }
    pngs = {}
    for name, (w, h) in png_specs.items():
        p = HERE / "renders" / name
        ok = p.exists() and p.stat().st_size > 20 * 1024 and p.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
        dims_ok, dims = False, None
        if ok:
            with Image.open(p) as im:
                im.verify()
            with Image.open(p) as im:
                dims = im.size
            dims_ok = dims == (w, h)
        pngs[name] = {"size_bytes": p.stat().st_size if p.exists() else 0, "dimensions": dims,
                      "pass": bool(ok and dims_ok)}
    checks["png_outputs"] = {"pass": all(v["pass"] for v in pngs.values()), "detail": pngs}

    overall = all(c["pass"] for c in checks.values())
    out = {"repair": "15R presentation repair: dashes donor-H...acceptor-O; captions/footer; tighter framing",
           "hbond_criterion": sel["hbond_criterion"], "checks": checks,
           "overall_verdict": "PASS" if overall else "FAIL"}
    (HERE / "validation" / "VALIDATION.json").write_text(json.dumps(out, indent=2) + "\n")
    print(json.dumps({"overall": out["overall_verdict"], "checks": {k: v["pass"] for k, v in checks.items()}}, indent=2))


if __name__ == "__main__":
    main()
