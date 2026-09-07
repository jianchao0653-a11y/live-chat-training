"""CI and local emulator acceptance. Own service process; synthetic memory only."""
import subprocess
import os
from assistant_qa import *

def main():
    adb('shell','wm','size','720x1280');adb('shell','wm','density','320')
    adb('install','--no-incremental','-r','-t',OUT/'lens-synthetic-qa.apk')
    install();workflow();cross_app()
    previous=(OUT/'fixture.json').stat().st_mtime if (OUT/'fixture.json').exists() else 0
    log=(OUT/'fixture.log').open('w')
    service=subprocess.Popen(['node','--disable-warning=ExperimentalWarning','native/scripts/native_fixture.mjs'],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
    try:
        for _ in range(50):
            if service.poll() is not None:raise RuntimeError('Synthetic server exited')
            if (OUT/'fixture.json').exists() and (OUT/'fixture.json').stat().st_mtime>previous:break
            time.sleep(.1)
        tap_text('建议');time.sleep(.5);pair();analyze();insert()
        (OUT/'ci-native-receipt.json').write_text(json.dumps({'synthetic':True,'abi':adb('shell','getprop','ro.product.cpu.abi'),'api':adb('shell','getprop','ro.build.version.sdk'),'checks':['keyboard_18','cross_app_chinese','pair','analyze_edit_return','confirmed_insert'],'realPhone':False,'cloudModel':False},indent=2))
    finally:
        try:adb('reverse','--remove','tcp:4317')
        except RuntimeError:pass
        finally:service.terminate();service.wait(timeout=10);log.close()

if __name__=='__main__': main()
