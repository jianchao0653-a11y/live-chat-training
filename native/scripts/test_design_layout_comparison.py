"""Reject incomplete receipts and real layout regressions, using synthetic data."""
from copy import deepcopy
import unittest
from compare_design_layout import compare,CONFIGS,STATES


def receipt():
    return {'status':'PASS','cleanupErrors':[],'synthetic':True,'realModel':False,
            'realPhone':False,'realTouches':True,'protectedScreensCaptured':False,
            'checks':{k:'PASS' for k in CONFIGS},'serial':'emulator-5556',
            'avd':'LensPreview','api':'36','configurations':{'synthetic':'same'},
            'comparisonRule':'exact','apkSha256':'synthetic',
            'geometry':{c+'-'+s:[{'bounds':'[0,0][96,96]'}] for c in CONFIGS for s in STATES},
            'touchRegions':{c+'-'+s:[0,0,96,96] for c in CONFIGS for s in STATES-{'keyboard'}}}


class ComparisonTests(unittest.TestCase):
    def test_identical_samples_pass(self):
        self.assertEqual('PASS',compare(receipt(),receipt())['status'])

    def test_changed_control_bounds_fail(self):
        changed=receipt();changed['geometry']['large-editor'][0]['bounds']='[0,0][96,95]'
        self.assertEqual('FAIL',compare(receipt(),changed)['status'])

    def test_changed_clipped_touch_region_fails(self):
        changed=receipt();changed['touchRegions']['narrow-details'][3]=95
        self.assertEqual('FAIL',compare(receipt(),changed)['status'])

    def test_missing_checks_or_cleanup_failure_cannot_pass(self):
        for key in ('checks','geometry','touchRegions','configurations','comparisonRule'):
            changed=receipt();del changed[key]
            self.assertEqual('FAIL',compare(receipt(),changed)['status'])
        changed=receipt();changed['cleanupErrors']=['synthetic failure']
        self.assertEqual('FAIL',compare(receipt(),changed)['status'])


if __name__=='__main__':unittest.main()
