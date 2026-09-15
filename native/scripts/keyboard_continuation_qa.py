"""Standalone synthetic continuous-maintenance QA using actual ADB touches.

Requires the current 0.18.0/code23 loopback debug APK and an already booted
emulator-5556/LensPreview AVD. Owns the same bounded fake cloud setup/cleanup as
keyboard_first_qa.py, but writes a separate continuation receipt and does not
change its nine delivery checks. Never starts a device or uses a real provider.
"""
import json
import os
import time
import keyboard_first_qa as first

CHAT = '输入或粘贴聊天片段，请注明双方发言'
START = '开启本次连续维护'
STOP = '停止本次连续维护'
GENERATE = '生成已批准内容'
NEXT = '补充下一段对话'
HISTORY = '查看本次已批准片段'
READY = '建议已生成，请选择并编辑候选。'
DUPLICATE = '这段对话已分析，请补充新的内容；本次未请求模型。'
REPLY = '今天过得怎么样？有空的话，想听你说说。'
ONE = '对方：hello'
TWO = '对方：thanks'
FRESH = '对方：fresh'
OTHER = '对方：other'
CONTINUATION_CHECKS = ['explicit_enable_does_not_submit', 'pending_input_and_duplicate_touch_are_blocked',
                       'first_round_exact_approved_payload', 'duplicate_round_has_no_new_model_calls',
                       'next_fragment_without_insertion_unlocks', 'second_round_exact_approved_accumulation',
                       'confirmed_insertion_keeps_current_maintenance', 'stop_clears_temporary_context',
                       'restart_does_not_reuse_stopped_history', 'customer_switch_does_not_mix_context']


