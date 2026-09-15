"""Actual 15-minute continuous-maintenance expiry QA on API 36.

The production monotonic deadline and delayed callback are unchanged. A local
synthetic fragment is typed and approved but never submitted; the suite waits
for the real deadline, verifies automatic clearing, and confirms zero provider
calls. No private input, model call or shortened test clock is used.
"""
import json
import os
import time
import keyboard_first_qa as first
import keyboard_continuation_qa as continuation

NAME = 'qaexpiry'
EXPIRED = '本次连续维护已到期，临时片段与旧候选已清空。请重新选择客户后开启。'
CHECKS = [
    'approved_fragment_present_before_expiry',
    'real_15_minute_deadline_expires_session',
    'expiry_clears_fragment_approvals_and_history',
    'expiry_uses_zero_provider_calls',
]


class ExpiryQA(continuation.ContinuationQA):
    def __init__(self, folder):
        super().__init__(folder)
        self.report.update(
            suite='keyboard-expiry', checks={name: 'NOT_RUN' for name in CHECKS},
            scope='Actual unchanged 15-minute monotonic continuous-maintenance expiry on API 36',
            notCovered=['network timeout', 'possible-charge retry', 'OEM/real phone/provider quality'])

    def main_flow(self):
        self.begin(CHECKS[0])
        self.tap('老用户维护', kind='description')
        self.wait_label('新增客户')
        self.new_customer(NAME)
        self.select_customer(NAME)
        started = time.monotonic()
        self.tap(continuation.START)
        self.enter_fragment('hello')
        self.approve(NAME)
        if self.field_text(continuation.CHAT) != continuation.ONE:
            raise AssertionError('Approved synthetic fragment missing before expiry')
        self.unchecked_after = False
        self.report['expiryStartedMonotonic'] = started
        self.passed(CHECKS[0])

        self.begin(CHECKS[1])
        self.wait_label(EXPIRED, 920)
        elapsed = time.monotonic()-started
        if not 870 <= elapsed <= 920:
            raise AssertionError(f'Observed deadline was not the real 15-minute session bound: {elapsed:.3f}s')
        self.report['expiryElapsedSeconds'] = round(elapsed, 3)
        self.passed(CHECKS[1])

        self.begin(CHECKS[2])
        self.require_fresh_state(NAME)
        tree = self.tree('expired-cleared')
        if continuation.ONE in self.texts(tree) or continuation.STOP in self.texts(tree):
            raise AssertionError('Expired continuation retained fragment/history or active Stop state')
        self.unchanged_host()
        self.passed(CHECKS[2])

        self.begin(CHECKS[3])
        receipt = json.loads((self.folder/'fixture-receipt.json').read_text(encoding='utf-8'))
        if receipt.get('synthetic') is not True or receipt.get('realProviderCalls') != 0 or receipt.get('calls'):
            raise AssertionError('Expiry test unexpectedly invoked a provider')
        self.report['observedSyntheticProviderCalls'] = 0
        self.passed(CHECKS[3])


if __name__ == '__main__':
    os.environ['LENS_SYNTHETIC_SCENARIO'] = 'default'
    os.environ['LENS_SYNTHETIC_REPLY_DELAY_MS'] = '0'
    first.main(qa_factory=ExpiryQA, output_group='keyboard-expiry-qa', description=__doc__)
