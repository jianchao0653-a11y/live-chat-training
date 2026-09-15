"""Actual-touch IME dropdown acceptance on the owned project emulator only.

Run with the same APK/DumpRunner arguments as keyboard_first_qa.py. The base
driver owns setup, synthetic fixture, APK identity and cleanup. --self-test
only exercises parsers and guards in memory; it never contacts ADB or a server.
No protected screenshots or substantive ACTION_SET_TEXT/input-text calls.
"""
import json
import os
import re
import sys
import time
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import patch

import keyboard_first_qa as first
from keyboard_details_qa import DetailsQA, NOTE, DRAFT
from keyboard_continuation_qa import ContinuationQA, CHAT, GENERATE, READY

CHECKS = [
    'create_platform_nondefault_persisted',
    'reply_goal_nondefault_reaches_approved_request',
    'details_platform_and_stage_nondefault_persisted',
    'feedback_nondefault_status_persisted',
    'memory_kind_and_category_nondefault_persisted',
    'source_nondefault_material_stays_local',
    'all_dropdowns_have_own_secure_flag_and_dismiss',
    'return_to_normal_preserves_host_and_zero_real_calls',
]
SELECTORS = {'create-platform', 'reply-goal', 'details-platform', 'details-stage',
             'feedback-status', 'memory-kind', 'memory-category', 'material-source'}


def own_attributes(block):
    start = re.search(r'\bmAttrs=\{', block)
    if not start:
        raise AssertionError('Window block has no own mAttrs')
    depth = 1
    for index in range(start.end(), len(block)):
        if block[index] == '{':
            depth += 1
            if depth > 32:
                raise AssertionError('Window attributes exceeded nesting bound')
        elif block[index] == '}':
            depth -= 1
            if depth == 0:
                return block[start.end():index]
    raise AssertionError('Window own mAttrs has no matching closing brace')


def window_records(raw):
    """Parse only window blocks; callers retain bounded original scoped dumps."""
    if len(raw.encode('utf-8')) > 1_000_000:
        raise AssertionError('Scoped window dump exceeded 1 MB')
    starts = list(re.finditer(r'^\s*Window #\d+ (Window\{[^\n]+\}):\s*$', raw, re.M))
    result = []
    for i, match in enumerate(starts):
        block = raw[match.end():starts[i+1].start() if i+1 < len(starts) else len(raw)]
        owner = re.search(r'\bmOwnerUid=(\d+)[^\n]*\bpackage=([^\s]+)', block)
        if not owner:
            raise AssertionError('Window block has no explicit owner UID/package')
        attrs = own_attributes(block)
        flags = re.search(r'\bfl=(.*?)(?=\s+\w+=|\n|$)', attrs)
        kind = re.search(r'\bty=([^\s}]+)', attrs)
        if not flags or not kind:
            raise AssertionError('Window own flags/type are unavailable')
        value = flags.group(1).strip()
        numeric = re.match(r'^(?:#|0x)([0-9a-fA-F]+)(?:\s|$)', value)
        def flag(name, bit):
            return bool(int(numeric.group(1), 16) & bit) if numeric else bool(re.search(
                r'(?<![A-Z_])'+re.escape(name)+r'(?![A-Z_])', value))
        parent = re.search(r'\bmParentWindow=(Window\{[^\n]+?\})', block)
        visible = ('mHasSurface=true' in block and bool(re.search(
            r'(?:isOnScreen(?:\(\))?=true|isReadyForDisplay\(\)=true|mViewVisibility=0x0\b)', block)))
        result.append({'window': match.group(1), 'uid': int(owner.group(1)),
                       'package': owner.group(2), 'type': kind.group(1),
                       'ownFlags': value, 'ownSecure': flag('SECURE', 0x2000),
                       'ownNotFocusable': flag('NOT_FOCUSABLE', 0x8),
                       'ownAltFocusableIme': flag('ALT_FOCUSABLE_IM', 0x20000),
                       'parent': parent.group(1) if parent else None, 'visible': visible})
    return result


