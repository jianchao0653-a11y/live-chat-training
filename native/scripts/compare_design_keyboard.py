"""Strict before/after comparison for the four main-keyboard touch scenarios."""
import argparse
import hashlib
import json
from pathlib import Path

SCENARIOS=('portrait','landscape','large-font','max-font')
STATES={prefix+name for prefix in ('keyboard-template-','keyboard-touched-') for name in SCENARIOS}
STATES.add('keyboard-template-portrait-full')


def compare(before,after):
    failures=[]
    for label,r in [('before',before),('after',after)]:
        if (r.get('status')!='PASS' or r.get('cleanupErrors')!=[] or r.get('displayRestored') is not True
            or r.get('synthetic') is not True or r.get('realModel') is not False
            or r.get('realPhone') is not False or r.get('protectedScreensCaptured') is not False):
            failures.append(label+': incomplete status/scope/cleanup')
        if r.get('checks')!={k:'PASS' for k in SCENARIOS}:failures.append(label+': incomplete configurations')
        if set(r.get('geometry',{}))!=STATES or any(not r['geometry'][k] for k in r.get('geometry',{})):
            failures.append(label+': missing/empty geometry')
        touches=r.get('realTouches',[])
        if not isinstance(touches,list) or len(touches)!=4 or {t.get('scenario') for t in touches}!=set(SCENARIOS):
            failures.append(label+': missing actual touch scenarios')
        elif any(t.get('realTouches') is not True or t.get('suggestionOpened') is not True for t in touches):
            failures.append(label+': actual touches or suggestion launch not accepted')
    for key in ('serial','avd','api','realTouches'):
        if key not in before or before.get(key)!=after.get(key):failures.append('Setup differs: '+key)
    for key in sorted(STATES):
        if before.get('geometry',{}).get(key)!=after.get('geometry',{}).get(key):
            failures.append('Geometry/state differs: '+key)
    return {'status':'FAIL' if failures else 'PASS','failures':failures,'geometryCheckpoints':len(STATES),
        'tolerancePixels':0,'beforeApkSha256':before.get('apkSha256'),'afterApkSha256':after.get('apkSha256'),
        'visualReviewAccepted':False,'scope':'Sampled complete IME hierarchy/state/bounds with real synthetic key touches; excludes protected pixels, OCR quality, human readability and OEM.'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--before',type=Path,required=True)
    parser.add_argument('--after',type=Path,required=True)
    parser.add_argument('--report',type=Path,required=True)
    args=parser.parse_args()
    result=compare(json.loads(args.before.read_text(encoding='utf-8')),json.loads(args.after.read_text(encoding='utf-8')))
    result['receipts']={label:{'path':p.as_posix(),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
                        for label,p in [('before',args.before),('after',args.after)]}
    if args.report.exists():raise RuntimeError('Preserve previous comparison; choose a new report')
    args.report.parent.mkdir(parents=True,exist_ok=True)
    args.report.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2))
    raise SystemExit(result['status']!='PASS')


if __name__=='__main__':main()
