"""No-device integration check for the explicitly owned budget UI fixture."""
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4

import keyboard_budget_qa as budget
import keyboard_first_qa as first


class BudgetFixtureTest(unittest.TestCase):
    def test_explicit_fixture_real_budget_rejections_preserve_ledger_without_model_calls(self):
        parent = first.q.ROOT/'output/keyboard-budget-fixture-checks'
        parent.mkdir(parents=True, exist_ok=True)
        folder = Path(tempfile.mkdtemp(prefix='no-device-', dir=parent))
        report = {'status': 'RUNNING', 'synthetic': True, 'deviceOperations': 0, 'realTouches': False,
                  'realProviderCalls': 0, 'checks': []}
        process = None
        # Pass only execution prerequisites and the explicit synthetic selector.
        env = {key: os.environ[key] for key in ('SystemRoot', 'WINDIR', 'TEMP', 'TMP', 'PATH') if key in os.environ}
        env['LENS_SYNTHETIC_SCENARIO'] = 'keyboard-budget'
        try:
            with (folder/'fixture.log').open('w', encoding='utf-8') as log:
                process = subprocess.Popen(['node', '--disable-warning=ExperimentalWarning',
                                            str(first.q.ROOT/'native/scripts/keyboard_budget_fixture.mjs'), '--out', str(folder)],
                                           stdin=subprocess.PIPE, stdout=log, stderr=subprocess.STDOUT,
                                           text=True, encoding='utf-8', env=env, cwd=first.q.ROOT,
                                           creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
                deadline = time.monotonic()+15
                while not (folder/'fixture.json').exists():
                    if process.poll() is not None or time.monotonic() >= deadline:
                        self.fail('Owned budget fixture did not become ready')
                    time.sleep(.05)
                fixture = json.loads((folder/'fixture.json').read_text(encoding='utf-8'))
                self.assertEqual(fixture.get('pid'), process.pid)
                self.assertIs(fixture.get('synthetic'), True)
                self.assertEqual(fixture.get('scenario'), 'keyboard-budget')
                self.assertRegex(fixture.get('base', ''), r'^http://127\.0\.0\.1:\d+$')

                def request(path, body, token=None):
                    headers = {'Content-Type': 'application/json'}
                    if token:
                        headers['Authorization'] = 'Bearer '+token
                    req = Request(fixture['base']+'/api/native/'+path, data=json.dumps(body).encode(), headers=headers, method='POST')
                    try:
                        with urlopen(req, timeout=10) as response:
                            return response.status, json.loads(response.read())
                    except HTTPError as error:
                        with error:
                            return error.code, json.loads(error.read())

                status, identity = request('auth/activate', {'code': fixture['invite'], 'approved': True, 'name': 'synthetic'})
                self.assertEqual(status, 200)
                status, person = request('library/people', {'name': 'Synthetic budget customer', 'platform': '微信'}, identity['token'])
                self.assertEqual(status, 200)
                for scenario, codes, reset, markers in budget.SCENARIOS:
                    status, result = request('analyze', {'request_id': str(uuid4()), 'person_id': person['id'],
                                            'pair_id': person['relationship']['id'], 'approved': True, 'task_type': 'OPENING',
                                            'context': 'synthetic-editor', 'host': 'com.synthetic.chat', 'mode': 'model', 'text': '', 'materials': []}, identity['token'])
                    self.assertEqual(status, 503 if reset is None else 429)
                    block = result['budget_block']
                    self.assertEqual([item['code'] for item in block['reasons']], codes)
                    self.assertEqual(block['reset_at'], reset)
                    self.assertEqual(block['day_timezone'], 'UTC')
                    for marker in markers:
                        self.assertIn(marker, block['message'])
                    self.assertEqual(result['error'], '模型预算尚未配置或已暂停。' if reset is None else '项目分析预算已用完，请稍后再试。')
                    self.assertNotIn('candidates', result)
                    report['checks'].append({'scenario': scenario, 'status': 'PASS', 'httpStatus': status, 'reasonCodes': codes, 'resetAt': reset})
                receipt = json.loads((folder/'fixture-receipt.json').read_text(encoding='utf-8'))
                self.assertEqual(receipt['calls'], [])
                self.assertEqual(len(receipt['attempts']), 5)
                for attempt in receipt['attempts']:
                    self.assertEqual(attempt['ledgerBeforeSha256'], receipt['initialLedgerSha256'])
                    self.assertEqual(attempt['ledgerAfterSha256'], receipt['initialLedgerSha256'])
                report['status'] = 'PASS'
        except Exception as error:
            report['status'] = 'FAIL'
            report['failureType'] = type(error).__name__
            raise
        finally:
            try:
                if process is not None and process.poll() is None:
                    process.stdin.write('stop\n')
                    process.stdin.flush()
                    process.wait(timeout=15)
                if process is not None:
                    self.assertEqual(process.returncode, 0)
                    receipt = json.loads((folder/'fixture-receipt.json').read_text(encoding='utf-8'))
                    self.assertEqual(receipt['status'], 'STOPPED')
                    self.assertIs(receipt['temporaryDataRemoved'], True)
                    self.assertIs(receipt['allAttemptsPreservedLedger'], True)
                    self.assertEqual(receipt['finalLedgerSha256'], receipt['initialLedgerSha256'])
                    report['temporaryDataRemoved'] = True
            except Exception:
                report['status'] = 'FAIL'
                report['cleanupFailed'] = True
                raise
            finally:
                if process is not None and process.poll() is None:
                    process.terminate()
                    process.wait(timeout=10)
                if process is not None and process.stdin is not None:
                    process.stdin.close()
                (folder/'fixture.json').unlink(missing_ok=True)
                (folder/'report.json').write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
                print(folder/'report.json', flush=True)

    def test_unknown_fixture_is_rejected_before_device_preflight(self):
        class UnknownFixture:
            fixture_name = '../unowned.mjs'
        with self.assertRaisesRegex(ValueError, 'explicitly owned keyboard fixtures'):
            first.main(qa_factory=UnknownFixture)


if __name__ == '__main__':
    unittest.main()
