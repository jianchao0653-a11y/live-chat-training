import copy
import unittest
import compare_design_activity as gate


class ActivityComparisonTests(unittest.TestCase):
    def receipt(self):
        return dict(status='PASS',cleanupErrors=[],displayRestored=True,synthetic=True,realPhone=False,
            realModel=False,realTouches=True,protectedScreensCaptured=False,
            checks={c:'PASS' for c in gate.CONFIGS},geometry={k:[{'bounds':'[0,0][10,10]'}] for k in gate.STATES},
            touchRegions={k:[0,0,10,10] for k in gate.TOUCHES},ocrContracts={k:'PASS' for k in gate.CONTRACTS},
            serial='emulator-5556',avd='LensPreview',api='36',configurations={'same':True},comparisonRule='same',testApk={'sha256':'same'})
    def test_equal_passes(self):
        before=self.receipt();self.assertEqual('PASS',gate.compare(before,copy.deepcopy(before))['status'])
    def test_empty_or_missing_cannot_pass(self):
        self.assertEqual('FAIL',gate.compare({}, {})['status'])
        for key in ('geometry','ocrContracts','touchRegions','testApk'):
            before=self.receipt();after=copy.deepcopy(before);del after[key]
            self.assertEqual('FAIL',gate.compare(before,after)['status'])
    def test_pixel_touch_or_contract_difference_rejected(self):
        for key in ('geometry','touchRegions','ocrContracts'):
            before=self.receipt();after=copy.deepcopy(before)
            after[key][next(iter(after[key]))]='different'
            self.assertEqual('FAIL',gate.compare(before,after)['status'])
    def test_test_apk_and_cleanup_must_match(self):
        for key in ('testApk','cleanupErrors'):
            before=self.receipt();after=copy.deepcopy(before);after[key]=['changed']
            self.assertEqual('FAIL',gate.compare(before,after)['status'])


if __name__=='__main__':unittest.main()
