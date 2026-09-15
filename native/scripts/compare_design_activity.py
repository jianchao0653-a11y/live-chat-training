"""Require all Activity/OCR checkpoints, physical touch rectangles and contracts."""
import argparse
import hashlib
import json
from pathlib import Path

CONFIGS={'portrait','large','narrow','landscape'}
STATES={c+'-'+s for c in CONFIGS for s in ('setup','library','assistant','ocr-top','ocr-bottom')}
TOUCHES={c+'-'+s for c in CONFIGS for s in ('login','new','library-cancel','cancel-field','cancel-include',
    'cancel-button','approve-field','approve-include','approve-button')}
CONTRACTS={c+'-'+a for c in CONFIGS for a in ('cancel','approve')}


def compare(before,after):
    errors=[]
    for label,r in [('before',before),('after',after)]:
        if r.get('status')!='PASS' or r.get('cleanupErrors')!=[] or r.get('displayRestored') is not True:
            errors.append(label+': status or cleanup incomplete')
        for key,value in {'synthetic':True,'realPhone':False,'realModel':False,'realTouches':True,'protectedScreensCaptured':False}.items():
            if r.get(key) is not value:errors.append(label+': invalid scope '+key)
        if r.get('checks')!={c:'PASS' for c in CONFIGS}:errors.append(label+': incomplete configurations')
        if set(r.get('geometry',{}))!=STATES or any(not v for v in r.get('geometry',{}).values()):errors.append(label+': incomplete geometry')
        if set(r.get('touchRegions',{}))!=TOUCHES:errors.append(label+': incomplete touch rectangles')
        if r.get('ocrContracts')!={c:'PASS' for c in CONTRACTS}:errors.append(label+': incomplete OCR contract results')
    for key in ('serial','avd','api','configurations','comparisonRule','testApk'):
        if key not in before or before.get(key)!=after.get(key):errors.append('Different setup: '+key)
    for key in sorted(STATES):
        if before.get('geometry',{}).get(key)!=after.get('geometry',{}).get(key):errors.append('Geometry/state differs: '+key)
    for key in sorted(TOUCHES):
        if before.get('touchRegions',{}).get(key)!=after.get('touchRegions',{}).get(key):errors.append('Touchable rectangle differs: '+key)
    return {'status':'FAIL' if errors else 'PASS','failures':errors,'geometryCheckpoints':len(STATES),
        'touchRegionCheckpoints':len(TOUCHES),'tolerancePixels':0,'visualReviewAccepted':False,
        'beforeApkSha256':before.get('apkSha256'),'afterApkSha256':after.get('apkSha256'),
        'scope':'Representative Setup/Library/Assistant/OCR states and real ADB editing/selection/cancel/approve. Not all subpages, human legibility or OEM.'}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for arg in ('before','after','report'):p.add_argument('--'+arg,type=Path,required=True)
    args=p.parse_args()
    assert not args.report.exists(),'Preserve existing comparison'
    result=compare(json.loads(args.before.read_text(encoding='utf-8')),json.loads(args.after.read_text(encoding='utf-8')))
    result['receipts']={name:{'path':path.as_posix(),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
                       for name,path in [('before',args.before),('after',args.after)]}
    args.report.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2));raise SystemExit(result['status']!='PASS')


if __name__=='__main__':main()
