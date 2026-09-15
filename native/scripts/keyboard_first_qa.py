"""Actual-touch synthetic keyboard acceptance. Does not start an emulator.

Run after building 0.18.0/code23 cloud-debug (loopback 4317) and DumpRunner:
    python native/scripts/keyboard_first_qa.py
Only emulator-5556 and a LensPreview project AVD are accepted. This owns a new
temporary fake cloud, resets only the project's synthetic app, and leaves a
bounded hierarchy/action receipt. FLAG_SECURE is preserved; no screenshots.
"""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time
from uuid import uuid4
import zipfile
import android_qa as q

PACKAGE = 'com.conversationlens.ime'
COMPONENT = PACKAGE + '/.LensImeService'
PRACTICE = '在这里试打 nihao、zhongguo、xiexie'
APPROVAL = '已核对文字与资料，同意提交给连接的服务'
MATERIAL = '填写一份客户资料（最多2000字），校对后加入'
DRAFT = '选择候选后可用本键盘修改'
CANDIDATE = '你好呀，今天过得怎么样？'
CHECKS = ['normal_nine_key', 'normal_full_pinyin', 'keyboard_customer_create_select',
          'internal_editor_isolation', 'profile_source_date_observations',
          'opening_edit_exact_confirmed_insert', 'switch_customer_revokes_old_draft',
          'new_to_maintain_list', 'customer_memory_panel']


