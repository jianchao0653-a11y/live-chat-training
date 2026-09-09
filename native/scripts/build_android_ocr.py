"""Standard Android packaging for bundled OCR; reuse the pinned native build."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
from build_android import ROOT, SDK, BUILD, APP, VENDOR, OUT, build, notices
from urllib.parse import urlparse

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--abis',nargs='+',choices=['arm64-v8a','x86_64'],default=['arm64-v8a','x86_64'])
    parser.add_argument('--cloud-url',default='')
    parser.add_argument('--release',action='store_true')
    parser.add_argument('--with-tests',action='store_true')
    parser.add_argument('--update-dependency-locks',action='store_true')
    args=parser.parse_args()
    endpoint=urlparse(args.cloud_url)
    debug_local=not args.release and args.cloud_url in ('http://127.0.0.1:4317','http://127.0.0.1:4318')
    if args.cloud_url and not debug_local and (endpoint.scheme!='https' or not endpoint.hostname or endpoint.username or endpoint.password or endpoint.query or endpoint.fragment or endpoint.path not in ('','/')):
        raise RuntimeError('Cloud endpoint must be an HTTPS root without credentials')
    if args.release and not args.cloud_url: raise RuntimeError('Release requires HTTPS endpoint')
    build(args.abis,native_only=True)
    if not (ROOT/'runtime/gradle-tools/gradle-8.13').exists():
        subprocess.run([__import__('sys').executable,str(ROOT/'native/scripts/prepare_gradle.py')],check=True)
    key=ROOT/'runtime/android-tools/lens-local-debug.keystore'
    if not args.release and not key.exists():
        subprocess.run([shutil.which('keytool'),'-genkeypair','-keystore',str(key),'-storepass','android','-keypass','android','-alias','androiddebugkey','-keyalg','RSA','-keysize','2048','-validity','3650','-dname','CN=Conversation Lens Local Debug,O=Local Test,C=CN'],check=True)
    stage=ROOT/'runtime/android-package'
    assets=stage/'assets'
    shutil.copytree(APP/'assets',assets,dirs_exist_ok=True)
    shutil.copy2(VENDOR/'rime-pinyin-simp/pinyin_simp.dict.yaml',assets/'rime')
    (assets/'THIRD_PARTY_NOTICES.txt').write_text(notices()+'\nBundled OCR: Google ML Kit, https://developers.google.com/ml-kit/terms\n',encoding='utf-8')
    shutil.copy2(SDK/'ndk/28.2.13676358/NOTICE.toolchain',assets/'NDK-NOTICES.txt')
    config=assets/'cloud-config.json'
    if args.cloud_url: config.write_text(json.dumps({'endpoint':args.cloud_url.rstrip('/')}),encoding='utf-8')
    elif config.exists(): config.unlink()
    # Recreate this bounded generated directory so a previous ABI cannot leak into a new build.
    jni=stage/'jni'
    if jni.exists():
        if not jni.resolve().is_relative_to((ROOT/'runtime').resolve()): raise RuntimeError('Unsafe staging directory')
        shutil.rmtree(jni)
    for abi in args.abis:
        dest=jni/abi;dest.mkdir(parents=True)
        shutil.copy2(BUILD/abi/'liblens_rime.so',dest)
        triple={'arm64-v8a':'aarch64-linux-android','x86_64':'x86_64-linux-android'}[abi]
        from build_android import NDK_HOST
        shutil.copy2(SDK/f'ndk/28.2.13676358/toolchains/llvm/prebuilt/{NDK_HOST}/sysroot/usr/lib/{triple}/libc++_shared.so',dest)
    manifest=(APP/'AndroidManifest.xml').read_text(encoding='utf-8')
    manifest=manifest.replace('package="com.conversationlens.ime"','').replace('android:debuggable="true"','').replace('android:extractNativeLibs="true"','')
    (stage/'AndroidManifest.xml').write_text(manifest,encoding='utf-8')
    gradle=ROOT/('runtime/gradle-tools/gradle-8.13/bin/gradle.bat' if os.name=='nt' else 'runtime/gradle-tools/gradle-8.13/bin/gradle')
    if not gradle.exists(): raise RuntimeError('Run prepare_gradle.py first')
    # Gradle 8.13 compares lock paths lexically (gradle/gradle#38153).
    # Unlike Ninja, Gradle accepts Unicode paths; pass canonical paths, never the junction.
    env={**os.environ,'ANDROID_HOME':str(SDK.resolve()),'ANDROID_SDK_ROOT':str(SDK.resolve()),'GRADLE_USER_HOME':str((ROOT/'runtime/gradle-home').resolve())}
    task='assembleRelease' if args.release else 'assembleDebug'
    tasks=[task]+(['assembleDebugAndroidTest'] if args.with_tests else [])
    locking=['--write-locks','--write-verification-metadata','sha256'] if args.update_dependency_locks or not (APP/'gradle.lockfile').exists() else []
    subprocess.run([str(gradle.resolve()),'-p',str(APP.resolve()),'--project-cache-dir',str((ROOT/'runtime/gradle-project-cache').resolve()),*tasks,*locking,'--console=plain'],env=env,check=True)
    variant='release' if args.release else 'debug'
    files=list((ROOT/f'runtime/android-gradle-build/outputs/apk/{variant}').glob('*.apk'))
    if len(files)!=1: raise RuntimeError('Expected exactly one APK')
    destination=OUT/('conversation-lens-0.17.3-cloud-unsigned.apk' if args.release else 'conversation-lens-0.17.3-'+('cloud-' if args.cloud_url else '')+'debug.apk')
    shutil.copy2(files[0],destination)
    receipt={'apk':destination.name,'sha256':hashlib.file_digest(destination.open('rb'),'sha256').hexdigest(),'cloudEndpoint':args.cloud_url,'abis':args.abis,'releaseSigned':False}
    (OUT/('prepared-release.json' if args.release else 'ocr-debug-receipt.json')).write_text(json.dumps(receipt,indent=2),encoding='utf-8')
    print('Prepared '+str(destination)+(' (unsigned; do not install)' if args.release else ''))

if __name__=='__main__': main()
