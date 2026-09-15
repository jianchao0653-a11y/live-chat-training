"""Compare complete before/after receipts without relaxing geometry tolerances."""
import argparse
import hashlib
import json
from pathlib import Path

CONFIGS = {'portrait','large','narrow','landscape'}
STATES = {'keyboard','roster','profile','details','editor'}


def compare(before, after):
    failures=[]
    expected={config+'-'+state for config in CONFIGS for state in STATES}
    regions=expected-{config+'-keyboard' for config in CONFIGS}
    for label,receipt in [('before',before),('after',after)]:
        if (receipt.get('status')!='PASS' or receipt.get('cleanupErrors')!=[]
                or receipt.get('synthetic') is not True or receipt.get('realModel') is not False
                or receipt.get('realPhone') is not False or receipt.get('realTouches') is not True
                or receipt.get('protectedScreensCaptured') is not False):
            failures.append(label+': invalid scope/status/cleanup')
        if receipt.get('checks')!={k:'PASS' for k in CONFIGS}:
            failures.append(label+': missing configuration checks')
        if set(receipt.get('geometry',{}))!=expected or set(receipt.get('touchRegions',{}))!=regions:
            failures.append(label+': missing or unexpected geometry/touch checkpoint')
    for key in ('serial','avd','api','configurations','comparisonRule'):
        if before.get(key)!=after.get(key) or key not in before:
            failures.append('Mismatched setup: '+key)
    for checkpoint in sorted(expected):
        if before.get('geometry',{}).get(checkpoint)!=after.get('geometry',{}).get(checkpoint):
            failures.append('Geometry/state differs: '+checkpoint)
    for checkpoint in sorted(regions):
        if before.get('touchRegions',{}).get(checkpoint)!=after.get('touchRegions',{}).get(checkpoint):
            failures.append('Touchable rectangle differs: '+checkpoint)
    return {'status':'FAIL' if failures else 'PASS','failures':failures,
            'geometryCheckpoints':len(expected),'touchRegionCheckpoints':len(regions),
            'beforeApkSha256':before.get('apkSha256'),'afterApkSha256':after.get('apkSha256'),
            'tolerancePixels':0, 'visualReviewAccepted':False,
            'scope':'Exact sampled hierarchy/state/bounds and clipped touch rectangles, with real synthetic touches. Not protected pixels, text legibility, all scroll positions, OEM or real-phone acceptance.'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--before',type=Path,required=True)
    parser.add_argument('--after',type=Path,required=True)
    parser.add_argument('--report',type=Path,required=True)
    args=parser.parse_args()
    result=compare(json.loads(args.before.read_text(encoding='utf-8')),
                   json.loads(args.after.read_text(encoding='utf-8')))
    result['receipts']={label:{'path':path.as_posix(),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
                        for label,path in [('before',args.before),('after',args.after)]}
    args.report.parent.mkdir(parents=True,exist_ok=True)
    args.report.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2))
    raise SystemExit(0 if result['status']=='PASS' else 1)


if __name__=='__main__':main()
