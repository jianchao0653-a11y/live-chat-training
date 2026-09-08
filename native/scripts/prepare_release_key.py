"""Create a separate production signing identity; never print passwords or private keys.

Windows passwords are sealed to the current user with DPAPI. This is a local
signing preparation step, not a signed APK or a verified off-machine backup.
"""
from pathlib import Path
import os,secrets,subprocess,json,hashlib,shutil
ROOT=Path(__file__).resolve().parents[2]
directory=ROOT/'runtime/release-signing'
keyfile=directory/'lens-production.jks'
passwordfile=directory/'password.dpapi'

def prepare():
    if os.name!='nt':raise RuntimeError('Provision production signing credentials through the release environment on this platform')
    if keyfile.exists() or passwordfile.exists():raise RuntimeError('Signing material already exists; refusing to overwrite')
    keytool=shutil.which('keytool')
    if not keytool:raise RuntimeError('JDK keytool is required')
    directory.mkdir(parents=True,exist_ok=True)
    password=secrets.token_urlsafe(48)
    env={**os.environ,'LENS_SIGNING_PASSWORD':password}
    sealed=subprocess.check_output(['powershell.exe','-NoProfile','-Command',
        '$lensSecure = ConvertTo-SecureString -String $env:LENS_SIGNING_PASSWORD -AsPlainText -Force; ConvertFrom-SecureString -SecureString $lensSecure'],env=env).decode().strip()
    passwordfile.write_text(sealed,encoding='ascii')
    subprocess.run([keytool,'-genkeypair','-keystore',str(keyfile),'-storetype','PKCS12','-storepass:env','LENS_SIGNING_PASSWORD','-keypass:env','LENS_SIGNING_PASSWORD','-alias','lensproduction','-keyalg','RSA','-keysize','3072','-validity','10000','-dname','CN=Conversation Lens Production,O=Conversation Lens,C=CN'],env=env,check=True,capture_output=True)
    cert=subprocess.check_output([keytool,'-exportcert','-keystore',str(keyfile),'-storepass:env','LENS_SIGNING_PASSWORD','-alias','lensproduction'],env=env)
    receipt={'productionKeyPrepared':True,'certificateSHA256':hashlib.sha256(cert).hexdigest(),'passwordProtection':'Windows DPAPI current user','offMachineBackupVerified':False,'productionApkSigned':False}
    output=ROOT/'output/cloud-v016';output.mkdir(parents=True,exist_ok=True)
    (output/'signing-preparation.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
    print(json.dumps(receipt))

if __name__=='__main__':prepare()
