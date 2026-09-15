"""Synthetic file-picker acceptance on the isolated project emulator."""
import subprocess
from assistant_qa import *

def main():
    adb('shell','am','force-stop','com.android.documentsui')
    install();cross_app()
    previous=(OUT/'fixture.json').stat().st_mtime if (OUT/'fixture.json').exists() else 0
    log=(OUT/'picker-service.log').open('w')
    service=subprocess.Popen(['node','--disable-warning=ExperimentalWarning','native/scripts/native_fixture.mjs'],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
    try:
        for _ in range(50):
            if service.poll() is not None:raise RuntimeError('Synthetic service exited')
            if (OUT/'fixture.json').exists() and (OUT/'fixture.json').stat().st_mtime>previous:break
            time.sleep(.1)
        adb('push',ROOT/'output/evals/ocr-samples/synthetic-1.png','/sdcard/Download/lens-synthetic-ocr.png')
        tap_text('建议');time.sleep(.5);pair()
        tap_text('选择一张聊天截图',scroll_find('选择一张聊天截图'));time.sleep(.5)
        def find(predicate):
            for _ in range(20):
                tree=snapshot('picker-ui')
                node=next((n for n in tree.iter('node') if predicate(n)),None)
                if node is not None:return node
                time.sleep(.2)
            raise AssertionError('Picker control missing')
        # Browse the actual external-storage provider; no fabricated Activity result.
        tap_node(find(lambda n:n.get('description')=='Show roots'))
        tap_node(find(lambda n:n.get('text')=='Android SDK built for x86_64' and n.get('enabled')=='true'))
        tap_node(find(lambda n:n.get('text')=='Download' and n.get('enabled')=='true'))
        node=find(lambda n:n.get('description','').startswith('lens-synthetic-ocr.png,'))
        screenshot('picker-file-visible');tap_node(node);time.sleep(.6)
        assert any('已读取你选择的图片' in x for x in labels()),labels()
        telemetry=json.loads((OUT/'fixture-telemetry.json').read_text());assert telemetry['mockModelCalls']==0
        snapshot('picker-approved-preview')
        tap_text('批准此图并提交转写',scroll_find('批准此图并提交转写'));time.sleep(1)
        telemetry=json.loads((OUT/'fixture-telemetry.json').read_text());assert telemetry['mockModelCalls']==1
        assert any('今天加班很累' in x for x in labels()),labels()
        tree=snapshot('picker-transcribed')
        assert all(n.get('checked')!='true' for n in tree.iter('node') if n.get('class')=='android.widget.CheckBox')
        (OUT/'picker-receipt.json').write_text(json.dumps({'status':'PASS_SYNTHETIC','checks':['system_file_selected','preview_zero_upload','approved_one_mock_ocr','transcript_requires_new_approval'],'cloudOCR':False,'realPhone':False,'apkSha256':hashlib.file_digest(APK.open('rb'),'sha256').hexdigest()},indent=2))
        print('PICKER_PASS',flush=True)
    finally:
        try:adb('reverse','--remove','tcp:4317')
        except RuntimeError:pass
        finally:service.terminate();service.wait(timeout=10);log.close()

if __name__=='__main__':main()
