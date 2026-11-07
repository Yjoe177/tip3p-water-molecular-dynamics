"""FINAL packaging order: report, manifest, ZIP, independent audit, sidecars."""
from __future__ import annotations
import csv,hashlib,json,subprocess,sys,zipfile
from pathlib import Path
P=Path(__file__).resolve().parents[1];W=P.parent;Z=W/(P.name+'.zip');IM=P/'FINAL_PACKAGE_MANIFEST_SHA256.csv';REPORT=P/'FINAL_PACKAGE_VALIDATION.json';OM=W/'FINAL_TIP3P_WATER_300K_273K_PROJECT_FINAL_MANIFEST_SHA256.csv';OR=W/'FINAL_TIP3P_WATER_300K_273K_PROJECT_FINAL_VALIDATION.json';VAL=P/'04_REPRODUCIBILITY/validate_final_tip3p_water_project_package_final.py'
def h(b):return hashlib.sha256(b).hexdigest().upper()
def entries():return [(x.relative_to(P).as_posix(),h(x.read_bytes()),x.stat().st_size) for x in sorted(P.rglob('*')) if x.is_file() and x!=IM]
def manifest(path,rs):
 with path.open('w',newline='') as f:w=csv.writer(f);w.writerow(['relative_path','sha256','bytes']);w.writerows(rs)
def main():
 # Explicit packaging mode writes the semantic report before the manifest. Default validation remains read-only.
 subprocess.run([sys.executable,str(VAL),'--skip-manifest','--report-out',str(REPORT)],check=True)
 rs=entries();manifest(IM,rs);manifest(OM,rs)
 with zipfile.ZipFile(Z,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
  for x in sorted(P.rglob('*')):
   if x.is_file():z.write(x,P.name+'/'+x.relative_to(P).as_posix())
 expected={n:(q,s) for n,q,s in rs};expected[IM.name]=(h(IM.read_bytes()),IM.stat().st_size)
 with zipfile.ZipFile(Z) as z:
  crc=z.testzip();pre=P.name+'/';actual={n[len(pre):] for n in z.namelist() if n.startswith(pre) and not n.endswith('/')};missing=sorted(set(expected)-actual);extra=sorted(actual-set(expected));bad=[]
  for n,(q,s) in expected.items():
   b=z.read(pre+n)
   if h(b)!=q or len(b)!=s:bad.append(n)
 report={'zip':Z.name,'zip_sha256':h(Z.read_bytes()),'manifest_rows_excluding_self':len(rs),'zip_file_entries':len(expected),'crc_failure':crc,'missing_entries':missing,'extra_entries':extra,'hash_or_size_mismatches':bad,'semantic_report':json.loads(REPORT.read_text()),'verdict':'FINAL_TIP3P_WATER_300K_273K_PROJECT_PACKAGE_FINAL_VALIDATED' if not(crc or missing or extra or bad) else 'FINAL_TIP3P_WATER_300K_273K_PROJECT_PACKAGE_FINAL_REJECTED'}
 OR.write_text(json.dumps(report,indent=2)+'\n');Z.with_name(Z.name+'.sha256').write_text(report['zip_sha256']+'  '+Z.name+'\n');print(f"{report['verdict']} {report['zip_sha256']} entries={len(expected)}")
 if report['verdict'].endswith('REJECTED'):raise RuntimeError(json.dumps(report,indent=2))
if __name__=='__main__':main()
