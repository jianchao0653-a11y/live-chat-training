"""Explicit UI actions against synthetic data on emulator-5556 only."""
import base64
import urllib.request
from android_qa import *

def api(path, method='GET', data=None):
    config=json.loads((OUT/'fixture.json').read_text(encoding='utf-8'))
    req=urllib.request.Request(config['base']+'/api/'+path,method=method,data=json.dumps(data).encode() if data is not None else None,headers={'Content-Type':'application/json','X-CSRF-Token':config['csrf']})
    return json.load(urllib.request.urlopen(req))

def fill(hint,value):
    # Opening an Activity is asynchronous on hosted emulators. Retry only the
    # explicit not-ready result, never retry analysis, OCR or insertion requests.
    deadline=time.monotonic()+12
    while True:
        result=adb('shell','am','instrument','-w','-e','hint',"'"+hint+"'",'-e','value',base64.b64encode(value.encode()).decode(),'com.conversationlens.ime.qa/.DumpRunner')
        if 'INSTRUMENTATION_RESULT: error=' not in result:return
        if 'Synthetic field not found' not in result or time.monotonic()>=deadline:
            snapshot('field-not-ready');raise AssertionError(result)
        time.sleep(.2)

def labels():
    return [n.get('text') for n in snapshot().iter('node') if n.get('package')=='com.conversationlens.ime' and n.get('text')]

def wait_labels(predicate, timeout=15):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        current=labels()
        if predicate(current):return current
        time.sleep(.2)
    raise AssertionError('UI did not reach expected state: '+str(current))

def scroll_find(text):
    for _ in range(8):
        tree=snapshot()
        for node in tree.iter('node'):
            if node.get('text')==text:
                coords=list(map(int,re.findall(r'\d+',node.get('bounds'))))
                if coords[1]>=48 and coords[3]<1184 and coords[3]>coords[1]:return tree
        adb('shell','input','swipe','620','1050','620','400','300')
    raise AssertionError('Control not visible: '+text)

def pair():
    wait_labels(lambda values:'配对连接' in values)
    scroll_find('配对连接')
    config=json.loads((OUT/'fixture.json').read_text(encoding='utf-8'))
    port=config['base'].rsplit(':',1)[1]
    adb('reverse','tcp:4317','tcp:'+port)
    code=api('devices/pairing','POST',{'streamer_id':'0001'})['code']
    fill('电脑设置页的六位配对码',code)
    tap_text('配对连接')
    wait_labels(lambda values:any('已连接 · 主播 0001' in x for x in values))
    print('PASS paired_scoped_roster',flush=True)

def analyze():
    fill('粘贴或输入你批准的聊天片段，标明说话人','对方：今天加班很累，想安静休息。')
    tap_text('已核对人物和片段，同意提交给连接的服务',scroll_find('已核对人物和片段，同意提交给连接的服务'))
    tap_text('分析已批准片段',scroll_find('分析已批准片段'));time.sleep(1)
    scroll_find('保留草稿并返回原聊天')
    fill('选择候选后可修改','合成草稿：你先好好休息。')
    tap_text('保留草稿并返回原聊天',scroll_find('保留草稿并返回原聊天'));time.sleep(1)
    print('PASS analysis_edit_return',flush=True)

def insert():
    tree=snapshot('assistant-return')
    editor=next(n for n in tree.iter('node') if n.get('class') in ['android.widget.EditText','android.widget.AutoCompleteTextView'] and n.get('password')=='false')
    tap_node(editor);time.sleep(.5)
    label='确认正在与「合成测试人物」聊天并插入'
    tap_text(label);time.sleep(.5)
    tree=snapshot('assistant-inserted')
    assert any('合成草稿：你先好好休息。' in n.get('text','') for n in tree.iter('node')),labels()
    assert not any(n.get('text')==label for n in tree.iter('node'))
    screenshot('assistant-inserted')
    print('PASS confirmed_single_use_insert',flush=True)

if __name__=='__main__':
    import sys
    globals()[sys.argv[1]]()
