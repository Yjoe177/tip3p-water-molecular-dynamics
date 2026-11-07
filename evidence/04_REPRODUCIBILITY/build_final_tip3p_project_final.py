"""Build FINAL only from safely extracted, hash-verified R3RF ZIP bytes."""
from __future__ import annotations
import hashlib,shutil,zipfile
from pathlib import Path
SELF=Path(__file__).resolve();WORK=SELF.parents[2] if SELF.parent.name=='04_REPRODUCIBILITY' else SELF.parent
SRC=WORK/'FINAL_TIP3P_WATER_300K_273K_PROJECT_PACKAGE_R3RF.zip';DST=WORK/'FINAL_TIP3P_WATER_300K_273K_PROJECT_PACKAGE_FINAL';EXPECTED='7DF736B32E228812849A062A1A696D9F68A9F30EADA320B56E35229668579F39';PREFIX='FINAL_TIP3P_WATER_300K_273K_PROJECT_PACKAGE_R3RF/'
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest().upper()
def write(p,s):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(s,encoding='utf-8')
def main():
 if DST.exists():raise RuntimeError(f'Refusing to overwrite existing destination: {DST}')
 if not SRC.is_file() or sha(SRC)!=EXPECTED:raise RuntimeError('R3RF source ZIP missing or SHA-256 mismatch')
 with zipfile.ZipFile(SRC) as z:
  for i in z.infolist():
   if i.is_dir():continue
   if not i.filename.startswith(PREFIX):raise RuntimeError(f'Unexpected ZIP root: {i.filename}')
   rel=Path(i.filename[len(PREFIX):])
   if not rel.parts or rel.is_absolute() or any(x in ('','..') for x in rel.parts):raise RuntimeError(f'Unsafe ZIP member: {i.filename}')
   out=DST/rel
   if DST.resolve() not in out.resolve().parents:raise RuntimeError(f'ZIP path traversal: {i.filename}')
   out.parent.mkdir(parents=True,exist_ok=True);out.write_bytes(z.read(i))
 for p in [DST/'FINAL_PACKAGE_MANIFEST_SHA256.csv',DST/'FINAL_PACKAGE_VALIDATION.json',DST/'04_REPRODUCIBILITY/build_final_tip3p_project_r3rf.py',DST/'04_REPRODUCIBILITY/validate_final_tip3p_water_project_package_r3rf.py',DST/'04_REPRODUCIBILITY/package_final_tip3p_water_project_r3rf.py']:p.unlink(missing_ok=True)
 write(DST/'README.md',(DST/'README.md').read_text(encoding='utf-8').replace('Package version: R3R','Package status: FINAL'))
 status=DST/'04_REPRODUCIBILITY/SCRIPT_STATUS.md';s=status.read_text(encoding='utf-8').replace('validate_final_tip3p_water_project_package_r3rf.py`: global read-only package validator.','validate_final_tip3p_water_project_package_final.py`: global standalone validator; no-argument operation is strictly read-only.').replace('package_final_tip3p_water_project_r3rf.py`','package_final_tip3p_water_project_final.py`');write(status,s)
 write(DST/'04_REPRODUCIBILITY/R3RF_TO_FINAL_CHANGE_REPORT.md','''# R3RF to FINAL change report\n\nThe exact changed/added/removed inventory is finalized after comparison. Permitted changes are limited to README final identity, deep/global validators, SCRIPT_STATUS, FINAL builder/packager, manifests/validation metadata, and this report. No scientific or evidence byte may change.\n''')
 shutil.copy2(SELF,DST/'04_REPRODUCIBILITY/build_final_tip3p_project_final.py');print('FINAL tree extracted only from verified R3RF ZIP')
if __name__=='__main__':main()
