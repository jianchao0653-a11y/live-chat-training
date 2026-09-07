"""Start an isolated, hidden AOSP emulator; never changes host virtualization."""
import json
import os
from pathlib import Path
import subprocess
from build_android import ROOT, SDK, OUT

avd_home = ROOT / 'runtime/android-avd'
avd = avd_home / 'LensPreview.avd'
avd.mkdir(parents=True, exist_ok=True)
OUT.mkdir(parents=True, exist_ok=True)
image = SDK / 'system-images/android-36/default/x86_64'
if not (image / 'system.img').exists():
    raise SystemExit('Run prepare_emulator.py first')
(avd_home / 'LensPreview.ini').write_text(f'avd.ini.encoding=UTF-8\npath={avd}\npath.rel=LensPreview.avd\ntarget=android-36\n', encoding='utf-8')
config = {
    'avd.ini.encoding':'UTF-8', 'AvdId':'LensPreview', 'avd.ini.displayname':'Lens Android 16 Synthetic QA',
    'abi.type':'x86_64', 'hw.cpu.arch':'x86_64', 'hw.cpu.ncore':'2', 'hw.ramSize':'2048',
    'hw.lcd.width':'720', 'hw.lcd.height':'1280', 'hw.lcd.density':'320',
    'hw.keyboard':'yes', 'hw.gpu.enabled':'yes', 'hw.gpu.mode':'swiftshader',
    'hw.mainKeys':'no', 'hw.audioInput':'no', 'hw.camera.back':'none', 'hw.camera.front':'none',
    'disk.dataPartition.size':'2G', 'image.sysdir.1':image.as_posix(),
    'tag.id':'default', 'tag.display':'Default Android System Image',
    'PlayStore.enabled':'false', 'showDeviceFrame':'no', 'skin.dynamic':'yes',
}
(avd / 'config.ini').write_text(''.join(f'{k}={v}\n' for k,v in config.items()), encoding='utf-8')
environment = {**os.environ, 'ANDROID_AVD_HOME':str(avd_home), 'ANDROID_HOME':str(SDK), 'ANDROID_SDK_ROOT':str(SDK)}
args = [str(SDK / 'emulator/emulator.exe'), '-avd', 'LensPreview', '-no-window', '-no-audio',
    '-no-snapshot', '-no-boot-anim', '-gpu', 'swiftshader', '-port', '5556']
with (OUT / 'emulator.log').open('wb') as log:
    process = subprocess.Popen(args, env=environment, stdout=log, stderr=subprocess.STDOUT,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
(OUT / 'emulator-process.json').write_text(json.dumps({'pid':process.pid,'serial':'emulator-5556','avd':str(avd)},indent=2),encoding='utf-8')
print('Started hidden synthetic emulator, PID',process.pid)
