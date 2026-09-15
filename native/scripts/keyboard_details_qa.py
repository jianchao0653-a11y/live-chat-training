"""Synthetic customer history, selected memory and feedback QA with real touches.

Uses keyboard_first_qa's exact APK hash, owned fixture, target proof and cleanup.
Requires an already booted emulator-5556/LensPreview and current loopback debug
APK. Does not start a device. All five customers and their data are synthetic.
Setup activation alone uses ACTION_SET_TEXT; substantive interactions use ADB
taps and the actual project keyboard. No provider calls or protected screenshots.
"""
import json
import os
import time
import keyboard_first_qa as first

CONFIRM = '我已核对当前客户和上述影响'
REREAD = '重新读取最新资料核对'
STALE = '客户资料已变化：此快照仅供核对，不能纳入记忆。'
NOTE = '实际观察'
DRAFT = '实际使用的文字（可空）'
CHECKS = [
    'history_profile_exact_source_trace',
    'only_selected_observations_saved_inference_pending',
    'unknown_write_result_requires_read_only_reconciliation',
    'old_snapshot_cannot_be_adopted_again',
    'unknown_feedback_creation',
    'acknowledged_write_refresh_failure_requires_reconciliation',
    'feedback_correction_preserves_independent_history',
    'unchanged_feedback_does_not_duplicate_event',
    'feedback_deletion_preserves_saved_memories',
    'analysis_deletion_preserves_saved_memories',
    'single_memory_deletion_isolated',
    'host_and_provider_isolation',
    'same_name_customer_selection_by_visible_background',
    'concurrent_revision_409_locks_old_observations_until_readback',
]