class QA:
    def __init__(self, folder):
        self.folder = folder
        self.report = {'status': 'RUNNING', 'synthetic': True, 'realPhone': False,
                       'realModel': False, 'realTouches': True, 'protectedScreensCaptured': False,
                       'checks': {name: 'NOT_RUN' for name in CHECKS}, 'actions': []}
        self.host_expected = ''
        self.screen = None

    def save(self):
        (self.folder/'report.json').write_text(json.dumps(self.report, ensure_ascii=False, indent=2), encoding='utf-8')

    def record(self, kind, value):
        if len(self.report['actions']) >= 1500:
            raise AssertionError('Bounded action limit reached')
        self.report['actions'].append({'action': kind, 'target': value, 'at': round(time.monotonic(), 3)})

    def passed(self, name):
        self.report['checks'][name] = 'PASS'
        self.report['activeCheck'] = None
        self.tree(name)
        self.save()
        print('PASS ' + name, flush=True)

    def begin(self, name):
        self.report['activeCheck'] = name
        self.report['checks'][name] = 'RUNNING'
        self.save()
        print('RUN ' + name, flush=True)

    def tree(self, name='ui'):
        deadline = time.monotonic()+5
        while True:
            tree = q.snapshot(name)
            packages = {node.get('package') for node in tree.iter('node')}
            # Android 8 UiAutomation can transiently return an empty hierarchy
            # or only the status/navigation bars while the verified Setup
            # activity remains resumed. Retry the current hierarchy only. A
            # real system dialog is returned immediately for consent QA.
            actionable_system_dialog = any(
                node.get('package') != PACKAGE
                and node.get('enabled') == 'true'
                and node.get('class', '').endswith('Button')
                for node in tree.iter('node')
            )
            if (str(self.report.get('api')) != '26' or PACKAGE in packages
                    or actionable_system_dialog or time.monotonic() >= deadline):
                break
            time.sleep(.15)
        if (self.folder/(name+'.xml')).stat().st_size > 2_000_000:
            raise AssertionError('Hierarchy exceeds bounded synthetic evidence limit')
        return tree

    def texts(self, tree=None):
        current = tree if tree is not None else self.tree()
        return [n.get('text', '') for n in current.iter('node') if n.get('package') == PACKAGE]

    def wait(self, predicate, message, seconds=25):
        deadline = time.monotonic()+seconds
        while time.monotonic() < deadline:
            tree = self.tree()
            try:
                if predicate(tree):
                    return tree
            except AssertionError:
                if str(self.report.get('api')) != '26':
                    raise
            time.sleep(.15)
        raise AssertionError(message)

    def wait_label(self, label, seconds=25):
        return self.wait(lambda tree: label in self.texts(tree), 'Expected UI text: '+label, seconds)

    def host_text(self, tree=None):
        current = tree if tree is not None else self.tree()
        fields = [n for n in current.iter('node') if n.get('package') == PACKAGE and n.get('hint') == PRACTICE and n.get('password') == 'false']
        if len(fields) != 1:
            raise AssertionError('Only the synthetic SetupActivity practice host is accepted')
        value = fields[0].get('text', '')
        return '' if value == PRACTICE else value

    def unchanged_host(self):
        actual = self.host_text()
        if actual != self.host_expected:
            raise AssertionError('Internal keyboard action altered synthetic host text')

    def ime_window(self, tree):
        found = [n for n in tree.findall('node') if any(c.get('description') == '普通输入' for c in n.iter('node'))]
        if len(found) != 1:
            raise AssertionError('Expected exactly one project IME window')
        return found[0]

    def ime_tree(self, name='ui'):
        deadline = time.monotonic()+5
        while True:
            tree = self.tree(name)
            try:
                self.ime_window(tree)
                return tree
            except AssertionError:
                if str(self.report.get('api')) != '26' or time.monotonic() >= deadline:
                    raise
                time.sleep(.15)

    def clipped(self, node, tree):
        parents = {child: parent for parent in tree.iter() for child in parent}
        x1, y1, x2, y2 = q.node_bounds(node)
        width, height = self.screen
        x1, y1, x2, y2 = max(0, x1), max(0, y1), min(width, x2), min(height, y2)
        current = parents.get(node)
        while current is not None and current.tag == 'node':
            if current.get('class', '').endswith('ScrollView') or parents.get(current) is tree:
                left, top, right, bottom = q.node_bounds(current)
                x1, y1, x2, y2 = max(x1, left), max(y1, top), min(x2, right), min(y2, bottom)
            current = parents.get(current)
        # Exclude navigation/status windows from app and IME hit regions.
        for window in tree.findall('node'):
            if window.get('package') == PACKAGE:
                continue
            left, top, right, bottom = q.node_bounds(window)
            if right-left > width*.7 and left < (x1+x2)/2 < right:
                if top <= 0 < bottom < height*.2:
                    y1 = max(y1, bottom)
                elif height*.8 < top < height <= bottom:
                    y2 = min(y2, top)
        return x1, y1, x2, y2

    def viewport(self, tree, scope, target=None):
        parents = {child: parent for parent in tree.iter() for child in parent}
        if target is not None:
            current = parents.get(target)
            while current is not None:
                if current.get('class', '').endswith('ScrollView'):
                    return self.clipped(current, tree)
                current = parents.get(current)
        source = self.ime_window(tree) if scope in ('panel', 'keys') else tree
        views = []
        for node in source.iter('node'):
            if node.get('class') != 'android.widget.ScrollView':
                continue
            keys = any(c.get('description') in ('q', '2 ABC', '返回文字键盘') for c in node.iter('node'))
            if (scope == 'keys' and not keys) or (scope == 'panel' and keys):
                continue
            rect = self.clipped(node, tree)
            if rect[2]-rect[0] >= 50 and rect[3]-rect[1] >= 50:
                views.append(rect)
        if not views:
            raise AssertionError('No safe scroll viewport: '+scope)
        return max(views, key=lambda rect: (rect[2]-rect[0])*(rect[3]-rect[1]))

    def reach(self, value, *, kind='text', scope='panel', enabled=True):
        previous = None
        stalled = 0
        for attempt in range(32):
            tree = self.tree()
            if scope in ('panel', 'keys'):
                try:
                    source = self.ime_window(tree)
                except AssertionError:
                    if str(self.report.get('api')) == '26' and attempt < 31:
                        time.sleep(.15)
                        continue
                    raise
            else:
                source = tree
            matches = [n for n in source.iter('node') if n.get('package') == PACKAGE and n.get(kind) == value and (not enabled or n.get('enabled') == 'true')]
            for node in matches:
                left, top, right, bottom = self.clipped(node, tree)
                if right-left >= 8 and bottom-top >= 8:
                    return node, (left, top, right, bottom)
            target = matches[0] if matches else None
            left, top, right, bottom = self.viewport(tree, scope, target)
            # Accessibility bounds may already be clipped to a thin edge strip.
            # Keep the 8-pixel tap gate; scroll down when less remains below its top.
            down = q.node_bounds(target)[1] > bottom-8 if target is not None else attempt < 16
            shape = tuple((n.get('text'), n.get('bounds')) for n in source.iter('node'))
            stalled = stalled+1 if shape == previous else 0
            previous = shape
            if stalled >= 3 and target is not None:
                raise AssertionError('Control is clipped or blocked: '+value)
            start = top+int((bottom-top)*(.78 if down else .22))
            end = top+int((bottom-top)*(.22 if down else .78))
            self.record('swipe', scope+(' down' if down else ' up'))
            q.adb('shell', 'input', 'swipe', (left+right)//2, start, (left+right)//2, end, 250)
            time.sleep(.15)
        raise AssertionError('Control not reachable: '+value)

    def tap(self, value, *, kind='text', scope='panel'):
        _node, (left, top, right, bottom) = self.reach(value, kind=kind, scope=scope)
        self.record('tap', value)
        q.adb('shell', 'input', 'tap', (left+right)//2, (top+bottom)//2)
        time.sleep(.15)

    def key(self, description):
        self.tap(description, kind='description', scope='keys')

    def field(self, hint, tree=None):
        current = tree if tree is not None else self.ime_tree()
        fields = [n for n in self.ime_window(current).iter('node') if n.get('hint') == hint]
        if len(fields) != 1:
            raise AssertionError('Expected internal keyboard field: '+hint)
        return fields[0]

    def field_text(self, hint, tree=None):
        field = self.field(hint, tree)
        value = field.get('text', '')
        return '' if value == hint else value

    def focus(self, hint):
        self.tap(hint, kind='hint')
        self.wait(lambda tree: self.field(hint, tree).get('focused') == 'true', 'Internal field did not gain focus')

    def language(self, chinese):
        tree = self.ime_tree()
        switch = '切换到中文' if chinese else '切换到英文'
        if any(n.get('description') == switch for n in self.ime_window(tree).iter('node')):
            self.key(switch)

    def ascii(self, value):
        if not re.fullmatch('[a-z]+', value):
            raise AssertionError('Synthetic ASCII entry is intentionally limited to lower-case letters')
        self.language(False)
        for char in value:
            self.key(char)

    def candidate(self, label):
        for _ in range(20):
            tree = self.ime_tree()
            if any(n.get('text') == label for n in q.candidate_buttons(tree)):
                self.tap(label, scope='keys')
                return
            if not q.key_nodes(tree=tree, description='下一页候选', enabled=True):
                break
            self.key('下一页候选')
        raise AssertionError('Pinyin candidate not found: '+label)

    def approve(self, name):
        for label in ['已核对当前聊天对象是「'+name+'」', APPROVAL]:
            node, _ = self.reach(label)
            if node.get('checked') != 'true':
                self.tap(label)

    def normal_input(self):
        self.begin('normal_nine_key')
        tree = self.ime_tree()
        if q.key_nodes(tree=tree, description='切换九宫格', enabled=True):
            self.key('切换九宫格')
        self.language(True)
        names = {'4': '4 GHI', '6': '6 MNO', '2': '2 ABC'}
        for char in '64426':
            self.key(names[char])
        self.candidate('你好')
        self.host_expected = '你好'
        self.wait(lambda tree: self.host_text(tree) == self.host_expected, 'Nine-key insertion mismatch')
        self.passed('normal_nine_key')
        self.begin('normal_full_pinyin')
        self.key('切换全键盘')
        for char in 'zhongguo':
            self.key(char)
        self.candidate('中国')
        self.host_expected += '中国'
        self.wait(lambda tree: self.host_text(tree) == self.host_expected, 'Full-pinyin insertion mismatch')
        self.passed('normal_full_pinyin')

    def new_customer(self, name):
        self.tap('新增客户')
        self.focus('客户昵称')
        self.ascii(name)
        self.wait(lambda tree: self.field_text('客户昵称', tree) == name, 'Customer name was not typed into local editor')
        self.unchanged_host()
        self.tap('保存客户')
        self.wait_label('选择：'+name+' · 微信')

    def select_customer(self, name):
        self.tap('选择：'+name+' · 微信')
        self.wait_label('当前客户：'+name+' · 微信')
        self.unchanged_host()

    def main_flow(self):
        self.normal_input()
        self.begin('keyboard_customer_create_select')
        self.tap('新用户破冰', kind='description')
        self.wait_label('新增客户')
        self.new_customer('qaone')
        self.new_customer('qatwo')
        self.select_customer('qaone')
        self.passed('keyboard_customer_create_select')
        self.begin('internal_editor_isolation')
        self.focus(MATERIAL)
        self.ascii('walk')
        self.language(True)
        for char in 'nihao':
            self.key(char)
        self.candidate('你好')
        self.wait(lambda tree: self.field_text(MATERIAL, tree) == 'walk你好', 'Internal pinyin did not commit exactly')
        self.unchanged_host()
        self.passed('internal_editor_isolation')
        self.begin('profile_source_date_observations')
        date = self.field_text('观察日期 YYYY-MM-DD')
        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', date):
            raise AssertionError('Observation date missing')
        self.tap('加入这份资料')
        self.wait(lambda tree: any('主动提供的客户资料 · 观察于 '+date in value and 'walk你好' in value for value in self.texts(tree)), 'Source/date row missing')
        # Same text from a second source must retain its own material identity.
        # Open the real Spinner, then touch its observed option across windows:
        # Android may host the dropdown outside the original IME window.
        self.tap('资料来源类型', kind='description')
        def source_options(tree):
            visible = []
            for node in tree.iter('node'):
                if node.get('package') != PACKAGE or node.get('text') != '朋友圈动态' or node.get('enabled') != 'true':
                    continue
                left, top, right, bottom = self.clipped(node, tree)
                if right-left >= 8 and bottom-top >= 8:
                    visible.append((node, (left, top, right, bottom)))
            return visible
        menu = self.wait(lambda tree: bool(source_options(tree)), 'Actual material-source Spinner option did not appear')
        options = source_options(menu)
        if len(options) != 1:
            raise AssertionError('Material-source Spinner option is ambiguous; refusing a positional choice')
        _, (left, top, right, bottom) = options[0]
        self.record('spinner_option_tap', '资料来源类型：朋友圈动态')
        q.adb('shell', 'input', 'tap', (left+right)//2, (top+bottom)//2)
        time.sleep(.15)
        def moments_selected(tree):
            selectors = [node for node in tree.iter('node') if node.get('package') == PACKAGE
                         and node.get('class') == 'android.widget.Spinner' and node.get('description') == '资料来源类型']
            return len(selectors) == 1 and [node.get('text') for node in selectors[0].iter('node') if node.get('text')] == ['朋友圈动态']
        self.wait(moments_selected, 'Actual source selection did not become 朋友圈动态')
        self.focus(MATERIAL)
        self.ascii('walk')
        self.language(True)
        for char in 'nihao':
            self.key(char)
        self.candidate('你好')
        self.wait(lambda tree: self.field_text(MATERIAL, tree) == 'walk你好', 'Second same-text material was not typed exactly with the real keyboard')
        if self.field_text('观察日期 YYYY-MM-DD') != date:
            raise AssertionError('Changing the source unexpectedly changed its observation date')
        self.unchanged_host()
        self.tap('加入这份资料')
        self.wait(lambda tree: '资料2 · 主动提供的朋友圈动态 · 观察于 '+date+'\nwalk你好' in self.texts(tree), 'Second same-text source/date row missing')
        self.approve('qaone')
        self.tap('分析已批准资料')
        self.wait_label('画像已生成，请核对依据与不确定项。', 40)
        self.wait(lambda tree: any('资料自述（待核对）：本次资料内容：walk你好' in value for value in self.texts(tree)), 'PROFILE observations not displayed')
        self.wait(lambda tree: any('依据 E1 · 资料1 · 主动提供的客户资料 · 观察于 '+date+'\n“walk你好”' in value for value in self.texts(tree)), 'PROFILE evidence did not identify its exact source and date')
        self.wait(lambda tree: any('依据 E2 · 资料2 · 主动提供的朋友圈动态 · 观察于 '+date+'\n“walk你好”' in value for value in self.texts(tree)), 'PROFILE E2 was not mapped to the distinct same-text moments source')
        if any('确认正在与「' in value and '并插入' in value for value in self.texts()):
            raise AssertionError('PROFILE must not expose an insertion action')
        fixture = json.loads((self.folder/'fixture-receipt.json').read_text(encoding='utf-8'))
        calls = [call for call in fixture['calls'] if call['taskType'] == 'PROFILE' and not call['judge']]
        if len(calls) != 1 or calls[0]['materials'][0]['text'] != 'walk你好' or calls[0]['materials'][0]['observed_at'] != date or calls[0]['materials'][0]['source'] != '主动提供的客户资料':
            raise AssertionError('Provider substitute did not receive exact approved source/date material')
        approved_materials = calls[0]['materials']
        if (len(approved_materials) != 2 or any(material.get('text') != 'walk你好' or material.get('observed_at') != date for material in approved_materials)
                or [material.get('kind') for material in approved_materials] != ['PROFILE_TEXT', 'MOMENTS_TEXT']
                or [material.get('source') for material in approved_materials] != ['主动提供的客户资料', '主动提供的朋友圈动态']
                or any(not isinstance(material.get('id'), str) or not material['id'] for material in approved_materials)
                or len({material['id'] for material in approved_materials}) != 2):
            raise AssertionError('Same-text materials were merged or lost their distinct approved source identities')
        if fixture.get('synthetic') is not True or fixture.get('realProviderCalls') != 0:
            raise AssertionError('The source-mapping acceptance requires the owned fixture and zero real provider calls')
        self.report['profileSourceMapping'] = {
            'sameText': 'walk你好', 'observationDate': date, 'materials': approved_materials,
            'expectedEvidenceSources': {'E1': approved_materials[0]['id'], 'E2': approved_materials[1]['id']},
            'sourceSelection': 'actual Spinner option tap', 'secondTextEntry': 'actual project keyboard',
            'profileRequests': len(calls), 'realProviderCalls': 0}
        self.unchanged_host()
        self.passed('profile_source_date_observations')
        self.begin('opening_edit_exact_confirmed_insert')
        self.tap('新客破冰')
        self.approve('qaone')
        self.tap('生成已批准内容')
        self.wait_label(CANDIDATE, 40)
        self.tap(CANDIDATE)
        self.wait(lambda tree: self.field_text(DRAFT, tree) == CANDIDATE, 'Candidate did not fill local draft')
        self.ascii('qa')
        exact = CANDIDATE+'qa'
        self.wait(lambda tree: self.field_text(DRAFT, tree) == exact, 'Edited draft mismatch')
        self.unchanged_host()
        self.tap('确认正在与「qaone」聊天并插入')
        self.host_expected += exact
        self.wait(lambda tree: self.host_text(tree) == self.host_expected, 'Named confirmation did not insert exact edited draft', 40)
        self.passed('opening_edit_exact_confirmed_insert')

        # A second, unconsumed candidate must disappear when the customer changes.
        self.begin('switch_customer_revokes_old_draft')
        self.tap('新用户破冰', kind='description')
        self.wait_label('选择：qaone · 微信')
        self.select_customer('qaone')
        self.tap('新客破冰')
        self.approve('qaone')
        self.tap('生成已批准内容')
        self.wait_label(CANDIDATE, 40)
        self.tap(CANDIDATE)
        self.tap('更换客户')
        self.wait_label('选择：qatwo · 微信')
        self.select_customer('qatwo')
        tree = self.ime_tree()
        if any(n.get('hint') == DRAFT or n.get('text') in (CANDIDATE, '确认正在与「qaone」聊天并插入') for n in self.ime_window(tree).iter('node')):
            raise AssertionError('Old customer draft/insert survived customer switch')
        self.unchanged_host()
        self.passed('switch_customer_revokes_old_draft')
        self.begin('new_to_maintain_list')
        self.tap('更换客户')
        self.wait_label('将「qaone」转入老用户维护')
        self.tap('将「qaone」转入老用户维护')
        self.wait(lambda tree: '选择：qaone · 微信' not in self.texts(tree) and '选择：qatwo · 微信' in self.texts(tree), 'Transferred customer remained in NEW list')
        self.tap('老用户维护', kind='description')
        self.wait_label('选择：qaone · 微信')
        if '选择：qatwo · 微信' in self.texts(self.ime_tree()):
            raise AssertionError('NEW customer leaked into MAINTAIN list')
        self.select_customer('qaone')
        self.wait_label('准备聊天回复')
        self.unchanged_host()
        self.passed('new_to_maintain_list')
        self.customer_memory_panel()

    def customer_memory_panel(self):
        self.begin('customer_memory_panel')
        self.tap('客户资料、记忆与反馈')
        self.wait_label('记忆与标记')
        self.tap('记忆与标记')
        self.wait_label('还没有保存的记忆或标记。')
        self.tap('添加记忆或标记')
        self.focus('记忆内容')
        self.ascii('walk')
        self.wait(lambda tree: self.field_text('记忆内容', tree) == 'walk', 'Memory content did not remain local')
        self.focus('记忆来源')
        self.ascii('manual')
        self.wait(lambda tree: self.field_text('记忆来源', tree) == 'manual', 'Memory source did not remain local')
        self.unchanged_host()
        self.tap('核对并保存记忆')
        self.tap('我已核对当前客户和上述影响')
        self.tap('确认保存记忆')
        self.wait(lambda tree: any('walk\n来源：manual' in value for value in self.texts(tree)), 'Saved memory and source not displayed')
        self.tap('刷新记忆')
        self.wait_label('修改或删除第 1 条')
        self.tap('修改或删除第 1 条')
        self.focus('记忆内容')
        self.ascii('more')
        self.wait(lambda tree: self.field_text('记忆内容', tree) == 'walkmore', 'Memory correction draft mismatch')
        self.tap('核对并保存记忆')
        self.tap('我已核对当前客户和上述影响')
        self.tap('确认保存记忆')
        self.wait(lambda tree: any('walkmore\n来源：manual' in value for value in self.texts(tree)), 'Corrected memory not displayed')
        self.tap('修改或删除第 1 条')
        self.tap('删除此条记忆')
        self.tap('我已核对当前客户和上述影响')
        self.tap('确认删除记忆')
        self.wait_label('还没有保存的记忆或标记。')
        self.tap('刷新记忆')
        self.wait_label('还没有保存的记忆或标记。')
        self.tap('返回辅助面板')
        self.wait_label('当前客户：qaone · 微信')
        if any(n.get('hint') == DRAFT for n in self.ime_window(self.ime_tree()).iter('node')):
            raise AssertionError('Maintenance return restored an old insertion draft')
        self.unchanged_host()
        self.passed('customer_memory_panel')


def verify_target():
    if q.SERIAL != 'emulator-5556':
        raise RuntimeError('This QA accepts only emulator-5556')
    if q.adb('shell', 'getprop', 'ro.kernel.qemu') != '1':
        raise RuntimeError('Target is not an emulator')
    names = q.adb('emu', 'avd', 'name').splitlines()
    if not names:
        raise RuntimeError('AVD identity was not returned; use the same execution identity as the verified project emulator')
    avd = names[0].strip()
    if not re.fullmatch(r'LensPreview(?:Api\d+)?', avd):
        raise RuntimeError('Target is not a project LensPreview AVD')
    if q.adb('shell', 'getprop', 'sys.boot_completed') != '1':
        raise RuntimeError('Start and boot the project emulator before running this script')
    return avd


def setup_login(qa, fixture):
    q.adb('shell', 'am', 'start', '-W', '-n', PACKAGE+'/.SetupActivity')
    q.adb('shell', 'ime', 'enable', COMPONENT)
    q.adb('shell', 'settings', 'put', 'secure', 'show_ime_with_hard_keyboard', '1')
    q.adb('shell', 'ime', 'set', COMPONENT)
    qa.wait_label('登录与人物资料')
    qa.tap('登录与人物资料', scope='activity')
    qa.wait_label('登录并开始')
    # Only setup activation uses the existing synthetic ACTION_SET_TEXT helper.
    # No keyboard-internal field or product button is filled/clicked this way.
    encoded = base64.b64encode(fixture['invite'].encode()).decode()
    max_attempts = 5 if qa.report.get('api') == '26' else 1
    result = ''
    for attempt in range(1, max_attempts+1):
        result = q.adb('shell', 'am', 'instrument', '-w', '-e', 'hint', "'一次性邀请码'", '-e', 'value', encoded, 'com.conversationlens.ime.qa/.DumpRunner')
        if 'INSTRUMENTATION_RESULT: error=' not in result:
            qa.report['syntheticActivationSetAttempts'] = attempt
            break
        if attempt < max_attempts:
            time.sleep(1)
    else:
        raise AssertionError('Synthetic activation setup field was not available')
    qa.record('synthetic_setup_set_text', '一次性邀请码')
    qa.tap('我已了解并同意上述数据处理方式', scope='activity')
    qa.tap('登录并开始', scope='activity')
    qa.wait_label('新建人物')
    q.adb('shell', 'am', 'force-stop', PACKAGE)
    q.adb('shell', 'am', 'start', '-W', '-n', PACKAGE+'/.SetupActivity')
    q.adb('shell', 'ime', 'set', COMPONENT)
    # Existing practice helper clips host input to its visible area above IME.
    from keyboard_ui_qa import focus_visible_practice
    focus_visible_practice()
    qa.wait_label('普通输入', 45)
    if qa.host_text():
        raise AssertionError('Synthetic host must start empty')


def main(*, qa_factory=QA, output_group='keyboard-first-qa', description=__doc__):
    # Other standalone suites may reuse the owned setup/cleanup, while the
    # default factory, nine checks and delivery evidence directory stay fixed.
    if not re.fullmatch(r'keyboard-[a-z-]+-qa', output_group):
        raise ValueError('Synthetic suite output group must stay within project output')
    fixture_name = getattr(qa_factory, 'fixture_name', 'keyboard_first_fixture.mjs')
    if fixture_name not in ('keyboard_first_fixture.mjs', 'keyboard_budget_fixture.mjs'):
        raise ValueError('Only explicitly owned keyboard fixtures are allowed')
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument('--apk', type=Path, default=q.ROOT/'output/native/conversation-lens-0.18.0-cloud-debug.apk')
    parser.add_argument('--dump-apk', type=Path, default=q.ROOT/'output/native/lens-synthetic-qa.apk')
    args = parser.parse_args()
    # All target proof and artifact preflight happen before app/data/settings mutations.
    avd = verify_target()
    for apk in (args.apk, args.dump_apk):
        if not apk.is_file():
            raise RuntimeError('Required built test APK does not exist: '+str(apk))
    with zipfile.ZipFile(args.apk) as apk:
        config = json.loads(apk.read('assets/cloud-config.json'))
        if config.get('endpoint') != 'http://127.0.0.1:4317':
            raise RuntimeError('APK must use the explicit loopback synthetic endpoint')
    if any('tcp:4317' in line.split() for line in q.adb('reverse', '--list').splitlines()):
        raise RuntimeError('Existing reverse port 4317 is owned elsewhere; refusing to replace it')
    folder = q.ROOT/'output'/output_group/(time.strftime('%Y%m%d-%H%M%S')+'-'+uuid4().hex[:8])
    folder.mkdir(parents=True)
    q.OUT = folder
    qa = qa_factory(folder)
    qa.screen = tuple(map(int, re.findall(r'(\d+)x(\d+)', q.adb('shell', 'wm', 'size'))[-1]))
    qa.report.update({'serial': q.SERIAL, 'avd': avd, 'api': q.adb('shell', 'getprop', 'ro.build.version.sdk'),
                      'apkSha256': hashlib.file_digest(args.apk.open('rb'), 'sha256').hexdigest()})
    qa.report.setdefault('scope', 'synthetic keyboard touch flow; no OEM, real model, image picker or OCR quality acceptance')
    qa.save()
    original = {key: q.adb('shell', 'settings', 'get', 'secure', key) for key in ['default_input_method', 'enabled_input_methods', 'show_ime_with_hard_keyboard']}
    service = None
    reversed_port = False
    mutated = False
    try:
        with (folder/'fixture.log').open('w', encoding='utf-8') as log:
            service = subprocess.Popen(['node', '--disable-warning=ExperimentalWarning', str(q.ROOT/'native/scripts'/fixture_name), '--out', str(folder)],
                                       cwd=q.ROOT, stdin=subprocess.PIPE, stdout=log, stderr=subprocess.STDOUT, text=True, encoding='utf-8',
                                       creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            deadline = time.monotonic()+15
            while not (folder/'fixture.json').exists():
                if service.poll() is not None or time.monotonic() >= deadline:
                    raise RuntimeError('Owned synthetic fixture failed to become ready; inspect fixture.log')
                time.sleep(.1)
            fixture = json.loads((folder/'fixture.json').read_text(encoding='utf-8'))
            if fixture.get('synthetic') is not True or fixture.get('pid') != service.pid or not re.fullmatch(r'http://127\.0\.0\.1:\d+', fixture.get('base', '')):
                raise RuntimeError('Synthetic fixture ownership/loopback proof failed')
            verify_target()
            q.adb('reverse', 'tcp:4317', 'tcp:'+fixture['base'].rsplit(':', 1)[1])
            reversed_port = True
            # An old project test package can use the production test certificate.
            # This is a fresh synthetic installation, not a signed upgrade test.
            verify_target()
            mutated = True
            if q.adb('shell', 'pm', 'path', PACKAGE).strip():
                if 'Success' not in q.adb('uninstall', PACKAGE):
                    raise RuntimeError('Old synthetic project APK could not be removed')
            for apk in (args.apk, args.dump_apk):
                if 'Success' not in q.adb('install', '--no-incremental', '-r', '-t', apk, timeout=180):
                    raise RuntimeError('Synthetic APK installation failed')
            package = q.adb('shell', 'dumpsys', 'package', PACKAGE)
            version_name = re.search(r'versionName=([^\s]+)', package)
            # Gradle debug declares exactly versionNameSuffix '-preview'. Keep
            # this finite allowlist; arbitrary prefixes/suffixes are not accepted.
            if version_name is None or version_name.group(1) not in ('0.18.0', '0.18.0-preview') or not re.search(r'versionCode=23(?:\s|$)', package):
                raise RuntimeError('Installed APK must be exactly 0.18.0 or 0.18.0-preview, code23')
            qa.report['installedVersionName'] = version_name.group(1)
            qa.report['installedVersionCode'] = 23
            verify_target()
            if 'Success' not in q.adb('shell', 'pm', 'clear', PACKAGE):
                raise RuntimeError('Synthetic app reset failed')
            setup_login(qa, fixture)
            qa.main_flow()
            if any(value != 'PASS' for value in qa.report['checks'].values()):
                raise AssertionError('Acceptance contains unexecuted checks')
            qa.report['status'] = 'PASS'
    except Exception as error:
        qa.report['status'] = 'FAIL'
        active = qa.report.get('activeCheck')
        if active:
            qa.report['checks'][active] = 'FAIL'
        qa.report['failure'] = {'type': type(error).__name__, 'message': str(error)[:2000]}
        raise
    finally:
        cleanup = []
        try:
            if mutated:
                verify_target()
                q.adb('shell', 'am', 'force-stop', PACKAGE)
                for key, value in original.items():
                    if value == 'null':
                        q.adb('shell', 'settings', 'delete', 'secure', key)
                    else:
                        q.adb('shell', 'settings', 'put', 'secure', key, value)
        except Exception as error:
            cleanup.append({'target': 'synthetic app/settings', 'errorType': type(error).__name__})
        try:
            if reversed_port:
                verify_target()
                q.adb('reverse', '--remove', 'tcp:4317')
        except Exception as error:
            cleanup.append({'target': 'owned reverse port', 'errorType': type(error).__name__})
        try:
            if service is not None and service.poll() is None:
                service.stdin.write('stop\n')
                service.stdin.flush()
                service.wait(timeout=15)
            if service is not None and service.returncode != 0:
                cleanup.append({'target': 'owned fixture', 'errorType': 'NonzeroExit'})
        except Exception as error:
            cleanup.append({'target': 'owned fixture', 'errorType': type(error).__name__})
            if service is not None and service.poll() is None:
                service.terminate()
                service.wait(timeout=10)
        finally:
            # Never keep even a synthetic invite in the final evidence bundle.
            metadata = folder/'fixture.json'
            if metadata.exists():
                metadata.unlink()
            qa.report['cleanupErrors'] = cleanup
            if cleanup:
                qa.report['status'] = 'FAIL'
            qa.save()
            print(str(folder/'report.json'), flush=True)
        if cleanup:
            raise RuntimeError('Synthetic QA cleanup incomplete; see receipt')


if __name__ == '__main__':
    main()
