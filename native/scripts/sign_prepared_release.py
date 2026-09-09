"""Sign a hash-checked prepared APK using the existing production key only.

Run HTTPS acceptance separately before this stage when network and DPAPI require
different Windows execution identities. No passwords are written to disk/output.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'output/native'
if len(sys.argv)!=2: raise SystemExit('Usage: sign_prepared_release.py https://DEPLOYED-DOMAIN')
receipt=json.loads((OUT/'prepared-release.json').read_text(encoding='utf-8'))
if receipt['cloudEndpoint'].rstrip('/')!=sys.argv[1].rstrip('/') or not sys.argv[1].startswith('https://'):
    raise SystemExit('Prepared endpoint mismatch')
if receipt['apk']!='conversation-lens-0.17.0-cloud-unsigned.apk': raise SystemExit('Unexpected prepared artifact')
source=OUT/receipt['apk']
if hashlib.file_digest(source.open('rb'),'sha256').hexdigest()!=receipt['sha256']:raise SystemExit('Prepared APK hash mismatch')
directory=ROOT/'runtime/release-signing'
key=directory/'lens-production.jks'
if not key.is_file():raise SystemExit('Existing production key is required; never regenerate for an upgrade')
environment=dict(os.environ)
if not environment.get('LENS_RELEASE_STORE_PASSWORD'):
    environment['LENS_SIGNING_DPAPI_FILE']=str(directory/'password.dpapi')
    unlock=subprocess.run(['powershell.exe','-NoProfile','-Command',
        '$ErrorActionPreference="Stop"; $lensSecure=Get-Content -LiteralPath $env:LENS_SIGNING_DPAPI_FILE -Raw | ConvertTo-SecureString; $lensCredential=New-Object System.Net.NetworkCredential("",$lensSecure); [Console]::Write($lensCredential.Password)'],env=environment,capture_output=True)
    if unlock.returncode or not unlock.stdout:raise SystemExit('DPAPI unlock failed; use the original Windows signing identity')
    environment['LENS_RELEASE_STORE_PASSWORD']=unlock.stdout.decode().strip()
    environment['LENS_RELEASE_KEY_PASSWORD']=environment['LENS_RELEASE_STORE_PASSWORD']
sdk=ROOT/'runtime/android-tools/sdk'
bt=sdk/'build-tools/36.0.0'
target=OUT/'conversation-lens-0.17.0-cloud-release.apk'
signer=[shutil.which('java'),'-jar',str(bt/'lib/apksigner.jar')]
subprocess.run(signer+['sign','--ks',str(key),'--ks-key-alias','lensproduction','--ks-pass','env:LENS_RELEASE_STORE_PASSWORD','--key-pass','env:LENS_RELEASE_KEY_PASSWORD','--out',str(target),str(source)],env=environment,check=True)
verification=subprocess.check_output(signer+['verify','--verbose','--print-certs',str(target)],text=True)
match=re.search(r'certificate SHA-256 digest: ([a-fA-F0-9]+)',verification)
expected='0ce1d2c5fd366f7b441296fa483a2af20be18f5b5dd1f10c791f6b4eb4cd692e'
if not match or match.group(1).lower()!=expected:raise SystemExit('Signing certificate differs from the installed pilot')
subprocess.run([str(bt/'zipalign.exe'),'-c','-P','16','4',str(target)],check=True)
receipt.update(apk=target.name,sha256=hashlib.file_digest(target.open('rb'),'sha256').hexdigest(),certificateSHA256=expected,releaseSigned=True,version='0.17.0',versionCode=18,qualityAccepted=False,productionReady=False)
(OUT/'release-receipt.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
print(json.dumps(receipt))
