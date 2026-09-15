import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

SCRIPT=Path(__file__).with_name('pc_server.py')
SPEC=importlib.util.spec_from_file_location('pc_server_controller',SCRIPT)
CONTROLLER=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CONTROLLER)


class PcServerControllerTests(unittest.TestCase):
    def test_running_receipt_with_missing_process_is_stale(self):
        receipt={'instance':'old','pid':12345,'port':4318,'status':'running'}
        with patch.object(CONTROLLER,'process_exists',return_value=False):
            result=CONTROLLER.observed(receipt,False)
        self.assertEqual(result['service']['observedStatus'],'stale')
        self.assertFalse(result['service']['processAlive'])
        self.assertFalse(result['loopbackResponding'])

    def test_live_process_without_health_is_unresponsive(self):
        receipt={'instance':'current','pid':12345,'port':4318,'status':'running'}
        with patch.object(CONTROLLER,'process_exists',return_value=True):
            result=CONTROLLER.observed(receipt,False)
        self.assertEqual(result['service']['observedStatus'],'unresponsive')
        self.assertTrue(result['service']['processAlive'])

    def test_stopped_receipt_does_not_claim_a_live_process(self):
        result=CONTROLLER.observed({'status':'stopped','pid':12345},False)
        self.assertEqual(result['service']['observedStatus'],'stopped')
        self.assertFalse(result['service']['processAlive'])


if __name__=='__main__':unittest.main()
