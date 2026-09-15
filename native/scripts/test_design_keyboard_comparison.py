"""Keep empty, incomplete or different keyboard evidence from passing."""
import copy
import unittest
import compare_design_keyboard as gate


class ComparisonTests(unittest.TestCase):
    def receipt(self):
        return dict(status='PASS',cleanupErrors=[],displayRestored=True,synthetic=True,realModel=False,
            realPhone=False,protectedScreensCaptured=False,checks={k:'PASS' for k in gate.SCENARIOS},
            geometry={k:[{'bounds':'[0,0][10,10]','text':'synthetic'}] for k in gate.STATES},
            realTouches=[dict(scenario=k,realTouches=True,suggestionOpened=True) for k in gate.SCENARIOS],
            serial='emulator-5556',avd='LensPreview',api='36')

    def test_complete_equal_passes(self):
        before=self.receipt()
        self.assertEqual('PASS',gate.compare(before,copy.deepcopy(before))['status'])

    def test_missing_evidence_rejected(self):
        for key in ('geometry','checks','realTouches','displayRestored','api'):
            before=self.receipt();after=copy.deepcopy(before);del after[key]
            with self.subTest(key=key):self.assertEqual('FAIL',gate.compare(before,after)['status'])

    def test_pixel_state_cleanup_difference_rejected(self):
        for change in ('bounds','text','cleanup'):
            before=self.receipt();after=copy.deepcopy(before)
            if change=='cleanup':after['cleanupErrors']=['incomplete']
            else:after['geometry']['keyboard-template-portrait'][0][change]='changed'
            with self.subTest(change=change):self.assertEqual('FAIL',gate.compare(before,after)['status'])

    def test_two_empty_reports_rejected(self):
        self.assertEqual('FAIL',gate.compare({}, {})['status'])


if __name__=='__main__':unittest.main()
