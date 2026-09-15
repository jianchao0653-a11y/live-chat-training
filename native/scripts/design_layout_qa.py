"""Same-device token-migration geometry evidence; only owned synthetic IME data.

Run with --apk pointing to either the preserved baseline or the rebuilt APK.
No screenshots: FLAG_SECURE remains enabled. Pixel/visual review stays separate.
"""
import json
import re
import time
import keyboard_first_qa as first
from keyboard_ui_qa import focus_visible_practice

CONFIGS = [('portrait', '720x1280', '1.0'), ('large', '720x1280', '2.0'),
           ('narrow', '640x1136', '1.0'), ('landscape', '1280x720', '1.0')]


class LayoutQA(first.QA):
    def __init__(self, folder):
        super().__init__(folder)
        self.report.update(suite='design-layout', checks={name: 'NOT_RUN' for name, _, _ in CONFIGS},
                           comparisonRule='v3: Exact bounds/state and touch rectangles; panel at end, keyboard at start. Scroll in panel padding to preserve the entry focus/input state. Zero pixel tolerance.',
                           notCovered=['protected pixel appearance', 'real phone/OEM', 'all scroll positions', 'OCR/model quality'])
        self.report['geometry'] = {}

    def checkpoint(self, name, target=None, kind='text'):
        if target:
            # AOSP ScrollView flings according to event velocity. A reachable
            # midpoint is not a reproducible scroll offset. Real swipes to the
            # clamped endpoint fix that variable without touching product code.
            previous = None
            unchanged = 0
            for attempt in range(24):
                tree = self.tree()
                shape = tuple((n.get('class'), n.get('text'), n.get('bounds'))
                              for n in self.ime_window(tree).iter('node'))
                unchanged = unchanged+1 if shape == previous else 0
                if unchanged >= 2:
                    break
                previous = shape
                left, top, right, bottom = self.viewport(tree, 'panel')
                # The 8dp body gutter keeps this drag outside EditText bounds,
                # so ACTION_DOWN cannot switch to the URI/date input target.
                first.q.adb('shell','input','swipe',left+4,top+int((bottom-top)*.85),
                            left+4,top+int((bottom-top)*.15),400)
                self.record('canonical_scroll_to_end', name)
                time.sleep(.3)
            else:
                raise AssertionError('Panel end did not stabilize: '+name)
            previous = None
            unchanged = 0
            for attempt in range(24):
                tree = self.tree()
                shape = tuple((n.get('class'), n.get('text'), n.get('description'), n.get('bounds'))
                              for n in self.ime_window(tree).iter('node'))
                unchanged = unchanged+1 if shape == previous else 0
                if unchanged >= 2:
                    break
                previous = shape
                left, top, right, bottom = self.viewport(tree, 'keys')
                first.q.adb('shell','input','swipe',left+4,top+int((bottom-top)*.15),
                            left+4,top+int((bottom-top)*.85),400)
                self.record('canonical_keyboard_scroll_to_start', name)
                time.sleep(.3)
            else:
                raise AssertionError('Keyboard start did not stabilize: '+name)
        previous = None
        for attempt in range(12):
            tree = self.tree(name)
            nodes = [dict(n.attrib) for n in self.ime_window(tree).iter('node')]
            # The tree contains transient platform node IDs; compare observable
            # layout/state, not accessibility identity or fixture timestamps.
            attrs = ('class', 'text', 'description', 'hint', 'bounds', 'enabled', 'clickable', 'checked', 'focused')
            geometry = [{k: n.get(k, '') for k in attrs} for n in nodes]
            if geometry == previous:
                if target:
                    matches = [n for n in self.ime_window(tree).iter('node')
                               if n.get(kind) == target and n.get('enabled') == 'true']
                    if len(matches) != 1:
                        raise AssertionError('Endpoint control ambiguous: '+target)
                    rect = self.clipped(matches[0], tree)
                    if rect[2]-rect[0] < 8 or rect[3]-rect[1] < 8:
                        raise AssertionError('Endpoint control not touchable: '+target)
                    self.report.setdefault('touchRegions', {})[name] = list(rect)
                self.report['geometry'][name] = geometry
                self.save()
                return
            previous = geometry
            time.sleep(.2)
        raise AssertionError('Unstable geometry at '+name)

    def main_flow(self):
        q = first.q
        original_size = q.adb('shell', 'wm', 'size')
        original_font = q.adb('shell', 'settings', 'get', 'system', 'font_scale')
        self.report['originalDisplay'] = {'size': original_size, 'font': original_font,
                                          'density': q.adb('shell', 'wm', 'density')}
        try:
            self.tap('新用户破冰', kind='description')
            self.wait_label('新增客户')
            self.new_customer('styleqa')
            for name, size, font in CONFIGS:
                self.begin(name)
                first.verify_target()
                q.adb('shell', 'am', 'force-stop', first.PACKAGE)
                q.adb('shell', 'wm', 'size', size)
                q.adb('shell', 'settings', 'put', 'system', 'font_scale', font)
                self.screen = tuple(map(int, size.split('x')))
                self.report.setdefault('configurations', {})[name] = {
                    'size': q.adb('shell', 'wm', 'size'),
                    'font': q.adb('shell', 'settings', 'get', 'system', 'font_scale'),
                    'density': q.adb('shell', 'wm', 'density')}
                q.adb('shell', 'am', 'start', '-W', '-n', first.PACKAGE+'/.SetupActivity')
                q.adb('shell', 'ime', 'set', first.COMPONENT)
                focus_visible_practice()
                self.wait_label('普通输入', 45)
                self.host_expected = self.host_text()
                self.checkpoint(name+'-keyboard')
                self.tap('新用户破冰', kind='description')
                self.wait_label('选择：styleqa · 微信')
                self.checkpoint(name+'-roster', '将「styleqa」转入老用户维护')
                self.select_customer('styleqa')
                self.checkpoint(name+'-profile', first.APPROVAL)
                self.tap('客户资料、记忆与反馈')
                self.wait_label('记忆与标记')
                self.checkpoint(name+'-details', '刷新客户资料')
                self.tap('记忆与标记')
                self.wait_label('添加记忆或标记')
                self.tap('添加记忆或标记')
                self.focus('记忆内容')
                self.ascii('walk')
                self.wait(lambda tree: self.field_text('记忆内容', tree) == 'walk', 'Local editor typing failed')
                self.checkpoint(name+'-editor', '放弃修改并返回记忆')
                self.unchanged_host()
                self.tap('普通输入', kind='description')
                self.wait_label('普通输入')
                self.passed(name)
        finally:
            first.verify_target()
            q.adb('shell', 'am', 'force-stop', first.PACKAGE)
            match = re.search(r'Override size:\s*(\S+)', original_size)
            q.adb('shell', 'wm', 'size', match.group(1) if match else 'reset')
            if original_font == 'null':
                q.adb('shell', 'settings', 'delete', 'system', 'font_scale')
            else:
                q.adb('shell', 'settings', 'put', 'system', 'font_scale', original_font)
            self.report['restoredDisplay'] = {
                'size': q.adb('shell', 'wm', 'size'),
                'font': q.adb('shell', 'settings', 'get', 'system', 'font_scale')}
            if self.report['restoredDisplay'] != {'size': original_size, 'font': original_font}:
                raise AssertionError('Display restore did not match its original settings')


if __name__ == '__main__':
    first.main(qa_factory=LayoutQA, output_group='keyboard-design-layout-qa')
