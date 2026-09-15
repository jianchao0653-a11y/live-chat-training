"""CI and local emulator acceptance. Own service process; synthetic memory only."""
import subprocess
import os
import argparse
from assistant_qa import *
from keyboard_first_qa import verify_target

def main(keyboard_only=False):
    verify_target()
    adb('shell','wm','size','720x1280');adb('shell','wm','density','320')
    adb('install','--no-incremental','-r','-t',OUT/'lens-synthetic-qa.apk')
    install();workflow();cross_app()
    if keyboard_only:
        # Preserve the ordinary input/password/incognito/system-switch and
        # cross-app checks without counting the obsolete helper navigation.
        ordinary=json.loads((OUT/'android-qa-receipt.json').read_text(encoding='utf-8'))
        cross=json.loads((OUT/'android-cross-app-receipt.json').read_text(encoding='utf-8'))
        (OUT/'ci-native-receipt.json').write_text(json.dumps({'sourceCommit':os.environ.get('GITHUB_SHA'),
            'apkSha256':hashlib.file_digest(APK.open('rb'),'sha256').hexdigest(),'synthetic':True,
            'abi':adb('shell','getprop','ro.product.cpu.abi'),'api':adb('shell','getprop','ro.build.version.sdk'),
            'scope':'ordinary-input-and-settings-host','checks':ordinary['checks'],'crossApp':cross,
            'assistantFlow':'separate keyboard_first_qa.py receipt required','realPhone':False,'cloudModel':False},indent=2),encoding='utf-8')
        return
    previous=(OUT/'fixture.json').stat().st_mtime if (OUT/'fixture.json').exists() else 0
    log=(OUT/'fixture.log').open('w')
    service=subprocess.Popen(['node','--disable-warning=ExperimentalWarning','native/scripts/native_fixture.mjs'],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
    try:
        for _ in range(50):
            if service.poll() is not None:raise RuntimeError('Synthetic server exited')
            if (OUT/'fixture.json').exists() and (OUT/'fixture.json').stat().st_mtime>previous:break
            time.sleep(.1)
        tap_text('建议');time.sleep(.5);pair();analyze();insert()
        (OUT/'ci-native-receipt.json').write_text(json.dumps({'sourceCommit':os.environ.get('GITHUB_SHA'),'apkSha256':hashlib.file_digest(APK.open('rb'),'sha256').hexdigest(),'synthetic':True,'abi':adb('shell','getprop','ro.product.cpu.abi'),'api':adb('shell','getprop','ro.build.version.sdk'),'checks':['keyboard_18','cross_app_chinese','pair','analyze_edit_return','confirmed_insert'],'realPhone':False,'cloudModel':False},indent=2))
    finally:
        try:adb('reverse','--remove','tcp:4317')
        except RuntimeError:pass
        finally:service.terminate();service.wait(timeout=10);log.close()

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--keyboard-only',action='store_true',help='Run current ordinary-input and cross-app checks; omit legacy AssistantActivity pairing')
    main(parser.parse_args().keyboard_only)
