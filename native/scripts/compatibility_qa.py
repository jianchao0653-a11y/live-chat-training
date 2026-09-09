"""Repeatable synthetic OS/configuration checks on emulator-5556 only.

Start the selected project AVD first. Does not download images, switch devices,
read real accounts, or call a paid provider. OEM touch/layout acceptance is separate.
"""
import argparse, hashlib, json, os, re, subprocess, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ADB = ROOT/'runtime/android-tools/sdk/platform-tools/adb.exe'
COMPONENT = 'com.conversationlens.ime.test/com.conversationlens.ime.OcrTestRunner'

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--api',required=True,type=int,choices=[26,34,36])
    args=parser.parse_args()
    def adb(*words):
        return subprocess.check_output([str(ADB),'-s','emulator-5556',*words],text=True,encoding='utf-8',errors='replace',timeout=240)
    if adb('shell','getprop','ro.kernel.qemu').strip()!='1':raise RuntimeError('Emulator required')
    if adb('shell','getprop','ro.build.version.sdk').strip()!=str(args.api):raise RuntimeError('Wrong API; refusing mislabeled evidence')
    name=adb('emu','avd','name').splitlines()[0].strip()
    if name!=('LensPreview' if args.api==36 else f'LensPreviewApi{args.api}'):raise RuntimeError('Project AVD required')
    folder=ROOT/'output/compatibility'/f'api{args.api}-{time.strftime("%Y%m%d-%H%M%S")}'
    folder.mkdir(parents=True)
    apk=ROOT/'output/native/conversation-lens-0.17.3-cloud-debug.apk'
    report={'api':args.api,'avd':name,'apkSha256':hashlib.file_digest(apk.open('rb'),'sha256').hexdigest(),'status':'RUNNING','checks':[],'realPhone':False,'oemAccepted':False}
    def save(): (folder/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    save()
    size=adb('shell','wm','size');density=adb('shell','wm','density');font=adb('shell','settings','get','system','font_scale').strip()
    def restore(kind,value):
        match=re.search(r'Override (?:size|density):\s*(\S+)',value)
        adb('shell','wm',kind,match.group(1) if match else 'reset')
    try:
        for filename in ['output/native/lens-synthetic-qa.apk','output/native/conversation-lens-0.17.3-cloud-debug.apk','runtime/android-gradle-build/outputs/apk/androidTest/debug/LensAndroid-debug-androidTest.apk']:
            result=adb('install','--no-incremental','-r','-t',str(ROOT/filename))
            if 'Success' not in result:raise RuntimeError('Install failed')
        for label,dimensions,dpi,scale in [('phone','720x1280','320','1.0'),('large-font','1080x2400','480','1.3'),('wide','1280x720','320','1.0')]:
            adb('shell','wm','size',dimensions);adb('shell','wm','density',dpi);adb('shell','settings','put','system','font_scale',scale)
            result=adb('shell','am','instrument','-w','-e','review','true',COMPONENT)
            (folder/(label+'-review.log')).write_text(result,encoding='utf-8')
            passed='review_ui=PASS' in result
            report['checks'].append({'name':label+'-review-contract','size':dimensions,'density':dpi,'fontScale':scale,'passed':passed});save()
            if not passed:raise RuntimeError('Review contract failed')
        adb('shell','wm','size','720x1280');adb('shell','wm','density','320');adb('shell','settings','put','system','font_scale','1.0')
        with (folder/'cloud-ui.log').open('w',encoding='utf-8') as log:
            result=subprocess.run([sys.executable,str(ROOT/'native/scripts/ci_cloud.py')],cwd=ROOT,env={**os.environ,'LENS_QA_SERIAL':'emulator-5556','PYTHONIOENCODING':'utf-8'},stdout=log,stderr=subprocess.STDOUT,timeout=600)
        report['checks'].append({'name':'synthetic-cloud-ui','passed':result.returncode==0});save()
        if result.returncode:raise RuntimeError('Cloud UI failed; inspect bounded log')
        report['status']='PASS'
    except Exception as error:
        report['status']='FAIL';report['failureType']=type(error).__name__;raise
    finally:
        try:
            restore('size',size);restore('density',density)
            if font=='null':adb('shell','settings','delete','system','font_scale')
            else:adb('shell','settings','put','system','font_scale',font)
        finally:save();print(folder.relative_to(ROOT)/'report.json',flush=True)

if __name__=='__main__':main()
