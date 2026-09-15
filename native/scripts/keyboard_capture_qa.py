"""Actual-touch one-frame capture QA on the owned synthetic emulator only.

Requires API 34+ emulator-5556/LensPreview, current 0.18.0/code23 loopback debug
APK, and DumpRunner. Reuses keyboard_first_qa's isolated fake cloud and cleanup.
Exercises real notification denial/allow and system MediaProjection consent.
Never grants capture with appops, writes screenshot files, invokes OCR/models,
opens a real chat app, or weakens FLAG_SECURE. Protected pixels may be black;
the bounded UI receipt proves a preview exists, not its pixel/OCR quality.
Use --stop-only for the separate notification-stop/retry suite. It does not
replace the seven-check capture suite required by delivery acceptance.
"""
import argparse
import json
from pathlib import Path
import re
import sys
import time
import keyboard_first_qa as first

NAME = 'qacapture'
INTENT = '本次画像关注点（选填，最多1000字）'
CAPTURE = '截取当前画面一次'
PREVIEW = '待校对图片，仅保存在本机内存'
DENIED = '未允许截图停止通知，未捕获画面；可选择图片或输入文字'
CANCELLED = '已取消截图授权，未捕获画面；请重新核对客户'
CAPTURED = '已截取一帧，请核对应用、聊天对象和文字；受保护或空白画面可改用文字。尚未上传'
STOPPED = '已主动停止截图'
NOTICE_TITLE = '3 秒后截取一帧画面'
STOP_LABEL = '停止截图'
SERVICE = first.PACKAGE+'.KeyboardCaptureService'
NOTIFICATIONS = 'android.permission.POST_NOTIFICATIONS'
PERMISSION_PACKAGES = {'com.android.permissioncontroller', 'com.google.android.permissioncontroller'}
SYSTEM_UI = {'com.android.systemui'}
DENY_LABELS = {"Don't allow", 'DON’T ALLOW', 'Don’t allow', "DON'T ALLOW", '不允许', '拒绝'}
ALLOW_LABELS = {'Allow', 'ALLOW', '允许'}
CANCEL_LABELS = {'Cancel', 'CANCEL', '取消'}
SINGLE_LABELS = {'Share one app', 'A single app', 'Single app', '共享一个应用', '单个应用', '共享单个应用'}
FULL_LABELS = {'Share entire screen', 'Entire screen', 'Your entire screen', '共享整个屏幕', '整个屏幕'}
START_LABELS = {'SHARE SCREEN', 'Share screen', 'Start now', 'START NOW', 'Start', 'START', '立即开始', '开始共享', '开始'}
FULL_SCREEN_NOTICE_PHRASES = {
    'all of the information that is visible on your screen',
    '屏幕上显示的所有信息',
    '屏幕上可见的所有信息',
}
CAPTURE_CHECKS = ['owned_customer_and_local_drafts',
                  'notification_denial_blocks_capture_and_restores_drafts',
                  'projection_cancel_restores_unapproved_drafts',
                  'explicit_full_screen_system_consent',
                  'returned_keyboard_frame_preview_and_renewed_approval',
                  'capture_service_and_projection_ended',
                  'discard_keeps_drafts_and_never_calls_models']
STOP_CHECKS = ['owned_customer_and_local_drafts',
               'notification_stop_releases_capture_without_frame',
               'fresh_capture_after_stop_returns_and_discards_preview']