class DetailsQA(first.QA):
    def __init__(self, folder):
        super().__init__(folder)
        self.report.update(suite='keyboard-details',
                           checks={name: 'NOT_RUN' for name in CHECKS},
                           scope='synthetic history source mapping, chosen observations, UNKNOWN feedback and isolated deletion',
                           notCovered=['real-phone/OEM behavior', 'provider or OCR quality',
                                       'process death during mutation', 'multiple concurrent client races'])

    def state(self, checkpoint=None):
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
        details = receipt.get('details', {})
        if (receipt.get('synthetic') is not True or receipt.get('realProviderCalls') != 0
                or receipt.get('calls') != [] or details.get('scenario') != 'keyboard-details'
                or details.get('fixtureError')):
            raise AssertionError('Expected the owned details fixture with zero model calls')
        if checkpoint:
            self.report.setdefault('observedSyntheticStates', {})[checkpoint] = details
        return details

    def person(self, name):
        return self.state()['people'][name]

    def request_count(self, route, method='POST'):
        return sum(r['route'] == route and r['method'] == method for r in self.state()['requests'])

    def arm(self, action, ordinal):
        if self.state()['controlId'] != ordinal-1:
            raise AssertionError('Unexpected synthetic fault sequence')
        (self.folder/'fixture-control.json').write_text(
            json.dumps({'id': ordinal, 'action': action}), encoding='utf-8')
        self.record('arm_owned_synthetic_fault', action)

    def confirm(self, title):
        node, _ = self.reach(CONFIRM)
        if node.get('checked') != 'false':
            raise AssertionError('A destructive/save confirmation was preselected')
        self.tap(CONFIRM)
        self.tap('确认'+title)

    def go_history(self, name):
        self.tap('查看分析历史与反馈')
        self.wait_label('分析历史与反馈 · '+name)

    def open_first(self, name):
        self.tap('查看第 1 条详情')
        self.wait_label('分析详情 · '+name)

    def observation(self, identity, tree=None):
        current = tree if tree is not None else self.tree()
        found = [node for node in self.ime_window(current).iter('node')
                 if node.get('description') == '选择画像观察 '+identity]
        if len(found) != 1:
            raise AssertionError('Expected uniquely identified observation '+identity)
        return found[0]

    def source_trace(self):
        source_one = '资料1 · 合成来源甲 · 观察于 2026-09-09'
        source_two = '资料2 · 合成来源乙 · 观察于 2026-09-10'
        for label in [source_one+'\n喜欢散步', source_two+'\n喜欢散步']:
            self.reach(label)
        expected = {'O1': '依据 E1 · '+source_one+'\n“喜欢散步”',
                    'O2': '依据 E2 · '+source_two+'\n“喜欢散步”',
                    'OI': '依据 E2 · '+source_two+'\n“喜欢散步”'}
        for identity, evidence in expected.items():
            self.reach('选择画像观察 '+identity, kind='description')
            tree = self.tree('source-'+identity)
            chosen = self.observation(identity, tree)
            if chosen.get('checked') != 'false':
                raise AssertionError('Historical observation was automatically selected')
            parents = {child: parent for parent in tree.iter() for child in parent}
            siblings = list(parents[chosen])
            after = siblings[siblings.index(chosen)+1:]
            labels = []
            for sibling in after:
                if sibling.get('description', '').startswith('选择画像观察 ') or sibling.get('text') == '仍需确认':
                    break
                labels.append(sibling.get('text', ''))
            if evidence not in labels or any('依据 ' in text and text != evidence for text in labels):
                raise AssertionError('Observation source was matched by duplicated quote instead of its exact evidence/material IDs: '+identity)
        person = self.person('qahistory')
        if person['claims'] or len(person['analyses']) != 1 or person['analyses'][0]['stale']:
            raise AssertionError('Initial profile must be current and must not automatically create memory')
        self.profile_id = person['analyses'][0]['id']
        self.report['expectedObservationSources'] = expected

    def selected_memories(self):
        person = self.person('qahistory')
        claims = person['claims']
        by_observation = {}
        for claim in claims:
            prefix = '画像 '+self.profile_id+'/'
            if not claim['source'].startswith(prefix):
                raise AssertionError('Saved memory lost its analysis/observation source')
            by_observation[claim['source'].split('\n')[0][len(prefix):]] = claim
        if len(claims) != 2 or set(by_observation) != {'O1', 'OI'}:
            raise AssertionError('Exactly the two explicitly chosen observations must be saved')
        own, inference = by_observation['O1'], by_observation['OI']
        if (own['kind'], own['review_state'], own['content']) != ('SELF_DECLARED', 'CONFIRMED', '资料自述喜欢散步。'):
            raise AssertionError('Self-declared observation changed its kind, status or content')
        if own['source'] != '画像 '+self.profile_id+'/O1\n合成来源甲（2026-09-09）：喜欢散步':
            raise AssertionError('Selected O1 memory was saved with the wrong material source')
        if (inference['kind'], inference['review_state']) != ('INFERRED', 'PENDING'):
            raise AssertionError('Inferred memory was automatically confirmed')
        if inference['source'] != '画像 '+self.profile_id+'/OI\n合成来源乙（2026-09-10）：喜欢散步':
            raise AssertionError('Inferred memory was saved with the wrong material source')
        if '待核实：不知道对方现在是否仍感兴趣。' not in inference['content']:
            raise AssertionError('Inference lost its uncertainty')
        if set(person['effectiveClaimIds']) != {own['id']}:
            raise AssertionError('Pending inference entered effective memory context')
        return by_observation

    def touch_locked(self, value, *, kind='text'):
        node, rect = self.reach(value, kind=kind, enabled=False)
        if node.get('enabled') != 'false':
            raise AssertionError('Unreconciled write left an old control enabled: '+value)
        left, top, right, bottom = rect
        self.record('tap', value+' (unreconciled write)')
        first.q.adb('shell', 'input', 'tap', (left+right)//2, (top+bottom)//2)
        time.sleep(.15)

    def readback_lock(self, route, button, destination, *, observation=None):
        self.wait_label(REREAD)
        count = self.request_count(route)
        total = len(self.state()['requests'])
        if count != 1:
            raise AssertionError('Initial synthetic mutation was automatically repeated')
        if observation:
            self.touch_locked('选择画像观察 '+observation, kind='description')
        self.touch_locked(button)
        tree = self.tree('before-read-only-'+route)
        if CONFIRM in self.texts(tree) or any(value.startswith('确认保存') for value in self.texts(tree)):
            raise AssertionError('Old write confirmation survived an unknown result or failed refresh')
        if self.request_count(route) != count or len(self.state()['requests']) != total:
            raise AssertionError('Disabled old controls made another request before actual read-only reconciliation')
        self.unchanged_host()
        self.tap(REREAD)
        self.wait_label(destination)
        self.wait_label('本次提交内容 · 保留供核对')
        if self.request_count(route) != count:
            raise AssertionError('Read-only reconciliation replayed the mutation')
        self.state('reconciled-'+route)

    def feedback_state(self, note):
        person = self.person('qafeedback')
        with_feedback = [a for a in person['analyses'] if a['outcome']]
        if len(person['analyses']) != 2 or len(with_feedback) != 1:
            raise AssertionError('Feedback mutation removed the independent analysis or duplicated an outcome')
        outcome = with_feedback[0]['outcome']
        if (outcome['status'], outcome['note'], outcome['draft']) != ('UNKNOWN', note, 'hello'):
            raise AssertionError('Unknown feedback status/note/draft was not persisted exactly')
        if person['outcomeEvents'] != 1:
            raise AssertionError('Feedback created duplicate effective outcome events')
        if len(person['claims']) != 1 or person['claims'][0]['content'] != 'feedbackkeep':
            raise AssertionError('Feedback mutation changed independent saved memory')
        return person

    def feedback_editor(self, existing=False):
        self.tap('修改实际反馈' if existing else '填写实际反馈')
        self.wait_label('填写实际反馈 · qafeedback')
        tree = self.tree()
        statuses = [n for n in self.ime_window(tree).iter('node') if n.get('description') == '实际反馈状态']
        if len(statuses) != 1 or '未知／尚无回应' not in [n.get('text') for n in statuses[0].iter('node')]:
            raise AssertionError('Feedback default/correction status is not UNKNOWN')

    def save_feedback(self):
        self.tap('核对并保存反馈')
        self.confirm('保存实际反馈')

    def switch_to(self, name):
        self.tap('返回辅助面板')
        self.wait_label('更换客户')
        self.tap('更换客户')
        self.select_customer(name)
        self.tap('客户资料、记忆与反馈')
        self.wait_label('客户资料 · '+name)

    def main_flow(self):
        self.begin(CHECKS[0])
        self.tap('新用户破冰', kind='description')
        self.wait_label('选择：qahistory · 微信')
        self.select_customer('qahistory')
        self.tap('客户资料、记忆与反馈')
        self.wait_label('客户资料 · qahistory')
        self.go_history('qahistory')
        self.open_first('qahistory')
        self.source_trace()
        self.state('initial-source')
        self.passed(CHECKS[0])

        self.begin(CHECKS[1])
        for identity in ('O1', 'OI'):
            self.tap('选择画像观察 '+identity, kind='description')
        if self.observation('O2').get('checked') != 'false':
            raise AssertionError('The same-text unchosen O2 became selected')
        self.arm('profile-drop-response', 1)
        self.tap('核对并保存所选观察')
        self.confirm('保存画像观察')
        self.wait_label(REREAD)
        self.selected_memories()
        faults = self.state('profile-unknown-result')['faults']
        if len(faults) != 1 or faults[0].get('applied') is not True:
            raise AssertionError('Profile response-drop fault did not run')
        self.passed(CHECKS[1])

        self.begin(CHECKS[2])
        self.readback_lock('profile-adopt', '核对并保存所选观察', '记忆与标记 · qahistory', observation='O1')
        self.selected_memories()
        self.passed(CHECKS[2])

        self.begin(CHECKS[3])
        self.tap('返回客户资料')
        self.go_history('qahistory')
        self.open_first('qahistory')
        self.wait_label(STALE)
        tree = self.tree()
        if ('核对并保存所选观察' in self.texts(tree)
                or any(n.get('description', '').startswith('选择画像观察 ') for n in self.ime_window(tree).iter('node'))):
            raise AssertionError('Old snapshot still exposes adoption controls after its version changed')
        self.tap('返回分析历史')
        self.open_first('qahistory')
        self.wait_label(STALE)
        self.selected_memories()
        if self.request_count('profile-adopt') != 1:
            raise AssertionError('Viewing a stale snapshot made another adoption request')
        self.state('stale-no-readoption')
        self.passed(CHECKS[3])

        self.begin(CHECKS[4])
        self.switch_to('qafeedback')
        self.go_history('qafeedback')
        self.open_first('qafeedback')
        self.feedback_editor()
        if first.q.key_nodes(tree=self.tree(), description='切换全键盘', enabled=True):
            self.key('切换全键盘')
        self.focus(NOTE)
        self.ascii('unseen')
        self.focus(DRAFT)
        self.ascii('hello')
        if self.field_text(NOTE) != 'unseen' or self.field_text(DRAFT) != 'hello':
            raise AssertionError('Actual feedback keyboard text differs from the local draft')
        self.unchanged_host()
        self.arm('feedback-refresh-failure', 2)
        self.save_feedback()
        self.wait_label(REREAD)
        self.feedback_state('unseen')
        faults = self.state('feedback-refresh-failed')['faults']
        if len(faults) != 2 or faults[-1].get('postStatus') != 200 or not faults[-1].get('applied'):
            raise AssertionError('Expected POST200 followed by one synthetic GET503')
        self.passed(CHECKS[4])

        self.begin(CHECKS[5])
        self.readback_lock('feedback-save', '核对并保存反馈', '分析历史与反馈 · qafeedback')
        self.feedback_state('unseen')
        self.passed(CHECKS[5])

        self.begin(CHECKS[6])
        self.open_first('qafeedback')
        self.feedback_editor(existing=True)
        self.focus(NOTE)
        self.ascii('later')
        self.wait(lambda tree: self.field_text(NOTE, tree) == 'unseenlater', 'Feedback correction was not typed exactly')
        self.save_feedback()
        self.wait_label('分析历史与反馈 · qafeedback')
        self.feedback_state('unseenlater')
        if self.request_count('feedback-save') != 2:
            raise AssertionError('Feedback correction made an unexpected number of POSTs')
        self.state('feedback-corrected')
        self.passed(CHECKS[6])

        self.begin(CHECKS[7])
        before = self.person('qafeedback')
        self.open_first('qafeedback')
        self.feedback_editor(existing=True)
        self.save_feedback()
        self.wait_label('分析历史与反馈 · qafeedback')
        after = self.feedback_state('unseenlater')
        if before != after or self.request_count('feedback-save') != 3:
            raise AssertionError('An explicitly repeated unchanged feedback altered revision/history or was automatically replayed')
        self.state('unchanged-feedback')
        self.passed(CHECKS[7])

        self.begin(CHECKS[8])
        history_before = self.person('qahistory')
        keep = self.person('qafeedback')['claims']
        self.open_first('qafeedback')
        self.tap('删除反馈及该客户旧分析')
        self.confirm('删除反馈')
        self.wait_label('客户资料 · qafeedback')
        deleted = self.person('qafeedback')
        if deleted['analyses'] or deleted['outcomeEvents'] or deleted['claims'] != keep or self.person('qahistory') != history_before:
            raise AssertionError('Feedback deletion did not clear all own history while preserving both customers memories and isolation')
        self.go_history('qafeedback')
        self.wait_label('暂时没有分析记录。')
        self.state('feedback-deleted')
        self.passed(CHECKS[8])

        self.begin(CHECKS[9])
        self.switch_to('qahistory')
        self.go_history('qahistory')
        self.open_first('qahistory')
        claims_before = self.person('qahistory')['claims']
        self.tap('删除这份分析快照')
        self.confirm('删除分析快照')
        self.wait_label('暂时没有分析记录。')
        person = self.person('qahistory')
        if person['analyses'] or person['claims'] != claims_before:
            raise AssertionError('Deleting the profile analysis also deleted separately saved memories')
        self.state('analysis-deleted')
        self.passed(CHECKS[9])

        self.begin(CHECKS[10])
        self.tap('返回客户资料')
        self.tap('记忆与标记')
        self.wait_label('记忆与标记 · qahistory')
        tree = self.tree()
        marker = '画像 '+self.profile_id+'/O1\n'
        labels = [node for node in self.ime_window(tree).iter('node') if marker in node.get('text', '')]
        if len(labels) != 1:
            raise AssertionError('Expected one displayed memory with exact O1 source')
        parents = {child: parent for parent in tree.iter() for child in parent}
        buttons = [node.get('text') for node in parents[labels[0]].iter('node')
                   if node.get('text', '').startswith('修改或删除第 ')]
        if len(buttons) != 1:
            raise AssertionError('Cannot uniquely match selected memory to its edit/delete card')
        own = self.selected_memories()
        self.tap(buttons[0])
        if '/O1\n' not in self.field_text('记忆来源'):
            raise AssertionError('The wrong saved memory was opened for deletion')
        self.tap('删除此条记忆')
        self.confirm('删除记忆')
        self.wait_label('记忆与标记 · qahistory')
        person = self.person('qahistory')
        if person['claims'] != [own['OI']] or person['effectiveClaimIds'] or person['analyses']:
            raise AssertionError('Deleting O1 changed pending OI or restored deleted analysis')
        if self.person('qafeedback')['claims'] != keep:
            raise AssertionError('Memory deletion changed the other customer')
        self.state('single-memory-deleted')
        self.passed(CHECKS[10])

        self.begin(CHECKS[11])
        self.tap('返回辅助面板')
        self.wait_label('当前客户：qahistory · 微信')
        self.unchanged_host()
        self.tap('普通输入', kind='description')
        self.unchanged_host()
        self.state('final')
        self.report['observedSyntheticProviderCalls'] = 0
        self.passed(CHECKS[11])

        self.begin(CHECKS[12])
        before = {key: self.person(key) for key in ('samewalk', 'samebake')}
        self.tap('新用户破冰', kind='description')
        self.wait_label('选择：qasame · 微信')
        for key, note in [('samewalk', '合成区分甲：喜欢徒步'), ('samebake', '合成区分乙：喜欢烘焙')]:
            self.reach('背景：'+note)
            tree = self.tree('same-name-row-'+key)
            anchors = [n for n in self.ime_window(tree).iter('node') if n.get('text') == '背景：'+note]
            if len(anchors) != 1:
                raise AssertionError('Cannot uniquely identify a same-name customer by the visible background')
            parents = {child: parent for parent in tree.iter() for child in parent}
            card = parents[anchors[0]]
            choices = [n for n in card.iter('node') if n.get('text') == '选择：qasame · 微信']
            if len(choices) != 1:
                raise AssertionError('Visible same-name background does not map to exactly one selection button')
            left, top, right, bottom = self.clipped(choices[0], tree)
            if right-left < 8 or bottom-top < 8:
                # Bring the known button into view by scrolling the card, never
                # choose one of the duplicate labels by its position in the list.
                left, top, right, bottom = self.viewport(tree, 'panel', choices[0])
                y = first.q.node_bounds(choices[0])[1]
                down = y >= bottom
                self.record('swipe', 'same-name row '+key)
                first.q.adb('shell', 'input', 'swipe', (left+right)//2,
                            top+int((bottom-top)*(.78 if down else .22)), (left+right)//2,
                            top+int((bottom-top)*(.22 if down else .78)), 250)
                tree = self.tree()
                anchors = [n for n in self.ime_window(tree).iter('node') if n.get('text') == '背景：'+note]
                parents = {child: parent for parent in tree.iter() for child in parent}
                choices = [n for n in parents[anchors[0]].iter('node') if n.get('text') == '选择：qasame · 微信']
                left, top, right, bottom = self.clipped(choices[0], tree)
            if right-left < 8 or bottom-top < 8 or choices[0].get('enabled') != 'true':
                raise AssertionError('Same-name customer button is not safely touchable next to its background')
            self.record('tap', '选择：qasame · 微信 / 背景：'+note)
            first.q.adb('shell', 'input', 'tap', (left+right)//2, (top+bottom)//2)
            self.wait_label('当前客户：qasame · 微信')
            self.wait_label('客户背景（由你填写，请核对）：'+note)
            self.unchanged_host()
            self.tap('客户资料、记忆与反馈')
            self.wait_label('客户资料 · qasame')
            self.wait(lambda current: any('背景：'+note+'\n' in value for value in self.texts(current)),
                      'Details panel opened the wrong same-name customer')
            self.tap('记忆与标记')
            self.wait(lambda current: any(value.startswith(key+'\n来源：') for value in self.texts(current)),
                      'Same-name selection exposed the other customer memory')
            other = 'samebake' if key == 'samewalk' else 'samewalk'
            if any(value.startswith(other+'\n来源：') for value in self.texts()):
                raise AssertionError('Same-name customer memories mixed together')
            self.tap('返回辅助面板')
            self.tap('更换客户')
        if {key: self.person(key) for key in before} != before:
            raise AssertionError('Viewing/selecting same-name customers mutated their data')
        self.unchanged_host()
        self.state('same-name-selected-by-background')
        self.passed(CHECKS[12])

        self.begin(CHECKS[13])
        self.select_customer('qastale')
        self.tap('客户资料、记忆与反馈')
        self.wait_label('客户资料 · qastale')
        self.go_history('qastale')
        self.open_first('qastale')
        self.wait_label('这是本次资料快照，尚未自动加入客户记忆。')
        initial = self.person('qastale')
        others = {key: value for key, value in self.state()['people'].items() if key != 'qastale'}
        if initial['claims'] or len(initial['analyses']) != 1 or initial['analyses'][0]['stale']:
            raise AssertionError('Concurrent test requires a separately current profile with no saved memory')
        for identity in ('O1', 'O2', 'OI'):
            if self.observation(identity).get('checked') != 'false':
                raise AssertionError('Concurrent test profile observations were preselected')
        self.tap('选择画像观察 O1', kind='description')
        self.arm('profile-concurrent-revision', 3)
        self.tap('核对并保存所选观察')
        self.confirm('保存画像观察')
        self.wait_label(REREAD)
        self.wait(lambda tree: any(value.startswith('资料状态已变化或暂不可写入，旧选择已暂停。') for value in self.texts(tree)),
                  'Actual server409 was not shown as a conflict requiring readback')
        state = self.state('concurrent-409-before-readback')
        requests = [r for r in state['requests'] if r['route'] == 'stale-profile-adopt' and r['method'] == 'POST']
        fault = state['faults'][-1]
        current = state['people']['qastale']
        if len(requests) != 1 or requests[0]['status'] != 409:
            raise AssertionError('Expected exactly one actual cloud adoption POST rejected with409')
        if (fault.get('action') != 'profile-concurrent-revision' or not fault.get('applied')
                or fault.get('responseSynthesized') is not False
                or fault.get('beforeRevision') != initial['revision']
                or fault.get('afterRevision') != current['revision']
                or initial['revision'] == current['revision']):
            raise AssertionError('The concurrent change did not advance the real revision before cloud validation')
        if len(current['claims']) != 1 or current['claims'][0]['content'] != 'concurrentreview':
            raise AssertionError('The rejected old observation was saved or concurrent memory was lost')
        self.readback_lock('stale-profile-adopt', '核对并保存所选观察', '记忆与标记 · qastale', observation='O1')
        self.wait_label('此前请求被服务拒绝；已读取最新资料，请重新核对后操作。')
        self.tap('返回客户资料')
        self.go_history('qastale')
        self.open_first('qastale')
        self.wait_label(STALE)
        tree = self.tree('concurrent-409-reread-stale')
        if ('核对并保存所选观察' in self.texts(tree)
                or any(node.get('description', '').startswith('选择画像观察 ') for node in self.ime_window(tree).iter('node'))):
            raise AssertionError('Re-reading the conflicted snapshot restored stale adoption choices')
        final = self.person('qastale')
        if (final != current or final['analyses'][0]['id'] != initial['analyses'][0]['id']
                or not final['analyses'][0]['stale'] or self.request_count('stale-profile-adopt') != 1):
            raise AssertionError('Conflict reconciliation mutated data, replayed POST or opened a different analysis')
        if {key: value for key, value in self.state()['people'].items() if key != 'qastale'} != others:
            raise AssertionError('Concurrent fixture changed an independent customer')
        self.unchanged_host()
        self.state('concurrent-409-final')
        self.passed(CHECKS[13])


if __name__ == '__main__':
    os.environ['LENS_SYNTHETIC_SCENARIO'] = 'keyboard-details'
    os.environ['LENS_SYNTHETIC_REPLY_DELAY_MS'] = '0'
    first.main(qa_factory=DetailsQA, output_group='keyboard-details-qa', description=__doc__)
