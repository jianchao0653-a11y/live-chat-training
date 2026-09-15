"""Actual 120-second Android read-timeout QA on the owned synthetic emulator.

The temporary loopback fixture accepts one allowlisted analyze POST and holds
the response open without invoking the provider. The production NativeClient
timeout is unchanged. The UI must return to a recoverable, non-insertable state
without an automatic retry. No real provider, account or private input is used.
"""
import json
import os
import time
import keyboard_first_qa as first
import keyboard_continuation_qa as continuation

NAME = 'qatimeout'
CHECKS = [
    'request_remains_pending_before_real_timeout',
    'native_client_times_out_after_120_seconds',
    'timeout_does_not_retry_or_expose_candidate',
    'actual_stop_clears_timed_out_context',
]


class TimeoutQA(continuation.ContinuationQA):
    def __init__(self, folder):
        super().__init__(folder)
        self.report.update(
            suite='keyboard-timeout', checks={name: 'NOT_RUN' for name in CHECKS},
            scope='Actual unchanged NativeClient 120-second read timeout against an owned held loopback response',
            notCovered=['possible-charge retry', '15-minute expiry', 'OEM/real phone/provider quality'])

    def network(self):
        path = self.folder/'fixture-receipt.json'
        if path.stat().st_size > 2_000_000:
            raise AssertionError('Oversized synthetic fixture receipt')
        receipt = json.loads(path.read_text(encoding='utf-8'))
        value = receipt.get('network', {})
        if receipt.get('synthetic') is not True or receipt.get('realProviderCalls') != 0 or value.get('fixtureError'):
            raise AssertionError('Invalid owned timeout fixture')
        if value.get('scenario') != 'keyboard-timeout':
            raise AssertionError('Wrong synthetic timeout scenario')
        return receipt, value

    def no_candidate(self, checkpoint):
        tree = self.tree(checkpoint)
        window = self.ime_window(tree)
        if any(node.get('hint') == first.DRAFT or '并插入' in node.get('text', '') for node in window.iter('node')):
            raise AssertionError('Timeout exposed a candidate or insertion action')
        self.unchanged_host()

    def main_flow(self):
        self.begin(CHECKS[0])
        self.tap('老用户维护', kind='description')
        self.wait_label('新增客户')
        self.new_customer(NAME)
        self.select_customer(NAME)
        self.tap(continuation.START)
        self.enter_fragment('hello')
        self.approve(NAME)
        started = time.monotonic()
        self.tap(continuation.GENERATE)
        self.wait(lambda tree: '正在生成，请稍候…' in self.texts(tree), 'Pending timeout state not visible', 5)
        time.sleep(5)
        receipt, network = self.network()
        if network.get('analyzeRequests') != 1 or not network.get('timeoutHeld') or receipt.get('calls'):
            raise AssertionError('Fixture did not hold exactly one provider-free analyze request')
        self.no_candidate('timeout-still-pending')
        self.passed(CHECKS[0])

        self.begin(CHECKS[1])
        self.wait(lambda tree: any('原片段已锁定，可按原请求重查' in text for text in self.texts(tree)),
                  'NativeClient did not surface its real read timeout', 145)
        deadline = time.monotonic()+10
        while time.monotonic() < deadline:
            receipt, network = self.network()
            if network.get('timeoutClosedAfterMs') is not None:
                break
            time.sleep(.1)
        elapsed = time.monotonic()-started
        closed_ms = network.get('timeoutClosedAfterMs')
        if closed_ms is None or not 118000 <= closed_ms <= 145000 or not 118 <= elapsed <= 150:
            raise AssertionError(f'Observed timeout outside the real 120-second tolerance: host={elapsed:.3f}s fixture={closed_ms}ms')
        self.report['timeoutTiming'] = {'hostElapsedSeconds': round(elapsed, 3), 'fixtureConnectionOpenMs': closed_ms,
                                        'configuredProductReadTimeoutMs': 120000}
        self.passed(CHECKS[1])

        self.begin(CHECKS[2])
        end = time.monotonic()+5
        observations = 0
        while time.monotonic() < end:
            self.no_candidate('timeout-no-auto-retry')
            receipt, network = self.network()
            if network.get('analyzeRequests') != 1 or len(network.get('requests', [])) != 1 or receipt.get('calls'):
                raise AssertionError('Timed-out request automatically retried or invoked a provider')
            observations += 1
        self.report['postTimeoutObservations'] = observations
        self.passed(CHECKS[2])

        self.begin(CHECKS[3])
        self.tap(continuation.STOP)
        self.require_fresh_state(NAME)
        self.no_candidate('timeout-after-stop')
        self.passed(CHECKS[3])


if __name__ == '__main__':
    os.environ['LENS_SYNTHETIC_SCENARIO'] = 'keyboard-timeout'
    os.environ['LENS_SYNTHETIC_REPLY_DELAY_MS'] = '0'
    first.main(qa_factory=TimeoutQA, output_group='keyboard-timeout-qa', description=__doc__)