class CaptureQA(first.QA):
    def __init__(self, folder):
        super().__init__(folder)
        self.report['suite'] = 'keyboard-capture'
        self.report['checks'] = {name: 'NOT_RUN' for name in CAPTURE_CHECKS}
        self.report['scope'] = 'synthetic SetupActivity; explicit full-screen system consent; in-memory preview and teardown'
        self.report['notCovered'] = ['captured pixel correctness or OCR quality', 'single-app capture',
                                     'rotation/resizing', 'OEM/real phone', 'notification stop-action touch',
                                     'screen-off, lock, timeout or process-death on device',
                                     'cross-app/customer identity matching']
        self.report['pixelFilesWritten'] = False
        self.report['ocrRequested'] = False
        self.report['notificationPermissionMethod'] = 'actual system deny and allow dialogs; no pm grant'
        self.report['notificationPermissionRestored'] = False

    def notification_granted(self):
        value = first.q.adb('shell', 'dumpsys', 'package', first.PACKAGE)
        if len(value) > 2_000_000:
            raise AssertionError('Synthetic package evidence exceeded the size bound')
        matches = re.findall(re.escape(NOTIFICATIONS)+r': granted=(true|false)', value)
        if len(matches) != 1:
            raise AssertionError('Expected one runtime notification permission state')
        return matches[0] == 'true'

    def system_nodes(self, tree, packages, predicate):
        matches = []
        for node in tree.iter('node'):
            if node.get('package') not in packages or node.get('enabled') != 'true' or not predicate(node):
                continue
            left, top, right, bottom = self.clipped(node, tree)
            if right-left >= 8 and bottom-top >= 8:
                matches.append((node, (left, top, right, bottom)))
        return matches

    def tap_system(self, packages, predicate, label, seconds=12):
        deadline = time.monotonic()+seconds
        while time.monotonic() < deadline:
            tree = self.tree('system-capture')
            matches = self.system_nodes(tree, packages, predicate)
            if len(matches) > 1:
                raise AssertionError('Ambiguous system capture control: '+label)
            if matches:
                node, (left, top, right, bottom) = matches[0]
                self.record('system_capture_tap', label+': '+node.get('text', ''))
                first.q.adb('shell', 'input', 'tap', (left+right)//2, (top+bottom)//2)
                time.sleep(.2)
                return node.get('text', '')
            time.sleep(.15)
        raise AssertionError('System capture control was not visible: '+label)

    @staticmethod
    def button_in(labels):
        return lambda node: node.get('text') in labels and node.get('class', '').endswith('Button')

    def assert_original_host(self):
        self.unchanged_host()
        activities = first.q.adb('shell', 'dumpsys', 'activity', 'activities')
        if len(activities) > 2_000_000:
            raise AssertionError('Activity evidence exceeded the synthetic bound')
        resumed = [line.strip() for line in activities.splitlines()
                   if re.search(r'\b(?:mResumedActivity|topResumedActivity|ResumedActivity)\s*[:=]', line)]
        if not resumed or any(first.PACKAGE+'/.SetupActivity' not in line for line in resumed):
            raise AssertionError('Only the original synthetic SetupActivity may be resumed for capture')
        self.report['verifiedCaptureHost'] = first.PACKAGE+'/.SetupActivity'

    def assert_drafts(self, *, unchecked):
        tree = self.tree('restored-capture-owner')
        self.ime_window(tree)
        if '当前客户：'+NAME+' · 微信' not in self.texts(tree):
            raise AssertionError('Capture returned to another customer')
        if self.field_text(INTENT, tree) != 'hello' or self.field_text(first.MATERIAL, tree) != 'before':
            raise AssertionError('Capture handoff changed the exact unsubmitted local drafts')
        expected = 'false' if unchecked else 'true'
        for label in ['已核对当前聊天对象是「'+NAME+'」', first.APPROVAL]:
            nodes = [node for node in self.ime_window(tree).iter('node') if node.get('text') == label]
            if len(nodes) != 1 or nodes[0].get('checked') != expected:
                raise AssertionError('Capture confirmation state is not '+expected+': '+label)
        if any(node.get('hint') == first.DRAFT or '并插入' in node.get('text', '')
               for node in self.ime_window(tree).iter('node')):
            raise AssertionError('A candidate insertion draft survived the capture handoff')
        self.assert_original_host()
        return tree

    def returned(self, message):
        # Observe automatic restoration first. Some systems require the user's
        # next touch on the original input field. That explicit product step is
        # allowed, but it must never be replaced with am start/force-show or a
        # fake result and cannot be described as automatic restoration.
        deadline = time.monotonic()+12
        mode = 'automatic'
        while time.monotonic() < deadline:
            tree = self.tree('capture-return-observation')
            if any(message in value for value in self.texts(tree)):
                break
            time.sleep(.15)
        else:
            self.assert_original_host()
            tree = self.tree('capture-before-original-host-touch')
            if self.system_nodes(tree, PERMISSION_PACKAGES, self.button_in(ALLOW_LABELS|DENY_LABELS)) \
                    or self.system_nodes(tree, SYSTEM_UI, self.button_in(CANCEL_LABELS|START_LABELS)):
                raise AssertionError('A consent dialog still covers the original input field')
            fields = [node for node in tree.iter('node') if node.get('package') == first.PACKAGE
                      and node.get('hint') == first.PRACTICE and node.get('password') == 'false']
            if len(fields) != 1:
                raise AssertionError('Original synthetic input field is unavailable for an explicit return touch')
            left, top, right, bottom = self.clipped(fields[0], tree)
            ime_windows = [node for node in tree.findall('node') if any(
                child.get('description') == '普通输入' for child in node.iter('node'))]
            if ime_windows:
                bottom = min(bottom, min(first.q.node_bounds(node)[1] for node in ime_windows))
            if right-left < 8 or bottom-top < 8:
                raise AssertionError('Original synthetic input field is not safely visible above the keyboard')
            self.record('host_restore_touch', 'Original SetupActivity practice field after 12-second observation')
            first.q.adb('shell', 'input', 'tap', (left+right)//2, (top+bottom)//2)
            mode = 'explicit_original_host_touch'
            self.wait(lambda current: any(message in value for value in self.texts(current)),
                      'Expected capture result did not return after touching the original field: '+message, 12)
        self.report.setdefault('restorationSteps', []).append({'result': message, 'method': mode})
        return self.assert_drafts(unchecked=True)

    def no_preview(self, tree):
        if any(node.get('description') == PREVIEW for node in self.ime_window(tree).iter('node')):
            raise AssertionError('Cancelled/denied capture unexpectedly supplied image pixels')

    def no_model_calls(self):
        path = self.folder/'fixture-receipt.json'
        if path.stat().st_size > 2_000_000:
            raise AssertionError('Synthetic fixture evidence exceeded its size bound')
        receipt = json.loads(path.read_text(encoding='utf-8'))
        if receipt.get('synthetic') is not True or receipt.get('realProviderCalls') != 0 or receipt.get('calls') != []:
            raise AssertionError('Capture/preview unexpectedly called a model provider')
        self.report['mockProviderCalls'] = 0
        self.report['realProviderCalls'] = 0

    def notification_dialog(self, allow):
        tree = self.wait(lambda current: bool(self.system_nodes(current, PERMISSION_PACKAGES,
                                                               self.button_in(ALLOW_LABELS)))
                         and bool(self.system_nodes(current, PERMISSION_PACKAGES, self.button_in(DENY_LABELS))),
                         'Actual runtime notification permission dialog did not appear', 15)
        labels = [node.get('text', '') for node in tree.iter('node') if node.get('package') in PERMISSION_PACKAGES]
        if not any('notification' in value.lower() or '通知' in value for value in labels):
            raise AssertionError('Visible permission dialog is not a notification request')
        self.tree('notification-allow-dialog' if allow else 'notification-deny-dialog')
        selected = self.tap_system(PERMISSION_PACKAGES, self.button_in(ALLOW_LABELS if allow else DENY_LABELS),
                                   'Allow notifications' if allow else 'Deny notifications')
        self.report.setdefault('notificationDialogChoices', []).append({'allowed': allow, 'button': selected,
                                                                       'actualSystemDialog': True})
        if self.notification_granted() != allow:
            raise AssertionError('Actual notification permission state did not match the system choice')

    def projection_dialog(self):
        tree = self.wait(lambda current: bool(self.system_nodes(current, SYSTEM_UI, self.button_in(CANCEL_LABELS)))
                         and (bool(self.system_nodes(current, SYSTEM_UI,
                                                     lambda node: node.get('class') == 'android.widget.Spinner'))
                              or bool(self.system_nodes(current, SYSTEM_UI, self.button_in(START_LABELS)))),
                         'Actual MediaProjection sharing dialog did not appear', 15)
        selectors = self.system_nodes(tree, SYSTEM_UI, lambda node: node.get('class') == 'android.widget.Spinner')
        if selectors:
            if len(selectors) != 1:
                raise AssertionError('Expected one system sharing-area selector')
            labels = [child.get('text') for child in selectors[0][0].iter('node') if child.get('text')]
            if len(labels) != 1 or labels[0] not in SINGLE_LABELS|FULL_LABELS:
                raise AssertionError('Unrecognized sharing-area selection; refusing a blind Start/Next')
            selected = labels[0]
            layout = 'area-selector'
        else:
            # The API 34 r04 AOSP image presents the earlier full-screen-only
            # consent page. Require its explicit full-screen disclosure before
            # accepting START NOW; do not infer consent from a generic button.
            notices = ' '.join(node.get('text', '') for node in tree.iter('node')
                               if node.get('package') in SYSTEM_UI).lower()
            if int(self.report['api']) != 34 or not any(
                    phrase.lower() in notices for phrase in FULL_SCREEN_NOTICE_PHRASES):
                raise AssertionError('System consent has no verified sharing-area selector or full-screen disclosure')
            selected = 'Entire screen'
            layout = 'api34-full-screen-only'
        self.report.setdefault('projectionDialogLayouts', []).append(layout)
        self.report.setdefault('projectionDialogInitialChoices', []).append(selected)
        self.tree('projection-consent-'+str(len(self.report['projectionDialogInitialChoices'])))
        return selected

    def choose_full_screen(self):
        initial = self.projection_dialog()
        if initial in SINGLE_LABELS:
            self.tap_system(SYSTEM_UI, lambda node: node.get('class') == 'android.widget.Spinner',
                            'Open sharing-area selector')
            selected = self.tap_system(SYSTEM_UI, lambda node: node.get('text') in FULL_LABELS,
                                      'Explicitly choose the entire synthetic screen')
        else:
            selected = initial
        tree = self.tree('projection-full-screen-selected')
        selectors = self.system_nodes(tree, SYSTEM_UI, lambda node: node.get('class') == 'android.widget.Spinner')
        if selectors:
            if len(selectors) != 1 or not any(child.get('text') in FULL_LABELS for child in selectors[0][0].iter('node')):
                raise AssertionError('The system did not select entire-screen sharing')
        else:
            notices = ' '.join(node.get('text', '') for node in tree.iter('node')
                               if node.get('package') in SYSTEM_UI).lower()
            if int(self.report['api']) != 34 or initial not in FULL_LABELS or not any(
                    phrase.lower() in notices for phrase in FULL_SCREEN_NOTICE_PHRASES):
                raise AssertionError('The system did not expose verified entire-screen sharing')
        if not self.system_nodes(tree, SYSTEM_UI, self.button_in(START_LABELS)):
            raise AssertionError('Full-screen Start/Share Screen action is not visible; do not click single-app Next')
        self.report['systemCaptureArea'] = {'initial': initial, 'selected': selected, 'fullScreenVerifiedBeforeStart': True}
        return self.tap_system(SYSTEM_UI, self.button_in(START_LABELS), 'Start explicitly selected full-screen capture')

    def stopped_state(self, label):
        services = first.q.adb('shell', 'dumpsys', 'activity', 'services', first.PACKAGE)
        projection = first.q.adb('shell', 'dumpsys', 'media_projection')
        if len(services) > 2_000_000 or len(projection) > 65536:
            raise AssertionError('Capture lifecycle evidence exceeded its bound')
        if 'ACTIVITY MANAGER SERVICES' not in services or 'MEDIA PROJECTION MANAGER' not in projection:
            raise AssertionError('The platform did not return inspectable capture service/projection state')
        active_services = [line.strip() for line in services.splitlines()
                           if 'ServiceRecord{' in line and ('KeyboardCaptureService' in line)]
        # AOSP's active grant is printed immediately after "Media Projection:".
        # Require the explicit null representation; name disappearance alone
        # cannot establish that capture stopped.
        projection_none = bool(re.search(r'(?m)^\s*Media Projection:[ \t]*\r?\n[ \t]*null[ \t]*$', projection))
        evidence = {'captureServiceRecords': active_services, 'projectionExplicitlyNull': projection_none}
        self.report.setdefault('captureLifecycle', {})[label] = evidence
        self.save()
        if active_services or not projection_none:
            raise AssertionError('Capture service/projection has not ended: '+label)

    def main_flow(self):
        if int(self.report['api']) < 34:
            raise RuntimeError('This consent-area/notification suite requires API34+; older devices are not silently passed')
        initial_permission = self.notification_granted()
        self.report['initialNotificationPermissionGranted'] = initial_permission
        if initial_permission:
            raise AssertionError('Fresh synthetic installation unexpectedly already allows notifications')
        try:
            self.capture_flow()
        finally:
            # Restore only the runtime grant this suite changed through the real
            # system dialog. first.main restores the IME/reverse/owned fixture.
            if self.notification_granted() != initial_permission:
                first.verify_target()
                first.q.adb('shell', 'pm', 'revoke', first.PACKAGE, NOTIFICATIONS)
            restored = self.notification_granted() == initial_permission
            self.report['notificationPermissionRestored'] = restored
            self.save()
            if not restored:
                raise AssertionError('Synthetic notification permission cleanup failed')

    def prepare_capture_drafts(self):
        self.begin('owned_customer_and_local_drafts')
        self.tap('新用户破冰', kind='description')
        self.wait_label('新增客户')
        self.new_customer(NAME)
        self.select_customer(NAME)
        self.focus(INTENT)
        self.ascii('hello')
        self.focus(first.MATERIAL)
        self.ascii('before')
        self.wait(lambda tree: self.field_text(first.MATERIAL, tree) == 'before', 'Synthetic source draft was not typed')
        self.approve(NAME)
        self.assert_drafts(unchecked=False)
        self.stopped_state('before-first-capture')
        self.no_model_calls()
        self.passed('owned_customer_and_local_drafts')

    def capture_flow(self):
        self.prepare_capture_drafts()
        self.begin('notification_denial_blocks_capture_and_restores_drafts')
        self.tap(CAPTURE)
        self.notification_dialog(False)
        self.no_preview(self.returned(DENIED))
        self.stopped_state('after-notification-denial')
        self.no_model_calls()
        self.passed('notification_denial_blocks_capture_and_restores_drafts')

        self.begin('projection_cancel_restores_unapproved_drafts')
        self.approve(NAME)
        self.assert_drafts(unchecked=False)
        self.tap(CAPTURE)
        self.notification_dialog(True)
        self.projection_dialog()
        self.tap_system(SYSTEM_UI, self.button_in(CANCEL_LABELS), 'Cancel actual MediaProjection consent')
        self.no_preview(self.returned(CANCELLED))
        self.stopped_state('after-projection-cancel')
        self.no_model_calls()
        self.passed('projection_cancel_restores_unapproved_drafts')

        self.begin('explicit_full_screen_system_consent')
        self.approve(NAME)
        self.assert_drafts(unchecked=False)
        self.tap(CAPTURE)
        self.report['systemCaptureStartButton'] = self.choose_full_screen()
        # passed() records only bounded XML, never a system screenshot.
        self.passed('explicit_full_screen_system_consent')

        self.begin('returned_keyboard_frame_preview_and_renewed_approval')
        tree = self.returned(CAPTURED)
        preview = [node for node in self.ime_window(tree).iter('node')
                   if node.get('description') == PREVIEW and node.get('class') == 'android.widget.ImageView']
        if len(preview) != 1:
            raise AssertionError('Captured frame preview is not present inside the original keyboard')
        self.reach(PREVIEW, kind='description', enabled=False)
        self.no_model_calls()
        self.report['previewEvidence'] = {'insideOriginalKeyboard': True, 'imageViews': 1,
                                          'pixelCorrectness': 'NOT_TESTED', 'protectedRegionsMayBeBlack': True}
        self.passed('returned_keyboard_frame_preview_and_renewed_approval')

        self.begin('capture_service_and_projection_ended')
        self.stopped_state('after-preview')
        self.passed('capture_service_and_projection_ended')

        self.begin('discard_keeps_drafts_and_never_calls_models')
        self.tap('丢弃图片')
        self.no_preview(self.assert_drafts(unchecked=True))
        self.no_model_calls()
        self.stopped_state('after-discard')
        self.passed('discard_keeps_drafts_and_never_calls_models')


class StopCaptureQA(CaptureQA):
    def __init__(self, folder):
        super().__init__(folder)
        self._notification_shade_opened = False
        self.report['suite'] = 'keyboard-capture-stop'
        self.report['checks'] = {name: 'NOT_RUN' for name in STOP_CHECKS}
        self.report['scope'] = 'synthetic SetupActivity; actual capture-notification stop within the unchanged three-second window, then a fresh capture'
        self.report['notificationPermissionMethod'] = 'actual system allow dialog; no pm grant'
        self.report['notCovered'] = ['notification denial', 'projection consent cancellation',
                                     'captured pixel correctness or OCR quality', 'single-app capture',
                                     'rotation/resizing', 'OEM/real phone',
                                     'screen-off, lock, timeout or process-death on device',
                                     'cross-app/customer identity matching']
        self.report['replacesFullCaptureSuite'] = False

    def notification_shade_state(self, tree):
        windows = [node for node in tree.findall('node')
                   if node.get('package') in SYSTEM_UI
                   and first.q.node_bounds(node)[3]-first.q.node_bounds(node)[1] > self.screen[1]*.7]
        if not windows:
            return 'absent'
        for window in windows:
            labels = {node.get('text', '') for node in window.iter('node')}
            # The capture notification may already have disappeared. Require
            # observed shade controls, never just an arbitrary SystemUI dialog.
            if NOTICE_TITLE in labels or (labels & {'Internet', '互联网'}
                                          and labels & {'Bluetooth', '蓝牙'}):
                return 'shade'
        return 'other_system_overlay'

    def close_owned_notification_shade(self):
        if not self._notification_shade_opened:
            return
        evidence = {'openedByThisSuite': True, 'actualBackPresses': 0,
                    'restored': False, 'usesStatusbarCommand': False}
        self.report['notificationShadeCleanup'] = evidence
        first.verify_target()
        # AOSP handles expanded quick settings before the notification shade.
        # At most two BACK presses, each gated by a fresh observed shade tree.
        for attempt in range(3):
            tree = self.tree('stop-shade-cleanup-'+str(attempt))
            state = self.notification_shade_state(tree)
            evidence.setdefault('observedStates', []).append(state)
            self.save()
            if state == 'absent':
                evidence['restored'] = True
                self._notification_shade_opened = False
                self.save()
                return
            if state != 'shade':
                raise AssertionError('Owned notification shade cleanup encountered another system overlay; refusing BACK')
            if attempt == 2:
                raise AssertionError('Owned notification shade remained after two observed real BACK presses')
            self.record('notification_shade_close', 'Actual BACK for this suite\'s observed notification shade')
            first.q.adb('shell', 'input', 'keyevent', '4')
            evidence['actualBackPresses'] += 1
            time.sleep(.2)

    def stop_from_actual_notification(self):
        starts = [action for action in self.report['actions']
                  if action['action'] == 'system_capture_tap'
                  and action['target'].startswith('Start explicitly selected full-screen capture:')]
        if not starts:
            raise AssertionError('An observed actual system Start tap is required before notification stop')
        started = starts[-1]['at']
        attempt = {'shareScreenTapAt': started, 'productCountdownSeconds': 3,
                   'notificationExpandedByQa': False, 'stopButtonTouched': False,
                   'usesServiceCommand': False, 'usesStatusbarCommand': False}
        self.report['notificationStopAttempt'] = attempt
        self.save()

        def remaining():
            elapsed = time.monotonic()-started
            attempt['elapsedFromShareTapSeconds'] = round(elapsed, 3)
            if elapsed >= 3:
                self.save()
                raise AssertionError('The unchanged three-second capture window elapsed before an actual notification Stop tap; no service-command substitute was used')

        def own_controls(tree, predicate):
            titles = [node for node in tree.iter('node')
                      if node.get('package') in SYSTEM_UI and node.get('text') == NOTICE_TITLE]
            if len(titles) != 1:
                raise AssertionError('The unique project capture notification is not visible in the actual notification shade')
            parents = {child: parent for parent in tree.iter() for child in parent}
            ancestor = parents.get(titles[0])
            while ancestor is not None and ancestor.tag == 'node':
                # Do not climb into the whole notification stack and accidentally
                # borrow an action/expander from another notification.
                bounds = first.q.node_bounds(ancestor)
                if bounds[3]-bounds[1] > self.screen[1]*.55:
                    break
                candidates = [node for node in ancestor.iter('node')
                              if node.get('package') in SYSTEM_UI and node.get('enabled') == 'true' and predicate(node)]
                visible = []
                for node in candidates:
                    left, top, right, bottom = self.clipped(node, tree)
                    if right-left >= 8 and bottom-top >= 8:
                        visible.append((node, (left, top, right, bottom)))
                if visible:
                    if len(visible) != 1:
                        raise AssertionError('Ambiguous control inside the observed project capture notification')
                    return visible
                ancestor = parents.get(ancestor)
            return []

        def touch_control(control, label):
            remaining()
            _, (left, top, right, bottom) = control
            self.record('notification_actual_touch', label)
            first.q.adb('shell', 'input', 'tap', (left+right)//2, (top+bottom)//2)

        remaining()
        width, height = self.screen
        self.record('notification_shade_swipe', 'Actual downward swipe from the status bar')
        first.q.adb('shell', 'input', 'swipe', width//2, 4, width//2, int(height*.70), 180)
        self._notification_shade_opened = True
        tree = self.tree('stop-notification-shade')
        remaining()
        stops = own_controls(tree, lambda node: node.get('text') == STOP_LABEL)
        if not stops:
            expands = {'Expand', 'Expand notification', '展开', '展开通知'}
            expansion = own_controls(tree, lambda node: node.get('description') in expands)
            if not expansion:
                raise AssertionError('The project notification exposes neither its Stop action nor one unambiguous Expand control; refusing guessed coordinates')
            touch_control(expansion[0], 'Expand only the project capture notification')
            attempt['notificationExpandedByQa'] = True
            tree = self.tree('stop-notification-expanded')
            remaining()
            stops = own_controls(tree, lambda node: node.get('text') == STOP_LABEL)
            if not stops:
                raise AssertionError('The project notification Stop action remained unavailable after one actual expansion')
        attempt['stopCommandIssuedAt'] = round(time.monotonic(), 3)
        touch_control(stops[0], STOP_LABEL)
        attempt['stopCommandCompletedAt'] = round(time.monotonic(), 3)
        attempt['stopButtonTouched'] = True
        attempt['stopTouchCommandCompletedWithinThreeSeconds'] = attempt['stopCommandCompletedAt']-started < 3
        self.save()
        if not attempt['stopTouchCommandCompletedWithinThreeSeconds']:
            raise AssertionError('The real Stop touch command completed after the three-second deadline; timing is not silently accepted')

    def capture_flow(self):
        self.prepare_capture_drafts()
        self.begin('notification_stop_releases_capture_without_frame')
        self.tap(CAPTURE)
        self.notification_dialog(True)
        self.report['stopCaptureStartButton'] = self.choose_full_screen()
        try:
            self.stop_from_actual_notification()
        finally:
            # A timing failure must also restore the system UI this suite opened.
            # Preserve the primary failure and report cleanup independently.
            had_primary_failure = sys.exc_info()[0] is not None
            try:
                self.close_owned_notification_shade()
            except Exception as error:
                self.report.setdefault('notificationShadeCleanup', {})['failure'] = {
                    'type': type(error).__name__, 'message': str(error)[:2000]}
                self.save()
                if not had_primary_failure:
                    raise
        tree = self.returned(STOPPED)
        self.no_preview(tree)
        self.stopped_state('after-actual-notification-stop')
        self.no_model_calls()
        self.report['notificationStopAttempt']['specificStoppedResultObserved'] = True
        self.report['notificationStopAttempt']['noFramePreview'] = True
        self.passed('notification_stop_releases_capture_without_frame')

        self.begin('fresh_capture_after_stop_returns_and_discards_preview')
        self.approve(NAME)
        self.assert_drafts(unchecked=False)
        self.tap(CAPTURE)
        self.report['retryCaptureStartButton'] = self.choose_full_screen()
        tree = self.returned(CAPTURED)
        preview = [node for node in self.ime_window(tree).iter('node')
                   if node.get('description') == PREVIEW and node.get('class') == 'android.widget.ImageView']
        if len(preview) != 1:
            raise AssertionError('A fresh consent after notification Stop did not return exactly one keyboard preview')
        self.stopped_state('after-fresh-capture-preview')
        self.no_model_calls()
        self.tap('丢弃图片')
        self.no_preview(self.assert_drafts(unchecked=True))
        self.stopped_state('after-fresh-capture-discard')
        self.no_model_calls()
        self.passed('fresh_capture_after_stop_returns_and_discards_preview')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apk', type=Path, default=first.q.ROOT/'output/native/conversation-lens-0.18.0-cloud-debug.apk')
    parser.add_argument('--dump-apk', type=Path, default=first.q.ROOT/'output/native/lens-synthetic-qa.apk')
    parser.add_argument('--stop-only', action='store_true', help='Run the separate actual notification Stop and fresh-capture suite; does not replace the full capture suite')
    args = parser.parse_args()
    # Keep setup/ownership/cleanup inside the same existing harness. No additional
    # harness flags or device controls are introduced by this optional suite.
    sys.argv = [sys.argv[0], '--apk', str(args.apk), '--dump-apk', str(args.dump_apk)]
    first.main(qa_factory=StopCaptureQA if args.stop_only else CaptureQA,
               output_group='keyboard-capture-stop-qa' if args.stop_only else 'keyboard-capture-qa', description=__doc__)


if __name__ == '__main__':
    main()
