"""Install pinned Android build tools locally; no global PATH/settings changes."""
import concurrent.futures
import hashlib
import json
from pathlib import Path
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / 'runtime' / 'android-tools'
PACKAGES = [
    ('platform-36_r02.zip', '2c1a80dd4d9f7d0e6dd336ec603d9b5c55a6f576', 'sdk/platforms/android-36', True),
    ('build-tools_r36_windows.zip', 'f16ccffd34de8790dede813a6c7d8e2c11a27b50', 'sdk/build-tools/36.0.0', True),
    ('platform-tools_r37.0.1-win.zip', 'e03e78b1d80b396f1c3358e31251cb31740e1110', 'sdk/platform-tools', True),
    ('android-ndk-r28c-windows.zip', '086bba43ff2f5eb0e387b15c8278bb4e0d89ba1d', 'sdk/ndk/28.2.13676358', True),
    ('cmake-3.22.1-windows.zip', '292778f32a7d5183e1c49c7897b870653f2d2c1b', 'sdk/cmake/3.22.1', False),
]

def install(spec):
    name, expected, folder, strip, *custom_url = spec
    TOOLS.mkdir(parents=True, exist_ok=True)
    archive = TOOLS / name
    url = custom_url[0] if custom_url else 'https://dl.google.com/android/repository/' + name
    if not archive.exists():
        print('Download ' + name, flush=True)
        temporary = archive.with_suffix('.part')
        with urllib.request.urlopen(url, timeout=60) as response, temporary.open('wb') as out:
            while chunk := response.read(1024 * 1024):
                out.write(chunk)
        temporary.replace(archive)
    sha1 = hashlib.file_digest(archive.open('rb'), 'sha1').hexdigest()
    if sha1 != expected:
        raise RuntimeError('Official repository checksum mismatch: ' + name)
    destination = TOOLS / folder
    marker = destination / '.lens-installed'
    if not marker.exists():
        destination.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(archive) as z:
            for member in z.infolist():
                parts = Path(member.filename).parts[1 if strip else 0:]
                if not parts:
                    continue
                target = destination.joinpath(*parts).resolve()
                if not target.is_relative_to(destination.resolve()):
                    raise RuntimeError('Unsafe archive path')
                if member.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with z.open(member) as src, target.open('wb') as out:
                        import shutil
                        shutil.copyfileobj(src, out)
        marker.write_text(expected)
    print('Verified ' + name, flush=True)
    return {'url': url, 'sha1': sha1, 'sha256': hashlib.file_digest(archive.open('rb'), 'sha256').hexdigest(), 'path': folder}

if __name__ == '__main__':
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        receipts = list(pool.map(install, PACKAGES))
    (TOOLS / 'receipts.json').write_text(json.dumps(receipts, indent=2), encoding='utf-8')
