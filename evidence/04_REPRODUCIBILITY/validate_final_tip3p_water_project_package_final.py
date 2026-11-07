"""Read-only-by-default FINAL validator with complete manifest enforcement."""
from __future__ import annotations
import argparse,csv,hashlib,json,subprocess,sys,struct,zlib
from pathlib import Path,PureWindowsPath
import numpy as np
ROOT=Path(__file__).resolve().parents[1];MANIFEST=ROOT/'FINAL_PACKAGE_MANIFEST_SHA256.csv'
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest().upper()
def png(p):
 d=p.read_bytes();i=8
 if d[:8]!=b'\x89PNG\r\n\x1a\n':return False
 while i<len(d):
  if i+12>len(d):return False
  n=struct.unpack('>I',d[i:i+4])[0];e=i+8+n
  if e+4>len(d) or zlib.crc32(d[i+4:e])&0xffffffff!=struct.unpack('>I',d[e:e+4])[0]:return False
  typ=d[i+4:i+8];i=e+4
  if typ==b'IEND':return i==len(d)
 return False
def path_hash_records(obj):
 found=[]
 if isinstance(obj,dict):
  if isinstance(obj.get('package_relative_path'),str) and isinstance(obj.get('sha256'),str):found.append((obj['package_relative_path'],obj['sha256']))
  if isinstance(obj.get('package_relative_current_path'),str) and isinstance(obj.get('sha256'),str):found.append((obj['package_relative_current_path'],obj['sha256']))
  for v in obj.values():found.extend(path_hash_records(v))
 elif isinstance(obj,list):
  for v in obj:found.extend(path_hash_records(v))
 return found
