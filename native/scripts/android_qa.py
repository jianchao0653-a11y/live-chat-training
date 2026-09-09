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
APK = OUT / 'conversation-lens-0.17.1-debug.apk'

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

def tap_text(label, tree=None):
    tree = tree if tree is not None else snapshot()
    matches = [node for node in tree.iter('node') if node.get('text') == label and node.get('enabled') == 'true']
    if not matches: raise AssertionError('No enabled control: '+label)
    tap_node(matches[-1])

def tap_node(node):
    left,top,right,bottom = map(int,re.findall(r'\d+',node.get('bounds')))
    adb('shell','input','tap',str((left+right)//2),str((top+bottom)//2))

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
    for _ in range(24):
        time.sleep(2)
        tree = snapshot('android-keyboard')
        if any('简体拼音 · 离线' in n.get('text','') for n in tree.iter('node')): break
    else:
        log=adb('logcat','-d','-b','crash');(OUT/'install-crash.txt').write_text(log,encoding='utf-8')
        raise AssertionError('Chinese engine not ready; selected='+adb('shell','settings','get','secure','default_input_method')+'; '+log[-5000:])
    screenshot('android-keyboard')
    # A newly shown IME can receive navigation-bar insets after reporting ready.
    # Wait for stable key geometry before coordinate-based UI interactions.
    geometry=None;stable=0
    for _ in range(20):
        current=tuple((n.get('text'),n.get('bounds')) for n in snapshot().iter('node') if n.get('text') in ['q','n','切换'] and n.get('class')=='android.widget.Button')
        stable=stable+1 if current==geometry and len(current)==3 else 0
        if stable>=2:break
        geometry=current;time.sleep(.2)
    else:raise AssertionError('IME geometry did not stabilize')
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
        for key in word:tap_text(key)
        time.sleep(.15)
        return snapshot()
    tree=type_word('nihao')
    check(any(n.get('text')=='你好' and n.get('class')=='android.widget.Button' for n in tree.iter('node')), 'pinyin_candidates')
    tap_text('›',tree);tree=snapshot()
    check(any(n.get('text')=='‹' and n.get('enabled')=='true' for n in tree.iter('node')),'candidate_next_page')
    tap_text('‹',tree);tree=snapshot()
    check(any(n.get('text')=='你好' and n.get('class')=='android.widget.Button' for n in tree.iter('node')),'candidate_previous_page')
    screenshot('android-nihao-candidates')
    tap_text('你好',tree)
    check(text_value(snapshot())=='你好','candidate_insertion')
    tree=type_word('zhongguo');tap_text('中国',tree)
    check(text_value(snapshot())=='你好中国','continuous_chinese_input')
    tap_text('⌫');check(text_value(snapshot())=='你好中','delete_committed_character')
    tree=type_word('xiexie');tap_text('谢谢',tree)
    check(text_value(snapshot())=='你好中谢谢','second_candidate_insertion')
    tap_text('123');tap_text('！')
    check(text_value(snapshot())=='你好中谢谢！','symbol_insertion')
    tap_text('ABC');tap_text('中')
    type_word('abc')
    check(text_value(snapshot())=='你好中谢谢！abc','english_input')
    tap_text('换行')
    check(text_value(snapshot()).endswith('abc\n'),'multiline_newline')
    tap_text('英');type_word('ni')
    tree=snapshot()
    password=next(n for n in editors(tree) if n.get('password')=='true')
    tap_node(password)
    time.sleep(.25)
    tree=snapshot('android-password')
    check(any('私密输入' in n.get('text','') for n in tree.iter('node')),'password_bypasses_chinese')
    check(not any(n.get('text')=='你' and n.get('class')=='android.widget.Button' for n in tree.iter('node')),'old_candidates_cleared_on_editor_switch')
    type_word('abc')
    screenshot('android-password')
    tree=snapshot()
    plain=next(n for n in editors(tree) if n.get('password')=='false')
    tap_node(plain);time.sleep(.25)
    tree=snapshot()
    check(any('简体拼音 · 离线' in n.get('text','') for n in tree.iter('node')),'chinese_restored_after_password')
    check(not any(n.get('text')=='你' and n.get('class')=='android.widget.Button' for n in tree.iter('node')),'fresh_editor_session')
    # System picker must remain accessible; don't select another keyboard automatically.
    tap_text('切换')
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
    for _ in range(30):
        tree=snapshot()
        if any(n.get('text')=='q' and n.get('class')=='android.widget.Button' and n.get('enabled')=='true' for n in tree.iter('node')):break
        time.sleep(.2)
    else:raise AssertionError('Settings editor did not show keyboard')
    for key in 'nihao':tap_text(key)
    tree=snapshot('android-cross-app-candidates');tap_text('你好',tree)
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
