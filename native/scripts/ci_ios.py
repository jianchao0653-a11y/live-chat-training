"""Build app + keyboard and run core tests on the runner's installed iOS Simulator."""
import json
import subprocess
from pathlib import Path
root=Path(__file__).resolve().parents[2]
out=root/'output/ios';out.mkdir(parents=True,exist_ok=True)
def run(args):return subprocess.check_output(args,text=True).strip()
devices=json.loads(run(['xcrun','simctl','list','devices','available','--json']))['devices']
candidates=[(runtime,d) for runtime,items in devices.items() if '.iOS-' in runtime for d in items if d['name'].startswith('iPhone') and d.get('isAvailable')]
if not candidates:raise RuntimeError('No installed iOS iPhone simulator')
runtime,device=candidates[-1];udid=device['udid']
receipt={'runtime':runtime,'device':device['name'],'xcode':run(['xcodebuild','-version']),'physicalDevice':False,'appChatPlatforms':False,'status':'RUNNING'}
try:
    if device['state']!='Booted':run(['xcrun','simctl','boot',udid])
    run(['xcrun','simctl','bootstatus',udid,'-b'])
    subprocess.run(['xcodebuild','-project',str(root/'native/ios/ConversationLens.xcodeproj'),'-scheme','ConversationLens','-destination','platform=iOS Simulator,id='+udid,'-derivedDataPath',str(out/'DerivedData'),'-resultBundlePath',str(out/'Tests.xcresult'),'CODE_SIGNING_ALLOWED=NO','test'],check=True)
    apps=list((out/'DerivedData/Build/Products/Debug-iphonesimulator').glob('ConversationLens.app'))
    if not apps:raise RuntimeError('App product missing')
    run(['xcrun','simctl','install',udid,str(apps[0])]);run(['xcrun','simctl','launch',udid,'com.conversationlens.app'])
    run(['xcrun','simctl','io',udid,'screenshot',str(out/'launch.png')]);receipt['status']='PASS_BUILD_CORE_TESTS_LAUNCH'
finally:
    (out/'receipt.json').write_text(json.dumps(receipt,indent=2))
    subprocess.run(['xcrun','simctl','shutdown',udid],check=False)
