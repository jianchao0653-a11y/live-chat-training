"""Repeatable synthetic OS/configuration checks on emulator-5556 only.

Start the selected project AVD first. Does not download images, switch devices,
read real accounts, or call a paid provider. OEM touch/layout acceptance is separate.
"""
import argparse, json, os, re, subprocess, sys, time
from pathlib import Path
from android_qa import ADB, wait_boot
from keyboard_acceptance import (bind_keyboard_receipt,DEFERRED_LIFECYCLE,SUITES,sha256,
    applicable_keyboard_suites,aggregate_keyboard_receipts)

ROOT = Path(__file__).resolve().parents[2]
COMPONENT = 'com.conversationlens.ime.test/com.conversationlens.ime.OcrTestRunner'

def restore_display(report, adb, original):
    """Attempt every owned display setting; cleanup failure can never retain PASS."""
    commands=[]
    for kind in ('size','density'):
        match=re.search(r'Override (?:size|density):\s*(\S+)',original[kind])
        commands.append((kind,('shell','wm',kind,match.group(1) if match else 'reset')))
    font=original['fontScale']
    commands.append(('fontScale',('shell','settings','delete','system','font_scale') if font=='null'
                     else ('shell','settings','put','system','font_scale',font)))
    errors=[]
    for setting,command in commands:
        try:adb(*command)
        except Exception as error:errors.append({'setting':setting,'errorType':type(error).__name__})
    report['cleanupErrors']=errors
    report['settingsRestorationCommandsSucceeded']=not errors
    if errors:
        report['status']='FAIL'
        report.setdefault('failureType','DisplayCleanupError')
    return errors

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--api',required=True,type=int,choices=[26,34,36])
    args=parser.parse_args()
    def adb(*words):
        return subprocess.check_output([str(ADB),'-s','emulator-5556',*words],text=True,encoding='utf-8',errors='replace',timeout=240)
    # start_emulator.py returns as soon as the process is created. Wait through
    # ADB's expected offline phase before collecting identity or evidence.
    wait_boot()
    if adb('shell','getprop','ro.kernel.qemu').strip()!='1':raise RuntimeError('Emulator required')
    if adb('shell','getprop','ro.build.version.sdk').strip()!=str(args.api):raise RuntimeError('Wrong API; refusing mislabeled evidence')
    name=adb('emu','avd','name').splitlines()[0].strip()
    allowed_names={f'LensPreviewApi{args.api}'}|({'LensPreview'} if args.api==36 else set())
    if name not in allowed_names:raise RuntimeError('Project AVD required')
    folder=ROOT/'output/compatibility'/f'api{args.api}-{time.strftime("%Y%m%d-%H%M%S")}'
    folder.mkdir(parents=True)
    apk=ROOT/'output/native/conversation-lens-0.18.0-cloud-debug.apk'
    report={'api':args.api,'avd':name,'apkSha256':sha256(apk),'status':'RUNNING','checks':[],'realPhone':False,'oemAccepted':False,
            'realModel':False,'qualityAccepted':False,'releaseApkRuntimeAccepted':False,'pendingKeyboardLifecycle':DEFERRED_LIFECYCLE}
    def save(): (folder/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    save()
    original={'size':adb('shell','wm','size'),'density':adb('shell','wm','density'),
              'fontScale':adb('shell','settings','get','system','font_scale').strip()}
    report['originalDisplay']=original;save()
    try:
        adb('shell','wm','size','720x1280');adb('shell','wm','density','320');adb('shell','settings','put','system','font_scale','1.0')
        bindings={}
        for suite in applicable_keyboard_suites(args.api):
            step='keyboard-'+suite+'-ui'
            report['activeCheck']=step;save()
            started_at=time.time()
            with (folder/(step+'.log')).open('w',encoding='utf-8') as log:
                result=subprocess.run([sys.executable,str(ROOT/'native/scripts'/SUITES[suite]['script'])],cwd=ROOT,
                    env={**os.environ,'LENS_QA_SERIAL':'emulator-5556','PYTHONIOENCODING':'utf-8'},stdout=log,stderr=subprocess.STDOUT,timeout=900)
            report['checks'].append({'name':step,'passed':result.returncode==0,'size':'720x1280','density':320,'fontScale':1.0});save()
            if result.returncode:raise RuntimeError(step+' failed; inspect bounded log')
            bindings[suite]=bind_keyboard_receipt(folder/(step+'.log'),apk,started_at,args.api,name,suite=suite)
            report['keyboardSuiteEvidence']=bindings;report['activeCheck']=None;save()
        report['keyboardAcceptance']=aggregate_keyboard_receipts(bindings,args.api,name);save()
        # The keyboard driver resets/reinstalls the synthetic app. Install the
        # matching instrumentation only afterwards, then keep all OCR gates.
        test_apk=ROOT/'runtime/android-gradle-build/outputs/apk/androidTest/debug/LensAndroid-debug-androidTest.apk'
        report['activeCheck']='install-review-tests';save()
        if 'Success' not in adb('install','--no-incremental','-r','-t',str(test_apk)):raise RuntimeError('Review test install failed')
        for label,dimensions,dpi,scale in [('phone','720x1280','320','1.0'),('large-font','1080x2400','480','1.3'),('wide','1280x720','320','1.0')]:
            report['activeCheck']=label+'-review-contract';save()
            adb('shell','wm','size',dimensions);adb('shell','wm','density',dpi);adb('shell','settings','put','system','font_scale',scale)
            result=adb('shell','am','instrument','-w','-e','review','true',COMPONENT)
            (folder/(label+'-review.log')).write_text(result,encoding='utf-8')
            passed='review_ui=PASS' in result
            report['checks'].append({'name':label+'-review-contract','size':dimensions,'density':dpi,'fontScale':scale,'passed':passed});save()
            if not passed:raise RuntimeError('Review contract failed')
        adb('shell','wm','size','720x1280');adb('shell','wm','density','320');adb('shell','settings','put','system','font_scale','1.0')
        report['activeCheck']='synthetic-ocr-bubble-attribution';save()
        result=adb('shell','am','instrument','-w','-e','bubbles','true',COMPONENT)
        (folder/'ocr-bubbles.log').write_text(result,encoding='utf-8')
        passed='bubble_attribution=PASS' in result
        report['checks'].append({'name':'synthetic-ocr-bubble-attribution','passed':passed});save()
        if not passed:raise RuntimeError('Synthetic OCR bubble attribution failed')
        report['status']=report['keyboardAcceptance']['status'];report['activeCheck']=None
    except Exception as error:
        report['status']='FAIL';report['failureType']=type(error).__name__
        if isinstance(error,subprocess.TimeoutExpired):
            report['timeout']={'step':report.get('activeCheck'),'seconds':error.timeout,
                               'childCleanup':'NOT_VERIFIED_AFTER_FORCED_TIMEOUT'}
        raise
    finally:
        cleanup=restore_display(report,adb,original)
        save();print(folder.relative_to(ROOT)/'report.json',flush=True)
        if cleanup:raise RuntimeError('Compatibility display cleanup incomplete; see failed receipt')

if __name__=='__main__':main()
