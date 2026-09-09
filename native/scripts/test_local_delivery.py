"""Fail-closed phase-resume tests. No key access, model calls or compilation."""
import json,subprocess,sys,tempfile,unittest
from pathlib import Path
from local_delivery import ROOT,OUT
class DeliveryTest(unittest.TestCase):
    def invoke(self,*args):
        return subprocess.run([sys.executable,str(ROOT/'native/scripts/local_delivery.py'),'--phase','sign',*args],cwd=ROOT,capture_output=True,text=True)
    def test_missing_receipt(self):self.assertNotEqual(self.invoke().returncode,0)
    def test_external_receipt_refused(self):self.assertNotEqual(self.invoke('--run',str(ROOT)).returncode,0)
    def test_stale_source_refused_before_signing(self):
        OUT.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=OUT,prefix='test-resume-') as directory:
            (Path(directory)/'report.json').write_text(json.dumps({'status':'PREPARED','endpoint':'https://outreach-alibi-reformer.ngrok-free.dev','sources':{}}),encoding='utf-8')
            result=self.invoke('--run',directory)
            self.assertNotEqual(result.returncode,0);self.assertIn('Prepared source or endpoint changed',result.stderr)
            self.assertFalse((Path(directory)/'sign-and-verify.log').exists())
    def test_bad_endpoint_refused(self):self.assertNotEqual(self.invoke('--endpoint','http://example.com').returncode,0)
if __name__=='__main__':unittest.main()