def secure_pair(records):
    owned = [r for r in records if r['package'] == first.PACKAGE and r['visible']]
    parents = [r for r in owned if r['type'] in ('2011', 'INPUT_METHOD', 'TYPE_INPUT_METHOD')]
    popups = [r for r in owned if r['type'] in ('1002', 'APPLICATION_SUB_PANEL', 'TYPE_APPLICATION_SUB_PANEL')]
    if len(parents) != 1 or len(popups) != 1:
        raise AssertionError('Expected exactly one visible owned IME and one owned dropdown subwindow')
    parent, popup = parents[0], popups[0]
    if not parent['ownSecure'] or not popup['ownSecure']:
        raise AssertionError('IME and dropdown must each declare their own FLAG_SECURE')
    if popup['ownNotFocusable'] is not True or popup['ownAltFocusableIme'] is not False:
        raise AssertionError('Dropdown must set its own NOT_FOCUSABLE and clear ALT_FOCUSABLE_IM')
    if popup['uid'] != parent['uid'] or popup['parent'] != parent['window']:
        raise AssertionError('Dropdown owner or parent does not match the current project IME')
    return {'ime': parent, 'dropdown': popup}


def window_frame(raw, identity):
    starts = list(re.finditer(r'^\s*Window #\d+ (Window\{[^\n]+\}):\s*$', raw, re.M))
    blocks = [raw[m.end():starts[i+1].start() if i+1 < len(starts) else len(raw)]
              for i, m in enumerate(starts) if m.group(1) == identity]
    if len(blocks) != 1:
        raise AssertionError('Cannot uniquely match the verified dropdown window frame')
    frames = re.findall(r'\b(?:mFrame|frame)=(\[-?\d+,-?\d+\]\[-?\d+,-?\d+\])', blocks[0])
    if len(frames) != 1:
        raise AssertionError('Verified dropdown must expose exactly one actual frame')
    return tuple(map(int, re.findall(r'-?\d+', frames[0])))


