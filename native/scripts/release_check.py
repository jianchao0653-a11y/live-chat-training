"""Read evidence declarations; never treat simulator receipts as release approval."""
from pathlib import Path
import json
root=Path(__file__).resolve().parents[2]
required={'android-stability','ios-build-ui','android-douyin','android-kuaishou','android-wechat','ios-douyin','ios-kuaishou','ios-wechat','gpt-human-calibrated','ocr-human-calibrated','authenticated-tenants','retention-and-backup-deletion','recovery-drill','signed-distribution','pilot-3-users-7-days','pilot-fix-and-next-3'}
report=json.loads((root/'native/release-readiness.json').read_text(encoding='utf-8'))
gates=report['gates'];ids=[g['id'] for g in gates]
if set(ids)!=required or len(ids)!=len(required):raise RuntimeError('Required release gates missing or duplicated')
pending=[g['id'] for g in gates if g['status']!='PASS' or not g['evidence']]
result={'version':report['version'],'status':'NOT_READY' if pending else 'EVIDENCE_REVIEW_REQUIRED','pending':pending,'automaticReleaseApproved':False}
out=root/'output/release';out.mkdir(parents=True,exist_ok=True)
(out/'readiness.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(result));raise SystemExit(2 if pending else 0)
