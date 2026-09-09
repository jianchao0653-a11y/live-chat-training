"""Fetch a pinned official Gradle distribution into project runtime only."""
import hashlib
from pathlib import Path
import urllib.request
import zipfile
import os

ROOT = Path(__file__).resolve().parents[2]
VERSION = '8.13'
SHA256 = '20f1b1176237254a6fc204d8434196fa11a4cfb387567519c61556e8710aed78'
folder = ROOT / 'runtime/gradle-tools'
folder.mkdir(parents=True, exist_ok=True)
archive = folder / ('gradle-' + VERSION + '-bin.zip')
if not archive.exists():
    with urllib.request.urlopen('https://downloads.gradle.org/distributions/' + archive.name, timeout=60) as response, archive.open('wb') as out:
        while chunk := response.read(1024 * 1024):
            out.write(chunk)
if hashlib.file_digest(archive.open('rb'), 'sha256').hexdigest() != SHA256:
    raise RuntimeError('Gradle archive hash mismatch; do not execute')
with zipfile.ZipFile(archive) as z:
    for entry in z.infolist():
        if not (folder / entry.filename).resolve().is_relative_to(folder.resolve()):
            raise RuntimeError('Unsafe archive path')
    z.extractall(folder)
if os.name!='nt': (folder/f'gradle-{VERSION}/bin/gradle').chmod(0o755)
print('Verified Gradle ' + VERSION + ' installed in project runtime')
