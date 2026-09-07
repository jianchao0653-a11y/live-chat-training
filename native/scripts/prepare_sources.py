"""Fetch upstream sources by locked commit; preserve originals and license files."""
import concurrent.futures
import hashlib
import json
from pathlib import Path
import tarfile
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
VENDOR = ROOT / 'runtime' / 'native-sources'

def fetch(spec):
    name = spec['repo'].split('/')[-1] if 'repo' in spec else spec['name']
    url = spec.get('url') or f"https://codeload.github.com/{spec['repo']}/tar.gz/{spec['commit']}"
    VENDOR.mkdir(parents=True, exist_ok=True)
    archive = VENDOR / (name + ('.tar.bz2' if url.endswith('.bz2') else '.tar.gz'))
    if not archive.exists():
        print('Download source ' + name, flush=True)
        with urllib.request.urlopen(url, timeout=60) as response, archive.with_suffix('.part').open('wb') as out:
            while chunk := response.read(1024 * 1024):
                out.write(chunk)
        archive.with_suffix('.part').replace(archive)
    digest = hashlib.file_digest(archive.open('rb'), 'sha256').hexdigest()
    if spec.get('sha256') and spec['sha256'] != digest:
        raise RuntimeError('Source checksum mismatch: ' + name)
    destination = VENDOR / name
    if not (destination / '.lens-extracted').exists():
        destination.mkdir(parents=True, exist_ok=True)
        with tarfile.open(archive) as tar:
            for member in tar:
                parts = Path(member.name).parts[1:]
                if not parts:
                    continue
                target = destination.joinpath(*parts).resolve()
                if not target.is_relative_to(destination.resolve()):
                    raise RuntimeError('Unsafe source path')
                if member.isdir():
                    target.mkdir(parents=True, exist_ok=True)
                elif member.isfile():
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with tar.extractfile(member) as src, target.open('wb') as out:
                        import shutil
                        shutil.copyfileobj(src, out)
        (destination / '.lens-extracted').write_text(digest)
    print('Verified source ' + name, flush=True)
    return {**spec, 'url': url, 'sha256': digest}

if __name__ == '__main__':
    lock = ROOT / 'native' / 'dependencies.lock.json'
    specs = json.loads(lock.read_text(encoding='utf-8'))
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        receipts = list(pool.map(fetch, specs))
    lock.write_text(json.dumps(receipts, indent=2) + '\n', encoding='utf-8')
