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
    adb('install','--no-incremental','-r',OUT/'conversation-lens-0.17.1-cloud-debug.apk')
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
    click('我的主播档案');wait_labels(lambda x:'保存主播档案' in x or '主播称呼' in x)
    fill('主播称呼','合成主播甲');fill('表达风格','简短自然，不催促')
    click('保存主播档案');tap_text('确认');wait_labels(lambda x:'新建人物' in x)
    click('新建人物');fill('昵称','合成测试人物');fill('关系背景（选填）','我们都喜欢散步')
    click('保存人物');wait_labels(lambda x:'添加记忆或标记' in x)
    click('添加记忆或标记');fill('内容','周末喜欢散步');fill('来源，例如：哪次聊天中的原话','合成用户确认')
    click('保存记忆或标记');wait_labels(lambda x:any('周末喜欢散步' in v for v in x))
    print('PASS cloud_login_create_person_memory',flush=True)
    click('返回人物列表');click('返回')
    tree=snapshot();editors=[n for n in tree.iter('node') if n.get('class')=='android.widget.EditText'];tap_node(editors[0])
    wait_labels(lambda x:'建议' in x,30);tap_text('建议')
    wait_labels(lambda x:any('主播：合成主播甲' in v for v in x))
    assert not any('电脑' in v or '配对连接' in v for v in labels())
    fill('粘贴或输入你批准的聊天片段，标明说话人','对方：今天加班很累，想安静休息。')
    click('已核对人物和片段，同意提交给连接的服务');click('分析已批准片段')
    click('查看策略、风险与原话依据');wait_labels(lambda x:'本次建议的依据' in x)
    assert any('风险：' in v and '原话依据：' in v and '今天加班很累' in v for v in labels())
    click('关闭');fill('选择候选后可修改','合成草稿：你先好好休息。')
    click('保留草稿并返回原聊天');time.sleep(1);insert()
    tap_text('建议');wait_labels(lambda x:'记录实际反馈' in x)
    assert any('合成草稿：你先好好休息。'==v for v in labels())
    click('记录实际反馈');wait_labels(lambda x:'实际反馈已记录' in x)
    import sqlite3
    with sqlite3.connect(fixture['syntheticDatabase']) as database:
        assert database.execute('SELECT draft FROM outcomes').fetchone()[0]=='合成草稿：你先好好休息。'
    print('PASS strategy_risk_evidence_and_edited_draft_feedback',flush=True)
    print('PASS cloud_analysis_edit_confirmed_insertion',flush=True)
    # Reopening App still has its saved session; no activation prompt.
    adb('shell','am','force-stop','com.conversationlens.ime');adb('shell','am','start','-W','-n','com.conversationlens.ime/.SetupActivity')
    click('登录与人物资料');wait_labels(lambda x:'合成测试人物 · 微信' in x)
    click('合成测试人物 · 微信');wait_labels(lambda x:'添加记忆或标记' in x)
    click('修改或删除');fill('内容','修正：周日喜欢散步');click('保存记忆或标记');tap_text('确认')
    wait_labels(lambda x:any('修正：周日喜欢散步' in v for v in x))
    click('删除人物及关联资料');tap_text('确认');wait_labels(lambda x:any('还没有人物' in v for v in x))
    print('PASS cloud_restart_edit_delete',flush=True)
    (OUT/'cloud-ui-receipt.json').write_text(json.dumps({'synthetic':True,'passed':['login','streamer-profile-save','streamer-profile-applied','person-create','memory-create','analyze','strategy-risk-evidence','edit','confirm-insert','edited-draft-feedback-persisted','restart-login','memory-edit','person-delete'],'realPhone':False,'realModel':False},indent=2),encoding='utf-8')

if __name__=='__main__':run()
