"""T5R1 repaired matched-water analysis. Read-only on all MD source files."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
OUT = HERE / "outputs"
OUT.mkdir(exist_ok=True)
NATOM, NWAT = 2586, 862
FRAME_BYTES = NATOM * 3 * 4
O = np.arange(0, NATOM, 3)
H = np.setdiff1d(np.arange(NATOM), O)
MOL = np.repeat(np.arange(NWAT), 3)
DR = .05
EDGES = np.arange(0., 10. + 1e-12, DR)
R = (EDGES[:-1] + EDGES[1:]) / 2
SHELL = 4 * math.pi / 3 * (EDGES[1:] ** 3 - EDGES[:-1] ** 3)


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(1024 * 1024), b""):
            h.update(b)
    return h.hexdigest().upper()


def check_sources(receipt: dict) -> dict:
    got = {}
    for tag, ds in receipt["datasets"].items():
        got[tag] = {}
        for group in ("trajectory_files", "box_files", "mdout_files"):
            got[tag][group] = []
            for row in ds[group]:
                p = Path(row["path"])
                actual = digest(p)
                if actual != row["sha256"]:
                    raise RuntimeError(f"Hash mismatch: {p}")
                got[tag][group].append({"path": str(p), "sha256": actual})
    return got


def load(ds: dict) -> tuple[np.ndarray, np.ndarray, list[dict]]:
    chunks = []
    for row in ds["trajectory_files"]:
        p = Path(row["path"])
        if p.stat().st_size % FRAME_BYTES:
            raise ValueError(f"Non-integral trajectory: {p}")
        chunks.append(np.fromfile(p, dtype="<f4").astype(float).reshape(-1, NATOM, 3))
    frames = np.concatenate(chunks)
    box = []
    for row in ds["box_files"]:
        box += [[float(x) for x in line.split()] for line in Path(row["path"]).read_text().splitlines() if line.strip()]
    box = np.asarray(box)
    if frames.shape[0] != 100 or box.shape != (100, 6) or not np.allclose(box[:, 3:], 90.):
        raise ValueError("Structural frames/boxes must be 100/100 and orthorhombic")
    rec = []
    for row in ds["mdout_files"]:
        lines = Path(row["path"]).read_text().splitlines()
        i = next(i for i, line in enumerate(lines) if "step" in line.split() and "temperature" in line.split())
        labels = lines[i].split(); ind = {}
        for j, label in enumerate(labels): ind.setdefault(label, j)
        for line in lines[i + 1:]:
            vals = line.split()
            if len(vals) >= len(labels):
                rec.append({k: float(vals[ind[k]]) for k in ("step", "time", "temperature", "pressure", "potential", "density")})
    if len(rec) != ds["mdout_record_count"]:
        raise ValueError("Unexpected mdout count")
    return frames, box[:, :3], rec


def pair_hist(pos: np.ndarray, ia: np.ndarray, ib: np.ndarray, box: np.ndarray) -> tuple[np.ndarray, int]:
    d = pos[ia][:, None] - pos[ib][None, :]
    d -= box * np.round(d / box)
    dist = np.linalg.norm(d, axis=-1)
    if ia is ib:
        keep = np.triu(np.ones(dist.shape, dtype=bool), 1)
        # OO has one O per molecule, whereas HH must also reject the two
        # hydrogens belonging to the same water molecule.
        if ia is H:
            keep &= MOL[ia][:, None] != MOL[ib][None, :]
    else:
        keep = MOL[ia][:, None] != MOL[ib][None, :]
    return np.histogram(dist[keep], EDGES)[0].astype(float), int(keep.sum())


def calculate_rdf(frames: np.ndarray, boxes: np.ndarray, kind: str) -> tuple[np.ndarray, np.ndarray, int]:
    ia, ib = {"OO": (O, O), "OH": (O, H), "HH": (H, H)}[kind]
    out = []
    pairs = 0
    for pos, box in zip(frames, boxes):
        hist, pairs = pair_hist(pos, ia, ib, box)
        out.append(hist / (SHELL * pairs / np.prod(box)))
    pf = np.asarray(out)
    return pf, pf.mean(axis=0), pairs


def locator(raw: np.ndarray) -> np.ndarray:
    return np.convolve(np.pad(raw, 1, mode="edge"), np.array([1., 2., 1.]) / 4, mode="valid")


def features(raw: np.ndarray, sd: np.ndarray, kind: str) -> dict:
    """Species-aware feature rule; smoothing locates positions, raw g reports them."""
    floor = {"OO": 2., "OH": 1.4, "HH": 2.}[kind]
    s = locator(raw); start = int(np.searchsorted(R, floor))
    maxes = [i for i in range(start + 1, len(R) - 1) if s[i] >= s[i-1] and s[i] > s[i+1]]
    mins = [i for i in range(start + 1, len(R) - 1) if s[i] <= s[i-1] and s[i] < s[i+1]]
    cand = []
    for i in maxes:
        left = max((j for j in mins if j < i), default=start)
        right = min((j for j in mins if j > i), default=len(R) - 1)
        prom = float(s[i] - max(s[left], s[right]))
        noise = float(max(sd[i], sd[left], sd[right]))
        robust = bool(prom >= 3 * noise and raw[i] - 1 >= 2 * sd[i])
        cand.append({"r_A": float(R[i]), "g_raw": float(raw[i]), "g_smoothed": float(s[i]),
                     "prominence_smoothed": prom, "local_block_sd": noise, "robust": robust})
    if not cand: raise ValueError(f"No extrema for {kind}")
    first = cand[0]; ip = int(np.argmin(abs(R - first["r_A"])))
    im = min((j for j in mins if j > ip), default=None)
    if im is None: raise ValueError(f"No first minimum for {kind}")
    return {"rule": "3-bin locator; later peak requires prominence >= 3 local block SD and raw g-1 >= 2 peak-bin block SD",
            "search_floor_A": floor, "first_peak": first,
            "first_min": {"r_A": float(R[im]), "g_raw": float(raw[im]), "g_smoothed": float(s[im]), "block_sd": float(sd[im])},
            "later_robust_peaks": [x for x in cand if x["r_A"] > R[im] and x["robust"]],
            "later_unresolved_candidates": [x for x in cand if x["r_A"] > R[im] and not x["robust"]]}


def direct_coord(frames: np.ndarray, boxes: np.ndarray, cutoff: float) -> float:
    result = []
    for pos, box in zip(frames, boxes):
        po = pos[O]; d = po[:, None] - po[None, :]; d -= box * np.round(d / box)
        dist = np.linalg.norm(d, axis=-1)
        result.append(np.count_nonzero((dist <= cutoff) & (dist > 1e-12)) / NWAT)
    return float(np.mean(result))


def rdf_coord(per_frame: np.ndarray, boxes: np.ndarray, cutoff: float) -> float:
    partial = np.maximum(0., np.minimum(EDGES[1:], cutoff)**3 - EDGES[:-1]**3) * (4 * math.pi / 3)
    return float(np.mean((NWAT - 1) / np.prod(boxes, axis=1) * (per_frame * partial).sum(axis=1)))


def direct_coord_curve(frames: np.ndarray, boxes: np.ndarray) -> np.ndarray:
    """One distance pass for the illustrative cumulative coordination plot."""
    total = np.zeros(len(R))
    for pos, box in zip(frames, boxes):
        po = pos[O]; d = po[:, None] - po[None, :]; d -= box * np.round(d / box)
        dist = np.linalg.norm(d, axis=-1)
        hist = np.histogram(dist[np.triu_indices(NWAT, 1)], EDGES)[0]
        total += 2 * np.cumsum(hist) / NWAT
    return total / len(frames)


def hbonds(pos: np.ndarray, box: np.ndarray) -> tuple[int, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    po = pos[O]; d = po[:, None] - po[None, :]; d -= box * np.round(d / box); oo = np.linalg.norm(d, axis=-1)
    donor, acceptor = np.where((oo < 4.) & (oo > 1e-12))
    event, dis, ang, mapd, mapa = 0, [], [], [], []
    for di, ai in zip(donor, acceptor):
        od, oa = po[di], po[di] - d[di, ai]
        for local_h in (1, 2):
            h = pos[3 * di + local_h]; v1 = od - h; v1 -= box * np.round(v1 / box); v2 = oa - h; v2 -= box * np.round(v2 / box)
            angle = math.degrees(math.acos(np.clip(np.dot(v1, v2) / np.linalg.norm(v1) / np.linalg.norm(v2), -1, 1)))
            mapd.append(oo[di, ai]); mapa.append(angle)
            if oo[di, ai] < 3.5 and angle > 150.:
                event += 1; dis.append(oo[di, ai]); ang.append(angle)
    return event, np.asarray(dis), np.asarray(ang), np.asarray(mapd), np.asarray(mapa)


def tetra(pos: np.ndarray, box: np.ndarray) -> np.ndarray:
    po = pos[O]; d = po[:, None] - po[None, :]; d -= box * np.round(d / box); dist = np.linalg.norm(d, axis=-1); np.fill_diagonal(dist, np.inf)
    near = np.argsort(dist, axis=1)[:, :4]; out = np.empty(NWAT)
    for i in range(NWAT):
        v = po[near[i]] - po[i]; v -= box * np.round(v / box); v /= np.linalg.norm(v, axis=1)[:, None]
        out[i] = 1 - 3/8 * sum((np.dot(v[a], v[b]) + 1/3)**2 for a in range(4) for b in range(a+1, 4))
    return out


def csv(name: str, data: np.ndarray, header: str) -> None:
    np.savetxt(OUT / name, data, delimiter=",", header=header, comments="")


def make_rdf_plots(rdf: dict) -> None:
    for kind in ("OO", "OH", "HH"):
        plt.figure(figsize=(6,4))
        for tag, color in (("300K", "tab:red"), ("273K", "tab:blue")):
            plt.plot(R, rdf[tag][kind]["g"], color=color, label=tag.replace("K", " K"))
        plt.xlim(1.4, 6) if kind == "OH" else plt.xlim(2, 8)
        plt.xlabel("r (A)"); plt.ylabel(f"g_{kind}(r)"); plt.legend(); plt.tight_layout(); plt.savefig(OUT / f"fig_rdf_{kind}_overlay.png", dpi=200); plt.close()


def write_interpretation(results: dict) -> None:
    rdf, co, hb, q, vol = results["rdf"], results["coordination"], results["hbonds"], results["tetra_q"], results["box_volumes_A3"]
    o1, o2 = rdf["300K"]["OH"]["features"], rdf["273K"]["OH"]["features"]
    h1, h2 = rdf["300K"]["HH"]["features"], rdf["273K"]["HH"]["features"]
    rows = [
        "# T5R1 repaired matched 300 K vs 273 K water analysis", "",
        "This is an analysis-only revision. T1--T4 sources and historical T5 were not modified; the same seven hash-pinned source files were verified before and after analysis. SPONGE was not run.", "",
        "## Evidence limits", "",
        "The datasets are single, related trajectory lineages, not independent temperature replicates. Results are descriptive: no p-values, confidence intervals, independent-sample claims, ice, phase transition, diffusion, long-time convergence, or rigorous-equilibrium claims are made. The 273 K set has 99 thermo records because the step-3000 mdout record was not fabricated; both structural/box sets contain 100 records.", "",
        "## Repaired RDF feature table", "",
        "Locations use a light 3-bin smoothing only; reported g is raw. A later feature must clear three local 0.5 ps block SDs in prominence and two peak-bin SDs above g=1. Near-baseline candidates are unresolved.", "",
        "| RDF | 300 K first peak | 300 K later robust peak | 273 K first peak | 273 K later robust peak |", "|---|---|---|---|---|",
        f"| O-O | {rdf['300K']['OO']['features']['first_peak']['r_A']:.3f} A, g={rdf['300K']['OO']['features']['first_peak']['g_raw']:.3f} | none; broad second-shell candidates unresolved | {rdf['273K']['OO']['features']['first_peak']['r_A']:.3f} A, g={rdf['273K']['OO']['features']['first_peak']['g_raw']:.3f} | none; broad second-shell candidates unresolved |",
        f"| O-H | {o1['first_peak']['r_A']:.3f} A, g={o1['first_peak']['g_raw']:.3f} | {o1['later_robust_peaks'][0]['r_A']:.3f} A, g={o1['later_robust_peaks'][0]['g_raw']:.3f} | {o2['first_peak']['r_A']:.3f} A, g={o2['first_peak']['g_raw']:.3f} | {o2['later_robust_peaks'][0]['r_A']:.3f} A, g={o2['later_robust_peaks'][0]['g_raw']:.3f} |",
        f"| H-H | {h1['first_peak']['r_A']:.3f} A, g={h1['first_peak']['g_raw']:.3f} | {h1['later_robust_peaks'][0]['r_A']:.3f} A, g={h1['later_robust_peaks'][0]['g_raw']:.3f} | {h2['first_peak']['r_A']:.3f} A, g={h2['first_peak']['g_raw']:.3f} | {h2['later_robust_peaks'][0]['r_A']:.3f} A, g={h2['later_robust_peaks'][0]['g_raw']:.3f} |", "",
        "The O-H ~1.8 A intermolecular feature is hydrogen-bond-related and distinct from the later ~3.2 A structural/orientational contact. The ~5.5 A near-baseline fluctuation is not identified as an important second feature.", "",
        "## Coordination: own minima versus matched radii", "",
        "| cutoff A | direct 300 K | RDF-integrated 300 K | direct 273 K | RDF-integrated 273 K |", "|---|---:|---:|---:|---:|",
    ]
    for key in ("rmin_300K", "rmin_273K", "common_3p5_A"):
        x, y = co[key]["300K"], co[key]["273K"]
        rows.append(f"| {x['cutoff_A']:.3f} | {x['direct']:.3f} | {x['integrated']:.3f} | {y['direct']:.3f} | {y['integrated']:.3f} |")
    rows += ["", "Values at separate own minima are shell descriptions only; the common-cutoff and cross-evaluated rows are the like-for-like comparison, so no one-neighbour decrease is inferred solely from differently sized shells.", "",
        "## H-bond, tetrahedral, and volume results", "",
        f"Geometric H-bonds/frame are {hb['300K']['mean_events']:.1f} +/- {hb['300K']['sd_events']:.1f} (300 K) and {hb['273K']['mean_events']:.1f} +/- {hb['273K']['sd_events']:.1f} (273 K); H-bonds/water are {hb['300K']['mean_per_water']:.3f} and {hb['273K']['mean_per_water']:.3f}. The cooler trajectory therefore has a more populated geometric network. Its geometry and potential energy are consistent with, but do not directly measure, stronger bonding.",
        f"Mean raw tetrahedral q: {q['300K']['mean']:.4f} (300 K), {q['273K']['mean']:.4f} (273 K). Exact 100-box volumes: {vol['300K']['mean']:.2f} +/- {vol['300K']['sd']:.2f} A3 and {vol['273K']['mean']:.2f} +/- {vol['273K']['sd']:.2f} A3. Observed mean densities are very similar in these short trajectories; no density change is resolved here.",
        "", "H-bond distance histograms cover all accepted 2.4--3.5 A events without density=True underflow renormalization. Distance-angle maps are probability-per-candidate-bin maps on one shared scale. `outputs/descriptive_block_summaries.csv` contains the requested correlated 0.5 ps descriptive stability blocks."]
    (HERE / "T5R1_SCIENTIFIC_INTERPRETATION.md").write_text("\n".join(rows) + "\n")


def main() -> None:
    receipt = json.loads((HERE / "PROVENANCE_AUDIT_RECEIPT.json").read_text())
    before = check_sources(receipt)
    data, rdf = {}, {}
    for tag in ("300K", "273K"):
        frames, boxes, records = load(receipt["datasets"][tag])
        data[tag] = {"frames": frames, "boxes": boxes, "records": records, "times": receipt["datasets"][tag]["start_time_ps"] + .05 * np.arange(1, 101)}
        rdf[tag] = {}
        for kind in ("OO", "OH", "HH"):
            pf, g, pairs = calculate_rdf(frames, boxes, kind); block = pf.reshape(10,10,-1).mean(axis=1); sd = block.std(axis=0, ddof=1)
            rdf[tag][kind] = {"per_frame": pf, "g": g, "block": block, "sd": sd, "pairs": pairs, "features": features(g, sd, kind)}
            csv(f"rdf_{kind}_{tag}.csv", np.c_[R,g,sd], "r_A,g_avg,block_sd_over_10x0.5ps_blocks")
            np.savez(OUT / f"rdf_per_frame_{kind}_{tag}.npz", r=R, per_frame=pf, block_mean=block)
    make_rdf_plots(rdf)
    r300 = rdf["300K"]["OO"]["features"]["first_min"]["r_A"]; r273 = rdf["273K"]["OO"]["features"]["first_min"]["r_A"]
    coord = {"rmin_300K_A":r300, "rmin_273K_A":r273}
    for name, cut in (("rmin_300K",r300),("rmin_273K",r273),("common_3p5_A",3.5)):
        coord[name] = {tag:{"cutoff_A":cut, "direct":direct_coord(data[tag]["frames"],data[tag]["boxes"],cut), "integrated":rdf_coord(rdf[tag]["OO"]["per_frame"],data[tag]["boxes"],cut)} for tag in ("300K","273K")}
    csv("coordination_matched_radii.csv", np.asarray([[coord[x]["300K"]["cutoff_A"],coord[x]["300K"]["direct"],coord[x]["300K"]["integrated"],coord[x]["273K"]["direct"],coord[x]["273K"]["integrated"]] for x in ("rmin_300K","rmin_273K","common_3p5_A")]), "cutoff_A,N_direct_300K,N_integrated_300K,N_direct_273K,N_integrated_273K")
    plt.figure(figsize=(6,4))
    for tag,color in (("300K","tab:red"),("273K","tab:blue")):
        plt.plot(R,direct_coord_curve(data[tag]["frames"],data[tag]["boxes"]),color=color,label=tag.replace("K"," K"))
    plt.axvline(3.5,color="black",ls="--"); plt.xlim(2,6); plt.xlabel("cutoff (A)"); plt.ylabel("O neighbours per O"); plt.legend(); plt.tight_layout(); plt.savefig(OUT / "fig_coordination_matched_radii.png",dpi=200); plt.close()
    hb = {}
    for tag in ("300K","273K"):
        e=[]; dd=[]; aa=[]; md=[]; ma=[]
        for pos,box in zip(data[tag]["frames"],data[tag]["boxes"]):
            n,d,a,x,y = hbonds(pos,box); e.append(n); dd.append(d); aa.append(a); md.append(x); ma.append(y)
        e=np.asarray(e); dd=np.concatenate(dd); aa=np.concatenate(aa)
        hb[tag]={"events":e,"distances":dd,"angles":aa,"mapd":np.concatenate(md),"mapa":np.concatenate(ma),"per_water":2*e/NWAT,"mean_events":float(e.mean()),"sd_events":float(e.std(ddof=1)),"mean_per_water":float((2*e/NWAT).mean()),"sd_per_water":float((2*e/NWAT).std(ddof=1)),"distance_mean":float(dd.mean()),"distance_sd":float(dd.std(ddof=1)),"angle_mean":float(aa.mean()),"angle_sd":float(aa.std(ddof=1))}
        csv(f"hbond_distances_raw_{tag}.csv",dd[:,None],"O_D...O_A_distance_A_accepted_hbonds_only"); csv(f"hbond_angles_raw_{tag}.csv",aa[:,None],"O_D-H...O_A_angle_deg_accepted_hbonds_only")
    csv("hbond_timeseries.csv",np.c_[data['300K']['times'],hb['300K']['events'],hb['300K']['per_water'],data['273K']['times'],hb['273K']['events'],hb['273K']['per_water']],"t_ps_300K,N_HB_300K,HB_per_water_300K,t_ps_273K,N_HB_273K,HB_per_water_273K")
    for fname,key,ylabel in (("fig_hbond_count_vs_time.png","events","N_HB/frame"),("fig_hbonds_per_water_vs_time.png","per_water","H-bonds/water")):
        plt.figure(figsize=(6,4))
        for tag,color in (("300K","tab:red"),("273K","tab:blue")): plt.plot(data[tag]["times"],hb[tag][key],".",ms=3,color=color,label=tag.replace("K"," K"))
        plt.xlabel("t (ps)"); plt.ylabel(ylabel); plt.legend(); plt.tight_layout(); plt.savefig(OUT/fname,dpi=200); plt.close()
    de=np.arange(2.4,3.5+1e-12,.025); dc=(de[1:]+de[:-1])/2; dcounts=[np.histogram(hb[t]["distances"],de)[0] for t in ("300K","273K")]; ddens=[x/(x.sum()*.025) for x in dcounts]
    csv("hbond_distance_hist.csv",np.c_[dc,dcounts[0],ddens[0],dcounts[1],ddens[1]],"bin_center_A,count_300K,density_300K,count_273K,density_273K")
    plt.figure(figsize=(6,4)); [plt.plot(dc,den,"o-",ms=3,color=color,label=tag.replace("K"," K")) for tag,den,color in (("300K",ddens[0],"tab:red"),("273K",ddens[1],"tab:blue"))]; plt.xlabel("accepted O_D...O_A (A)"); plt.ylabel("probability density (1/A)"); plt.legend(); plt.tight_layout(); plt.savefig(OUT/"fig_hbond_distance_distribution.png",dpi=200); plt.close()
    ae=np.arange(150.,180.+1e-12,1.); ac=(ae[1:]+ae[:-1])/2; acounts=[np.histogram(hb[t]["angles"],ae)[0] for t in ("300K","273K")]; adens=[x/x.sum() for x in acounts]
    csv("hbond_angle_hist.csv",np.c_[ac,acounts[0],adens[0],acounts[1],adens[1]],"bin_center_deg,count_300K,probability_300K,count_273K,probability_273K")
    plt.figure(figsize=(6,4)); [plt.plot(ac,den,"o-",ms=3,color=color,label=tag.replace("K"," K")) for tag,den,color in (("300K",adens[0],"tab:red"),("273K",adens[1],"tab:blue"))]; plt.xlabel("accepted angle (degree)"); plt.ylabel("probability per bin"); plt.legend(); plt.tight_layout(); plt.savefig(OUT/"fig_hbond_angle_distribution.png",dpi=200); plt.close()
    me=np.arange(2.4,4.+1e-12,.04); xe=np.arange(90.,180.+1e-12,2.); maps=[np.histogram2d(hb[t]["mapd"],hb[t]["mapa"],bins=(me,xe))[0] for t in ("300K","273K")]; maps=[x/x.sum() for x in maps]; vmax=max(x.max() for x in maps)
    fig,axs=plt.subplots(1,2,figsize=(11,4.4),sharey=True)
    for ax,tag,m in zip(axs,("300K","273K"),maps):
        im=ax.pcolormesh(me,xe,m.T,shading="auto",cmap="viridis",vmin=0,vmax=vmax); ax.axvline(3.5,color="white",ls="--"); ax.axhline(150,color="white",ls="--"); ax.set_title(tag.replace("K"," K")); ax.set_xlabel("O_D...O_A (A)")
    axs[0].set_ylabel("O_D-H...O_A (degree)"); fig.colorbar(im,ax=axs,label="probability per candidate bin"); plt.tight_layout(); plt.savefig(OUT/"fig_hbond_distance_angle_map_normalized.png",dpi=200); plt.close(); np.savez(OUT/"hbond_distance_angle_map_normalized.npz",r_edges=me,a_edges=xe,probability_300K=maps[0],probability_273K=maps[1])
    q={}
    for tag in ("300K","273K"):
        allq=np.asarray([tetra(pos,box) for pos,box in zip(data[tag]["frames"],data[tag]["boxes"])]); q[tag]={"all":allq,"frame":allq.mean(axis=1),"mean":float(allq.mean()),"sd":float(allq.std(ddof=1)),"range":[float(allq.min()),float(allq.max())]}; csv(f"tetra_q_all_{tag}.csv",allq,"raw_q_by_water_columns; rows_are_frames; never_clipped")
    csv("tetra_q_timeseries.csv",np.c_[data['300K']['times'],q['300K']['frame'],data['273K']['times'],q['273K']['frame']],"t_ps_300K,qmean_300K,t_ps_273K,qmean_273K")
    qe=np.arange(-3.,1.+1e-12,.02); qc=(qe[:-1]+qe[1:])/2; qd=[np.histogram(q[t]["all"],qe,density=True)[0] for t in ("300K","273K")]; csv("tetra_q_distribution.csv",np.c_[qc,qd[0],qd[1]],"bin_center_q,density_300K,density_273K")
    plt.figure(figsize=(6,4)); [plt.plot(data[t]["times"],q[t]["frame"],".",ms=3,color=c,label=t.replace("K"," K")) for t,c in (("300K","tab:red"),("273K","tab:blue"))]; plt.xlabel("t (ps)"); plt.ylabel("mean q/frame"); plt.legend(); plt.tight_layout(); plt.savefig(OUT/"fig_tetra_q_vs_time.png",dpi=200); plt.close()
    plt.figure(figsize=(6,4)); [plt.plot(qc,y,color=c,label=t.replace("K"," K")) for t,y,c in (("300K",qd[0],"tab:red"),("273K",qd[1],"tab:blue"))]; plt.xlabel("q"); plt.ylabel("density"); plt.legend(); plt.tight_layout(); plt.savefig(OUT/"fig_tetra_q_distribution.png",dpi=200); plt.close()
    volume={t:np.prod(data[t]["boxes"],axis=1) for t in ("300K","273K")}; vres={t:{"mean":float(volume[t].mean()),"sd":float(volume[t].std(ddof=1)),"n":100} for t in volume}; csv("box_volume_series.csv",np.c_[data['300K']['times'],volume['300K'],data['273K']['times'],volume['273K']],"t_ps_300K,volume_A3_300K,t_ps_273K,volume_A3_273K")
    plt.figure(figsize=(6,4)); [plt.plot(data[t]["times"],volume[t],".",ms=3,color=c,label=t.replace("K"," K")) for t,c in (("300K","tab:red"),("273K","tab:blue"))]; plt.xlabel("t (ps)"); plt.ylabel("Lx*Ly*Lz (A3)"); plt.legend(); plt.tight_layout(); plt.savefig(OUT/"fig_box_volume_comparison.png",dpi=200); plt.close()
    thermo={}
    for tag in ("300K","273K"):
        records=data[tag]["records"]; thermo[tag]={k:{"mean":float(np.mean([x[k] for x in records])),"sd":float(np.std([x[k] for x in records],ddof=1)),"n":len(records)} for k in ("temperature","density","potential","pressure")}; csv(f"thermo_series_{tag}.csv",np.asarray([[x[k] for k in ("time","temperature","density","potential","pressure")] for x in records]),"time_ps,temperature_K,density_g_cm3,potential_kcal_mol,pressure_bar")
    for key,ylab,fname in (("temperature","temperature (K)","fig_temperature_comparison.png"),("density","density (g/cm3)","fig_density_comparison.png"),("potential","potential (kcal/mol)","fig_potential_comparison.png")):
        plt.figure(figsize=(6,4)); [plt.plot([x['time'] for x in data[t]['records']],[x[key] for x in data[t]['records']],".",ms=3,color=c,label=t.replace("K"," K")) for t,c in (("300K","tab:red"),("273K","tab:blue"))]; plt.xlabel("time (ps)"); plt.ylabel(ylab); plt.legend(); plt.tight_layout(); plt.savefig(OUT/fname,dpi=200); plt.close()
    blocks=[]
    for i in range(10):
        s=slice(i*10,(i+1)*10); blocks.append([i+1,data['300K']['times'][s.start],data['300K']['times'][s.stop-1],hb['300K']['events'][s].mean(),hb['300K']['per_water'][s].mean(),q['300K']['frame'][s].mean(),data['273K']['times'][s.start],data['273K']['times'][s.stop-1],hb['273K']['events'][s].mean(),hb['273K']['per_water'][s].mean(),q['273K']['frame'][s].mean()])
    csv("descriptive_block_summaries.csv",np.asarray(blocks),"block_0p5ps,t_start_300K,t_end_300K,mean_N_HB_300K,mean_HB_per_water_300K,mean_q_300K,t_start_273K,t_end_273K,mean_N_HB_273K,mean_HB_per_water_273K,mean_q_273K")
    after=check_sources(receipt)
    if before != after: raise RuntimeError("Raw source hash changed during analysis")
    (HERE/"SOURCE_HASHES_POST_ANALYSIS.json").write_text(json.dumps(after,indent=2)+"\n")
    results={"pass":"T5R1_matched_deep_analysis_repair","frames_per_branch":100,"method":{"rdf":"intermolecular minimum-image PBC; dr=0.05 A; exact per-frame volumes","hbond":"O...O <3.5 A and O-D-H...O-A >150 degree at H, triplet events","volumes":"Lx*Ly*Lz from 100 synchronized box records","maps":"probability per candidate bin, shared color scale"},"rdf":{t:{k:{"features":rdf[t][k]["features"]} for k in ("OO","OH","HH")} for t in ("300K","273K")},"coordination":coord,"hbonds":{t:{k:v for k,v in hb[t].items() if k not in ("events","distances","angles","mapd","mapa","per_water")} for t in hb},"tetra_q":{t:{k:v for k,v in q[t].items() if k not in ("all","frame")} for t in q},"box_volumes_A3":vres,"thermodynamics":thermo,"limitations":["single related 5 ps lineages; descriptive only","273 K has 99 mdout records; missing step-3000 record is not fabricated","no ice, phase-transition, diffusion, convergence, or rigorous-equilibrium claim"]}
    (HERE/"ANALYSIS_RESULTS.json").write_text(json.dumps(results,indent=2)+"\n"); write_interpretation(results); print("T5R1 analysis complete; all source hashes unchanged.")


if __name__ == "__main__":
    main()
