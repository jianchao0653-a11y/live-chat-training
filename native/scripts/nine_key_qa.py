"""Synthetic nine-key UI acceptance on the project emulator only."""
import json
import time
import android_qa as q

checks=[]
def check(value,name):
    if not value: raise AssertionError(name)
    checks.append(name)

q.wait_boot()
tree=q.snapshot('nine-before')
q.tap_text('九宫',tree)
labels={'2':'2 ABC','3':'3 DEF','4':'4 GHI','5':'5 JKL','6':'6 MNO','7':'7 PQRS','8':'8 TUV','9':'9 WXYZ'}
for key in '64426': q.tap_text(labels[key])
found=False
for page in range(20):
    tree=q.snapshot('nine-candidates')
    if any(n.get('text')=='你好' and n.get('class')=='android.widget.Button' for n in tree.iter('node')):
        q.tap_text('你好',tree);found=True;break
    if not any(n.get('text')=='›' and n.get('enabled')=='true' for n in tree.iter('node')):break
    q.tap_text('›',tree)
check(found,'numeric_input_candidate_found')
tree=q.snapshot('nine-committed')
check(any(n.get('text')=='你好' and n.get('class')=='android.widget.EditText' for n in tree.iter('node')),'numeric_candidate_inserted')
q.screenshot('nine-keyboard')
q.adb('shell','am','force-stop','com.conversationlens.ime')
q.adb('shell','am','start','-W','-n','com.conversationlens.ime/.SetupActivity')
time.sleep(2)
q.adb('shell','ime','set','com.conversationlens.ime/.LensImeService')
tree=q.snapshot()
q.tap_node(next(n for n in tree.iter('node') if n.get('class')=='android.widget.EditText' and n.get('password')=='false'))
time.sleep(3)
tree=q.snapshot('nine-preference')
check(any(n.get('text')=='2 ABC' for n in tree.iter('node')),'layout_survives_process_restart')
q.tap_text('全键',tree)
tree=q.snapshot('nine-return-full')
check(any(n.get('text')=='q' for n in tree.iter('node')),'full_keyboard_toggle')
(q.OUT/'nine-key-receipt.json').write_text(json.dumps({'status':'PASS','checks':checks,'synthetic':True},indent=2),encoding='utf-8')
print('NINE_UI_PASS '+str(len(checks)))