class ContinuationQA(first.QA):
    def __init__(self, folder):
        super().__init__(folder)
        self.report['suite'] = 'keyboard-continuation'
        self.report['checks'] = {name: 'NOT_RUN' for name in CONTINUATION_CHECKS}
        self.report['scope'] = 'synthetic explicitly enabled continuous maintenance; approved fragments only'
        self.report['notCovered'] = ['network failure/retry_of recovery', 'stop during in-flight response',
                                     '15-minute expiry on device', 'OEM or real-provider quality']

    def fixture_calls(self):
        path = self.folder/'fixture-receipt.json'
        if path.stat().st_size > 2_000_000:
            raise AssertionError('Synthetic fixture evidence exceeded its size bound')
        receipt = json.loads(path.read_text(encoding='utf-8'))
        if receipt.get('synthetic') is not True or receipt.get('realProviderCalls') != 0:
            raise AssertionError('Only the owned synthetic provider is permitted')
        calls = receipt.get('calls', [])
        if any(call.get('taskType') != 'REPLY' for call in calls):
            raise AssertionError('Continuation fixture unexpectedly received another task type')
        return calls

    def assert_model_payloads(self, expected, *, judge_complete=True):
        calls = self.fixture_calls()
        main_calls = [call for call in calls if call.get('judge') is False]
        if [call.get('chat') for call in main_calls] != expected:
            raise AssertionError('Model input contains missing, duplicated, unapproved or cross-customer chat')
        if any(call.get('goal') != '自然接话' for call in main_calls):
            raise AssertionError('Maintenance goal changed unexpectedly')
        if judge_complete:
            judge_calls = [call for call in calls if call.get('judge') is True]
            if [call.get('chat') for call in judge_calls] != expected or len(calls) != 2*len(expected):
                raise AssertionError('Each approved round must have exactly one model and one judge call')
        self.report['observedApprovedModelPayloads'] = expected
        self.report['observedSyntheticProviderCalls'] = len(calls)

    def enter_fragment(self, word):
        self.focus(CHAT)
        if self.field_text(CHAT):
            raise AssertionError('A new fragment editor must be empty before typing')
        self.language(True)
        if first.q.key_nodes(tree=self.ime_tree(), description='切换全键盘', enabled=True):
            self.key('切换全键盘')
        for letter in 'duifang':
            self.key(letter)
        self.candidate('对方')
        self.key('符')
        self.key('：')
        self.key('返回文字键盘')
        self.ascii(word)
        expected = '对方：'+word
        self.wait(lambda tree: self.field_text(CHAT, tree) == expected, 'Typed fragment did not stay in its local editor')
        self.unchanged_host()

    def controls_enabled(self, tree, name, enabled):
        expected = str(enabled).lower()
        controls = [self.field(CHAT, tree)]
        # Android AdapterView accessibility overwrites enabled with the selected
        # child's state. Spinner.disableChildrenWhenDisabled defaults to false,
        # so the Spinner itself can be disabled while its node reports true.
        # The pending test below proves its actual physical-touch behavior.
        self.goal_state(tree)
        for kind, value in [('text', '已核对当前聊天对象是「'+name+'」'), ('text', first.APPROVAL)]:
            matches = [node for node in self.ime_window(tree).iter('node') if node.get(kind) == value]
            if len(matches) != 1:
                raise AssertionError('Missing continuation control: '+value)
            controls.append(matches[0])
        return all(node.get('enabled') == expected for node in controls)

    def goal_state(self, tree):
        matches = [node for node in self.ime_window(tree).iter('node') if node.get('description') == '本次回复目标']
        if len(matches) != 1:
            raise AssertionError('Expected one maintenance goal Spinner')
        node = matches[0]
        values = [child.get('text') for child in node.iter('node') if child.get('text')]
        if len(values) != 1:
            raise AssertionError('Goal Spinner does not expose one selected value')
        return {'accessibilityEnabled': node.get('enabled'), 'selectedValue': values[0]}

    def assert_pending_spinner_touch_blocked(self):
        before = self.goal_state(self.ime_tree())
        if before['selectedValue'] != '自然接话':
            raise AssertionError('Unexpected initial maintenance goal')
        self.touch_disabled('本次回复目标', kind='description')
        tree = self.tree('pending-spinner-after-touch')
        after = self.goal_state(tree)
        if after['selectedValue'] != before['selectedValue'] or any(label in self.texts(tree) for label in ('关心近况', '修复误会', '表达边界')):
            raise AssertionError('A locked goal Spinner opened or changed after an actual touch')
        if '正在生成，请稍候…' not in self.texts(tree) or not self.controls_enabled(tree, 'qacont', False):
            raise AssertionError('Spinner touch was not observed during the pending lock')
        self.report['pendingSpinnerTouch'] = {'before': before, 'after': after, 'popupOpened': False,
                                              'actualTouch': True, 'goalStillLockedDuringRequest': True}

    def unchecked(self, name):
        tree = self.ime_tree()
        for label in ['已核对当前聊天对象是「'+name+'」', first.APPROVAL]:
            matches = [node for node in self.ime_window(tree).iter('node') if node.get('text') == label]
            if len(matches) != 1 or matches[0].get('checked') != 'false':
                raise AssertionError('A new fragment/customer must require new approval')

    def touch_disabled(self, value, *, scope='panel', kind='text'):
        # A physical tap on the disabled control/key tests the routing boundary.
        # Never replace this with accessibility performClick or ACTION_SET_TEXT.
        _node, (left, top, right, bottom) = self.reach(value, kind=kind, scope=scope, enabled=False)
        self.record('tap', value+' (pending request)')
        first.q.adb('shell', 'input', 'tap', (left+right)//2, (top+bottom)//2)
        time.sleep(.15)

    def generate(self, name, expected):
        self.approve(name)
        self.tap(GENERATE)
        self.wait_label(READY, 45)
        self.wait(lambda tree: self.controls_enabled(tree, name, True), 'Successful request did not unlock fragment controls')
        self.assert_model_payloads(expected)
        self.unchanged_host()

    def require_fresh_state(self, name):
        self.wait_label('当前客户：'+name+' · 微信')
        tree = self.ime_tree()
        if self.field_text(CHAT, tree) or any(node.get('hint') == first.DRAFT for node in self.ime_window(tree).iter('node')):
            raise AssertionError('Stopped or switched continuation retained its input or candidate draft')
        self.wait_label(START)
        self.unchecked(name)
        self.unchanged_host()

    def main_flow(self):
        self.begin('explicit_enable_does_not_submit')
        self.tap('老用户维护', kind='description')
        self.wait_label('新增客户')
        self.new_customer('qacont')
        self.new_customer('qaother')
        self.select_customer('qacont')
        self.tap(START)
        self.wait_label(STOP)
        self.unchecked('qacont')
        self.enter_fragment('hello')
        self.assert_model_payloads([])
        self.passed('explicit_enable_does_not_submit')

        self.begin('pending_input_and_duplicate_touch_are_blocked')
        self.approve('qacont')
        self.tap(GENERATE)
        # The fixture's bounded first-REPLY delay makes this state observable.
        # If it is unavailable, fail; never infer that a skipped pending check passed.
        self.wait(lambda tree: '正在生成，请稍候…' in self.texts(tree) and self.controls_enabled(tree, 'qacont', False),
                  'Pending request/input lock was not observed; check the synthetic delay fixture', 5)
        self.assert_pending_spinner_touch_blocked()
        self.touch_disabled('x', scope='keys', kind='description')
        self.touch_disabled(GENERATE)
        if self.field_text(CHAT) != ONE:
            raise AssertionError('Typing changed a locked pending fragment')
        self.unchanged_host()
        self.assert_model_payloads([ONE], judge_complete=False)
        self.wait_label(READY, 45)
        self.wait(lambda tree: self.controls_enabled(tree, 'qacont', True), 'Completed pending request left controls locked')
        self.assert_model_payloads([ONE])
        self.passed('pending_input_and_duplicate_touch_are_blocked')

        self.begin('first_round_exact_approved_payload')
        self.assert_model_payloads([ONE])
        self.unchanged_host()
        self.passed('first_round_exact_approved_payload')

        self.begin('duplicate_round_has_no_new_model_calls')
        self.tap(GENERATE)
        self.wait_label(DUPLICATE)
        self.assert_model_payloads([ONE])
        self.unchanged_host()
        self.passed('duplicate_round_has_no_new_model_calls')

        self.begin('next_fragment_without_insertion_unlocks')
        self.tap(NEXT)
        self.wait(lambda tree: self.field_text(CHAT, tree) == '' and self.controls_enabled(tree, 'qacont', True),
                  'Next-fragment action without insertion did not unlock and clear the editor')
        self.unchecked('qacont')
        self.enter_fragment('thanks')
        self.assert_model_payloads([ONE])
        self.passed('next_fragment_without_insertion_unlocks')

        self.begin('second_round_exact_approved_accumulation')
        both = ONE+'\n\n'+TWO
        self.generate('qacont', [ONE, both])
        self.tap(HISTORY)
        self.wait_label(both)
        self.passed('second_round_exact_approved_accumulation')

        self.begin('confirmed_insertion_keeps_current_maintenance')
        self.tap(REPLY)
        self.wait(lambda tree: self.field_text(first.DRAFT, tree) == REPLY, 'Candidate did not fill the editable draft')
        self.ascii('qa')
        exact = REPLY+'qa'
        self.wait(lambda tree: self.field_text(first.DRAFT, tree) == exact, 'Edited reply mismatch')
        self.unchanged_host()
        self.tap('确认正在与「qacont」聊天并插入')
        self.host_expected += exact
        self.wait(lambda tree: self.host_text(tree) == self.host_expected, 'Exact confirmed reply was not inserted', 40)
        self.wait_label('当前客户：qacont · 微信')
        self.wait(lambda tree: self.field_text(CHAT, tree) == '' and self.controls_enabled(tree, 'qacont', True),
                  'Confirmed insertion did not retain an unlocked maintenance panel')
        self.unchecked('qacont')
        self.assert_model_payloads([ONE, both])
        self.passed('confirmed_insertion_keeps_current_maintenance')

        self.begin('stop_clears_temporary_context')
        self.enter_fragment('unsent')
        self.assert_model_payloads([ONE, both])
        self.tap(STOP)
        self.wait_label('已停止本次连续维护，临时片段已清空。已提交的分析可在客户历史中管理。')
        self.require_fresh_state('qacont')
        if any(value in self.texts(self.ime_tree()) for value in (ONE, TWO, both, '对方：unsent')):
            raise AssertionError('Stop retained temporary approved or unapproved conversation text')
        self.assert_model_payloads([ONE, both])
        self.passed('stop_clears_temporary_context')

        self.begin('restart_does_not_reuse_stopped_history')
        self.tap(START)
        self.wait_label(STOP)
        self.enter_fragment('fresh')
        self.generate('qacont', [ONE, both, FRESH])
        self.passed('restart_does_not_reuse_stopped_history')

        self.begin('customer_switch_does_not_mix_context')
        self.tap('更换客户')
        self.wait_label('选择：qaother · 微信')
        self.select_customer('qaother')
        self.require_fresh_state('qaother')
        self.tap(START)
        self.enter_fragment('other')
        self.generate('qaother', [ONE, both, FRESH, OTHER])
        self.tap(STOP)
        self.require_fresh_state('qaother')
        self.assert_model_payloads([ONE, both, FRESH, OTHER])
        self.passed('customer_switch_does_not_mix_context')


if __name__ == '__main__':
    # Strictly synthetic and consumed only by the fake provider implementation.
    # A finite delay makes pending-state real-touch assertions reproducible.
    os.environ['LENS_SYNTHETIC_REPLY_DELAY_MS'] = '20000'
    first.main(qa_factory=ContinuationQA, output_group='keyboard-continuation-qa', description=__doc__)
