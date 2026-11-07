"""Independent read-only validator for T5R1 derived analysis products."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
OUT = HERE / "outputs"
NATOM, NWAT = 2586, 862
FB = NATOM * 3 * 4
O = np.arange(0, NATOM, 3); H = np.setdiff1d(np.arange(NATOM), O); MOL = np.repeat(np.arange(NWAT), 3)
DR = .05; E = np.arange(0., 10. + 1e-12, DR); R = (E[1:] + E[:-1]) / 2; SHELL = 4 * math.pi / 3 * (E[1:]**3 - E[:-1]**3)
checks = []


def check(name: str, passed: bool, detail: str = "") -> None:
    checks.append({"check": name, "passed": bool(passed), "detail": detail})


def sha(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda: f.read(1024 * 1024), b""): h.update(b)
    return h.hexdigest().upper()


def load(ds: dict) -> tuple[np.ndarray, np.ndarray]:
    a = []
    for row in ds["trajectory_files"]:
        p = Path(row["path"]); a.append(np.fromfile(p, dtype="<f4").astype(float).reshape(-1, NATOM, 3))
    box = []
    for row in ds["box_files"]:
        box += [[float(v) for v in line.split()] for line in Path(row["path"]).read_text().splitlines() if line.strip()]
    return np.concatenate(a), np.asarray(box)[:, :3]


def rdf(frames: np.ndarray, boxes: np.ndarray, kind: str) -> np.ndarray:
    ia, ib = {"OO":(O,O),"OH":(O,H),"HH":(H,H)}[kind]; allg = []
    for pos, box in zip(frames, boxes):
        d = pos[ia,None] - pos[ib][None,:]; d -= box * np.round(d / box); dist = np.linalg.norm(d,axis=-1)
        if ia is ib:
            keep = np.triu(np.ones(dist.shape,dtype=bool),1)
            if ia is H: keep &= MOL[ia,None] != MOL[ib][None,:]
        else:
            keep = MOL[ia,None] != MOL[ib][None,:]
        hist = np.histogram(dist[keep], E)[0]; allg.append(hist / (SHELL * keep.sum() / np.prod(box)))
    return np.asarray(allg)


def find_features(raw: np.ndarray, sd: np.ndarray, kind: str) -> dict:
    # Independent implementation of the documented 3-bin locator/rule.
    floor = {"OO":2.,"OH":1.4,"HH":2.}[kind]; s = np.r_[raw[0],raw,raw[-1]]
    s = (s[:-2] + 2*s[1:-1] + s[2:]) / 4; start = np.searchsorted(R,floor)
    mx = [i for i in range(start+1,len(R)-1) if s[i] >= s[i-1] and s[i] > s[i+1]]
    mn = [i for i in range(start+1,len(R)-1) if s[i] <= s[i-1] and s[i] < s[i+1]]
    items=[]
    for i in mx:
        left=max((j for j in mn if j<i),default=start); right=min((j for j in mn if j>i),default=len(R)-1)
        pr=s[i]-max(s[left],s[right]); noise=max(sd[i],sd[left],sd[right])
        items.append((i,bool(pr >= 3*noise and raw[i]-1 >= 2*sd[i])))
    ip=items[0][0]; imin=min(j for j in mn if j>ip)
    return {"first":float(R[ip]),"minimum":float(R[imin]),"later": [float(R[i]) for i,ok in items if R[i]>R[imin] and ok],"unresolved":[float(R[i]) for i,ok in items if R[i]>R[imin] and not ok]}


def hbond_frame(pos: np.ndarray, box: np.ndarray) -> tuple[int, list[float], list[float]]:
    po=pos[O]; d=po[:,None]-po[None,:]; d-=box*np.round(d/box); oo=np.linalg.norm(d,axis=-1); di,ai=np.where((oo<4)&(oo>1e-12))
    n=0; dis=[]; ang=[]
    for donor,acceptor in zip(di,ai):
        od=po[donor]; oa=od-d[donor,acceptor]
        for lh in (1,2):
            h=pos[3*donor+lh]; x=od-h; x-=box*np.round(x/box); y=oa-h; y-=box*np.round(y/box)
            theta=math.degrees(math.acos(np.clip(np.dot(x,y)/np.linalg.norm(x)/np.linalg.norm(y),-1,1)))
            if oo[donor,acceptor]<3.5 and theta>150: n+=1; dis.append(float(oo[donor,acceptor])); ang.append(theta)
    return n,dis,ang


def q_one(pos: np.ndarray, box: np.ndarray, i: int) -> float:
    po=pos[O]; d=po-po[i]; d-=box*np.round(d/box); dis=np.linalg.norm(d,axis=1); dis[i]=np.inf; ids=np.argsort(dis)[:4]; v=d[ids]/np.linalg.norm(d[ids],axis=1)[:,None]
    return 1-3/8*sum((np.dot(v[a],v[b])+1/3)**2 for a in range(4) for b in range(a+1,4))


def main() -> None:
    receipt=json.loads((HERE/"PROVENANCE_AUDIT_RECEIPT.json").read_text()); result=json.loads((HERE/"ANALYSIS_RESULTS.json").read_text())
    post=json.loads((HERE/"SOURCE_HASHES_POST_ANALYSIS.json").read_text())
    raw={}
    for tag,ds in receipt["datasets"].items():
        source_rows=[]
        for group in ("trajectory_files","box_files","mdout_files"):
            for row in ds[group]:
                p=Path(row["path"]); actual=sha(p); source_rows.append(actual==row["sha256"] and any(x["sha256"]==actual for x in post[tag][group]))
        check(f"{tag}_all_pinned_source_hashes_unchanged",all(source_rows),f"{sum(source_rows)}/{len(source_rows)} files")
        frames,boxes=load(ds); raw[tag]={"frames":frames,"boxes":boxes}
        check(f"{tag}_100_frames_and_boxes",frames.shape==(100,NATOM,3) and boxes.shape==(100,3),str((frames.shape,boxes.shape)))
        check(f"{tag}_box_geometry",np.all(boxes>0),"positive Lx,Ly,Lz")
        vol=np.prod(boxes,axis=1); saved=np.loadtxt(OUT/"box_volume_series.csv",delimiter=",",skiprows=1)[:,1 if tag=="300K" else 3]
        check(f"{tag}_exact_box_volumes_match_raw",np.allclose(vol,saved,rtol=0,atol=1e-9),f"mean={vol.mean():.5f} n={len(vol)}")
    for tag in ("300K","273K"):
        for kind in ("OO","OH","HH"):
            pf=rdf(raw[tag]["frames"],raw[tag]["boxes"],kind); g=pf.mean(0); block=pf.reshape(10,10,-1).mean(1); sd=block.std(0,ddof=1)
            saved=np.loadtxt(OUT/f"rdf_{kind}_{tag}.csv",delimiter=",",skiprows=1)
            check(f"{tag}_{kind}_rdf_recompute_matches",np.allclose(g,saved[:,1],rtol=0,atol=2e-12),"full independent raw RDF recomputation")
            check(f"{tag}_{kind}_rdf_large_r_normalized",abs(g[R>8.5].mean()-1)<.04,f"mean={g[R>8.5].mean():.4f}")
            f=find_features(g,sd,kind); claimed=result["rdf"][tag][kind]["features"]
            check(f"{tag}_{kind}_feature_locations_independent",abs(f["first"]-claimed["first_peak"]["r_A"])<1e-9 and abs(f["minimum"]-claimed["first_min"]["r_A"])<1e-9 and f["later"]==[x["r_A"] for x in claimed["later_robust_peaks"]],str(f))
            if kind=="OH": check(f"{tag}_OH_short_peak_below_2A",f["first"]<2 and abs(f["first"]-1.825)<.051,f"r={f['first']:.3f}")
            check(f"{tag}_{kind}_no_promoted_baseline_wiggle",all(x["g_raw"]-1 >= 2*np.interp(x["r_A"],R,sd) for x in claimed["later_robust_peaks"]),"all claimed later features clear raw-g rule")
        # Same-molecule exclusion check in covalent region.
        oh=np.loadtxt(OUT/f"rdf_OH_{tag}.csv",delimiter=",",skiprows=1); hh=np.loadtxt(OUT/f"rdf_HH_{tag}.csv",delimiter=",",skiprows=1)
        check(f"{tag}_OH_excludes_intramolecular_pairs",oh[(oh[:,0]>.85)&(oh[:,0]<1.1),1].max()<.05,"covalent O-H region")
        check(f"{tag}_HH_excludes_intramolecular_pairs",hh[(hh[:,0]>1.45)&(hh[:,0]<1.65),1].max()<.05,"intramolecular H-H region")
    # Recompute direct coordination in a single pair-distance pass for all reported radii.
    coord=result["coordination"]; radii=[coord[k]["300K"]["cutoff_A"] for k in ("rmin_300K","rmin_273K","common_3p5_A")]
    for tag in ("300K","273K"):
        direct=np.zeros(3)
        for pos,box in zip(raw[tag]["frames"],raw[tag]["boxes"]):
            po=pos[O]; d=po[:,None]-po[None,:]; d-=box*np.round(d/box); dis=np.linalg.norm(d,axis=-1)
            direct += [np.count_nonzero((dis<=cut)&(dis>1e-12))/NWAT for cut in radii]
        direct/=100
        for value,key in zip(direct,("rmin_300K","rmin_273K","common_3p5_A")):
            claimed=coord[key][tag]; check(f"{tag}_{key}_direct_coordination_recompute",abs(value-claimed["direct"])<1e-10,f"{value:.6f}")
            check(f"{tag}_{key}_direct_vs_rdf_integrated",abs(claimed["direct"]-claimed["integrated"])<.05,f"{claimed['direct']:.4f} vs {claimed['integrated']:.4f}")
    # Histogram count coverage is explicit; no density=True drop/re-normalization is permitted.
    hist=np.loadtxt(OUT/"hbond_distance_hist.csv",delimiter=",",skiprows=1)
    for col,tag in ((1,"300K"),(3,"273K")):
        rawd=np.loadtxt(OUT/f"hbond_distances_raw_{tag}.csv",delimiter=",",skiprows=1); count=int(hist[:,col].sum())
        check(f"{tag}_HB_histogram_covers_all_raw_events",len(rawd)==count and rawd.min()>=2.4 and rawd.max()<=3.5,f"raw={len(rawd)} hist={count}; range={rawd.min():.4f}-{rawd.max():.4f}")
        check(f"{tag}_HB_distance_density_integrates_1",abs((hist[:,col+1]*.025).sum()-1)<1e-12,f"integral={(hist[:,col+1]*.025).sum():.12f}")
        rawang=np.loadtxt(OUT/f"hbond_angles_raw_{tag}.csv",delimiter=",",skiprows=1)
        check(f"{tag}_HB_exact_cutoffs_in_raw_outputs",rawd.max()<=3.5 and rawang.min()>150 and len(rawd)==len(rawang),"O...O<3.5 and H-vertex angle>150")
        for frame in (0,50,99):
            n,dd,aa=hbond_frame(raw[tag]["frames"][frame],raw[tag]["boxes"][frame])
            series=np.loadtxt(OUT/"hbond_timeseries.csv",delimiter=",",skiprows=1)[:,1 if tag=="300K" else 4]
            check(f"{tag}_HB_frame_{frame}_independent_geometry",n==int(series[frame]) and all(x<3.5 for x in dd) and all(x>150 for x in aa),f"events={n}")
    # q values are independently recomputed for a fixed deterministic sample.
    for tag in ("300K","273K"):
        saved=np.loadtxt(OUT/f"tetra_q_all_{tag}.csv",delimiter=",",skiprows=1)
        ok=True
        for frame,water in ((0,0),(7,111),(19,222),(33,333),(47,444),(61,555),(75,666),(89,777),(99,861),(50,400)):
            ok &= abs(q_one(raw[tag]["frames"][frame],raw[tag]["boxes"][frame],water)-saved[frame,water])<1e-12
        check(f"{tag}_tetra_q_independent_recompute",ok,"10 fixed frame/water samples")
    required=["ANALYSIS_RESULTS.json","PROVENANCE_AUDIT_RECEIPT.json","SOURCE_HASHES_POST_ANALYSIS.json","T5R1_SCIENTIFIC_INTERPRETATION.md","analyze_t5r1_matched_water.py","validate_t5r1.py"]
    required += ["rdf_OH_300K.csv","rdf_OH_273K.csv","coordination_matched_radii.csv","hbond_distance_hist.csv","box_volume_series.csv","descriptive_block_summaries.csv","hbond_distance_angle_map_normalized.npz","fig_rdf_OH_overlay.png","fig_box_volume_comparison.png"]
    check("all_required_T5R1_products_exist",all((HERE/x).exists() if not x.startswith(("rdf_","coord","hbond","box_","descriptive","fig_")) else (OUT/x).exists() for x in required),str(len(required)))
    verdict="T5R1_MATCHED_DEEP_ANALYSIS_REPAIR_VALIDATED" if all(x["passed"] for x in checks) else "T5R1_MATCHED_DEEP_ANALYSIS_REPAIR_FAILED"
    report={"verdict":verdict,"check_count":len(checks),"passed_count":sum(x["passed"] for x in checks),"failed_count":sum(not x["passed"] for x in checks),"checks":checks}
    (HERE/"validation").mkdir(exist_ok=True); (HERE/"validation"/"T5R1_MATCHED_DEEP_ANALYSIS_REPAIR_VALIDATION.json").write_text(json.dumps(report,indent=2)+"\n")
    print(f"{verdict}: {report['passed_count']}/{report['check_count']} checks passed")
    if verdict.endswith("FAILED"): raise SystemExit(1)


if __name__ == "__main__": main()
