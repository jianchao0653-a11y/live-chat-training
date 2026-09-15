"""Fail-closed phase-resume tests. No key access, model calls or compilation."""
import json,subprocess,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import local_delivery as delivery
from local_delivery import ROOT,OUT,source_receipt
class DeliveryTest(unittest.TestCase):
    def invoke(self,*args):
        return subprocess.run([sys.executable,'-X','utf8',str(ROOT/'native/scripts/local_delivery.py'),'--phase','sign',*args],cwd=ROOT,capture_output=True,text=True,encoding='utf-8')
    def test_missing_receipt(self):self.assertNotEqual(self.invoke().returncode,0)
    def test_external_receipt_refused(self):self.assertNotEqual(self.invoke('--run',str(ROOT)).returncode,0)
    def test_stale_source_refused_before_signing(self):
        OUT.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=OUT,prefix='test-resume-') as directory:
            (Path(directory)/'report.json').write_text(json.dumps({'status':'PREPARED','scope':'android-and-server','endpoint':'https://outreach-alibi-reformer.ngrok-free.dev','sources':{}}),encoding='utf-8')
            result=self.invoke('--run',directory)
            self.assertNotEqual(result.returncode,0);self.assertIn('Prepared source or endpoint changed',result.stderr)
            self.assertFalse((Path(directory)/'sign-and-verify.log').exists())
    def test_scope_change_refused_before_signing(self):
        OUT.mkdir(parents=True,exist_ok=True)
        for prepared_scope,flags in [('android-and-server',['--apk-only']),('android-apk-only',[])]:
            with self.subTest(prepared_scope=prepared_scope),tempfile.TemporaryDirectory(dir=OUT,prefix='test-scope-') as directory:
                (Path(directory)/'report.json').write_text(json.dumps({'status':'PREPARED','scope':prepared_scope,'endpoint':'https://outreach-alibi-reformer.ngrok-free.dev','sources':source_receipt()}),encoding='utf-8')
                result=self.invoke('--run',directory,*flags)
                self.assertNotEqual(result.returncode,0);self.assertIn('Prepared delivery scope changed',result.stderr)
                self.assertFalse((Path(directory)/'sign-and-verify.log').exists())
                self.assertFalse((Path(directory)/'server-package.log').exists())
    def test_bad_endpoint_refused(self):self.assertNotEqual(self.invoke('--endpoint','http://example.com').returncode,0)

class SourceReceiptTest(unittest.TestCase):
    def test_build_inputs_are_bound_and_generated_or_private_trees_are_never_read(self):
        with tempfile.TemporaryDirectory(prefix='lens-source-receipt-') as directory:
            root=Path(directory)/'build';root.mkdir()
            included=['package.json','启动测试版.cmd','本机验收打包.cmd','native/android/CMakeLists.txt',
                      'native/scripts/helper.ps1','native/licenses/NOTICE.txt','app/public/icon.svg',
                      'native/ios/App/LensApp.swift','.github/workflows/mobile-ci.yml']
            excluded=['native/android/runtime/gradle-project-cache/cache.properties','native/output/receipt.json',
                      'native/private/key.json','native/android/build/generated.java','native/scripts/__pycache__/cache.py',
                      'app/.gradle/cache.properties','runtime/private/key.json','private-note.txt']
            for name in included+excluded:
                path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('synthetic '+name,encoding='utf-8')
            original_read=Path.read_bytes
            def bounded_read(path):
                relative=path.relative_to(root).as_posix()
                if relative not in included:raise AssertionError('Receipt read excluded synthetic file: '+relative)
                return original_read(path)
            with patch.object(Path,'read_bytes',bounded_read):
                before=source_receipt(root)
                (root/'native/android/CMakeLists.txt').write_text('changed native build input',encoding='utf-8')
                after=source_receipt(root)
            self.assertEqual(set(before),set(included))
            self.assertNotEqual(before['native/android/CMakeLists.txt'],after['native/android/CMakeLists.txt'])

class LocalTimeoutTest(unittest.TestCase):
    def test_step_timeout_is_explicitly_failed_without_claiming_child_cleanup(self):
        with tempfile.TemporaryDirectory(prefix='lens-delivery-timeout-') as directory:
            root=Path(directory);(root/'runtime').mkdir()
            out=root/'output/local-delivery'
            with patch.object(delivery,'ROOT',root),patch.object(delivery,'OUT',out), \
                    patch.object(delivery,'source_receipt',return_value={}), \
                    patch.object(delivery.sys,'argv',['local_delivery.py','--phase','checks','--apk-only']), \
                    patch.object(delivery.subprocess,'run',side_effect=subprocess.TimeoutExpired('synthetic command',900)):
                with self.assertRaises(SystemExit):delivery.main()
            paths=list(out.glob('*/report.json'));self.assertEqual(len(paths),1)
            report=json.loads(paths[0].read_text(encoding='utf-8'))
            self.assertEqual(report['status'],'FAILED')
            self.assertFalse(report['checks'][0]['passed'])
            self.assertEqual(report['checks'][0]['status'],'TIMEOUT')
            self.assertEqual(report['checks'][0]['childCleanup'],'NOT_VERIFIED_AFTER_FORCED_TIMEOUT')

if __name__=='__main__':unittest.main()
