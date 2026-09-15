"""Publish only an explicit source allowlist; never scan private intake or runtime.

--check validates the current files without copying. --destination must name a
new directory. The receipt binds byte hashes; it does not assert production QA.
"""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shutil

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / 'release/source-files.json'
FORBIDDEN_PARTS = {'runtime', 'output', '01_inputs', '.git', '__pycache__', 'node_modules'}
FORBIDDEN_SUFFIXES = {'.sqlite', '.db', '.dpapi', '.pem', '.key', '.jks', '.keystore', '.apk', '.lensbackup', '.log'}
PATTERNS = {
    'private-key': re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
    'provider-key': re.compile(r'\bsk-[A-Za-z0-9_-]{24,}\b'),
    'github-token': re.compile(r'\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})\b'),
    'aws-key': re.compile(r'\bAKIA[A-Z0-9]{16}\b'),
}

def safe_path(value):
    if not isinstance(value, str) or '\\' in value or ':' in value:
        raise ValueError('Invalid allowlist path')
    path = PurePosixPath(value)
    if path.is_absolute() or '..' in path.parts or not path.parts or any(p in FORBIDDEN_PARTS for p in path.parts):
        raise ValueError('Forbidden allowlist path: ' + value)
    if path.suffix.lower() in FORBIDDEN_SUFFIXES or path.name.startswith('.env'):
        raise ValueError('Forbidden file type: ' + value)
    return path

def inventory(root=ROOT):
    spec = json.loads((root/'release/source-files.json').read_text(encoding='utf-8'))
    if spec.get('format') != 1:
        raise ValueError('Unknown allowlist format')
    files, targets, errors = [], set(), []
    for entry in spec['files']:
        source, target = safe_path(entry['source']), safe_path(entry['path'])
        if str(target).casefold() in targets:
            raise ValueError('Duplicate publication path: ' + str(target))
        targets.add(str(target).casefold())
        file = root / source
        for parent in [file, *file.parents]:
            if parent == root: break
            if parent.is_symlink() or (hasattr(parent,'is_junction') and parent.is_junction()):
                raise ValueError('Link in publication path: ' + str(source))
        if not file.resolve().is_relative_to(root.resolve()) or not file.is_file():
            raise ValueError('Missing/escaped source: ' + str(source))
        data = file.read_bytes()
        text = data.decode('utf-8-sig')
        for rule, pattern in PATTERNS.items():
            if pattern.search(text): errors.append({'path': str(target), 'rule': rule})
        files.append({'source': str(source), 'path': str(target), 'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)})
    if errors:
        # Never print the matching credential text.
        raise ValueError('Potential sensitive source requires review: ' + json.dumps(errors))
    for required in ['README.md', 'LICENSE', 'THIRD_PARTY_NOTICES.md', 'package.json', '.github/workflows/source-ci.yml']:
        if required.casefold() not in targets: raise ValueError('Missing release requirement: ' + required)
    # Every static local JS import must be shipped alongside its consumer.
    for item in files:
        if Path(item['path']).suffix not in {'.mjs', '.js'}: continue
        text = (root/item['source']).read_text(encoding='utf-8')
        for relative in re.findall(r'(?:from\s*|import\s*\(\s*)[\'"](\.[^\'"]+)[\'"]', text):
            resolved = (root/Path(item['path']).parent/relative).resolve()
            if not resolved.is_relative_to(root.resolve()) or resolved.relative_to(root.resolve()).as_posix().casefold() not in targets:
                raise ValueError('Missing local JS import: ' + item['path'] + ' -> ' + relative)
    return files

def main():
    parser=argparse.ArgumentParser();group=parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--check',action='store_true');group.add_argument('--destination',type=Path)
    args=parser.parse_args();files=inventory()
    receipt={'format':1,'version':json.loads((ROOT/'package.json').read_text())['version'],
             'productionReady':False,'secretScan':'bounded-pattern-check-only','historyScanned':False,'files':files}
    if args.destination:
        target=args.destination.resolve()
        if target.exists(): raise ValueError('Publication destination must not exist')
        if not target.is_relative_to((ROOT/'output').resolve()): raise ValueError('Use a new directory under output')
        target.mkdir(parents=True)
        for item in files:
            out=target/item['path'];out.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/item['source'],out)
        (target/'SOURCE-MANIFEST.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'status':'PASS','files':len(files),'version':receipt['version'],'productionReady':False,'historyScanned':False}))

if __name__=='__main__': main()
