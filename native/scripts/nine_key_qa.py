"""Synthetic nine-key behavior acceptance on the project emulator only."""
import json
import time
import android_qa as q

checks=[]

def check(value,name):
    if not value: raise AssertionError(name)
    checks.append(name)

def editor_text(tree=None):
    tree=tree if tree is not None else q.snapshot()
    fields=[n for n in tree.iter('node')
            if n.get('package')=='com.conversationlens.ime'
            and n.get('class')=='android.widget.EditText'
            and n.get('hint')=='在这里试打 nihao、zhongguo、xiexie'
            and n.get('password')=='false']
    if len(fields)!=1:raise AssertionError('Synthetic practice editor must be active')
    value=fields[0].get('text','')
    return '' if value==fields[0].get('hint') else value

labels={'1':'分词','2':'2 ABC','3':'3 DEF','4':'4 GHI','5':'5 JKL',
        '6':'6 MNO','7':'7 PQRS','8':'8 TUV','9':'9 WXYZ'}

def type_nine(digits):
    for key in digits:q.tap_key(description=labels[key])
    return q.wait_keyboard('nine')

q.wait_boot()
q.ensure_full_keyboard()
prefix=editor_text()
q.tap_key('九宫')
q.wait_keyboard('nine')
type_nine('64426')
found=False
for page in range(20):
    tree=q.snapshot('nine-candidates')
    if any(n.get('text')=='你好' for n in q.candidate_buttons(tree)):
        q.tap_candidate('你好',tree);found=True;break
    if not q.key_nodes(tree=tree,description='下一页候选',enabled=True):break
    q.tap_key(description='下一页候选',tree=tree)
check(found,'numeric_input_candidate_found')
q.wait_keyboard('nine')
committed=prefix+'你好'
check(editor_text()==committed,'numeric_candidate_inserted')

type_nine('64')
q.tap_key(description='重输当前拼音')
q.wait_keyboard('nine')
tree=q.snapshot('nine-retype')
check(editor_text(tree)==committed and not q.candidate_buttons(tree),
      'retype_clears_only_uncommitted_pinyin')
check(not q.key_nodes(tree=tree,description='重输当前拼音',enabled=True),
      'retype_without_composition_cannot_delete_committed_text')

# The top numeric-pinyin candidate need not be the same word across dictionaries.
# Assert its actual text is committed before each literal, without guessing it.
for literal,name in [('，','punctuation_follows_composition'),('0','zero_follows_composition')]:
    tree=type_nine('64426')
    candidates=q.candidate_buttons(tree)
    check(bool(candidates),'candidate_before_'+name)
    expected=candidates[0].get('text','')
    q.tap_key(description=literal,tree=tree)
    q.wait_keyboard('nine')
    committed+=expected+literal
    check(editor_text()==committed and not q.candidate_buttons(),name)

# SetupActivity is a synthetic, non-FLAG_SECURE host. Keep protected helper
# windows protected; screenshot only after confirming the practice editor.
editor_text()
q.screenshot('nine-keyboard')
q.adb('shell','am','force-stop','com.conversationlens.ime')
q.adb('shell','am','start','-W','-n','com.conversationlens.ime/.SetupActivity')
time.sleep(2)
q.adb('shell','ime','set','com.conversationlens.ime/.LensImeService')
tree=q.snapshot()
q.tap_node(next(n for n in tree.iter('node')
                if n.get('class')=='android.widget.EditText'
                and n.get('hint')=='在这里试打 nihao、zhongguo、xiexie'))
tree=q.wait_keyboard('nine')
check(bool(q.key_nodes(tree=tree,description='2 ABC',enabled=True)),
      'layout_survives_process_restart')
q.tap_key('全键',tree)
tree=q.wait_keyboard('full')
check(bool(q.key_nodes(tree=tree,description='q',enabled=True)),'full_keyboard_toggle')
(q.OUT/'nine-key-receipt.json').write_text(json.dumps({
    'status':'PASS','checks':checks,'synthetic':True,'realPhone':False,
    'touchInput':True,'apkSha256':q.hashlib.file_digest(q.APK.open('rb'),'sha256').hexdigest()
},ensure_ascii=False,indent=2),encoding='utf-8')
print('NINE_UI_PASS '+str(len(checks)))
