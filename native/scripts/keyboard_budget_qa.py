"""Actual-touch budget messages using the owned synthetic keyboard harness.

Does not start a device. Root must exclusively own emulator-5556/LensPreview,
the current loopback debug APK and DumpRunner before executing this suite.
Five actual OPENING submissions hit real budget checks in an explicitly
selected temporary fixture. No private inputs or real model calls are used.
"""
import json
import os
import re
import time
import keyboard_first_qa as first

NAME = 'qabudget'
SCENARIOS = [
    ('daily', ['PROJECT_DAILY_AMOUNT'], 1789084800000,
     ['全项目今天的金额额度不足以预留本次分析。', '2026-09-11 08:00（北京时间）']),
    ('monthly', ['PROJECT_MONTHLY_AMOUNT'], 1790812800000,
     ['全项目本月的金额额度不足以预留本次分析。', '2026-10-01 08:00（北京时间）']),
    ('both', ['PROJECT_DAILY_AMOUNT', 'PROJECT_MONTHLY_AMOUNT'], 1790812800000,
     ['全项目今天的金额额度不足以预留本次分析。', '全项目本月的金额额度不足以预留本次分析。',
      '2026-09-11 08:00（北京时间）', '最早可在 2026-10-01 08:00（北京时间）']),
    ('paused', ['BUDGET_PROTECTION_PAUSED'], None,
     ['模型用量触发保护，已暂停新分析', '等待额度重置不会解除暂停。']),
    ('missing', ['BUDGET_NOT_CONFIGURED'], None,
     ['模型预算尚未完成配置，需要开发端核对', '等待额度重置不会自动恢复。'])
]


