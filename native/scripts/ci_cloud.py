"""Own a synthetic cloud fixture for emulator acceptance, no actual provider key."""
import subprocess
from cloud_qa import run
from android_qa import ROOT,OUT,adb,time,json

if __name__=='__main__':
    previous=(OUT/'cloud-fixture.json').stat().st_mtime if (OUT/'cloud-fixture.json').exists() else 0
    with (OUT/'cloud-fixture.log').open('w') as log:
        service=subprocess.Popen(['node','--disable-warning=ExperimentalWarning','native/scripts/cloud_fixture.mjs'],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
        try:
            for _ in range(80):
                if service.poll() is not None:raise RuntimeError('Synthetic cloud fixture exited')
                if (OUT/'cloud-fixture.json').exists() and (OUT/'cloud-fixture.json').stat().st_mtime>previous:break
                time.sleep(.1)
            else:raise RuntimeError('Synthetic fixture not ready')
            run()
        finally:
            try:adb('reverse','--remove','tcp:4317')
            finally:service.terminate();service.wait(timeout=15)
