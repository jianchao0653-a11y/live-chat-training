"""Local checks, emulator acceptance and signed delivery; no paid model calls.

Normal Windows use: all. Agent sandbox use: prepare in build identity, then
sign --run RECEIPT_DIR in the existing DPAPI signing identity. No key export.
Use --apk-only in both prepare and sign for an Android-only update; existing
server archives are preserved and the receipt's delivery scope cannot change.
"""
import argparse,hashlib,json,os,sqlite3,subprocess,sys,time,uuid
from pathlib import Path
from keyboard_acceptance import (bind_keyboard_receipt,validate_prepared_release,DEFERRED_LIFECYCLE,
    SUITES,applicable_keyboard_suites,aggregate_keyboard_receipts,revalidate_keyboard_bundle)
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'output/local-delivery'
SUFFIXES={'.mjs','.js','.json','.html','.css','.java','.cpp','.h','.xml','.yaml','.yml','.gradle','.properties','.lockfile','.py',
          '.txt','.cmd','.ps1','.svg','.webmanifest','.service','.timer','.example','.swift','.entitlements'}
EXCLUDED_SOURCE_DIRS={'runtime','output','private','build','.gradle','__pycache__','.git','.codex','.agents'}
def source_receipt(root=ROOT):
    root=Path(root)
    paths=[root/'package.json']
    paths.extend(root/name for name in ('启动测试版.cmd','本机验收打包.cmd') if (root/name).is_file())
    for folder in ('app','native','.github'):
        paths.extend(p for p in (root/folder).rglob('*') if p.is_file() and p.suffix in SUFFIXES
                     and not EXCLUDED_SOURCE_DIRS.intersection(p.relative_to(root).parts[:-1]))
    return {p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(set(paths))}
