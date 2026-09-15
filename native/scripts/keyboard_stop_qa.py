"""Actual-touch stop during a delayed synthetic REPLY on the owned project AVD.

Uses the existing fixture's bounded 30-second delay; no product timeout changes,
private input, real provider, direct service stop, or synthetic UI performClick.
The current build12 APK is reused. Capture notification Stop is a separate gate.
"""
import os
import time
import keyboard_first_qa as first
import keyboard_continuation_qa as continuation

NAME = 'qastop'
STOPPED = '已停止本次连续维护，临时片段已清空。已提交的分析可在客户历史中管理。'
CHARGE = '已发出的请求可能仍在处理或计费，停止不会撤回已产生的费用。'
CHECKS = ['pending_request_observed_before_stop', 'actual_stop_clears_context_and_approvals',
          'late_response_cannot_restore_stopped_result', 'fresh_session_excludes_stopped_fragment',
          'normal_keyboard_and_host_unchanged']


class StopQA(continuation.ContinuationQA):
    def __init__(self, folder):
        super().__init__(folder)
        self.report.update(suite='keyboard-stop', checks={name: 'NOT_RUN' for name in CHECKS},
                           scope='Actual IME stop during in-flight synthetic REPLY and late-result rejection',
                           notCovered=['notification capture Stop', 'network unknown/retry_of recovery',
                                       'actual 120-second network timeout', '15-minute session expiry',
                                       'process death/rotation/OEM/real provider quality'])

    def no_result(self, checkpoint):
        tree = self.tree(checkpoint)
        self.ime_window(tree)
        for node in self.ime_window(tree).iter('node'):
            if node.get('hint') == first.DRAFT or '并插入' in node.get('text', ''):
                raise AssertionError('A stopped response restored a candidate or insertion action')
        if continuation.READY in self.texts(tree):
            raise AssertionError('A stopped request restored its ready status')
        self.unchecked(NAME)
        self.unchanged_host()

    def main_flow(self):
        self.begin('pending_request_observed_before_stop')
        self.tap('老用户维护', kind='description')
        self.wait_label('新增客户')
        self.new_customer(NAME)
        self.select_customer(NAME)
        self.tap(continuation.START)
        self.enter_fragment('hello')
        self.approve(NAME)
        self.tap(continuation.GENERATE)
        self.wait(lambda tree: '正在生成，请稍候…' in self.texts(tree)
                  and self.controls_enabled(tree, NAME, False), 'Pending state not observed', 5)
        self.assert_model_payloads([continuation.ONE], judge_complete=False)
        calls = self.fixture_calls()
        if len(calls) != 1 or calls[0].get('judge') is not False:
            raise AssertionError('The first response already completed before Stop could be tested')
        self.report['beforeStop'] = {'monotonic': time.monotonic(), 'syntheticCalls': len(calls),
                                    'pendingInputLocked': True}
        self.passed('pending_request_observed_before_stop')

        self.begin('actual_stop_clears_context_and_approvals')
        self.tap(continuation.STOP)
        self.wait_label(STOPPED+'\n'+CHARGE)
        self.require_fresh_state(NAME)
        if len(self.fixture_calls()) != 1:
            raise AssertionError('Stop must be observed before the delayed reply completes')
        self.report['afterStop'] = {'monotonic': time.monotonic(), 'syntheticCalls': 1,
                                   'realStopTouch': True, 'possibleChargeMessageVisible': True}
        self.no_result('stopped-no-result')
        self.passed('actual_stop_clears_context_and_approvals')

        self.begin('late_response_cannot_restore_stopped_result')
        deadline = time.monotonic()+40
        while len(self.fixture_calls()) < 2:
            if time.monotonic() >= deadline:
                raise AssertionError('Delayed original reply did not reach its synthetic judge')
            self.no_result('waiting-for-stopped-response')
            time.sleep(.25)
        self.assert_model_payloads([continuation.ONE])
        # Allow the completed response to reach the Android main-thread callback.
        # Repeated actual UI snapshots observe the stopped state, rather than
        # treating the provider invocation alone as callback completion proof.
        observed_until = time.monotonic()+5
        observations = 0
        while time.monotonic() < observed_until:
            self.no_result('late-response-still-stopped')
            self.require_fresh_state(NAME)
            observations += 1
        self.report['lateResponse'] = {'syntheticCalls': 2, 'observations': observations,
                                       'lastObservedAt': time.monotonic(), 'oldCandidateAbsent': True,
                                       'scope': 'UI observed after delayed main/judge calls; fresh request below also completes'}
        self.passed('late_response_cannot_restore_stopped_result')

        self.begin('fresh_session_excludes_stopped_fragment')
        self.tap(continuation.START)
        self.enter_fragment('fresh')
        self.generate(NAME, [continuation.ONE, continuation.FRESH])
        self.tap(continuation.HISTORY)
        self.wait_label(continuation.FRESH)
        if continuation.ONE in self.texts():
            raise AssertionError('Restart reused the stopped fragment as visible approved history')
        self.assert_model_payloads([continuation.ONE, continuation.FRESH])
        self.passed('fresh_session_excludes_stopped_fragment')

        self.begin('normal_keyboard_and_host_unchanged')
        self.tap(continuation.STOP)
        self.require_fresh_state(NAME)
        self.tap('普通输入', kind='description')
        self.wait(lambda tree: bool(first.q.key_nodes(tree=tree, description='空格', enabled=True)),
                  'Normal keyboard did not return')
        self.unchanged_host()
        self.assert_model_payloads([continuation.ONE, continuation.FRESH])
        self.passed('normal_keyboard_and_host_unchanged')


if __name__ == '__main__':
    os.environ['LENS_SYNTHETIC_SCENARIO'] = 'default'
    os.environ['LENS_SYNTHETIC_REPLY_DELAY_MS'] = '30000'
    first.main(qa_factory=StopQA, output_group='keyboard-stop-qa', description=__doc__)
