"""No-device contract checks for the isolated keyboard-details fixture.

This validates seed/fault/receipt ownership, not Android acceptance. It starts
only fresh temporary loopback fixtures and removes their synthetic invitations.
"""
import http.client
import json
import os
from pathlib import Path
import subprocess
import time
import unittest
from urllib.error import HTTPError
from urllib.request import ProxyHandler, Request, build_opener
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]


class DetailsFixtureTest(unittest.TestCase):
    def run_fixture(self, scenario, check):
        folder = ROOT/'output/keyboard-details-fixture-qa'/(time.strftime('%Y%m%d-%H%M%S')+'-'+uuid4().hex[:8])
        folder.mkdir(parents=True)
        env = dict(os.environ, LENS_SYNTHETIC_SCENARIO=scenario, LENS_SYNTHETIC_REPLY_DELAY_MS='0')
        status = 'FAIL'
        with (folder/'fixture.log').open('w', encoding='utf-8') as log:
            service = subprocess.Popen(['node', '--disable-warning=ExperimentalWarning',
                                        str(ROOT/'native/scripts/keyboard_first_fixture.mjs'), '--out', str(folder)],
                                       cwd=ROOT, env=env, stdin=subprocess.PIPE, stdout=log, stderr=subprocess.STDOUT,
                                       text=True, encoding='utf-8', creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            try:
                deadline = time.monotonic()+15
                while not (folder/'fixture.json').exists():
                    if service.poll() is not None or time.monotonic() >= deadline:
                        self.fail('Owned fixture failed to start; inspect '+str(folder/'fixture.log'))
                    time.sleep(.05)
                meta = json.loads((folder/'fixture.json').read_text(encoding='utf-8'))
                self.assertTrue(meta['synthetic'])
                self.assertEqual(meta['pid'], service.pid)
                self.assertRegex(meta['base'], r'^http://127\.0\.0\.1:\d+$')
                # Only this verified owned loopback origin bypasses OS proxy
                # autodetection, so intentional socket loss reaches the probe.
                opener = build_opener(ProxyHandler({}))
                def request(path, payload=None, token=None):
                    headers = {'Content-Type': 'application/json'}
                    if token:
                        headers['Authorization'] = 'Bearer '+token
                    req = Request(meta['base']+'/api/native/'+path,
                                  data=json.dumps(payload).encode() if payload is not None else None, headers=headers)
                    try:
                        with opener.open(req, timeout=10) as response:
                            return response.status, json.load(response)
                    except HTTPError as error:
                        return error.code, json.load(error)
                code, auth = request('auth/activate', {'code': meta['invite'], 'name': 'SyntheticFixtureContract', 'approved': True})
                self.assertEqual(code, 200)
                token = auth['token']
                check(folder, lambda path, payload=None: request(path, payload, token))
                status = 'PASS'
            finally:
                if service.poll() is None:
                    service.stdin.write('stop\n')
                    service.stdin.flush()
                    service.wait(timeout=15)
                service.stdin.close()
                metadata = folder/'fixture.json'
                if metadata.exists():
                    metadata.unlink()
                report = {'status': status, 'scenario': scenario, 'synthetic': True,
                          'deviceUsed': False, 'androidAcceptance': 'NOT_RUN', 'realProviderCalls': 0}
                (folder/'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
                self.assertEqual(service.returncode, 0)
                final = json.loads((folder/'fixture-receipt.json').read_text(encoding='utf-8'))
                self.assertEqual(final['status'], 'STOPPED')
                self.assertTrue(final['temporaryDataRemoved'])
                self.assertEqual(final['realProviderCalls'], 0)
                self.assertEqual(final['calls'], [])
                print(str(folder/'report.json'), flush=True)

    def test_default_remains_unseeded(self):
        def check(folder, request):
            status, result = request('library/people')
            self.assertEqual(status, 200)
            self.assertEqual(result['people'], [])
            receipt = json.loads((folder/'fixture-receipt.json').read_text(encoding='utf-8'))
            self.assertNotIn('details', receipt)
        self.run_fixture('default', check)

    def test_seeded_source_and_one_shot_fault_contract(self):
        def check(folder, request):
            def state():
                return json.loads((folder/'fixture-receipt.json').read_text(encoding='utf-8'))['details']
            initial = state()
            history = initial['people']['qahistory']
            feedback = initial['people']['qafeedback']
            self.assertEqual(history['claims'], [])
            self.assertEqual(len(history['analyses']), 1)
            self.assertFalse(history['analyses'][0]['stale'])
            profile_id = history['analyses'][0]['id']
            status, profile = request('library/analyses/'+profile_id)
            self.assertEqual(status, 200)
            materials = profile['analysis']['result']['materials']
            self.assertEqual([m['text'] for m in materials], ['喜欢散步', '喜欢散步'])
            self.assertNotEqual(materials[0]['source'], materials[1]['source'])
            (folder/'fixture-control.json').write_text(json.dumps({'id': 1, 'action': 'profile-drop-response'}), encoding='utf-8')
            with self.assertRaises((http.client.RemoteDisconnected, ConnectionResetError)):
                request('library/analyses/'+profile_id+'/memories', {'confirmed': True, 'observation_ids': ['O1', 'OI']})
            after = state()
            self.assertTrue(after['faults'][0]['applied'])
            self.assertEqual(len(after['people']['qahistory']['claims']), 2)
            self.assertEqual(len(after['people']['qahistory']['effectiveClaimIds']), 1)
            inferred = next(c for c in after['people']['qahistory']['claims'] if c['kind'] == 'INFERRED')
            self.assertEqual(inferred['review_state'], 'PENDING')
            self.assertIn('合成来源乙（2026-09-10）', inferred['source'])
            status, refreshed = request('library/analyses/'+profile_id)
            self.assertEqual(status, 200)
            self.assertTrue(refreshed['stale'])
            # The fault is one-shot; a second explicit POST receives the backend's
            # true stale conflict rather than another lost response.
            status, _ = request('library/analyses/'+profile_id+'/memories', {'confirmed': True, 'observation_ids': ['O1']})
            self.assertEqual(status, 409)
            feedback_id = next(a['id'] for a in feedback['analyses'] if a['summary'] == '合成反馈记录甲')
            (folder/'fixture-control.json').write_text(json.dumps({'id': 2, 'action': 'feedback-refresh-failure'}), encoding='utf-8')
            payload = {'status': 'UNKNOWN', 'note': 'unseen', 'draft': 'hello'}
            status, _ = request('library/feedback/'+feedback_id+'/save', payload)
            self.assertEqual(status, 200)
            status, _ = request('library/people/'+feedback['id']+'/history')
            self.assertEqual(status, 503)
            status, result = request('library/people/'+feedback['id']+'/history')
            self.assertEqual(status, 200)
            self.assertEqual(len(result['history']), 2)
            self.assertEqual(result['history'][0]['outcome']['status'], 'UNKNOWN')
            latest = state()
            self.assertTrue(latest['faults'][1]['applied'])
            self.assertEqual(latest['faults'][1]['postStatus'], 200)
            self.assertEqual(latest['people']['qafeedback']['outcomeEvents'], 1)
            self.assertEqual(len(latest['people']['qafeedback']['claims']), 1)
            self.assertNotIn('fixtureError', latest)
            # Read a current independent profile, then mutate actual customer
            # memory at the next adoption POST. Only cloud's revision validator
            # is allowed to emit409; the fixture does not synthesize that response.
            stale = latest['people']['qastale']
            stale_id = stale['analyses'][0]['id']
            status, result = request('library/analyses/'+stale_id)
            self.assertEqual(status, 200)
            self.assertFalse(result['stale'])
            self.assertEqual(stale['claims'], [])
            (folder/'fixture-control.json').write_text(json.dumps({'id': 3, 'action': 'profile-concurrent-revision'}), encoding='utf-8')
            status, result = request('library/analyses/'+stale_id+'/memories', {'confirmed': True, 'observation_ids': ['O1']})
            self.assertEqual(status, 409)
            self.assertIn('客户资料已变化', result['error'])
            concurrent = state()
            fault = concurrent['faults'][-1]
            self.assertEqual(fault['action'], 'profile-concurrent-revision')
            self.assertFalse(fault['responseSynthesized'])
            self.assertEqual(fault['beforeRevision'], stale['revision'])
            self.assertNotEqual(fault['beforeRevision'], fault['afterRevision'])
            changed = concurrent['people']['qastale']
            self.assertEqual(changed['revision'], fault['afterRevision'])
            self.assertEqual(len(changed['claims']), 1)
            self.assertEqual(changed['claims'][0]['content'], 'concurrentreview')
            status, result = request('library/analyses/'+stale_id)
            self.assertEqual(status, 200)
            self.assertTrue(result['stale'])
            self.assertEqual(result['analysis']['id'], stale_id)
            self.assertEqual(state()['people']['qastale'], changed)
        self.run_fixture('keyboard-details', check)


if __name__ == '__main__':
    unittest.main()