def run_checks(check_manifest=True):
 c=[]
 def ck(n,o,d=''):c.append({'name':n,'passed':bool(o),'detail':d})
 ck('correct_FINAL_root',ROOT.name=='FINAL_TIP3P_WATER_300K_273K_PROJECT_PACKAGE_FINAL',ROOT.name)
 readme=(ROOT/'README.md').read_text();ck('root_README_final_status_correct',readme.startswith('# Final TIP3P Water Project\n\nPackage status: FINAL\n') and 'Package version: R3' not in readme,'FINAL identity')
 if check_manifest:
  rows=list(csv.DictReader(MANIFEST.open(newline='',encoding='utf-8'))) if MANIFEST.is_file() else [];listed=[r.get('relative_path','') for r in rows];actual=sorted(p.relative_to(ROOT).as_posix() for p in ROOT.rglob('*') if p.is_file() and p!=MANIFEST)
  ck('internal_manifest_inventory_exact',len(listed)==len(set(listed)) and sorted(listed)==actual,f'rows={len(rows)} files={len(actual)}')
  sizebad=[r['relative_path'] for r in rows if not(ROOT/r['relative_path']).is_file() or (ROOT/r['relative_path']).stat().st_size!=int(r['bytes'])];ck('internal_manifest_sizes_exact',not sizebad,str(sizebad[:3]))
  hashbad=[r['relative_path'] for r in rows if (ROOT/r['relative_path']).is_file() and sha(ROOT/r['relative_path'])!=r['sha256'].upper()];ck('internal_manifest_sha256_exact',not hashbad,str(hashbad[:3]))
 t1=ROOT/'02_EXPERIMENT_2_TEMPERATURE_COMPARISON/01_300K_MATCHED_REFERENCE/validate_packaged_T1_reference.py';deep=ROOT/'02_EXPERIMENT_2_TEMPERATURE_COMPARISON/04_FINAL_DEEP_ANALYSIS';dval=deep/'validate_final_deep_analysis_subset.py'
 tr=subprocess.run([sys.executable,str(t1)],capture_output=True,text=True);dr=subprocess.run([sys.executable,str(dval)],capture_output=True,text=True);ck('T1_local_validator_PASS',tr.returncode==0 and 'PACKAGED_T1_REFERENCE_VALIDATED' in tr.stdout,tr.stdout.strip());ck('deep_local_validator_PASS',dr.returncode==0 and 'FINAL_DEEP_ANALYSIS_SUBSET_VALIDATED' in dr.stdout,dr.stdout.strip())
 sp=json.loads((ROOT/'00_PROJECT_OVERVIEW/SOURCE_PROVENANCE.json').read_text());records=path_hash_records(sp);bad=[p for p,h in records if not(ROOT/p).is_file() or sha(ROOT/p)!=h.upper()];ck('all_provenance_path_hash_records',len(records)==25 and not bad,f'verified={len(records)} bad={bad[:3]}')
 portable=[]
 for x in [q for g in sp['immutable_deep_raw_sources'].values() for q in g]:portable.append(PureWindowsPath(x['original_path_from_provenance']).name==Path(x['package_relative_current_path']).name)
 ck('Windows_POSIX_provenance_portability',len(portable)==9 and all(portable),'9/9 PureWindowsPath resolutions')
 eiv=sp['experiment_1_validation'];ck('experiment1_validation_provenance',eiv['all_required_checks_pass'] is True and (ROOT/eiv['package_relative_path']).is_file() and eiv['frozen_R7R_authority_sha256']=='91463032E3CF1BC5A718EAA767383CBC56CD2752631E9CD63C3865F96BC31186','resolves and accepted')
 reg=json.loads((deep/'METHOD_SNAPSHOT_SHA256.json').read_text());files=sorted(p.name for p in (deep/'method_snapshot').glob('*') if p.is_file());ck('method_registry_exact',sorted(reg['snapshots'])==files and all(sha(deep/'method_snapshot'/n)==h for n,h in reg['snapshots'].items()),f'{len(files)} snapshots')
 fig=list((ROOT/'01_EXPERIMENT_1_ORIGINAL_300K/05_figures').glob('*.png'))+list((deep/'outputs').glob('*.png'));ck('all_23_PNGs_readable',len(fig)==23 and all(png(x) for x in fig),f'{len(fig)} figures')
 db=[];dats=list(ROOT.rglob('*.dat'))
 for p in dats:
  b=Path(str(p).replace('_traj.dat','_traj.box'));n=p.stat().st_size//(2586*3*4)
  if p.stat().st_size%(2586*3*4) or not b.is_file() or len(b.read_text().splitlines())!=n:db.append(str(p.relative_to(ROOT)))
 ck('all_13_trajectory_box_pairs',len(dats)==13 and not db,f'pairs={len(dats)} bad={db[:2]}')
 jb=[];cb=[];pb=[];nb=[];zero=[]
 for p in ROOT.rglob('*.json'):
  try:json.loads(p.read_text())
  except:jb.append(str(p.relative_to(ROOT)))
 for p in ROOT.rglob('*.csv'):
  try:
   with p.open(newline='') as f:list(csv.reader(f))
  except:cb.append(str(p.relative_to(ROOT)))
 for p in ROOT.rglob('*.py'):
  try:
   try:s=p.read_text(encoding='utf-8')
   except UnicodeDecodeError:s=p.read_text(encoding='cp1252')
   compile(s,str(p),'exec')
  except:pb.append(str(p.relative_to(ROOT)))
 for p in ROOT.rglob('*.npz'):
  try:
   with np.load(p) as x:
    if not all(np.isfinite(x[k]).all() for k in x.files):nb.append(str(p.relative_to(ROOT)))
  except:nb.append(str(p.relative_to(ROOT)))
 for p in ROOT.rglob('*'):
  if p.is_file() and p.stat().st_size==0:zero.append(str(p.relative_to(ROOT)))
 for n,b in [('all_JSON_parse',jb),('all_CSV_readable',cb),('all_Python_compile',pb),('all_NPZ_finite',nb),('no_zero_byte_files',zero)]:ck(n,not b,', '.join(b[:3]) or 'pass')
 builder=(ROOT/'04_REPRODUCIBILITY/build_final_tip3p_project_final.py').read_text();ck('builder_verified_ZIP_safe_extract','SRC=WORK/' in builder and 'zipfile.ZipFile(SRC)' in builder and 'ZIP path traversal' in builder and 'if DST.exists():raise RuntimeError' in builder,'verified archive, traversal protection, fail closed')
 forbidden=[p.relative_to(ROOT).as_posix() for p in ROOT.rglob('*') if '__pycache__' in p.as_posix().lower() or p.suffix.lower() in ('.zip','.tmp','.temp','.bak') or p.name.startswith('~$')];ck('no_temporary_or_nested_archive_material',not forbidden,str(forbidden[:3]))
 return {'validator':Path(__file__).name,'read_only_default':True,'manifest_checked':check_manifest,'provenance_path_hash_records_verified':len(records),'checks':c,'passed':sum(x['passed'] for x in c),'total':len(c),'verdict':'FINAL_TIP3P_WATER_300K_273K_PROJECT_PACKAGE_FINAL_VALIDATED' if all(x['passed'] for x in c) else 'FINAL_TIP3P_WATER_300K_273K_PROJECT_PACKAGE_FINAL_REJECTED'}
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--report-out');ap.add_argument('--skip-manifest',action='store_true');a=ap.parse_args();r=run_checks(not a.skip_manifest)
 if a.report_out:Path(a.report_out).write_text(json.dumps(r,indent=2)+'\n')
 print(f"{r['verdict']} ({r['passed']}/{r['total']}) provenance_records={r['provenance_path_hash_records_verified']}");return 0 if r['verdict'].endswith('VALIDATED') else 1
if __name__=='__main__':raise SystemExit(main())
