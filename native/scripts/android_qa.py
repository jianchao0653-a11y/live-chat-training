"""Synthetic QA on this project's emulator only, never on a personal phone."""
import argparse
import json
import hashlib
from pathlib import Path
import re
import subprocess
import time
import xml.etree.ElementTree as ET
import os

ROOT = Path(__file__).resolve().parents[2]
SDK = Path(os.environ.get('ANDROID_SDK_ROOT',os.environ.get('ANDROID_HOME',str(ROOT / 'runtime/android-tools/sdk'))))
BUILD = ROOT / 'runtime/native-build-ascii'
OUT = ROOT / 'output/native'
ADB = SDK / ('platform-tools/adb.exe' if os.name=='nt' else 'platform-tools/adb')
SERIAL = os.environ.get('LENS_QA_SERIAL','emulator-5556')
if not re.fullmatch(r'emulator-\d+',SERIAL): raise RuntimeError('QA only supports emulators')
APK = OUT / 'conversation-lens-0.18.0-debug.apk'

def adb(*args, binary=False, timeout=45):
    result = subprocess.run([str(ADB), '-s', SERIAL, *map(str,args)], capture_output=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError(result.stderr.decode('utf-8', errors='replace') + result.stdout.decode('utf-8', errors='replace'))
    return result.stdout if binary else result.stdout.decode('utf-8', errors='replace').strip()

def wait_boot():
    for _ in range(60):
        try:
            if adb('shell','getprop','sys.boot_completed',timeout=5) == '1': return
        except (RuntimeError, subprocess.TimeoutExpired): pass
        time.sleep(3)
    raise RuntimeError('Emulator did not finish booting')

def snapshot(name='ui'):
    result = adb('shell','am','instrument','-w','com.conversationlens.ime.qa/.DumpRunner')
    match = re.search(r'INSTRUMENTATION_RESULT: hierarchy=(.*)',result)
    if not match: raise RuntimeError('Window inspector failed: '+result)
    xml = match.group(1)
    (OUT / (name+'.xml')).write_text(xml,encoding='utf-8')
    return ET.fromstring(xml)

def screenshot(name):
    (OUT / (name+'.png')).write_bytes(adb('exec-out','screencap','-p',binary=True))

def node_bounds(node):
    values = list(map(int, re.findall(r'-?\d+', node.get('bounds', ''))))
    if len(values) != 4:
        raise AssertionError('Control has invalid bounds')
    return tuple(values)


def has_area(node):
    left, top, right, bottom = node_bounds(node)
    return right > left and bottom > top and right > 0 and bottom > 0


def tap_text(label, tree=None):
    tree = tree if tree is not None else snapshot()
    matches = [node for node in tree.iter('node') if node.get('text') == label
               and node.get('enabled') == 'true' and has_area(node)]
    if not matches: raise AssertionError('No enabled visible control: '+label)
    tap_node(matches[-1])


def tap_node(node):
    left, top, right, bottom = node_bounds(node)
    if not has_area(node) or left < 0 or top < 0:
        raise AssertionError('Control is outside the visible viewport')
    adb('shell','input','tap',str((left+right)//2),str((top+bottom)//2))


def focus_practice_editor(password, tree=None):
    tree = tree if tree is not None else snapshot()
    expected = str(password).lower()
    def target(current):
        return next(n for n in current.iter('node')
                    if n.get('package') == 'com.conversationlens.ime'
                    and n.get('class') == 'android.widget.EditText'
                    and n.get('password') == expected)
    field = target(tree)
    left, top, right, bottom = node_bounds(field)
    # The inspector reports host bounds behind the overlaid IME. Its transparent
    # top padding also consumes touches, so clip to the actual keyboard window.
    ime_windows = [n for n in tree.findall('node')
                   if any(child.get('description') == '切换输入法'
                          for child in n.iter('node'))]
    if ime_windows:
        bottom = min(bottom, min(node_bounds(n)[1] for n in ime_windows))
    if right <= left or bottom-top < 8:
        raise AssertionError('Practice editor has no safely visible touch area')
    adb('shell','input','tap',str((left+right)//2),str((top+bottom)//2))
    deadline = time.monotonic()+5
    while time.monotonic() < deadline:
        current = snapshot()
        if target(current).get('focused') == 'true':
            return current
        time.sleep(.15)
    raise AssertionError('Practice editor did not gain focus: password='+expected)


def key_nodes(label=None, tree=None, *, description=None, enabled=None):
    tree = tree if tree is not None else snapshot()
    return [n for n in tree.iter('node')
            if n.get('package') == 'com.conversationlens.ime'
            and n.get('class') == 'android.widget.Button'
            and (description is None or n.get('description') == description)
            and (label is None or n.get('text') == label)
            and (enabled is None or n.get('enabled') == str(enabled).lower())
            and has_area(n)]


def tap_key(label=None, tree=None, *, description=None):
    # Key descriptions remain stable when captions wrap or become symbols.
    # Poll only readiness; send exactly one actual touch, never repeat an action.
    deadline = time.monotonic() + 5
    while True:
        current = tree if tree is not None else snapshot()
        matches = key_nodes(label, current, description=description, enabled=True)
        if len(matches) > 1:
            raise AssertionError('Ambiguous keyboard control: '+str(description or label))
        if matches:
            tap_node(matches[0]); return
        if tree is not None or time.monotonic() >= deadline:
            raise AssertionError('No enabled keyboard control: '+str(description or label))
        time.sleep(.15)


def candidate_buttons(tree=None):
    tree = tree if tree is not None else snapshot()
    found = []
    for row in tree.iter('node'):
        if row.get('class') == 'android.widget.HorizontalScrollView':
            found.extend(n for n in row.iter('node')
                         if n.get('package') == 'com.conversationlens.ime'
                         and n.get('class') == 'android.widget.Button'
                         and n.get('enabled') == 'true' and has_area(n))
    return found


def tap_candidate(label, tree=None):
    matches = [n for n in candidate_buttons(tree) if n.get('text') == label]
    if len(matches) != 1:
        raise AssertionError('Expected one visible candidate: '+label)
    tap_node(matches[0])


def wait_keyboard(layout=None, timeout=48):
    # Readiness is usable keys with stable geometry, not a visible status slogan.
    required = {'full':['q','n','切换输入法'], 'nine':['2 ABC','6 MNO','切换输入法']}
    deadline = time.monotonic() + timeout
    previous = None; stable = 0
    while time.monotonic() < deadline:
        tree = snapshot()
        for mode in ([layout] if layout else ['full','nine']):
            groups = [key_nodes(tree=tree, description=d, enabled=True) for d in required[mode]]
            if all(len(group) == 1 for group in groups):
                geometry = (mode, tuple(node_bounds(group[0]) for group in groups))
                stable = stable + 1 if geometry == previous else 0
                previous = geometry
                if stable >= 2: return tree
                break
        else:
            previous = None; stable = 0
        time.sleep(.15)
    raise AssertionError('Usable keyboard keys did not stabilize: '+str(layout))


def ensure_full_keyboard():
    tree = wait_keyboard()
    if not key_nodes(tree=tree, description='q', enabled=True):
        tap_key('全键', tree)
    return wait_keyboard('full')


def smoke():
    remote = '/data/local/tmp/lens-rime-qa'
    adb('shell','mkdir','-p',remote+'/shared',remote+'/user')
    for source in [BUILD/'x86_64/rime_smoke', BUILD/'x86_64/liblens_rime.so',
        SDK/'ndk/28.2.13676358/toolchains/llvm/prebuilt/windows-x86_64/sysroot/usr/lib/x86_64-linux-android/libc++_shared.so']:
        adb('push',source,remote+'/'+source.name)
    for source in (BUILD/'assets/rime').iterdir(): adb('push',source,remote+'/shared/'+source.name)
    adb('shell','chmod','755',remote+'/rime_smoke')
    result = adb('shell',f'LD_LIBRARY_PATH={remote} {remote}/rime_smoke {remote}/shared {remote}/user',timeout=90)
    (OUT/'rime-smoke.txt').write_text(result+'\n',encoding='utf-8')
    print(result,flush=True)
    assert 'RIME_SMOKE_PASS' in result

def install():
    print(adb('install','--no-incremental','-r',APK),flush=True)
    adb('shell','cmd','statusbar','collapse')
    adb('shell','input','keyevent','82')
    adb('shell','am','force-stop','com.conversationlens.ime')
    adb('shell','am','start','-W','-n','com.conversationlens.ime/.SetupActivity')
    for _ in range(60):
        if 'com.conversationlens.ime/.LensImeService' in adb('shell','ime','list','-a','-s'):break
        time.sleep(.5)
    else:raise AssertionError('Installed IME was not registered: '+adb('shell','dumpsys','package','com.conversationlens.ime'))
    adb('shell','ime','enable','com.conversationlens.ime/.LensImeService')
    adb('shell','settings','put','secure','show_ime_with_hard_keyboard','1')
    time.sleep(2)
    # Force-stop can asynchronously select the stock IME on API 34. Select ours
    # after the Activity launch has completed, then verify the actual setting.
    adb('shell','ime','set','com.conversationlens.ime/.LensImeService')
    assert adb('shell','settings','get','secure','default_input_method')=='com.conversationlens.ime/.LensImeService'
    screenshot('android-setup')
    tree = snapshot('android-setup')
    editors = [n for n in tree.iter('node') if n.get('class')=='android.widget.EditText']
    assert editors, 'Practice field must be visible'
    tap_node(editors[0])
    try:
        ensure_full_keyboard()
    except AssertionError:
        log=adb('logcat','-d','-b','crash');(OUT/'install-crash.txt').write_text(log,encoding='utf-8')
        raise
    screenshot('android-keyboard')
    print('IME_READY',flush=True)

def workflow():
    checks = []
    def check(value, name):
        assert value, name
        checks.append(name); print('PASS '+name,flush=True)
    def editors(tree):
        return [n for n in tree.iter('node') if n.get('class')=='android.widget.EditText' and n.get('package')=='com.conversationlens.ime']
    def text_value(tree):
        return next(n.get('text') for n in editors(tree) if n.get('password')=='false')
    def type_word(word):
        for key in word:tap_key(description=key)
        time.sleep(.15)
        return snapshot()
    tree=type_word('nihao')
    check(any(n.get('text')=='你好' and n.get('class')=='android.widget.Button' for n in tree.iter('node')), 'pinyin_candidates')
    tap_key(description='下一页候选',tree=tree);tree=snapshot()
    check(any(n.get('text')=='‹' and n.get('enabled')=='true' for n in tree.iter('node')),'candidate_next_page')
    tap_key(description='上一页候选',tree=tree);tree=snapshot()
    check(any(n.get('text')=='你好' and n.get('class')=='android.widget.Button' for n in tree.iter('node')),'candidate_previous_page')
    screenshot('android-nihao-candidates')
    tap_candidate('你好',tree)
    check(text_value(snapshot())=='你好','candidate_insertion')
    tree=type_word('zhongguo');tap_candidate('中国',tree)
    check(text_value(snapshot())=='你好中国','continuous_chinese_input')
    tap_key(description='退格');check(text_value(snapshot())=='你好中','delete_committed_character')
    tree=type_word('xiexie');tap_candidate('谢谢',tree)
    check(text_value(snapshot())=='你好中谢谢','second_candidate_insertion')
    tap_key('符');tap_key(description='！')
    check(text_value(snapshot())=='你好中谢谢！','symbol_insertion')
    tap_key(description='返回文字键盘');tap_key(description='切换到英文')
    type_word('abc')
    check(text_value(snapshot())=='你好中谢谢！abc','english_input')
    tap_key(description='换行')
    check(text_value(snapshot()).endswith('abc\n'),'multiline_newline')
    tap_key(description='切换到中文');wait_keyboard('full');type_word('ni')
    tree=snapshot()
    focus_practice_editor(True,tree)
    time.sleep(.25)
    tree=snapshot('android-password')
    check(any(n.get('password')=='true' and n.get('focused')=='true' for n in editors(tree)),'password_editor_focused')
    check(not key_nodes('建议',tree) and not candidate_buttons(tree),'password_hides_suggestions_and_candidates')
    check(not any(n.get('text')=='你' and n.get('class')=='android.widget.Button' for n in tree.iter('node')),'old_candidates_cleared_on_editor_switch')
    type_word('abc')
    screenshot('android-password')
    tree=snapshot()
    focus_practice_editor(False,tree);time.sleep(.25)
    tree=wait_keyboard('full')
    check(any(n.get('password')=='false' and n.get('focused')=='true' for n in editors(tree)),'plain_editor_focused')
    check(not candidate_buttons(tree),'fresh_editor_session')
    before_restore=text_value(tree)
    tree=type_word('nihao');tap_candidate('你好',tree)
    after_restore=text_value(snapshot())
    check(any(after_restore==before_restore[:i]+'你好'+before_restore[i:]
              for i in range(len(before_restore)+1)),
          'chinese_restored_after_password')
    # System picker must remain accessible; don't select another keyboard automatically.
    tap_key(description='切换输入法')
    for _ in range(20):
        tree=snapshot('android-picker')
        if any('Android Keyboard' in n.get('text','') for n in tree.iter('node')):break
        time.sleep(.2)
    check(any('Android Keyboard' in n.get('text','') for n in tree.iter('node')),'system_keyboard_picker')
    screenshot('android-picker')
    # Android 16's picker groups IMEs by non-clickable headers; select the subtype row.
    if any(n.get('text')=='English (US)' for n in tree.iter('node')):tap_text('English (US)',tree)
    else:tap_node(next(n for n in tree.iter('node') if 'Android Keyboard' in n.get('text','')))
    selected=''
    for _ in range(60):
        selected=adb('shell','settings','get','secure','default_input_method')
        if selected=='com.android.inputmethod.latin/.LatinIME':break
        time.sleep(.2)
    if selected!='com.android.inputmethod.latin/.LatinIME':snapshot('system-picker-switch-failed');screenshot('system-picker-switch-failed')
    check(selected=='com.android.inputmethod.latin/.LatinIME','switch_back_to_system_keyboard; actual='+selected)
    adb('shell','ime','set','com.conversationlens.ime/.LensImeService');time.sleep(.2)
    tree=snapshot('android-workflow-final');screenshot('android-workflow-final')
    listing=adb('shell','run-as','com.conversationlens.ime','find','files','no_backup','-type','f')
    (OUT/'android-private-file-list.txt').write_text(listing,encoding='utf-8')
    check('.userdb/' not in listing,'no_user_dictionary_learning_files')
    process=adb('shell','pidof','com.conversationlens.ime')
    log=adb('logcat','-d','--pid='+process,'-s','AndroidRuntime:E')
    (OUT/'android-app-crash-log.txt').write_text(log,encoding='utf-8')
    check('FATAL EXCEPTION' not in log,'no_app_crashes')
    receipt={'checks':checks,'os':adb('shell','getprop','ro.build.fingerprint'),'abi':adb('shell','getprop','ro.product.cpu.abi'),
        'apkSha256':hashlib.file_digest(APK.open('rb'),'sha256').hexdigest(),
        'serial':SERIAL,'onlySyntheticData':True,'realPhoneVerified':False,'threeChatPlatformsVerified':False}
    (OUT/'android-qa-receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8')
    print('ANDROID_UI_PASS '+str(len(checks)),flush=True)

def cross_app():
    adb('shell','am','force-stop','com.android.settings.intelligence')
    adb('shell','am','force-stop','com.android.settings')
    adb('shell','am','start','-a','android.settings.SETTINGS');time.sleep(.5)
    for _ in range(20):
        tree=snapshot()
        search=next((n for n in tree.iter('node') if n.get('text','').casefold()=='search settings'),None)
        if search is not None:break
        time.sleep(.2)
    assert search is not None,'Settings search not found'
    tap_node(search)
    for _ in range(20):
        tree=snapshot()
        field=next((n for n in tree.iter('node') if n.get('package')=='com.android.settings.intelligence' and n.get('class')=='android.widget.AutoCompleteTextView'),None)
        if field is not None:break
        time.sleep(.2)
    assert field is not None,'Settings search editor not found'
    tap_node(field)
    ensure_full_keyboard()
    for key in 'nihao':tap_key(description=key)
    tree=snapshot('android-cross-app-candidates');tap_candidate('你好',tree)
    tree=snapshot('android-cross-app-committed');screenshot('android-cross-app-committed')
    assert any(n.get('text')=='你好' and n.get('package')=='com.android.settings.intelligence'
        and n.get('class')=='android.widget.AutoCompleteTextView' for n in tree.iter('node'))
    (OUT/'android-cross-app-receipt.json').write_text(json.dumps({'status':'PASS','host':'com.android.settings.intelligence',
        'input':'nihao','inserted':'你好','synthetic':True,'chatPlatformsVerified':False},ensure_ascii=False,indent=2),encoding='utf-8')
    print('CROSS_APP_INSERT_PASS',flush=True)

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('phase',choices=['smoke','install','snapshot','workflow','cross-app'])
    args = parser.parse_args()
    wait_boot()
    if args.phase == 'smoke': smoke()
    elif args.phase == 'install': install()
    elif args.phase == 'workflow': workflow()
    elif args.phase == 'cross-app': cross_app()
    else:
        tree=snapshot('android-current');screenshot('android-current')
        print(json.dumps([{'text':n.get('text'),'class':n.get('class'),'bounds':n.get('bounds'),'enabled':n.get('enabled')} for n in tree.iter('node') if n.get('text') or n.get('class')=='android.widget.EditText'],ensure_ascii=True,indent=2))
