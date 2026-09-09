"""Local checks, emulator acceptance and signed delivery; no paid model calls.

Normal Windows use: all. Agent sandbox use: prepare in build identity, then
sign --run RECEIPT_DIR in the existing DPAPI signing identity. No key export.
"""
import argparse,hashlib,json,os,sqlite3,subprocess,sys,time,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'output/local-delivery'
SUFFIXES={'.mjs','.js','.json','.html','.css','.java','.cpp','.h','.xml','.yaml','.yml','.gradle','.properties','.lockfile','.py'}
def source_receipt():
    paths=[ROOT/'package.json']
    for folder in ('app','native'):
        paths.extend(p for p in (ROOT/folder).rglob('*') if p.is_file() and p.suffix in SUFFIXES and not any(x in p.parts for x in ('build','.gradle','__pycache__')))
    return {p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(set(paths))}
def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--phase',choices=['checks','prepare','sign','all'],default='all')
    parser.add_argument('--run',type=Path)
    parser.add_argument('--endpoint',default='https://outreach-alibi-reformer.ngrok-free.dev')
    args=parser.parse_args()
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
        if report.get('status')!='PREPARED' or report.get('endpoint')!=endpoint or report.get('sources')!=source_receipt():parser.error('Prepared source or endpoint changed; prepare again')
        prepared=json.loads((ROOT/'output/native/prepared-release.json').read_text(encoding='utf-8'))
        if prepared!=report['prepared']:parser.error('Prepared artifact receipt changed')
    else:
        if args.run:parser.error('--run only applies to sign')
        folder=OUT/(time.strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:8]);folder.mkdir()
        report={'status':'RUNNING','endpoint':endpoint,'sources':source_receipt(),'checks':[],'realPhone':False,'realModel':False,'qualityAccepted':False,'productionReady':False}
    def save(): (folder/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    env={**os.environ,'PYTHONIOENCODING':'utf-8','LENS_QA_SERIAL':'emulator-5556'}
    def run(name,cmd,timeout=900):
        print('RUN '+name,flush=True);start=time.monotonic()
        with (folder/(name+'.log')).open('w',encoding='utf-8') as log:
            result=subprocess.run(list(map(str,cmd)),cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=timeout)
        report['checks'].append({'name':name,'passed':result.returncode==0,'seconds':round(time.monotonic()-start,2)});save()
        if result.returncode:raise RuntimeError(name+' failed; see its bounded local log')
    def python(name,script,*args):run(name,[sys.executable,ROOT/'native/scripts'/script,*args])
    started=False
    adb=ROOT/'runtime/android-tools/sdk/platform-tools/adb.exe'
    def device(*args):return subprocess.check_output([str(adb),'-s','emulator-5556',*args],text=True,stderr=subprocess.STDOUT,timeout=90)
    try:
        save()
        if args.phase!='sign':
            run('node-tests',['node','--disable-warning=ExperimentalWarning','--test','--test-concurrency=1',*sorted((ROOT/'app/tests').glob('*.test.mjs'))])
            python('input-policy','test_policy.py');python('https-tests','test_https_acceptance.py')
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
            if avd_name not in ('LensPreview','LensPreviewApi26','LensPreviewApi34'):raise RuntimeError('Refusing non-project AVD')
            report['emulator']={'api':device('shell','getprop','ro.build.version.sdk').strip(),'avd':avd_name,'size':device('shell','wm','size').strip(),'density':device('shell','wm','density').strip(),'fontScale':device('shell','settings','get','system','font_scale').strip()};save()
            # Only this project's emulator synthetic app is reset; no personal device is targeted.
            subprocess.run([str(adb),'-s','emulator-5556','uninstall','com.conversationlens.ime'],capture_output=True,timeout=90)
            run('install-qa',[adb,'-s','emulator-5556','install','--no-incremental','-r','-t',ROOT/'output/native/lens-synthetic-qa.apk'])
            python('cloud-ui','ci_cloud.py')
            run('install-review-tests',[adb,'-s','emulator-5556','install','--no-incremental','-r',ROOT/'runtime/android-gradle-build/outputs/apk/androidTest/debug/LensAndroid-debug-androidTest.apk'])
            run('ocr-review-ui',[adb,'-s','emulator-5556','shell','am','instrument','-w','-e','review','true','com.conversationlens.ime.test/com.conversationlens.ime.OcrTestRunner'])
            if 'review_ui=PASS' not in (folder/'ocr-review-ui.log').read_text(encoding='utf-8'):raise RuntimeError('OCR review instrumentation did not pass')
            python('https-boundary','https_acceptance.py',endpoint)
            python('release-build','build_android_ocr.py','--release','--cloud-url',endpoint)
            if report['sources']!=source_receipt():raise RuntimeError('Sources changed during acceptance')
            report['prepared']=json.loads((ROOT/'output/native/prepared-release.json').read_text(encoding='utf-8'))
            report['status']='PREPARED';save()
        if args.phase in ('all','sign'):
            python('sign-and-verify','sign_prepared_release.py',endpoint)
            report['release']=json.loads((ROOT/'output/native/release-receipt.json').read_text(encoding='utf-8'))
            python('server-package','package_cloud.py')
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