def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--phase',choices=['checks','prepare','sign','all'],default='all')
    parser.add_argument('--run',type=Path)
    parser.add_argument('--endpoint',default='https://outreach-alibi-reformer.ngrok-free.dev')
    parser.add_argument('--apk-only',action='store_true',help='Deliver the Android APK without repackaging the existing backend; required again when resuming sign')
    args=parser.parse_args()
    scope='android-apk-only' if args.apk_only else 'android-and-server'
    from https_acceptance import validate_root
    endpoint=validate_root(args.endpoint)
    lock=sqlite3.connect(ROOT/'runtime/local-delivery-lock.sqlite',timeout=0,isolation_level=None)
    try:lock.execute('BEGIN EXCLUSIVE')
    except sqlite3.OperationalError:raise SystemExit('Another local delivery is running')
    OUT.mkdir(parents=True,exist_ok=True)
    if args.phase=='sign':
        if not args.run:parser.error('sign requires --run from successful prepare')
        folder=args.run.resolve()
        if not folder.is_relative_to(OUT.resolve()):parser.error('run must be under output/local-delivery')
        report=json.loads((folder/'report.json').read_text(encoding='utf-8'))
        if report.get('scope')!=scope:parser.error('Prepared delivery scope changed; prepare and sign must use the same --apk-only setting')
        if report.get('status')!='PREPARED' or report.get('endpoint')!=endpoint or report.get('sources')!=source_receipt():parser.error('Prepared source or endpoint changed; prepare again')
        prepared=json.loads((ROOT/'output/native/prepared-release.json').read_text(encoding='utf-8'))
        if prepared!=report['prepared']:parser.error('Prepared artifact receipt changed')
    else:
        if args.run:parser.error('--run only applies to sign')
        folder=OUT/(time.strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:8]);folder.mkdir()
        report={'status':'RUNNING','scope':scope,'endpoint':endpoint,'sources':source_receipt(),'checks':[],'realPhone':False,'realModel':False,'qualityAccepted':False,'productionReady':False,
                'releaseApkRuntimeAccepted':False,'pendingKeyboardLifecycle':DEFERRED_LIFECYCLE}
    def save(): (folder/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    env={**os.environ,'PYTHONIOENCODING':'utf-8','LENS_QA_SERIAL':'emulator-5556'}
    def run(name,cmd,timeout=900):
        print('RUN '+name,flush=True);start=time.monotonic();started_at=time.time()
        check={'name':name,'passed':False,'status':'RUNNING'}
        report['checks'].append(check);report['activeCheck']=name;save()
        try:
            with (folder/(name+'.log')).open('w',encoding='utf-8') as log:
                result=subprocess.run(list(map(str,cmd)),cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=timeout)
            check.update({'passed':result.returncode==0,'status':'PASS' if result.returncode==0 else 'FAIL'})
        except subprocess.TimeoutExpired:
            check.update({'status':'TIMEOUT','timeoutSeconds':timeout,'childCleanup':'NOT_VERIFIED_AFTER_FORCED_TIMEOUT'})
            raise
        except Exception:
            check['status']='FAIL';raise
        finally:
            check['seconds']=round(time.monotonic()-start,2);report['activeCheck']=None;save()
        if result.returncode:raise RuntimeError(name+' failed; see its bounded local log')
        return started_at
    def python(name,script,*args):return run(name,[sys.executable,ROOT/'native/scripts'/script,*args])
    started=False
    adb=ROOT/'runtime/android-tools/sdk/platform-tools/adb.exe'
    def device(*args):return subprocess.check_output([str(adb),'-s','emulator-5556',*args],text=True,stderr=subprocess.STDOUT,timeout=90)
    try:
        save()
        if args.phase!='sign':
            run('node-tests',['node','--disable-warning=ExperimentalWarning','--test','--test-concurrency=1',*sorted((ROOT/'app/tests').glob('*.test.mjs'))])
            python('input-policy','test_policy.py');python('https-tests','test_https_acceptance.py');python('keyboard-evidence-tests','test_keyboard_acceptance.py')
            run('synthetic-evals',['node','app/evals/run.mjs','--mode','local'])
            if args.phase=='checks':report['status']='CHECKS_PASSED';save();return
            python('cloud-debug-build','build_android_ocr.py','--abis','x86_64','--with-tests','--cloud-url','http://127.0.0.1:4317')
            python('qa-build','build_qa.py')
            try:booted=device('shell','getprop','sys.boot_completed').strip()=='1'
            except subprocess.SubprocessError:booted=False
            if not booted:
                python('start-emulator','start_emulator.py');started=True
                for _ in range(90):
                    try:
                        if device('shell','getprop','sys.boot_completed').strip()=='1':break
                    except subprocess.SubprocessError:pass
                    time.sleep(2)
                else:raise RuntimeError('Project emulator did not boot')
            if device('shell','getprop','ro.kernel.qemu').strip()!='1':raise RuntimeError('Refusing non-emulator target')
            avd_name=device('emu','avd','name').splitlines()[0].strip()
            if avd_name not in ('LensPreview','LensPreviewApi26','LensPreviewApi34','LensPreviewApi36'):raise RuntimeError('Refusing non-project AVD')
            report['emulator']={'api':device('shell','getprop','ro.build.version.sdk').strip(),'avd':avd_name,'size':device('shell','wm','size').strip(),'density':device('shell','wm','density').strip(),'fontScale':device('shell','settings','get','system','font_scale').strip()};save()
            # The current driver owns its verified emulator reset, fake provider,
            # loopback forwarding and cleanup. Never point it at args.endpoint.
            # API26 can run ordinary/continuation compatibility, but this
            # prepare must also exercise capture on API34+ before signing.
            bindings={}
            for suite in applicable_keyboard_suites(report['emulator']['api'],require_complete=True):
                step='keyboard-'+suite+'-ui'
                started_at=python(step,SUITES[suite]['script'])
                bindings[suite]=bind_keyboard_receipt(folder/(step+'.log'),ROOT/'output/native/conversation-lens-0.18.0-cloud-debug.apk',
                    started_at,report['emulator']['api'],avd_name,suite=suite)
                report['keyboardSuiteEvidence']=bindings;save()
            report['keyboardAcceptance']=aggregate_keyboard_receipts(bindings,report['emulator']['api'],avd_name,require_complete=True);save()
            run('install-review-tests',[adb,'-s','emulator-5556','install','--no-incremental','-r','-t',ROOT/'runtime/android-gradle-build/outputs/apk/androidTest/debug/LensAndroid-debug-androidTest.apk'])
            run('ocr-review-ui',[adb,'-s','emulator-5556','shell','am','instrument','-w','-e','review','true','com.conversationlens.ime.test/com.conversationlens.ime.OcrTestRunner'])
            if 'review_ui=PASS' not in (folder/'ocr-review-ui.log').read_text(encoding='utf-8'):raise RuntimeError('OCR review instrumentation did not pass')
            run('ocr-bubble-layout',[adb,'-s','emulator-5556','shell','am','instrument','-w','-e','bubbles','true','com.conversationlens.ime.test/com.conversationlens.ime.OcrTestRunner'])
            if 'bubble_attribution=PASS' not in (folder/'ocr-bubble-layout.log').read_text(encoding='utf-8'):raise RuntimeError('Synthetic OCR bubble attribution did not pass')
            python('https-boundary','https_acceptance.py',endpoint)
            python('release-build','build_android_ocr.py','--release','--abis','arm64-v8a','x86_64','--cloud-url',endpoint)
            if report['sources']!=source_receipt():raise RuntimeError('Sources changed during acceptance')
            report['prepared']=json.loads((ROOT/'output/native/prepared-release.json').read_text(encoding='utf-8'))
            report['releaseArtifactValidation']=validate_prepared_release(report['prepared'],endpoint)
            report['status']='PREPARED';save()
        if args.phase in ('all','sign'):
            revalidate_keyboard_bundle(report.get('keyboardAcceptance'),ROOT/'output/native/conversation-lens-0.18.0-cloud-debug.apk',
                report['emulator']['api'],report['emulator']['avd'])
            python('sign-and-verify','sign_prepared_release.py',endpoint)
            report['release']=json.loads((ROOT/'output/native/release-receipt.json').read_text(encoding='utf-8'))
            if scope=='android-and-server':python('server-package','package_cloud.py')
            report['status']='SIGNED_TEST_BUILD';report.pop('failureType',None);save()
    except Exception as error:
        # Keep PREPARED on signing-identity failure so the original identity can safely resume.
        if report.get('status')!='PREPARED':report['status']='FAILED'
        report['failureType']=type(error).__name__;save();raise SystemExit('Local delivery incomplete. See '+str(folder.relative_to(ROOT)/'report.json'))
    finally:
        if started:
            try:device('emu','kill')
            except subprocess.SubprocessError:pass
        lock.close()
        print('Receipt: '+str(folder.relative_to(ROOT)/'report.json'),flush=True)
if __name__=='__main__':main()