class SelectorQA(DetailsQA):
    def __init__(self, folder):
        super().__init__(folder)
        self.report.update(suite='keyboard-selector', checks={name: 'NOT_RUN' for name in CHECKS},
                           scope='eight actual dropdown selections, own-window secure flags, persisted synthetic state and one approved synthetic reply',
                           windowEvidence=[], selectorSelections=[], humanAccepted=False,
                           qualityAccepted=False, productionReady=False,
                           notCovered=['real-phone/OEM behavior', 'pixel capture resistance',
                                       'real model/OCR quality', 'all Android versions from one run'])
        self.started = time.monotonic()

    def record(self, kind, value):
        if time.monotonic()-self.started > 1800:
            raise AssertionError('Selector suite exceeded its 30 minute action deadline')
        super().record(kind, value)

    def receipt(self):
        path = self.folder/'fixture-receipt.json'
        deadline = time.monotonic()+2
        while True:
            if path.stat().st_size > 2_000_000:
                raise AssertionError('Synthetic receipt exceeded its size bound')
            try:
                receipt = json.loads(path.read_text(encoding='utf-8'))
                break
            except json.JSONDecodeError:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(.05)
        if (receipt.get('synthetic') is not True or receipt.get('realProviderCalls') != 0
                or receipt.get('details', {}).get('scenario') != 'keyboard-details'
                or receipt.get('details', {}).get('fixtureError')):
            raise AssertionError('Expected the owned details fixture and zero real provider calls')
        calls = receipt.get('calls')
        if not isinstance(calls, list) or len(calls) > 2 or any(c.get('taskType') != 'REPLY' for c in calls):
            raise AssertionError('Only one approved synthetic reply plus its independent judge is allowed')
        return receipt

    def state(self, checkpoint=None):
        state = self.receipt()['details']
        if checkpoint:
            self.report.setdefault('observedSyntheticStates', {})[checkpoint] = state
        return state

    def window_state(self, checkpoint):
        if (self.report.get('serial') != 'emulator-5556'
                or not re.fullmatch(r'LensPreview(?:Api\d+)?', self.report.get('avd', ''))):
            raise AssertionError('Window inspection requires base-driver project emulator proof')
        records = []
        files = {}
        # WindowManager supports title filters. Keep exact original bounded
        # output for failed-format diagnosis; never query activities/accounts.
        for label in ('InputMethod', 'PopupWindow'):
            raw = first.q.adb('shell', 'dumpsys', 'window', '-a', label, timeout=15)
            if len(raw.encode('utf-8')) > 1_000_000:
                raise AssertionError('Scoped dumpsys output exceeded 1 MB')
            path = self.folder/(checkpoint+'-'+label+'.txt')
            if path.exists():
                raise AssertionError('Window evidence must not overwrite an earlier attempt')
            path.write_text(raw, encoding='utf-8')
            files[label] = path.name
            records.extend(window_records(raw))
        # A popup may also contain InputMethod in its title. Deduplicate exact
        # identities while rejecting contradictory representations.
        unique = {}
        for item in records:
            if item['window'] in unique and unique[item['window']] != item:
                raise AssertionError('Scoped dumps disagree about one window')
            unique[item['window']] = item
        self.last_window_files = files
        return list(unique.values())

    def selected(self, description, tree=None):
        current = tree if tree is not None else self.tree()
        nodes = [n for n in self.ime_window(current).iter('node') if n.get('description') == description
                 and n.get('class', '').endswith('Spinner')]
        if len(nodes) != 1:
            raise AssertionError('Expected one identified selector: '+description)
        values = [n.get('text') for n in nodes[0].iter('node') if n.get('text')]
        if len(set(values)) != 1:
            raise AssertionError('Selector does not show one unambiguous selected label')
        return values[0]

    def popup_choice(self, tree, label, frame):
        # A touch-modal popup can occlude its background IME in accessibility.
        # Its identity/security is independently established by secure_pair.
        # Match the surviving standalone ListView root to that window's frame.
        roots = [root for root in tree.findall('node') if root.get('package') == first.PACKAGE
                 and first.q.node_bounds(root) == frame
                 and any(node.get('class', '').endswith('ListView') for node in root.iter('node'))]
        if len(roots) != 1:
            raise AssertionError('Expected one independent dropdown accessibility root at its verified window frame')
        matches = [node for node in roots[0].iter('node') if node.get('text') == label
                   and node.get('package') == first.PACKAGE and node.get('enabled') == 'true']
        if len(matches) != 1:
            raise AssertionError('Nondefault choice must be unique in the verified dropdown root')
        rect = self.clipped(matches[0], tree)
        if rect[2]-rect[0] < 8 or rect[3]-rect[1] < 8:
            raise AssertionError('Nondefault dropdown choice is clipped')
        return matches[0], rect

    def selection_restored(self, tree, description, value):
        ime = [root for root in tree.findall('node')
               if any(node.get('description') == '普通输入' for node in root.iter('node'))]
        if len(ime) != 1:
            return False
        nodes = [node for node in ime[0].iter('node') if node.get('description') == description
                 and node.get('class', '').endswith('Spinner')]
        return len(nodes) == 1 and [node.get('text') for node in nodes[0].iter('node')
                                   if node.get('text')] == [value]

    def choose(self, identity, description, old, new):
        if identity not in SELECTORS or any(x['id'] == identity for x in self.report['selectorSelections']):
            raise AssertionError('Selector identity is unknown or was already executed')
        self.reach(description, kind='description')
        before_tree = self.tree(identity+'-before')
        if self.selected(description, before_tree) != old or old == new:
            raise AssertionError('Selector must start at the expected different value')
        before_records = self.window_state(identity+'-before')
        before_files = dict(self.last_window_files)
        self.tap(description, kind='description')
        self.wait(lambda t: any(n.get('text') == new for n in t.iter('node')
                               if n.get('package') == first.PACKAGE), 'Dropdown did not expose '+new)
        pair = secure_pair(self.window_state(identity+'-open'))
        open_files = dict(self.last_window_files)
        self.report['windowEvidence'].append({'id': identity, 'open': pair,
                                             'openDumpFiles': open_files,
                                             'before': {'hierarchy': identity+'-before.xml',
                                                        'dumpFiles': before_files, 'records': before_records},
                                             'openHierarchy': identity+'-open.xml'})
        self.save()
        tree = self.tree(identity+'-open')
        frame = window_frame((self.folder/open_files['PopupWindow']).read_text(encoding='utf-8'),
                             pair['dropdown']['window'])
        node, (left, top, right, bottom) = self.popup_choice(tree, new, frame)
        point = [(left+right)//2, (top+bottom)//2]
        self.report['windowEvidence'][-1]['optionTouch'] = {
            'label': new, 'windowFrame': list(frame), 'nodeBounds': list(first.q.node_bounds(node)),
            'clippedBounds': [left, top, right, bottom], 'point': point,
            'hierarchy': identity+'-open.xml'}
        self.record('tap_dropdown_option', identity+': '+new)
        self.report['actions'][-1]['point'] = point
        self.save()
        first.q.adb('shell', 'input', 'tap', *point)
        self.tree(identity+'-after-tap')
        after_records = self.window_state(identity+'-after-tap')
        self.report['windowEvidence'][-1]['afterTap'] = {
            'hierarchy': identity+'-after-tap.xml', 'dumpFiles': dict(self.last_window_files),
            'records': after_records}
        self.save()
        self.wait(lambda t: self.selection_restored(t, description, new),
                  'After the actual dropdown tap, the IME and selected value did not return: '+description)
        # Dismiss animation is bounded; every attempt receives a unique file.
        for attempt in range(4):
            records = self.window_state(identity+'-closed-'+str(attempt))
            visible = [r for r in records if r['package'] == first.PACKAGE and r['visible']
                       and r['type'] in ('1002', 'APPLICATION_SUB_PANEL', 'TYPE_APPLICATION_SUB_PANEL')]
            if not visible:
                break
            time.sleep(.2)
        else:
            raise AssertionError('Dropdown remained visible after choosing a value')
        self.report['windowEvidence'][-1]['dismissed'] = True
        self.report['windowEvidence'][-1]['closed'] = {
            'dumpFiles': dict(self.last_window_files), 'records': records}
        self.report['selectorSelections'].append({'id': identity, 'description': description,
                                                  'before': old, 'after': new, 'actualTouch': True})
        self.unchanged_host()
        self.save()

    def full_keyboard(self):
        if first.q.key_nodes(tree=self.tree(), description='切换全键盘', enabled=True):
            self.key('切换全键盘')

    def show_details(self, name):
        self.tap('客户资料、记忆与反馈')
        self.wait_label('客户资料 · '+name)

    def main_flow(self):
        self.begin(CHECKS[0])
        self.tap('老用户维护', kind='description')
        self.wait_label('新增客户')
        self.tap('新增客户')
        self.full_keyboard()
        self.focus('客户昵称')
        self.ascii('qaselector')
        if self.field_text('客户昵称') != 'qaselector':
            raise AssertionError('Synthetic customer nickname was not typed exactly')
        self.choose('create-platform', '聊天平台', '微信', '抖音')
        self.tap('保存客户')
        self.wait_label('选择：qaselector · 抖音')
        self.tap('刷新')
        self.wait_label('选择：qaselector · 抖音')
        self.tap('选择：qaselector · 抖音')
        self.wait_label('当前客户：qaselector · 抖音')
        self.passed(CHECKS[0])

        self.begin(CHECKS[1])
        self.choose('reply-goal', '本次回复目标', '自然接话', '表达边界')
        ContinuationQA.enter_fragment(self, 'hello')
        if self.receipt()['calls']:
            raise AssertionError('A dropdown or typing made an unapproved model request')
        self.approve('qaselector')
        self.tap(GENERATE)
        self.wait_label(READY, 45)
        calls = self.receipt()['calls']
        if (len(calls) != 2 or [c.get('judge') for c in calls] != [False, True]
                or any((c.get('chat'), c.get('goal')) != ('对方：hello', '表达边界') for c in calls)):
            raise AssertionError('The selected goal/typed fragment did not reach both synthetic provider stages exactly')
        self.report['approvedSyntheticReply'] = {'chat': '对方：hello', 'goal': '表达边界', 'calls': calls}
        self.unchanged_host()
        self.passed(CHECKS[1])

        self.begin(CHECKS[2])
        self.show_details('qaselector')
        self.tap('修改客户与关系资料')
        self.wait_label('修改客户资料 · qaselector')
        self.choose('details-platform', '聊天平台', '抖音', '快手')
        self.choose('details-stage', '关系阶段', '初识', '稳定联系')
        self.tap('核对并保存客户资料')
        self.confirm('保存客户资料')
        self.wait_label('客户资料 · qaselector')
        self.wait(lambda t: any('平台：快手\n关系阶段：稳定联系\n' in v for v in self.texts(t)),
                  'Saved platform/stage were not returned by the server')
        self.tap('修改客户与关系资料')
        self.wait_label('修改客户资料 · qaselector')
        if self.selected('聊天平台') != '快手' or self.selected('关系阶段') != '稳定联系':
            raise AssertionError('Readback editors lost the saved nondefault platform/stage')
        self.tap('放弃修改并重新读取')
        self.confirm('放弃本页修改')
        self.wait_label('客户资料 · qaselector')
        self.tap('返回辅助面板')
        self.wait_label('当前客户：qaselector · 快手')
        self.passed(CHECKS[2])

        self.begin(CHECKS[3])
        self.tap('普通输入', kind='description')
        self.tap('新用户破冰', kind='description')
        self.wait_label('选择：qafeedback · 微信')
        self.select_customer('qafeedback')
        self.show_details('qafeedback')
        self.go_history('qafeedback')
        self.open_first('qafeedback')
        self.feedback_editor()
        self.choose('feedback-status', '实际反馈状态', '未知／尚无回应', '混合回应')
        self.full_keyboard()
        self.focus(NOTE)
        self.ascii('mixed')
        self.focus(DRAFT)
        self.ascii('hello')
        self.save_feedback()
        self.wait_label('分析历史与反馈 · qafeedback')
        person = self.person('qafeedback')
        outcomes = [a['outcome'] for a in person['analyses'] if a['outcome']]
        if (len(outcomes) != 1 or any(outcomes[0].get(k) != v for k, v in
                {'status': 'MIXED', 'note': 'mixed', 'draft': 'hello'}.items())
                or person['outcomeEvents'] != 1 or self.request_count('feedback-save') != 1):
            raise AssertionError('Actual feedback touch did not persist exactly one MIXED feedback')
        posts = [r for r in self.state()['requests'] if r['route'] == 'feedback-save' and r['method'] == 'POST']
        if [r['status'] for r in posts] != [200]:
            raise AssertionError('Feedback must have one actual successful POST')
        self.open_first('qafeedback')
        self.tap('修改实际反馈')
        self.wait_label('填写实际反馈 · qafeedback')
        if self.selected('实际反馈状态') != '混合回应' or self.field_text(NOTE) != 'mixed':
            raise AssertionError('Reopened feedback did not retain the saved selected status')
        self.tap('放弃修改并返回记录')
        self.confirm('放弃本页修改')
        self.wait_label('分析详情 · qafeedback')
        self.state('feedback-mixed-persisted')
        self.passed(CHECKS[3])

        self.begin(CHECKS[4])
        self.switch_to('qahistory')
        self.tap('记忆与标记')
        self.wait_label('记忆与标记 · qahistory')
        self.tap('添加记忆或标记')
        self.wait_label('添加记忆或标记 · qahistory')
        self.choose('memory-kind', '内容性质', '对方自述', '待核实推测')
        self.choose('memory-category', '保存类别', '聊天记忆', '客户标记')
        self.focus('记忆内容')
        self.ascii('selector')
        self.focus('记忆来源')
        self.ascii('synthetic')
        self.tap('核对并保存记忆')
        self.confirm('保存记忆')
        self.wait_label('记忆与标记 · qahistory')
        claims = self.person('qahistory')['claims']
        if (len(claims) != 1 or any(claims[0].get(k) != v for k, v in
                {'kind': 'INFERRED', 'review_state': 'PENDING', 'category': 'TAG',
                 'content': 'selector', 'source': 'synthetic'}.items())
                or self.person('qahistory')['effectiveClaimIds']):
            raise AssertionError('Nondefault kind/category were not persisted as a pending inferred tag')
        self.tap('修改或删除第 1 条')
        self.wait_label('更正记忆或标记 · qahistory')
        if self.selected('内容性质') != '待核实推测' or self.selected('保存类别') != '客户标记':
            raise AssertionError('Reopened memory lost the persisted nondefault choices')
        self.tap('放弃修改并返回记忆')
        self.confirm('放弃本页修改')
        self.wait_label('记忆与标记 · qahistory')
        self.tap('返回辅助面板')
        self.wait_label('当前客户：qahistory · 微信')
        self.state('memory-inferred-tag-persisted')
        self.passed(CHECKS[4])

        self.begin(CHECKS[5])
        self.choose('material-source', '资料来源类型', '客户资料', '朋友圈动态')
        self.focus(first.MATERIAL)
        self.ascii('source')
        self.tap('加入这份资料')
        self.wait(lambda t: any('朋友圈动态' in v and 'source' in v for v in self.texts(t)),
                  'Selected source did not label the locally added material')
        if len(self.receipt()['calls']) != 2:
            raise AssertionError('Selecting/adding an unapproved material made a model request')
        self.passed(CHECKS[5])

        self.begin(CHECKS[6])
        selections = self.report['selectorSelections']
        windows = self.report['windowEvidence']
        if (len(selections) != 8 or {x['id'] for x in selections} != SELECTORS
                or len(windows) != 8 or {x['id'] for x in windows} != SELECTORS
                or any(x.get('dismissed') is not True for x in windows)):
            raise AssertionError('Eight exact dropdown identities need own-secure and dismissal evidence')
        self.passed(CHECKS[6])

        self.begin(CHECKS[7])
        self.tap('普通输入', kind='description')
        self.unchanged_host()
        tree = self.tree('normal-final')
        if any(n.get('hint') in (CHAT, first.MATERIAL, NOTE, '记忆内容')
               for n in self.ime_window(tree).iter('node')):
            raise AssertionError('Returning to normal retained a sensitive internal editor')
        for description in ('q', 'w', 'e'):
            nodes = first.q.key_nodes(tree=tree, description=description, enabled=True)
            if len(nodes) != 1:
                raise AssertionError('Normal full keyboard did not expose the expected enabled letter keys')
            left, top, right, bottom = self.clipped(nodes[0], tree)
            if right-left < 8 or bottom-top < 8:
                raise AssertionError('Normal keyboard key is not visibly touchable')
        self.report['normalKeyboard'] = {'hierarchy': 'normal-final.xml',
                                         'screenSize': list(self.screen),
                                         'enabledVisibleKeys': ['q', 'w', 'e'],
                                         'hostExpected': '', 'hostObserved': self.host_text(tree),
                                         'internalEditorsAbsent': True}
        if len(self.receipt()['calls']) != 2 or self.state()['faults']:
            raise AssertionError('Unexpected model request or synthetic fault in selector suite')
        self.report['observedSyntheticProviderCalls'] = 2
        self.report['realModelCalls'] = 0
        self.state('final')
        self.passed(CHECKS[7])


def self_test():
    class Guards(unittest.TestCase):
        def sample(self, flags='#2000', popup_flags='#2008', parent='Window{abc u0 InputMethod}'):
            def block(index, name, ty, own_flags, attached=''):
                return (f'  Window #{index} Window{{{name}}}:\n'
                        f'    mOwnerUid=10123 mShowToOwnerOnly=false package={first.PACKAGE} appop=NONE\n'
                        f'    mAttrs={{(0,0)(fillxwrap) ty={ty} fl={own_flags}}}\n'
                        f'    {attached}\n    mViewVisibility=0x0 mHasSurface=true\n')
            return block(0, 'abc u0 InputMethod', 2011, flags)+block(
                1, 'def u0 PopupWindow:123', 1002, popup_flags, 'mParentWindow='+parent)

        def test_numeric_and_named_flags(self):
            for parent, popup in [('#2000', '#2008'), ('0x18002000', '0x2008'),
                                  ('NOT_FOCUSABLE SECURE', 'SECURE|NOT_FOCUSABLE|LAYOUT_IN_SCREEN')]:
                self.assertTrue(secure_pair(window_records(self.sample(parent, popup)))['dropdown']['ownSecure'])
            nested = self.sample('SECURE', 'SECURE NOT_FOCUSABLE').replace(
                'ty=2011 fl=SECURE', 'sim={adjust=resize} ty=INPUT_METHOD\n      fl=SECURE')
            self.assertTrue(secure_pair(window_records(nested))['ime']['ownSecure'])

        def test_secure_not_inherited_or_substring_matched(self):
            for parent, popup in [('#2000', '#0'), ('#0', '#2000'), ('SECURE', 'NOT_SECURE'),
                                  ('SECURE', 'NOT_FOCUSABLE pfl=SECURE')]:
                with self.assertRaises(AssertionError):
                    secure_pair(window_records(self.sample(parent, popup)))

        def test_parent_and_owner_must_match(self):
            with self.assertRaises(AssertionError):
                secure_pair(window_records(self.sample(parent='Window{other u0 InputMethod}')))
            records = window_records(self.sample())
            records[1]['uid'] += 1
            with self.assertRaises(AssertionError):
                secure_pair(records)

        def test_dropdown_must_not_take_focus_or_set_alt_ime(self):
            for flags in ['#2000', '#22008', 'SECURE', 'SECURE NOT_FOCUSABLE ALT_FOCUSABLE_IM']:
                with self.assertRaisesRegex(AssertionError, 'NOT_FOCUSABLE'):
                    secure_pair(window_records(self.sample(popup_flags=flags)))

        def test_missing_and_duplicated_windows_rejected(self):
            records = window_records(self.sample())
            for invalid in [[], records[:1], records+[records[1]], [dict(r, visible=False) for r in records]]:
                with self.assertRaises(AssertionError):
                    secure_pair(invalid)

        def test_bound_and_own_attrs_required(self):
            with self.assertRaises(AssertionError):
                window_records('x'*1_000_001)
            with self.assertRaises(AssertionError):
                window_records(self.sample().replace('mAttrs=', 'otherAttrs='))
            with self.assertRaises(AssertionError):
                own_attributes('mAttrs={sim={adjust=resize}')
            with self.assertRaises(AssertionError):
                own_attributes('mAttrs={'+'{'*32+'}'*33)

        def test_device_guard_before_adb(self):
            qa = SelectorQA(Path('.'))
            with patch.object(first.q, 'adb', side_effect=AssertionError('ADB must not be called')) as adb:
                with self.assertRaisesRegex(AssertionError, 'project emulator proof'):
                    qa.window_state('guard')
                adb.assert_not_called()

        def test_exact_selector_set_and_action_deadline(self):
            self.assertEqual(len(SELECTORS), 8)
            qa = SelectorQA(Path('.'))
            qa.started -= 1801
            with self.assertRaisesRegex(AssertionError, 'deadline'):
                qa.record('tap', 'synthetic')

        def test_modal_popup_without_background_ime_is_touchable(self):
            qa = SelectorQA(Path('.'))
            qa.screen = (720, 1280)
            tree = ET.fromstring('<hierarchy><node package="'+first.PACKAGE+'" bounds="[37,183][601,722]">'
                '<node class="android.widget.ListView" bounds="[45,195][593,710]">'
                '<node package="'+first.PACKAGE+'" text="choice" enabled="true" bounds="[45,324][593,452]"/>'
                '</node></node></hierarchy>')
            self.assertEqual(qa.popup_choice(tree, 'choice', (37,183,601,722))[1], (45,324,593,452))
            self.assertFalse(qa.selection_restored(tree, 'selector', 'choice'))
            with self.assertRaises(AssertionError):
                qa.popup_choice(tree, 'choice', (38,183,601,722))
            tree[0][0].append(ET.fromstring('<node package="'+first.PACKAGE+'" text="choice" enabled="true" bounds="[45,453][593,581]"/>'))
            with self.assertRaises(AssertionError):
                qa.popup_choice(tree, 'choice', (37,183,601,722))

        def test_verified_popup_frame_is_not_parent_frame(self):
            raw = self.sample().replace('mParentWindow=',
                'Frames: parent=[0,282][720,1280] frame=[37,183][601,722] last=[37,183][601,722]\n mParentWindow=')
            self.assertEqual(window_frame(raw, 'Window{def u0 PopupWindow:123}'), (37,183,601,722))
            with self.assertRaises(AssertionError):
                window_frame(raw, 'Window{missing u0 PopupWindow:123}')

    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Guards))
    if not result.wasSuccessful():
        raise SystemExit(1)
    print('SELECTOR_SELF_TEST_PASS: 10 parser/guard tests; no device, service or model calls')


if __name__ == '__main__':
    if sys.argv[1:] == ['--self-test']:
        self_test()
    else:
        os.environ['LENS_SYNTHETIC_SCENARIO'] = 'keyboard-details'
        os.environ['LENS_SYNTHETIC_REPLY_DELAY_MS'] = '0'
        first.main(qa_factory=SelectorQA, output_group='keyboard-selector-qa', description=__doc__)
