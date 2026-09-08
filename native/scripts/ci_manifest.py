"""Allowlisted source bundle; excludes input texts, databases, backups, outputs and credentials."""
from pathlib import Path
import json
import re
import sys
root=Path(__file__).resolve().parents[2]
allowed={'.mjs','.js','.html','.css','.svg','.webmanifest','.json','.java','.cpp','.h','.xml','.yaml','.yml','.py','.swift','.plist','.entitlements','.md','.txt','.ps1'}
paths=[]
for folder in ['app','native','.github']:
    for path in (root/folder).rglob('*'):
        if path.is_file() and path.suffix in allowed and '__pycache__' not in path.parts and not any(x in path.parts for x in ['.xcodeproj','DerivedData']):paths.append(path)
paths += [root/'package.json',root/'.gitignore']
paths += [root/'03_decisions/MADR-032-035.md']
paths += [root/'03_decisions/MADR-036.md',root/'02_product/MOBILE_UI_SYSTEM.md',root/'07_reviews/V0_15_UI_ACCEPTANCE.md']
paths += [root/'03_decisions/MADR-037.md',root/'07_reviews/V0_15_SECURITY_REVIEW.md']
paths += [root/'01_inputs/REFERENCE_REUSE_V014.md',root/'07_reviews/V0_14_ACCEPTANCE.md']
entries=[]
for p in sorted(set(paths)):
    if p.resolve().is_relative_to(root.resolve()) is False or p.is_symlink():raise RuntimeError('Source escaped workspace')
    content=p.read_text(encoding='utf-8');relative=p.relative_to(root).as_posix()
    if re.search(r'sk-(?:proj-)?[A-Za-z0-9_-]{30,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',content):raise RuntimeError('Potential credential in '+relative)
    entries.append({'path':relative,'mode':'100644','type':'blob','content':content})
if '--json' in sys.argv:print(json.dumps(entries,ensure_ascii=True))
else:print(json.dumps({'files':len(entries),'bytes':sum(len(e['content'].encode()) for e in entries),'paths':[e['path'] for e in entries]},indent=2))
