"""Encrypted stopped-service account backup; key is sealed with current-user DPAPI."""
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[2]
directory=ROOT/'runtime/pc-backup-private'
directory.mkdir(parents=True,exist_ok=True)
protected=directory/'key.dpapi'
env={**os.environ,'LENS_BACKUP_DPAPI':str(protected)}
if not protected.exists():
    env['LENS_NEW_BACKUP_KEY']=secrets.token_hex(32)
    script='$ErrorActionPreference="Stop"; $lensValue=ConvertTo-SecureString $env:LENS_NEW_BACKUP_KEY -AsPlainText -Force; $lensValue | ConvertFrom-SecureString | Set-Content -LiteralPath $env:LENS_BACKUP_DPAPI -Encoding ASCII'
    r=subprocess.run(['powershell.exe','-NoProfile','-Command',script],env=env,capture_output=True)
    env.pop('LENS_NEW_BACKUP_KEY',None)
    if r.returncode:raise SystemExit('Could not seal backup key')
script='$ErrorActionPreference="Stop"; $lensValue=(Get-Content -LiteralPath $env:LENS_BACKUP_DPAPI -Raw).Trim() | ConvertTo-SecureString; $lensCredential=New-Object System.Net.NetworkCredential("",$lensValue); [Console]::Write($lensCredential.Password)'
r=subprocess.run(['powershell.exe','-NoProfile','-Command',script],env=env,capture_output=True)
if r.returncode or len(r.stdout.strip())!=64:raise SystemExit('Backup key requires original Windows identity')
env['LENS_BACKUP_KEY_HEX']=r.stdout.decode().strip()
code="import {backupCloud} from './app/cloud-maintenance.mjs'; const r=await backupCloud('runtime/pc-server/data','runtime/pc-backups',Buffer.from(process.env.LENS_BACKUP_KEY_HEX,'hex')); console.log(JSON.stringify(r));"
r=subprocess.run(['node','--disable-warning=ExperimentalWarning','--input-type=module','-e',code],cwd=ROOT,env=env,capture_output=True)
if r.returncode:raise SystemExit('Encrypted backup failed; confirm the PC service is stopped. No data or key is printed.')
receipt=json.loads(r.stdout)
print(json.dumps(receipt))
