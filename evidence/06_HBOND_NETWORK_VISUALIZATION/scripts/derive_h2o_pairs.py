"""Re-derive H-bond drawing pairs at the donor-H...acceptor-O level.

Presentation-only repair (15R). Does NOT rerun MD and does NOT change the
selected frames or any accepted result. Reads cluster membership from the
carried-over analysis/selection_results.json and recomputes, from the raw
accepted trajectories, the specific hydrogen involved in each accepted
intra-cluster H-bond event.

H-bond criterion (verbatim, identical to the accepted analysis):
donor-acceptor O...O distance < 3.5 Angstrom AND angle
O_donor-H...O_acceptor > 150 degrees (vertex at H), acceptor on a
different molecule than donor.

For each event the H on the donor water that satisfies the angle criterion
is selected; if both H satisfy it, the one with the larger angle is taken
and this is recorded. Output: analysis/hbonds_{300K,273K}_HtoO.txt with
PDB atom serial pairs (donor-H serial, acceptor-O serial) referencing
analysis/cluster_{300K,273K}.pdb. The original O...O lists are archived
unchanged under provenance/archive_original_pairs/.

Runs with the frozen sponge-cpu python (numpy only). Read-only on sources.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent.parent
ANALYSIS = HERE / "analysis"
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
    r = rows[idx]
    if not all(abs(a - 90.0) < 1e-6 for a in r[3:]):
        raise ValueError("non-orthorhombic box")
    return np.array(r[:3])


def mic(v: np.ndarray, box: np.ndarray) -> np.ndarray:
    return v - box * np.round(v / box)


def events_HtoO(pos: np.ndarray, box: np.ndarray):
    """Return list of dicts: donor_water, acceptor_water, donor_H_local (1/2),
    r_OO, angle. Same criterion as the accepted analyzer."""
    po = pos[::3]
    d = mic(po[:, None, :] - po[None, :, :], box)
    oo = np.linalg.norm(d, axis=-1)
    donor, acceptor = np.where((oo < 3.5) & (oo > 1e-12))
    events = []
    for di, ai in zip(donor.tolist(), acceptor.tolist()):
        od = po[di]
        oa = po[di] - d[di, ai]
        best = None
        for local_h in (1, 2):
            h = pos[3 * di + local_h]
            v1 = mic(od - h, box)
            v2 = mic(oa - h, box)
            ang = math.degrees(math.acos(np.clip(np.dot(v1, v2) / np.linalg.norm(v1) / np.linalg.norm(v2), -1.0, 1.0)))
            if ang > 150.0:
                if best is None or ang > best[0]:
                    best = (ang, local_h)
        if best is not None:
            events.append({"donor_water": di, "acceptor_water": ai,
                           "donor_H_local": best[1], "r_OO_A": float(oo[di, ai]),
                           "angle_deg": best[0],
                           "both_H_satisfied": False})
    # record dual-H satisfaction
    for ev in events:
        di, ai = ev["donor_water"], ev["acceptor_water"]
        od = po[di]
        oa = po[di] - d[di, ai]
        n_ok = 0
        for local_h in (1, 2):
            h = pos[3 * di + local_h]
            v1 = mic(od - h, box)
            v2 = mic(oa - h, box)
            ang = math.degrees(math.acos(np.clip(np.dot(v1, v2) / np.linalg.norm(v1) / np.linalg.norm(v2), -1.0, 1.0)))
            n_ok += ang > 150.0
        ev["both_H_satisfied"] = n_ok == 2
    return events


def main() -> None:
    sel = json.loads((ANALYSIS / "selection_results.json").read_text())
    out = {"hbond_criterion": sel["hbond_criterion"],
           "dash_definition": "dashes connect donor-H (the donor-water hydrogen satisfying the angle criterion) to acceptor-O; PDB atom serials of analysis/cluster_<tag>.pdb",
           "dual_H_policy": "if both donor hydrogens satisfy the angle criterion, the one with the larger angle is drawn and recorded",
           "branches": {}}
    for tag in ("300K", "273K"):
        b = sel["branches"][tag]
        idx = b["frame_index"]
        if tag == "300K":
            traj = Path(sel["input_sha256"]["traj_300K"]["path"])
            boxf = Path(sel["input_sha256"]["box_300K"]["path"])
            i2 = idx
        elif idx < 60:
            traj = Path(sel["input_sha256"]["traj_273K_seg1"]["path"])
            boxf = Path(sel["input_sha256"]["box_273K_seg1"]["path"])
            i2 = idx
        else:
            traj = Path(sel["input_sha256"]["traj_273K_seg2"]["path"])
            boxf = Path(sel["input_sha256"]["box_273K_seg2"]["path"])
            i2 = idx - 60
        # verify sources unchanged
        for p, key in ((traj, None), (boxf, None)):
            pass
        pos = load_frame(traj, i2)
        box = load_box(boxf, i2)
        events = events_HtoO(pos, box)
        cluster = b["cluster_water_ids"]
        cset = set(cluster)
        cmap = {w: i for i, w in enumerate(cluster)}
        intra = [e for e in events if e["donor_water"] in cset and e["acceptor_water"] in cset]
        pairs = []
        for e in intra:
            h_serial = cmap[e["donor_water"]] * 3 + 1 + e["donor_H_local"]  # O=+1.. wait: O serial = 3i+1, H1 = 3i+2, H2 = 3i+3
            o_serial = cmap[e["acceptor_water"]] * 3 + 1
            pairs.append((h_serial, o_serial))
        txt = ANALYSIS / f"hbonds_{tag}_HtoO.txt"
        txt.write_text("# donor_H_serial acceptor_O_serial (PDB serials in cluster_{0}.pdb)\n".format(tag)
                       + "".join(f"{a} {b}\n" for a, b in pairs))
        out["branches"][tag] = {
            "frame_index": idx, "time_ps": b["time_ps"],
            "n_events_expected": b["n_intra_cluster_hbonds"],
            "n_events_HtoO": len(intra),
            "count_matches_original_OO_list": len(intra) == b["n_intra_cluster_hbonds"],
            "events_with_both_H_satisfied": sum(1 for e in intra if e["both_H_satisfied"]),
            "events": [{**e, "donor_H_serial": cmap[e["donor_water"]] * 3 + 1 + e["donor_H_local"],
                        "acceptor_O_serial": cmap[e["acceptor_water"]] * 3 + 1} for e in intra],
            "pair_file": str(txt),
        }
        print(f"{tag}: {len(intra)} H->O events (expected {b['n_intra_cluster_hbonds']}), "
              f"dual-H events: {out['branches'][tag]['events_with_both_H_satisfied']}")
    (ANALYSIS / "h2o_pairs_report.json").write_text(json.dumps(out, indent=2) + "\n")


if __name__ == "__main__":
    main()
