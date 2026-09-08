"""Build with the locally prepared signing key and an explicitly supplied HTTPS domain."""
from pathlib import Path
import os,sys,subprocess
from urllib.parse import urlparse
ROOT=Path(__file__).resolve().parents[2]
if len(sys.argv)!=2:raise SystemExit('Usage: build_release.py https://DEPLOYED-DOMAIN')
u=urlparse(sys.argv[1])
if u.scheme!='https' or not u.hostname or u.username or u.password or u.query or u.fragment or u.path not in ['','/']:
    raise SystemExit('A deployed HTTPS service root is required')
if os.name!='nt':raise SystemExit('Use build_android.py --release with securely provisioned signing environment on this platform')
from https_acceptance import probe
if not probe(sys.argv[1])['passed']:
    raise SystemExit('HTTPS API acceptance failed; signing key was not opened. Check gateway health and authorization boundaries.')
directory=ROOT/'runtime/release-signing'
environment={**os.environ,'LENS_SIGNING_DPAPI_FILE':str(directory/'password.dpapi')}
password=subprocess.check_output(['powershell.exe','-NoProfile','-Command',
    '$lensSecure = Get-Content -LiteralPath $env:LENS_SIGNING_DPAPI_FILE -Raw | ConvertTo-SecureString; $lensCredential = New-Object System.Net.NetworkCredential("", $lensSecure); [Console]::Write($lensCredential.Password)'],env=environment).decode().strip()
if not password:raise SystemExit('Unable to unlock production signing password')
environment.update({'LENS_RELEASE_KEYSTORE':str(directory/'lens-production.jks'),'LENS_RELEASE_ALIAS':'lensproduction','LENS_RELEASE_STORE_PASSWORD':password,'LENS_RELEASE_KEY_PASSWORD':password})
subprocess.run([sys.executable,str(ROOT/'native/scripts/build_android.py'),'--cloud-url',sys.argv[1],'--release'],env=environment,check=True)
