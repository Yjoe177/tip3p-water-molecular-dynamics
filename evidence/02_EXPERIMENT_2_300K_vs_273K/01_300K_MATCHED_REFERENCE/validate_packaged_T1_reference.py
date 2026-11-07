"""Read-only validation of the packaged T1 reference; never launches SPONGE."""
from __future__ import annotations
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parent
def sha(p):
 h=hashlib.sha256();h.update(p.read_bytes());return h.hexdigest().upper()
def main():
 r=ROOT/'run/tempcomp_300K_reference';checks=[]
 def ck(n,o):checks.append((n,bool(o)))
 ck('100_trajectory_frames',(r/'tempcomp_300K_reference_traj.dat').stat().st_size==100*2586*3*4)
 ck('100_boxes',len((r/'tempcomp_300K_reference_traj.box').read_text().splitlines())==100)
 ck('100_thermo',len([x for x in (r/'tempcomp_300K_reference.mdout').read_text().splitlines()[1:] if x.split()])==100)
 ck('input_start_hashes',sha(ROOT/'input/tempcomp_300K_reference_start_coordinate.txt')=='E6DDAF9DEB248D5076B2AD783843456AB697D8456B1E42B85130D82A57DFAA81' and sha(ROOT/'input/tempcomp_300K_reference_start_velocity.txt')=='E43EA18C0569294A4FD644C80479AAF855D1737DCE8EA6808FDCBF6D2C71277B')
 ck('accepted_validator',json.loads((ROOT/'validation/T1_300K_REFERENCE_POSTRUN_VALIDATION.json').read_text()).get('status')=='T1_300K_REFERENCE_POSTRUN_PASS')
 print('PACKAGED_T1_REFERENCE_VALIDATED' if all(x[1] for x in checks) else 'PACKAGED_T1_REFERENCE_REJECTED',f'({sum(x[1] for x in checks)}/{len(checks)})');return 0 if all(x[1] for x in checks) else 1
if __name__=='__main__':raise SystemExit(main())