class BudgetQA(first.QA):
    fixture_name = 'keyboard_budget_fixture.mjs'

    def __init__(self, folder):
        super().__init__(folder)
        self.report.update({'suite': 'keyboard-budget', 'scope': 'five real keyboard budget rejection messages with synthetic ledgers and fixed UTC clock',
                            'checks': {name+'_budget_message': 'NOT_RUN' for name, *_ in SCENARIOS},
                            'notCovered': ['real account budgets', 'real provider quality', 'OEM or physical phone',
                                           'optical typography inspection', 'older client without budget_block']})

    def receipt(self):
        path = self.folder/'fixture-receipt.json'
        if path.stat().st_size > 2_000_000:
            raise AssertionError('Synthetic fixture evidence exceeded the size bound')
        receipt = json.loads(path.read_text(encoding='utf-8'))
        if receipt.get('synthetic') is not True or receipt.get('scenario') != 'keyboard-budget' or receipt.get('realProviderCalls') != 0 or receipt.get('calls') != []:
            raise AssertionError('Only the explicit budget fixture with zero model calls is accepted')
        return receipt

    def read_whole_message(self, text, name):
        # Accessibility provides the exact status text. Real bounded swipes must
        # also make both ends reachable; an off-screen text match is insufficient.
        self.reach(text)
        top_seen = bottom_seen = False
        views = []
        for _ in range(16):
            tree = self.tree(name+'-message-view')
            nodes = [n for n in self.ime_window(tree).iter('node') if n.get('text') == text]
            if len(nodes) != 1:
                raise AssertionError('Expected one unchanged budget status message')
            node = nodes[0]
            raw = first.q.node_bounds(node)
            visible = self.clipped(node, tree)
            if raw[0] < visible[0] or raw[2] > visible[2]:
                raise AssertionError('Budget status is horizontally clipped')
            top_seen = top_seen or (visible[1] <= raw[1] < visible[3]-4)
            bottom_seen = bottom_seen or (visible[1]+4 < raw[3] <= visible[3])
            views.append({'nodeBounds': raw, 'visibleBounds': visible})
            if top_seen and bottom_seen:
                self.report.setdefault('messageViews', {})[name] = {'topReachable': True, 'bottomReachable': True, 'views': views}
                return
            left, top, right, bottom = self.viewport(tree, 'panel', node)
            # Reveal the missing beginning first, then read through the end.
            down = top_seen
            start = top+int((bottom-top)*(.78 if down else .22))
            end = top+int((bottom-top)*(.22 if down else .78))
            self.record('budget_message_swipe', name+(' toward end' if down else ' toward beginning'))
            first.q.adb('shell', 'input', 'swipe', (left+right)//2, start, (left+right)//2, end, 250)
            time.sleep(.15)
        raise AssertionError('The complete budget status was not reachable by bounded scrolling')

    def check_rejection(self, ordinal, scenario, codes, reset, markers):
        tree = self.wait(lambda current: any(all(marker in value for marker in markers) and '\n问题编号：' in value for value in self.texts(current)),
                         'The keyboard did not display the exact budget cause/date', 30)
        matches = [value for value in self.texts(tree) if all(marker in value for marker in markers) and '\n问题编号：' in value]
        if len(matches) != 1:
            raise AssertionError('Expected one correlated budget message')
        visible = matches[0]
        receipt = self.receipt()
        attempts = receipt.get('attempts', [])
        if len(attempts) != ordinal:
            raise AssertionError('A UI submission was missing or silently repeated')
        attempt = attempts[-1]
        block = attempt.get('budgetBlock') or {}
        if attempt.get('scenario') != scenario or attempt.get('taskType') != 'OPENING' or attempt.get('status') != (503 if reset is None else 429):
            raise AssertionError('The UI did not reach the expected real budget check')
        if [item.get('code') for item in block.get('reasons', [])] != codes or block.get('reset_at') != reset or block.get('day_timezone') != 'UTC':
            raise AssertionError('Budget reasons or UTC reset metadata differ from the scenario')
        if visible.split('\n问题编号：', 1)[0] != block.get('message'):
            raise AssertionError('The client clipped, changed or ignored the server budget message')
        if not re.fullmatch(r'[0-9a-f-]{36}', visible.split('\n问题编号：', 1)[1]):
            raise AssertionError('The error lost its correlated request number')
        if scenario == 'monthly' and '2026-09-11' in visible:
            raise AssertionError('Monthly exhaustion was incorrectly presented as recovering tomorrow')
        if reset is None and ('最早可在' in visible or re.search(r'\d{4}-\d{2}-\d{2} 08:00', visible)):
            raise AssertionError('A paused or unconfigured service promised a cycle recovery')
        if attempt.get('ledgerBeforeSha256') != receipt.get('initialLedgerSha256') or attempt.get('ledgerAfterSha256') != receipt.get('initialLedgerSha256'):
            raise AssertionError('Rejected work changed the original uncertain spend')
        if attempt.get('providerCallsBefore') != 0 or attempt.get('providerCallsAfter') != 0:
            raise AssertionError('Rejected work reached a model')
        for node in self.ime_window(tree).iter('node'):
            if node.get('hint') == first.DRAFT or '并插入' in node.get('text', '') or node.get('text') == first.CANDIDATE:
                raise AssertionError('Budget rejection exposed a candidate or insertion action')
        self.read_whole_message(visible, scenario)
        self.unchanged_host()
        self.report.setdefault('budgetMessages', {})[scenario] = {'text': visible, 'reasonCodes': codes, 'resetAt': reset,
                                                                 'candidateAbsent': True, 'modelCalls': 0, 'ledgerUnchanged': True}

    def main_flow(self):
        if self.receipt().get('attempts'):
            raise AssertionError('The fixture must be fresh before touching the keyboard')
        self.tap('新用户破冰', kind='description')
        self.wait_label('新增客户')
        self.new_customer(NAME)
        self.select_customer(NAME)
        self.tap('新客破冰')
        for ordinal, (scenario, codes, reset, markers) in enumerate(SCENARIOS, 1):
            self.begin(scenario+'_budget_message')
            if ordinal > 1:
                # Actual task switches clear the previous request/error locally.
                # No clipboard or injected internal text is used.
                self.tap('新客画像')
                self.tap('新客破冰')
            self.approve(NAME)
            self.tap('生成已批准内容')
            self.check_rejection(ordinal, scenario, codes, reset, markers)
            self.passed(scenario+'_budget_message')
        self.report['observedSyntheticProviderCalls'] = len(self.receipt()['calls'])


if __name__ == '__main__':
    os.environ['LENS_SYNTHETIC_SCENARIO'] = 'keyboard-budget'
    first.main(qa_factory=BudgetQA, output_group='keyboard-budget-qa', description=__doc__)
