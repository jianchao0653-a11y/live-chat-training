"""Synthetic system-document-picker/OCR acceptance for the keyboard image bridge.

No emulator is started by this script. Run it only after other project QA has
released reverse port 4317:
    python native/scripts/keyboard_image_qa.py
The owned fixture, login, customer setup and touch helpers are reused from
keyboard_first_qa.py. Only emulator-5556/LensPreview is accepted; the synthetic
project app is reset. No user images, screenshots, real providers or existing
server processes are used. --prepare-only generates the original test PNG and
manifest without contacting any device or starting a fixture.
"""
import argparse
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
import keyboard_first_qa as first

PACKAGE = first.PACKAGE
DOC_PACKAGES = {'com.android.documentsui', 'com.google.android.documentsui'}
NAME = 'qapicture'
INTENT = '本次画像关注点（选填，最多1000字）'
PREVIEW = '待校对图片，仅保存在本机内存'
CHECKS = ['owned_customer_and_local_drafts', 'system_picker_cancel_restores_unapproved_drafts',
          'system_selected_synthetic_image_preview', 'original_owner_drafts_and_unchecked_approval',
          'local_profile_ocr_requires_review', 'host_unchanged_and_no_model_calls']
PROFILE_LINES = ['合成客户资料', '昵称：qapicture', '兴趣：散步和阅读', '最近想养一盆绿植', '这张图片只用于测试']
OCR_MARKERS = ['散步', '阅读', '绿植']


