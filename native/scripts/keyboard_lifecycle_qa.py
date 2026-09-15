"""Actual-touch pending-response invalidation across four Android lifecycles.

Each owned synthetic REPLY waits 30 seconds. While it is pending, the suite
hides the IME, switches to normal mode, rotates the emulator, or force-stops and
restarts only the synthetic app process. Every late response must finish in the
fixture yet remain absent after the keyboard is reopened. No real provider,
private input, personal device or runtime database is used.
"""
import json
import os
import re
import time
import keyboard_first_qa as first
import keyboard_continuation_qa as continuation

NAME = 'qalifecycle'
CHECKS = [
    'hide_keyboard_invalidates_pending_response',
    'switch_mode_invalidates_pending_response',
    'rotation_invalidates_pending_response',
    'process_restart_invalidates_pending_response',
]


class LifecycleQA(continuation.ContinuationQA):
    def __init__(self, folder):
        super().__init__(folder)
        self.report.update(
            suite='keyboard-lifecycle', checks={name: 'NOT_RUN' for name in CHECKS},
            scope='Actual pending REPLY invalidation on IME hide, mode switch, rotation and app process restart',
            notCovered=['screen lock/call interruption', 'OEM/real phone/provider quality'])
        self.request_index = 0

    def receipt(self):
        path = self.folder/'fixture-receipt.json'
        if path.stat().st_size > 2_000_000:
            raise AssertionError('Oversized synthetic fixture receipt')
        value = json.loads(path.read_text(encoding='utf-8'))
        if value.get('synthetic') is not True or value.get('realProviderCalls') != 0 or value.get('errorType'):
            raise AssertionError('Invalid owned lifecycle fixture')
        return value

    def wait_calls(self, count, timeout=45):
        deadline = time.monotonic()+timeout
        while time.monotonic() < deadline:
            value = self.receipt()
            if len(value.get('calls', [])) >= count:
                return value
            time.sleep(.15)
        raise AssertionError(f'Lifecycle fixture did not reach {count} provider calls')

    def open_customer(self):
        first.q.focus_practice_editor(False)
        first.q.wait_keyboard()
        self.tap('老用户维护', kind='description')
        self.wait_label('选择：'+NAME+' · 微信')
        self.select_customer(NAME)
        self.require_fresh_state(NAME)

    def start_pending(self, word):
        self.tap(continuation.START)
        self.enter_fragment(word)
        self.approve(NAME)
        self.tap(continuation.GENERATE)
        self.wait(lambda tree: '正在生成，请稍候…' in self.texts(tree), 'Pending lifecycle request not visible', 5)
        self.request_index += 1
        value = self.wait_calls(self.request_index*2-1, 8)
        calls = value['calls']
        current = calls[-1]
        if current.get('judge') is not False or current.get('chat') != '对方：'+word:
            raise AssertionError('Lifecycle request did not use the exact approved fragment')
        self.unchanged_host()

    def wait_late_and_reopen(self):
        value = self.wait_calls(self.request_index*2, 45)
        current = value['calls'][-2:]
        if [item.get('judge') for item in current] != [False, True] or current[0].get('chat') != current[1].get('chat'):
            raise AssertionError('Delayed lifecycle request did not finish one main/judge pair')
        time.sleep(2)
        self.open_customer()
        tree = self.tree('lifecycle-reopened')
        if continuation.READY in self.texts(tree) or any(node.get('hint') == first.DRAFT for node in self.ime_window(tree).iter('node')):
            raise AssertionError('Late lifecycle response restored a candidate after reopening')

    @staticmethod
    def ime_visible(tree):
        return any(node.get('description') == '切换输入法' for node in tree.iter('node'))

    @staticmethod
    def landscape(tree):
        bounds = [list(map(int, re.findall(r'-?\d+', node.get('bounds', '')))) for node in tree.iter('node')]
        bounds = [item for item in bounds if len(item) == 4]
        return max(item[2] for item in bounds) > max(item[3] for item in bounds)

    def wait_orientation(self, landscape, timeout=12):
        deadline = time.monotonic()+timeout
        while time.monotonic() < deadline:
            tree = self.tree('landscape' if landscape else 'portrait')
            if self.landscape(tree) is landscape:
                return tree
            time.sleep(.2)
        raise AssertionError('Emulator did not reach expected orientation')

    def main_flow(self):
        original_auto = first.q.adb('shell','settings','get','system','accelerometer_rotation')
        original_rotation = first.q.adb('shell','settings','get','system','user_rotation')
        try:
            self.tap('老用户维护', kind='description')
            self.wait_label('新增客户')
            self.new_customer(NAME)
            self.select_customer(NAME)

            self.begin(CHECKS[0])
            self.start_pending('hide')
            self.record('system_key', 'BACK hides IME during pending request')
            first.q.adb('shell','input','keyevent','4')
            deadline = time.monotonic()+8
            while time.monotonic() < deadline:
                if not self.ime_visible(self.tree('ime-hidden')):
                    break
                time.sleep(.2)
            else:
                raise AssertionError('BACK did not hide the pending IME')
            self.wait_late_and_reopen()
            self.passed(CHECKS[0])

            self.begin(CHECKS[1])
            self.start_pending('mode')
            self.tap('普通输入', kind='description')
            first.q.wait_keyboard()
            if not first.q.key_nodes(tree=self.tree('normal-after-switch'), description='q', enabled=True):
                raise AssertionError('Pending request did not switch to normal input mode')
            self.wait_late_and_reopen()
            self.passed(CHECKS[1])

            self.begin(CHECKS[2])
            self.start_pending('rotate')
            first.q.adb('shell','settings','put','system','accelerometer_rotation','0')
            first.q.adb('shell','settings','put','system','user_rotation','1')
            self.wait_orientation(True)
            first.q.adb('shell','settings','put','system','user_rotation','0')
            self.wait_orientation(False)
            self.wait_late_and_reopen()
            self.passed(CHECKS[2])

            self.begin(CHECKS[3])
            self.start_pending('death')
            old_pid = first.q.adb('shell','pidof',first.PACKAGE).strip()
            if not re.fullmatch(r'\d+', old_pid):
                raise AssertionError('Synthetic app process identity is ambiguous')
            self.record('force_stop', 'owned synthetic app process '+old_pid)
            first.q.adb('shell','am','force-stop',first.PACKAGE)
            self.wait_calls(self.request_index*2, 45)
            first.q.adb('shell','am','start','-W','-n',first.PACKAGE+'/.SetupActivity')
            first.q.adb('shell','ime','enable',first.COMPONENT)
            first.q.adb('shell','ime','set',first.COMPONENT)
            first.q.focus_practice_editor(False)
            first.q.wait_keyboard()
            new_pid = first.q.adb('shell','pidof',first.PACKAGE).strip()
            if not re.fullmatch(r'\d+', new_pid) or new_pid == old_pid:
                raise AssertionError('Synthetic app process was not actually restarted')
            self.open_customer()
            tree = self.tree('process-restarted-fresh')
            if continuation.READY in self.texts(tree) or any(node.get('hint') == first.DRAFT for node in self.ime_window(tree).iter('node')):
                raise AssertionError('Process restart restored a late candidate')
            self.report['processRestart'] = {'oldPid': int(old_pid), 'newPid': int(new_pid), 'sameAppData': True}
            value = self.receipt()
            if len(value.get('calls', [])) != 8:
                raise AssertionError('Lifecycle suite did not finish exactly four main/judge pairs')
            self.report['observedSyntheticProviderCalls'] = 8
            self.passed(CHECKS[3])
        finally:
            first.q.adb('shell','settings','put','system','user_rotation',original_rotation)
            first.q.adb('shell','settings','put','system','accelerometer_rotation',original_auto)


if __name__ == '__main__':
    os.environ['LENS_SYNTHETIC_SCENARIO'] = 'keyboard-lifecycle'
    os.environ['LENS_SYNTHETIC_REPLY_DELAY_MS'] = '30000'
    first.main(qa_factory=LifecycleQA, output_group='keyboard-lifecycle-qa', description=__doc__)
