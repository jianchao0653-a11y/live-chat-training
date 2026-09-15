"""Actual IME recovery after a synthetic response is lost after server commit.

The real owned cloud handler, budget and cached-result route are used. Only the
first analyze socket is destroyed at res.end. No real provider or runtime DB.
"""
import json
import os
import time
import keyboard_first_qa as first
import keyboard_continuation_qa as continuation

NAME = 'qanetwork'
CHECKS = ['committed_response_loss_is_visible', 'unknown_result_does_not_automatically_retry',
          'explicit_recheck_reuses_result_without_new_charge', 'recovered_fragment_committed_once']


class NetworkQA(continuation.ContinuationQA):
    def __init__(self, folder):
        super().__init__(folder)
        self.report.update(suite='keyboard-network', checks={name: 'NOT_RUN' for name in CHECKS},
                           scope='Real-touch original-result recheck after response loss on owned synthetic service',
                           notCovered=['explicit retry_of after uncertain provider failure', 'actual 120-second timeout',
                                       '15-minute expiry', 'notification capture Stop', 'real phone/OEM/provider quality'])

    def network(self):
        path = self.folder/'fixture-receipt.json'
        if path.stat().st_size > 2000000:
            raise AssertionError('Oversized synthetic fixture receipt')
        receipt = json.loads(path.read_text(encoding='utf-8'))
        value = receipt.get('network', {})
        if receipt.get('synthetic') is not True or receipt.get('realProviderCalls') != 0 or value.get('fixtureError'):
            raise AssertionError('Invalid owned network fixture')
        if value.get('scenario') != 'keyboard-network':
            raise AssertionError('Wrong synthetic scenario')
        return value

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
                  'Lost response did not display original-request recovery state', 40)
        state = self.network()
        if state['analyzeRequests'] != 1 or len(state['responses']) != 1:
            raise AssertionError('Unexpected analyze count before user recheck')
        original = state['responses'][0]
        if original['status'] != 200 or not original['droppedAfterCommit'] or not original['analysisId']:
            raise AssertionError('Response was not lost after successful analysis commit')
        ledger = original['ledger']
        if len(ledger) != 1 or ledger[0]['state'] != 'DONE' or ledger[0]['calls'] != 2 or ledger[0]['charged'] <= 0:
            raise AssertionError('Expected one completed charged synthetic task')
        self.assert_model_payloads([continuation.ONE])
        self.report['originalCompletedResponse'] = original
        self.unchanged_host()
        self.passed(CHECKS[0])

        self.begin(CHECKS[1])
        self.touch_disabled('x', scope='keys', kind='description')
        if self.field_text(continuation.CHAT) != continuation.ONE:
            raise AssertionError('Unknown request allowed its approved fragment to change')
        end = time.monotonic()+5
        while time.monotonic() < end:
            tree = self.tree('unknown-result-no-auto-retry')
            if any(n.get('hint') == first.DRAFT or '并插入' in n.get('text', '')
                   for n in self.ime_window(tree).iter('node')):
                raise AssertionError('Unknown response exposed insertion controls')
            if self.network()['analyzeRequests'] != 1:
                raise AssertionError('Unknown result automatically retried')
        self.assert_model_payloads([continuation.ONE])
        self.passed(CHECKS[1])

        self.begin(CHECKS[2])
        self.tap(continuation.GENERATE)
        self.wait_label(continuation.READY, 40)
        state = self.network()
        if state['analyzeRequests'] != 2 or len(state['responses']) != 2:
            raise AssertionError('Explicit recheck did not issue exactly one request')
        recovered = state['responses'][1]
        if recovered['status'] != 200 or recovered['droppedAfterCommit']:
            raise AssertionError('Recheck response did not succeed normally')
        for key in ('analysisId', 'context', 'budget', 'ledger', 'providerCalls'):
            if recovered[key] != original[key]:
                raise AssertionError('Original result/ledger changed during recheck: '+key)
        self.assert_model_payloads([continuation.ONE])
        self.report['recoveredResponse'] = recovered
        self.unchanged_host()
        self.passed(CHECKS[2])

        self.begin(CHECKS[3])
        self.tap(continuation.HISTORY)
        self.wait_label(continuation.ONE)
        self.tap(continuation.GENERATE)
        self.wait_label(continuation.DUPLICATE)
        if self.network()['analyzeRequests'] != 2:
            raise AssertionError('Recovered fragment was submitted a third time')
        self.tap(continuation.STOP)
        self.require_fresh_state(NAME)
        self.assert_model_payloads([continuation.ONE])
        self.passed(CHECKS[3])


if __name__ == '__main__':
    os.environ['LENS_SYNTHETIC_SCENARIO'] = 'keyboard-network'
    os.environ['LENS_SYNTHETIC_REPLY_DELAY_MS'] = '0'
    first.main(qa_factory=NetworkQA, output_group='keyboard-network-qa', description=__doc__)
