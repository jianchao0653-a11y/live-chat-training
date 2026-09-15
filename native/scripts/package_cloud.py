"""Build a source-only deploy ZIP from explicit project paths, never credentials/data."""
from pathlib import Path
import hashlib,json,re,zipfile
ROOT=Path(__file__).resolve().parents[2]
files=[ROOT/'package.json']
files+=list((ROOT/'app').glob('*.mjs'))
files+=list((ROOT/'native/deploy').iterdir())
files+=[ROOT/'native/CLOUD_ACCEPTANCE_PACKET.md',ROOT/'03_decisions/MADR-040.md',ROOT/'03_decisions/MADR-041.md',ROOT/'02_product/ANDROID_FIRST_RELEASE_FLOW.md']
entries=[]
for p in sorted(files):
    if not p.is_file() or p.is_symlink() or not p.resolve().is_relative_to(ROOT):raise RuntimeError('Unexpected deploy source')
    data=p.read_bytes()
    if re.search(rb'sk-(?:proj-)?[A-Za-z0-9_-]{30,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',data):raise RuntimeError('Potential secret in deploy source')
    entries.append((p.relative_to(ROOT).as_posix(),data))
out=ROOT/'output/cloud';out.mkdir(parents=True,exist_ok=True)
version=json.loads((ROOT/'package.json').read_text(encoding='utf-8'))['version']
archive=out/f'conversation-lens-{version}-server.zip'
manifest={'version':version,'productionReady':False,'credentialsIncluded':False,'files':[{'path':name,'sha256':hashlib.sha256(data).hexdigest()} for name,data in entries]}
with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED) as z:
    for name,data in entries:z.writestr(name,data)
    z.writestr('DEPLOY-MANIFEST.json',json.dumps(manifest,indent=2))
with zipfile.ZipFile(archive) as z:
    assert z.testzip() is None
    assert all(hashlib.sha256(z.read(e['path'])).hexdigest()==e['sha256'] for e in manifest['files'])
receipt={'archive':archive.name,'sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),'sourceFiles':len(entries),'zipVerified':True,'deployed':False}
(out/'package-receipt.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
print(json.dumps(receipt))
