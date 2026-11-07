"""Strict read-only validation of the packaged final deep-analysis subset."""
from __future__ import annotations
import hashlib,json,math
from pathlib import Path,PureWindowsPath
import numpy as np
ROOT=Path(__file__).resolve().parent;PKG=ROOT.parents[1];OUT=ROOT/'outputs'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest().upper()
def run_checks():
 c=[]
 def ck(n,o,d=''):c.append({'name':n,'passed':bool(o),'detail':d})
 r=json.loads((ROOT/'ANALYSIS_RESULTS.json').read_text());receipt=json.loads((ROOT/'PROVENANCE_AUDIT_RECEIPT.json').read_text());t1=PKG/'02_EXPERIMENT_2_TEMPERATURE_COMPARISON/01_300K_MATCHED_REFERENCE/run/tempcomp_300K_reference';s1=PKG/'02_EXPERIMENT_2_TEMPERATURE_COMPARISON/03_273K_PRODUCTION/segment01_60_frames';s2=PKG/'02_EXPERIMENT_2_TEMPERATURE_COMPARISON/03_273K_PRODUCTION/segment02_40_frames'
 mp={'tempcomp_300K_reference_traj.dat':t1/'tempcomp_300K_reference_traj.dat','tempcomp_300K_reference_traj.box':t1/'tempcomp_300K_reference_traj.box','tempcomp_300K_reference.mdout':t1/'tempcomp_300K_reference.mdout','tempcomp_273K_production_5ps_traj.dat':s1/'tempcomp_273K_production_5ps_traj.dat','tempcomp_273K_production_5ps_resume_traj.dat':s2/'tempcomp_273K_production_5ps_resume_traj.dat','tempcomp_273K_production_5ps_traj.box':s1/'tempcomp_273K_production_5ps_traj.box','tempcomp_273K_production_5ps_resume_traj.box':s2/'tempcomp_273K_production_5ps_resume_traj.box','tempcomp_273K_production_5ps.mdout':s1/'tempcomp_273K_production_5ps.mdout','tempcomp_273K_production_5ps_resume.mdout':s2/'tempcomp_273K_production_5ps_resume.mdout'};bad=[]
 for b in receipt['datasets'].values():
  for k in ('trajectory_files','box_files','mdout_files'):
   for x in b[k]:
    n=PureWindowsPath(x['path']).name
    if n not in mp or sha(mp[n])!=x['sha256'].upper():bad.append(n)
 ck('nine_immutable_source_hashes',len(mp)==9 and not bad,str(bad));ck('expected_final_outputs',len(list(OUT.glob('*.csv')))==22 and len(list(OUT.glob('*.npz')))==7 and len(list(OUT.glob('*.png')))==15,'22 CSV, 7 NPZ, 15 PNG')
 shape=[];finite=True
 for p in OUT.glob('*.npz'):
  with np.load(p) as x:
   finite&=all(np.isfinite(x[k]).all() for k in x.files)
   if p.name.startswith('rdf_per_frame'):shape.append(x['per_frame'].shape==(100,200) and x['block_mean'].shape==(10,200) and x['r'].shape==(200,))
 ck('npz_finite_expected_shapes',finite and len(shape)==6 and all(shape),'RDF (100,200), blocks (10,200)')
 for kind,domain,hfile,rpat,cname,dname in [('distance',(None,3.5),'hbond_distance_hist.csv','hbond_distances_raw_{}.csv','count_{}','density_{}'),('angle',(150.0,180.0),'hbond_angle_hist.csv','hbond_angles_raw_{}.csv','count_{}','density_{}_degree1')]:
  hist=np.genfromtxt(OUT/hfile,delimiter=',',names=True);centers=hist[hist.dtype.names[0]];width=float(np.median(np.diff(centers)));lo=float(centers[0]-width/2);hi=float(centers[-1]+width/2)
  for temp,n in [('300K',110870),('273K',119586)]:
   raw=np.loadtxt(OUT/rpat.format(temp),delimiter=',',skiprows=1);counts=hist[cname.format(temp)];dens=hist[dname.format(temp)];inside=np.isfinite(raw).all() and raw.min()>=lo-1e-12 and raw.max()<=hi+1e-12
   if domain[0] is not None:inside=inside and raw.min()>=domain[0] and raw.max()<=domain[1]
   ck(f'{kind}_histogram_full_coverage_{temp}',len(raw)==n and int(round(counts.sum()))==n and inside,f'n={len(raw)} count_sum={counts.sum():.0f} edges=[{lo},{hi}]');ck(f'{kind}_histogram_normalized_{temp}',math.isclose(float((dens*width).sum()),1.0,rel_tol=0,abs_tol=2e-12),f'integral={(dens*width).sum():.15f}')
 for temp in ('300K','273K'):
  q=np.loadtxt(OUT/f'tetra_q_all_{temp}.csv',delimiter=',',skiprows=1,usecols=2);a=r['tetra_q'][temp];ck(f'tetra_q_population_finite_unclipped_{temp}',q.shape==(86200,) and np.isfinite(q).all() and q.min()>=-3 and q.max()<=1+1e-12,f'n={len(q)} range=[{q.min()},{q.max()}]');ck(f'tetra_q_mean_sd_match_{temp}',math.isclose(float(q.mean()),a['mean'],abs_tol=1e-12) and math.isclose(float(q.std(ddof=1)),a['sd'],abs_tol=1e-12),'mean/sample SD agree')
 expected={'300K':{'OO':(2.775,2.7082021093798248,3.525,0.9313013197458585,[]),'OH':(1.825,1.2555171411711001,2.425,0.2869204029750898,[(3.225,1.434102154847194)]),'HH':(2.475,1.2516853938342571,3.025,0.8434204205923614,[(3.775,1.1191080822989257)])},'273K':{'OO':(2.775,2.9210158509993853,3.375,0.8698861732508644,[]),'OH':(1.825,1.4014511211993204,2.425,0.2391246692651301,[(3.225,1.4973465066001344)]),'HH':(2.425,1.3152123671018479,3.025,0.7881828020093552,[(3.775,1.1381399821179887),(4.825,1.0253509162990004)])}};fb=[]
 for temp,pairs in expected.items():
  for pair,e in pairs.items():
   f=r['rdf'][temp][pair]['features'];got=(f['first_peak']['r_A'],f['first_peak']['g_raw'],f['first_min']['r_A'],f['first_min']['g_raw'],[(x['r_A'],x['g_raw']) for x in f['later_robust_peaks']])
   if any(not math.isclose(float(a),float(b),abs_tol=1e-12) for a,b in zip(got[:4],e[:4])) or len(got[4])!=len(e[4]) or any(not(math.isclose(a[0],b[0],abs_tol=1e-12) and math.isclose(a[1],b[1],abs_tol=1e-12)) for a,b in zip(got[4],e[4])):fb.append(temp+pair)
 ck('accepted_OO_OH_HH_feature_metadata',not fb,str(fb));tails=[]
 for temp in ('300K','273K'):
  for pair in ('OO','OH','HH'):
   with np.load(OUT/f'rdf_per_frame_{pair}_{temp}.npz') as x:tails.append(abs(float(x['per_frame'][:,-20:].mean())-1)<0.15)
 ck('rdf_large_r_normalization_sanity',all(tails),'all six tails near one');ck('coordination_thermo_volume_agreement',math.isclose(r['coordination']['common_3p5_A']['300K']['direct'],5.206612529002319,abs_tol=1e-12) and math.isclose(r['coordination']['common_3p5_A']['273K']['direct'],5.117030162412992,abs_tol=1e-12) and r['thermodynamics']['300K']['temperature']['n']==100 and r['thermodynamics']['273K']['temperature']['n']==99 and r['box_volumes_A3']['300K']['n']==100 and r['box_volumes_A3']['273K']['n']==100,'accepted values/counts')
 text=(ROOT/'FINAL_SCIENTIFIC_INTERPRETATION.md').read_text();ck('final_interpretation_and_limitations',text.startswith('# Final Matched 300 K vs 273 K TIP3P Water Scientific Interpretation') and 'do not directly measure' in text.lower() and '## limitations' in text.lower(),'title/conclusions/limitations')
 return {'checks':c,'passed':sum(x['passed'] for x in c),'total':len(c),'verdict':'FINAL_DEEP_ANALYSIS_SUBSET_VALIDATED' if all(x['passed'] for x in c) else 'FINAL_DEEP_ANALYSIS_SUBSET_REJECTED'}
def main():
 r=run_checks();print(f"{r['verdict']} ({r['passed']}/{r['total']})");return 0 if r['verdict'].endswith('VALIDATED') else 1
if __name__=='__main__':raise SystemExit(main())
