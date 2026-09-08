"""Cloud UI acceptance with synthetic fixture on the project emulator only."""
from assistant_qa import *

def click(label):
    # Native controls near the last row can extend below the old 1184px test
    # cutoff on API34 even when their center is reachable above navigation.
    # Test the actual button action and its result, not a fixed pixel bottom.
    size=re.findall(r'(\d+)x(\d+)',adb('shell','wm','size'))[-1]
    height=int(size[1]);last=[]
    for _ in range(12):
        tree=snapshot();last=[n.attrib for n in tree.iter('node') if n.get('package')=='com.conversationlens.ime' and n.get('text')]
        for n in tree.iter('node'):
            if n.get('text')==label and n.get('enabled')=='true':
                left,top,right,bottom=map(int,re.findall(r'-?\d+',n.get('bounds')))
                if right>left and bottom>top and 48<(top+bottom)//2<height-80:
                    tap_node(n);return
        adb('shell','input','swipe','620',str(height-220),'620','400','300')
        time.sleep(.2)
    raise AssertionError('Cloud control not reachable: '+label+'; state='+json.dumps(last,ensure_ascii=False))

def run():
    fixture=json.loads((OUT/'cloud-fixture.json').read_text(encoding='utf-8'))
    adb('reverse','tcp:4317','tcp:'+fixture['base'].rsplit(':',1)[1])
    adb('install','--no-incremental','-r',OUT/'conversation-lens-0.16.0-cloud-debug.apk')
    # This helper is constrained to the synthetic emulator; start a fresh test account.
    adb('shell','pm','clear','com.conversationlens.ime')
    adb('shell','am','force-stop','com.conversationlens.ime')
    adb('shell','am','start','-W','-n','com.conversationlens.ime/.SetupActivity')
    adb('shell','ime','enable','com.conversationlens.ime/.LensImeService')
    adb('shell','ime','set','com.conversationlens.ime/.LensImeService')
    click('登录与人物资料')
    wait_labels(lambda x:'登录并开始' in x)
    fill('一次性邀请码',fixture['invite'])
    click('我已了解并同意上述数据处理方式')
    click('登录并开始')
    wait_labels(lambda x:'新建人物' in x)
    assert '服务地址' not in labels()
    click('新建人物');fill('昵称','合成测试人物');fill('关系背景（选填）','我们都喜欢散步')
    click('保存人物');wait_labels(lambda x:'添加确认记忆' in x)
    click('添加确认记忆');fill('记忆内容','周末喜欢散步');fill('来源，例如：本人明确说过','合成用户确认')
    click('保存记忆');wait_labels(lambda x:any('周末喜欢散步' in v for v in x))
    print('PASS cloud_login_create_person_memory',flush=True)
    click('返回人物列表');click('返回')
    tree=snapshot();editors=[n for n in tree.iter('node') if n.get('class')=='android.widget.EditText'];tap_node(editors[0])
    wait_labels(lambda x:'建议' in x,30);tap_text('建议')
    wait_labels(lambda x:any('已登录' in v for v in x))
    assert not any('电脑' in v or '配对连接' in v for v in labels())
    analyze();insert()
    print('PASS cloud_analysis_edit_confirmed_insertion',flush=True)
    # Reopening App still has its saved session; no activation prompt.
    adb('shell','am','force-stop','com.conversationlens.ime');adb('shell','am','start','-W','-n','com.conversationlens.ime/.SetupActivity')
    click('登录与人物资料');wait_labels(lambda x:'合成测试人物 · 微信' in x)
    click('合成测试人物 · 微信');wait_labels(lambda x:'添加确认记忆' in x)
    click('修改或删除这条记忆');fill('记忆内容','修正：周日喜欢散步');click('保存记忆');tap_text('确认')
    wait_labels(lambda x:any('修正：周日喜欢散步' in v for v in x))
    click('删除人物及关联资料');tap_text('确认');wait_labels(lambda x:any('还没有人物' in v for v in x))
    print('PASS cloud_restart_edit_delete',flush=True)
    (OUT/'cloud-ui-receipt.json').write_text(json.dumps({'synthetic':True,'passed':['login','person-create','memory-create','analyze','edit','confirm-insert','restart-login','memory-edit','person-delete'],'realPhone':False,'realModel':False},indent=2),encoding='utf-8')

if __name__=='__main__':run()
