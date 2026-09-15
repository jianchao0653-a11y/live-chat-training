"""Actual-touch correlated paid-retry QA on the owned synthetic emulator.

The first provider call fails after budget admission. The same original HTTP
request is then rechecked, the server returns its canonical retry_of, and only
an explicit on-device possible-charge confirmation may create a new request.
Synthetic allowlisted POST fields and task ledgers are retained for comparison;
no real provider, account, token, runtime database or private text is used.
"""
import json
import os
import time
import keyboard_first_qa as first
import keyboard_continuation_qa as continuation

NAME = 'qaretry'
RETRY_CONFIRM = '上次请求可能已计费，确认再次生成并占用新的额度'
CHECKS = [
    'provider_started_failure_exposes_original_request_recheck',
    'original_recheck_preserves_request_and_requires_confirmation',
    'explicit_retry_uses_new_id_and_exact_original_fields',
    'retry_completes_once_and_preserves_old_ledger',
]


class RetryQA(continuation.ContinuationQA):
    def __init__(self, folder):
        super().__init__(folder)
        self.report.update(
            suite='keyboard-retry', checks={name: 'NOT_RUN' for name in CHECKS},
            scope='Actual IME possible-charge retry confirmation with allowlisted raw POST field comparison',
            notCovered=['actual 120-second timeout', '15-minute expiry', 'OEM/real phone/provider quality'])

    def network(self):
        path = self.folder/'fixture-receipt.json'
        if path.stat().st_size > 2_000_000:
            raise AssertionError('Oversized synthetic fixture receipt')
        receipt = json.loads(path.read_text(encoding='utf-8'))
        value = receipt.get('network', {})
        if receipt.get('synthetic') is not True or receipt.get('realProviderCalls') != 0 or value.get('fixtureError'):
            raise AssertionError('Invalid owned retry fixture')
        if value.get('scenario') != 'keyboard-retry':
            raise AssertionError('Wrong synthetic retry scenario')
        return receipt, value

    def wait_requests(self, count, timeout=20):
        deadline = time.monotonic()+timeout
        while time.monotonic() < deadline:
            receipt, network = self.network()
            if len(network.get('requests', [])) >= count and len(network.get('responses', [])) >= count:
                return receipt, network
            time.sleep(.1)
        raise AssertionError(f'Synthetic retry fixture did not record {count} complete requests')

    def main_flow(self):
        self.begin(CHECKS[0])
        self.tap('老用户维护', kind='description')
        self.wait_label('新增客户')
        self.new_customer(NAME)
        self.select_customer(NAME)
        self.tap(continuation.START)
        self.enter_fragment('hello')
        self.approve(NAME)
        self.tap(continuation.GENERATE)
        self.wait(lambda tree: any('原片段已锁定，可按原请求重查' in text for text in self.texts(tree)),
                  'Charged synthetic failure did not expose original-request recheck', 40)
        receipt, network = self.wait_requests(1)
        first_request = network['requests'][0]['fields']
        first_response = network['responses'][0]
        if first_response['status'] != 500 or first_response['ledger'][0]['state'] != 'FAILED':
            raise AssertionError('First provider failure did not retain a failed task')
        if first_response['ledger'][0]['calls'] != 1 or first_response['ledger'][0]['reserved'] <= 0:
            raise AssertionError('First provider failure was not retained as reserved possible-charge work')
        if len(receipt['calls']) != 1 or receipt['calls'][0].get('judge') is not False:
            raise AssertionError('Unexpected provider call receipt before recheck')
        self.report['firstRequest'] = first_request
        self.report['firstFailedLedger'] = first_response['ledger'][0]
        self.passed(CHECKS[0])

        self.begin(CHECKS[1])
        self.tap(continuation.GENERATE)
        self.wait_label(RETRY_CONFIRM, 20)
        receipt, network = self.wait_requests(2)
        one, two = [item['fields'] for item in network['requests'][:2]]
        if one != two:
            raise AssertionError('Original request recheck changed POST fields or request_id')
        if network['responses'][1]['status'] != 409:
            raise AssertionError('Original recheck did not return correlated possible-charge conflict')
        if len(receipt['calls']) != 1:
            raise AssertionError('Original recheck silently called the provider again')
        self.touch_disabled(continuation.GENERATE)
        receipt, network = self.network()
        if len(network['requests']) != 2 or len(receipt['calls']) != 1:
            raise AssertionError('Retry was possible before explicit possible-charge confirmation')
        self.passed(CHECKS[1])

        self.begin(CHECKS[2])
        self.tap(RETRY_CONFIRM)
        self.tap(continuation.GENERATE)
        self.wait_label(continuation.READY, 40)
        receipt, network = self.wait_requests(3)
        one, two, three = [item['fields'] for item in network['requests'][:3]]
        stable = ['person_id','pair_id','context','host','approved','mode','task_type','text','goal']
        if any(one.get(key) != three.get(key) for key in stable):
            raise AssertionError('Explicit retry changed an original semantic POST field')
        if one['request_id'] != two['request_id'] or three['request_id'] == one['request_id']:
            raise AssertionError('Retry request ID correlation is invalid')
        if 'retry_of' in one or 'acknowledge_possible_charge' in one or 'retry_of' in two or 'acknowledge_possible_charge' in two:
            raise AssertionError('Unconfirmed requests carried retry authorization fields')
        if three.get('retry_of') != one['request_id'] or three.get('acknowledge_possible_charge') is not True:
            raise AssertionError('Confirmed retry did not carry exact retry_of authorization')
        if any(item.get('unknownKeys') for item in network['requests']):
            raise AssertionError('Analyze POST contained fields outside the reviewed allowlist')
        self.report['requestFieldComparison'] = {
            'stableFields': stable, 'originalRequestId': one['request_id'],
            'retryRequestId': three['request_id'], 'retryOf': three['retry_of'],
            'originalAndRecheckExact': one == two,
        }
        self.passed(CHECKS[2])

        self.begin(CHECKS[3])
        final = network['responses'][2]
        if final['status'] != 200 or len(final['ledger']) != 2 or len(receipt['calls']) != 3:
            raise AssertionError('Explicit retry did not complete exactly one model/judge pair')
        old, new = final['ledger']
        if old != self.report['firstFailedLedger']:
            raise AssertionError('Explicit retry mutated the original charged ledger')
        if old['id'] != one['request_id'] or new['id'] != three['request_id'] or new['state'] != 'DONE':
            raise AssertionError('Final retry ledgers are not correlated to the observed request IDs')
        main_calls = [call for call in receipt['calls'] if call.get('judge') is False]
        judge_calls = [call for call in receipt['calls'] if call.get('judge') is True]
        if [call.get('chat') for call in main_calls] != [continuation.ONE, continuation.ONE]:
            raise AssertionError('Failed and retried main calls did not use the exact approved fragment')
        if [call.get('chat') for call in judge_calls] != [continuation.ONE]:
            raise AssertionError('Successful retry did not receive exactly one independent judge call')
        self.report['observedApprovedModelPayloads'] = [continuation.ONE, continuation.ONE]
        self.report['observedSyntheticProviderCalls'] = 3
        self.tap(continuation.HISTORY)
        self.wait_label(continuation.ONE)
        self.tap(continuation.GENERATE)
        self.wait_label(continuation.DUPLICATE)
        receipt, network = self.network()
        if len(network['requests']) != 3 or len(receipt['calls']) != 3:
            raise AssertionError('Completed retried fragment was submitted again')
        self.tap(continuation.STOP)
        self.require_fresh_state(NAME)
        self.passed(CHECKS[3])


if __name__ == '__main__':
    os.environ['LENS_SYNTHETIC_SCENARIO'] = 'keyboard-retry'
    os.environ['LENS_SYNTHETIC_REPLY_DELAY_MS'] = '0'
    first.main(qa_factory=RetryQA, output_group='keyboard-retry-qa', description=__doc__)
