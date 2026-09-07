"""Read metadata from an explicitly selected Android device; never claims task success."""
import argparse
import json
import subprocess
from pathlib import Path
from datetime import datetime,timezone
from android_qa import ADB
parser=argparse.ArgumentParser();parser.add_argument('--serial',required=True);parser.add_argument('--output',required=True);args=parser.parse_args()
def adb(*parts):return subprocess.check_output([str(ADB),'-s',args.serial,*parts],text=True,encoding='utf-8').strip()
if adb('get-state')!='device':raise RuntimeError('Device not authorized')
emulator=adb('shell','getprop','ro.kernel.qemu')=='1'
apps={'抖音':'com.ss.android.ugc.aweme','快手':'com.smile.gifmaker','微信/视频号':'com.tencent.mm'}
versions={}
for label,package in apps.items():
    lines=adb('shell','dumpsys','package',package).splitlines()
    versions[label]=next((x.strip().split('=',1)[1] for x in lines if 'versionName=' in x),'NOT_INSTALLED')
checks=['install','chinese_input','consented_capture_or_picker','correct_person','edit_candidate','insert_without_send','manual_send','revoke','offline_recovery','rotation','large_font','screen_lock','delete']
result={'capturedAt':datetime.now(timezone.utc).isoformat(),'serial':args.serial,'emulator':emulator,'manufacturer':adb('shell','getprop','ro.product.manufacturer'),'model':adb('shell','getprop','ro.product.model'),'os':adb('shell','getprop','ro.build.version.release'),'build':adb('shell','getprop','ro.build.fingerprint'),'appVersions':versions,'platformChecks':{p:{c:'NOT_RUN' for c in checks} for p in apps},'physicalAcceptance':'NOT_ACCEPTED','note':'Metadata collection is not a test pass; attach observed results and consenting participant code separately.'}
path=Path(args.output);path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');print('DEVICE_METADATA_RECORDED; task checks remain NOT_RUN')