def generate_profile(folder):
    from PIL import Image, ImageDraw, ImageFont
    fonts = [Path('C:/Windows/Fonts/msyh.ttc'),
             Path('/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc'),
             Path('/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc')]
    font_file = next((path for path in fonts if path.is_file()), None)
    if font_file is None:
        raise RuntimeError('A local Chinese font is required to generate the synthetic QA image')
    font = ImageFont.truetype(str(font_file), 44)
    image = Image.new('RGB', (1000, 700), '#ffffff')
    draw = ImageDraw.Draw(image)
    for index, line in enumerate(PROFILE_LINES):
        draw.text((60, 60+index*115), line, font=font, fill='#151515')
    filename = 'lens-keyboard-profile-'+uuid4().hex[:12]+'.png'
    source = folder/filename
    image.save(source)
    image.close()
    manifest = {'synthetic': True, 'originallyGenerated': True, 'userImageRead': False,
                'file': filename, 'width': 1000, 'height': 700, 'expectedLines': PROFILE_LINES,
                'requiredOcrMarkers': OCR_MARKERS,
                'sha256': hashlib.file_digest(source.open('rb'), 'sha256').hexdigest()}
    (folder/'synthetic-image.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    return source, manifest


class ImageQA(first.QA):
    def __init__(self, folder):
        super().__init__(folder)
        self.report['checks'] = {name: 'NOT_RUN' for name in CHECKS}
        self.report.update({'scope': 'real system picker and local profile OCR on an owned synthetic AVD',
                            'protectedScreensCaptured': False, 'flagSecureAltered': False,
                            'imageUploaded': False, 'ocrQualityAccepted': False,
                            'notCovered': ['slow document provider', 'rotation during picking',
                                           'different chat in the same app', 'OEM or physical phone']})

    def picker_tree(self, seconds=15):
        return self.wait(lambda tree: any(node.get('package') in DOC_PACKAGES for node in tree.iter('node')),
                         'The real system DocumentsUI picker did not appear', seconds)

    def system_nodes(self, tree, predicate):
        matches = []
        for node in tree.iter('node'):
            if node.get('package') not in DOC_PACKAGES or node.get('enabled') != 'true' or not predicate(node):
                continue
            left, top, right, bottom = self.clipped(node, tree)
            if right-left >= 8 and bottom-top >= 8:
                matches.append((node, (left, top, right, bottom)))
        return matches

    def tap_system(self, predicate, label, seconds=10, lower=False):
        deadline = time.monotonic()+seconds
        while time.monotonic() < deadline:
            tree = self.tree('system-picker')
            matches = self.system_nodes(tree, predicate)
            if matches:
                # Drawer roots are below the toolbar title, which can share a label.
                matches.sort(key=lambda pair: pair[1][1], reverse=lower)
                node, (left, top, right, bottom) = matches[0]
                self.record('system_picker_tap', label)
                q.adb('shell', 'input', 'tap', (left+right)//2, (top+bottom)//2)
                time.sleep(.2)
                return node
            time.sleep(.15)
        raise AssertionError('System picker control was not visible: '+label)

    def open_picker(self):
        self.tap('选择一张图片')
        tree = self.picker_tree()
        packages = sorted({node.get('package') for node in tree.iter('node') if node.get('package') in DOC_PACKAGES})
        activities = q.adb('shell', 'dumpsys', 'activity', 'activities')
        if 'act=android.intent.action.OPEN_DOCUMENT' not in activities:
            raise AssertionError('The live picker task does not show ACTION_OPEN_DOCUMENT')
        self.report.setdefault('pickerVisits', []).append({'packages': packages, 'action': 'android.intent.action.OPEN_DOCUMENT'})
        self.save()

    def cancel_picker(self):
        # DocumentsUI consumes Back to close drawers/search/selection or pop a
        # directory before Back can cancel the Activity. Inspect every transition
        # and never send Back after the real picker has left the screen.
        def shape(tree):
            return tuple((node.get('class'), node.get('text'), node.get('description'), node.get('bounds'))
                         for node in tree.iter('node') if node.get('package') in DOC_PACKAGES)
        tree = self.tree('system-picker-before-cancel')
        for count in range(6):
            previous = shape(tree)
            if not previous:
                self.report['pickerCancelBackPresses'] = count
                self.save()
                return
            self.record('system_picker_back', 'KEYCODE_BACK: navigate or cancel')
            q.adb('shell', 'input', 'keyevent', '4')
            tree = self.wait(lambda current: shape(current) != previous,
                             'DocumentsUI did not change after the bounded Back action', 6)
            self.tree('system-picker-cancel-step-'+str(count+1))
        if shape(tree):
            raise AssertionError('System picker did not cancel within six observed Back transitions')
        self.report['pickerCancelBackPresses'] = 6
        self.save()

    def await_restored(self):
        # The bridge returns to the original practice host. Never navigate to
        # another Activity or fake a result to make restoration pass.
        self.wait_label('当前客户：'+NAME+' · 微信', 45)
        tree = self.tree('restored-owner')
        if self.field_text(INTENT, tree) != 'hello' or self.field_text(first.MATERIAL, tree) != 'before':
            raise AssertionError('Picker handoff did not preserve the exact unsent local drafts')
        for label in ['已核对当前聊天对象是「'+NAME+'」', first.APPROVAL]:
            found = [node for node in self.ime_window(tree).iter('node') if node.get('text') == label]
            if len(found) != 1 or found[0].get('checked') != 'false':
                raise AssertionError('Returned image content must require renewed customer/content approval')
        if any(node.get('hint') == first.DRAFT or '并插入' in node.get('text', '') for node in self.ime_window(tree).iter('node')):
            raise AssertionError('An old insertion draft survived the picker handoff')
        self.unchanged_host()
        return tree

    def choose_generated_file(self, filename):
        if not re.fullmatch(r'lens-keyboard-profile-[a-f0-9]{12}\.png', filename):
            raise AssertionError('Only this run\'s generated synthetic filename can be selected')
        def own_file(node):
            return node.get('text') == filename or node.get('description', '').startswith(filename+',')
        tree = self.tree('picker-select-open')
        if not self.system_nodes(tree, own_file):
            roots = {'Show roots', '显示根目录', '显示根位置', 'Open navigation drawer', '打开导航抽屉'}
            self.tap_system(lambda node: node.get('description') in roots, 'open document roots')
            self.tap_system(lambda node: node.get('text') in {'Downloads', '下载'}, 'Downloads root', lower=True)
            deadline = time.monotonic()+4
            while time.monotonic() < deadline:
                tree = self.tree('picker-downloads')
                if self.system_nodes(tree, own_file):
                    break
                time.sleep(.2)
            else:
                # ADB-created files can be absent from the Downloads provider's
                # index. Browse the real external-storage provider instead.
                self.tap_system(lambda node: node.get('description') in roots, 'open external-storage roots')
                model = q.adb('shell', 'getprop', 'ro.product.model')
                storage_labels = {model, 'Android SDK built for x86_64', 'Internal storage', '内部存储'}
                self.tap_system(lambda node: node.get('text') in storage_labels, 'owned AVD internal storage', lower=True)
                self.tap_system(lambda node: node.get('text') in {'Download', 'Downloads', '下载'}, 'Download directory', lower=True)
        self.tap_system(own_file, filename)
        self.report['selectedFile'] = filename
        # A picker variant may require its final Open action after selecting a row.
        time.sleep(.4)
        tree = self.tree('picker-file-tapped')
        if any(node.get('package') in DOC_PACKAGES for node in tree.iter('node')):
            buttons = self.system_nodes(tree, lambda node: node.get('text') in {'Open', 'OPEN', '打开'} and node.get('class', '').endswith('Button'))
            if buttons:
                self.tap_system(lambda node: node.get('text') in {'Open', 'OPEN', '打开'} and node.get('class', '').endswith('Button'), 'Open selected synthetic file')

    def no_provider_calls(self):
        receipt = json.loads((self.folder/'fixture-receipt.json').read_text(encoding='utf-8'))
        if receipt.get('realProviderCalls') != 0 or receipt.get('calls') != []:
            raise AssertionError('Picker, preview or local OCR unexpectedly called a model provider')
        self.report['mockProviderCalls'] = 0
        self.report['realProviderCalls'] = 0

    def main_flow(self, source):
        self.begin('owned_customer_and_local_drafts')
        self.tap('新用户破冰', kind='description')
        self.wait_label('新增客户')
        self.new_customer(NAME)
        self.select_customer(NAME)
        self.focus(INTENT)
        self.ascii('hello')
        self.focus(first.MATERIAL)
        self.ascii('before')
        self.wait(lambda tree: self.field_text(first.MATERIAL, tree) == 'before', 'Local source draft was not typed')
        self.approve(NAME)
        self.unchanged_host()
        self.passed('owned_customer_and_local_drafts')

        self.begin('system_picker_cancel_restores_unapproved_drafts')
        self.open_picker()
        self.cancel_picker()
        tree = self.await_restored()
        if any(node.get('description') == PREVIEW for node in self.ime_window(tree).iter('node')):
            raise AssertionError('Cancelled picker unexpectedly supplied image pixels')
        self.no_provider_calls()
        self.passed('system_picker_cancel_restores_unapproved_drafts')

        self.begin('system_selected_synthetic_image_preview')
        self.approve(NAME)
        self.open_picker()
        self.choose_generated_file(source.name)
        tree = self.await_restored()
        if not any(node.get('description') == PREVIEW and node.get('class') == 'android.widget.ImageView' for node in self.ime_window(tree).iter('node')):
            raise AssertionError('Selected image preview is not hosted inside the keyboard window')
        self.reach(PREVIEW, kind='description', enabled=False)
        self.no_provider_calls()
        self.passed('system_selected_synthetic_image_preview')
        self.begin('original_owner_drafts_and_unchecked_approval')
        self.await_restored()
        self.passed('original_owner_drafts_and_unchecked_approval')

        self.begin('local_profile_ocr_requires_review')
        self.tap('在本机识别文字')
        self.wait(lambda tree: all(marker in self.field_text(first.MATERIAL, tree) for marker in OCR_MARKERS),
                  'Local profile OCR did not return the known synthetic profile words', 45)
        tree = self.tree('profile-ocr-awaiting-review')
        recognized = self.field_text(first.MATERIAL, tree)
        if not recognized.startswith('before\n\n'):
            raise AssertionError('OCR replaced the unsent source draft instead of appending reviewable text')
        if any(prefix in recognized for prefix in ['非聊天：', '对方：', '我：']):
            raise AssertionError('Profile-image OCR incorrectly assigned chat bubble speakers')
        for label in [first.APPROVAL, '已核对当前聊天对象是「'+NAME+'」']:
            if any(node.get('text') == label and node.get('checked') == 'true' for node in self.ime_window(tree).iter('node')):
                raise AssertionError('OCR content was approved without a new user action')
        self.report['recognizedSyntheticText'] = recognized
        self.report['ocrMarkersMatched'] = OCR_MARKERS
        self.passed('local_profile_ocr_requires_review')
        self.begin('host_unchanged_and_no_model_calls')
        self.unchanged_host()
        self.no_provider_calls()
        self.passed('host_unchanged_and_no_model_calls')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apk', type=Path, default=q.ROOT/'output/native/conversation-lens-0.18.0-cloud-debug.apk')
    parser.add_argument('--dump-apk', type=Path, default=q.ROOT/'output/native/lens-synthetic-qa.apk')
    parser.add_argument('--prepare-only', action='store_true')
    args = parser.parse_args()
    if not args.prepare_only:
        avd = first.verify_target()
        for apk in (args.apk, args.dump_apk):
            if not apk.is_file():
                raise RuntimeError('Required built test APK does not exist: '+str(apk))
        with zipfile.ZipFile(args.apk) as archive:
            if json.loads(archive.read('assets/cloud-config.json')).get('endpoint') != 'http://127.0.0.1:4317':
                raise RuntimeError('Only the explicit synthetic loopback APK is accepted')
        if any('tcp:4317' in line.split() for line in q.adb('reverse', '--list').splitlines()):
            raise RuntimeError('Another QA owns reverse port 4317; finish it before running image QA')
    folder = q.ROOT/'output/keyboard-image-qa'/(time.strftime('%Y%m%d-%H%M%S')+'-'+uuid4().hex[:8])
    folder.mkdir(parents=True)
    source, manifest = generate_profile(folder)
    if args.prepare_only:
        print(str(folder/'synthetic-image.json'), flush=True)
        return
    q.OUT = folder
    qa = ImageQA(folder)
    qa.screen = tuple(map(int, re.findall(r'(\d+)x(\d+)', q.adb('shell', 'wm', 'size'))[-1]))
    qa.report.update({'serial': q.SERIAL, 'avd': avd, 'api': q.adb('shell', 'getprop', 'ro.build.version.sdk'),
                      'apkSha256': hashlib.file_digest(args.apk.open('rb'), 'sha256').hexdigest(), 'sourceImage': manifest})
    qa.save()
    original = {key: q.adb('shell', 'settings', 'get', 'secure', key) for key in ['default_input_method', 'enabled_input_methods', 'show_ime_with_hard_keyboard']}
    service = None
    reversed_port = mutated = pushed = False
    remote = '/sdcard/Download/'+source.name
    try:
        with (folder/'fixture.log').open('w', encoding='utf-8') as log:
            service = subprocess.Popen(['node', '--disable-warning=ExperimentalWarning', str(q.ROOT/'native/scripts/keyboard_first_fixture.mjs'), '--out', str(folder)],
                                       cwd=q.ROOT, stdin=subprocess.PIPE, stdout=log, stderr=subprocess.STDOUT, text=True, encoding='utf-8',
                                       creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            deadline = time.monotonic()+15
            while not (folder/'fixture.json').exists():
                if service.poll() is not None or time.monotonic() >= deadline:
                    raise RuntimeError('Owned synthetic fixture failed to become ready; inspect fixture.log')
                time.sleep(.1)
            fixture = json.loads((folder/'fixture.json').read_text(encoding='utf-8'))
            if fixture.get('synthetic') is not True or fixture.get('pid') != service.pid or not re.fullmatch(r'http://127\.0\.0\.1:\d+', fixture.get('base', '')):
                raise RuntimeError('Synthetic fixture ownership proof failed')
            first.verify_target()
            q.adb('reverse', 'tcp:4317', 'tcp:'+fixture['base'].rsplit(':', 1)[1])
            reversed_port = True
            first.verify_target()
            mutated = True
            if q.adb('shell', 'pm', 'path', PACKAGE).strip() and 'Success' not in q.adb('uninstall', PACKAGE):
                raise RuntimeError('Old synthetic project APK could not be removed')
            for apk in (args.apk, args.dump_apk):
                if 'Success' not in q.adb('install', '--no-incremental', '-r', '-t', apk, timeout=180):
                    raise RuntimeError('Synthetic APK installation failed')
            package = q.adb('shell', 'dumpsys', 'package', PACKAGE)
            version = re.search(r'versionName=([^\s]+)', package)
            if version is None or version.group(1) not in ('0.18.0', '0.18.0-preview') or not re.search(r'versionCode=23(?:\s|$)', package):
                raise RuntimeError('Installed APK must be exactly 0.18.0/code23')
            qa.report.update({'installedVersionName': version.group(1), 'installedVersionCode': 23})
            if 'Success' not in q.adb('shell', 'pm', 'clear', PACKAGE):
                raise RuntimeError('Synthetic app reset failed')
            # Only our original PNG, with a unique ASCII basename, enters the AVD.
            q.adb('push', source, remote)
            pushed = True
            first.setup_login(qa, fixture)
            qa.main_flow(source)
            if any(value != 'PASS' for value in qa.report['checks'].values()):
                raise AssertionError('Image acceptance contains unexecuted checks')
            qa.report['status'] = 'PASS'
    except Exception as error:
        qa.report['status'] = 'FAIL'
        if qa.report.get('activeCheck'):
            qa.report['checks'][qa.report['activeCheck']] = 'FAIL'
        qa.report['failure'] = {'type': type(error).__name__, 'message': str(error)[:2000]}
        raise
    finally:
        cleanup = []
        try:
            if mutated:
                first.verify_target()
                q.adb('shell', 'am', 'force-stop', PACKAGE)
                for key, value in original.items():
                    q.adb('shell', 'settings', 'delete', 'secure', key) if value == 'null' else q.adb('shell', 'settings', 'put', 'secure', key, value)
            if pushed:
                first.verify_target()
                if not re.fullmatch(r'/sdcard/Download/lens-keyboard-profile-[a-f0-9]{12}\.png', remote):
                    raise RuntimeError('Unexpected generated image cleanup target')
                q.adb('shell', 'rm', '-f', remote)
        except Exception as error:
            cleanup.append({'target': 'synthetic app/settings/image', 'errorType': type(error).__name__})
        try:
            if reversed_port:
                first.verify_target()
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
            metadata = folder/'fixture.json'
            if metadata.exists():
                metadata.unlink()
            qa.report['cleanupErrors'] = cleanup
            if cleanup:
                qa.report['status'] = 'FAIL'
            qa.save()
            print(str(folder/'report.json'), flush=True)
        if cleanup:
            raise RuntimeError('Synthetic image QA cleanup incomplete; see receipt')


if __name__ == '__main__':
    main()
