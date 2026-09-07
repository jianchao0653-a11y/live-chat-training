"""Additional isolated emulator checks; restores display settings and owns its test server."""
import subprocess
from assistant_qa import *

def main():
    log=(OUT/'stability-service.log').open('w')
    process=subprocess.Popen(['node','--disable-warning=ExperimentalWarning','native/scripts/native_fixture.mjs'],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
    original={key:adb('shell','settings','get',space,key) for space,key in [('system','accelerometer_rotation'),('system','user_rotation'),('system','font_scale')]}
    checks=[]
    try:
        time.sleep(.5);tap_text('建议');time.sleep(.4);pair()
        fill('粘贴或输入你批准的聊天片段，标明说话人','对方：合成旋转测试，今天加班很累。')
        adb('shell','settings','put','system','accelerometer_rotation','0');adb('shell','settings','put','system','user_rotation','1');time.sleep(1)
        assert any('合成旋转测试' in x for x in labels()),labels();checks.append('rotation_preserves_transcript')
        adb('shell','settings','put','system','user_rotation','0');time.sleep(.5)
        adb('shell','settings','put','system','font_scale','1.3');time.sleep(.5)
        assert any('合成旋转测试' in x for x in labels()),labels();scroll_find('分析已批准片段');checks.append('large_font_preserves_input_and_reachable_action')
        adb('shell','settings','put','system','font_scale','1.0');time.sleep(.5)
        tree=snapshot('stability-rotation-font')
        assert all(n.get('checked')!='true' for n in tree.iter('node') if n.get('class')=='android.widget.CheckBox');checks.append('recreated_ui_requires_new_approval')
        adb('reverse','--remove','tcp:4317')
        tap_text('已核对人物和片段，同意提交给连接的服务',scroll_find('已核对人物和片段，同意提交给连接的服务'))
        tap_text('分析已批准片段',scroll_find('分析已批准片段'));time.sleep(2)
        assert '保留草稿并返回原聊天' not in labels();snapshot('stability-offline');checks.append('offline_has_no_insertable_result')
        config=json.loads((OUT/'fixture.json').read_text(encoding='utf-8'));adb('reverse','tcp:4317','tcp:'+config['base'].rsplit(':',1)[1])
        analyze();insert();checks.append('network_recovery_reanalysis_insert')
        assert 'FATAL EXCEPTION' not in adb('shell','logcat','-d','-b','crash')
        (OUT/'stability-receipt.json').write_text(json.dumps({'checks':checks,'apkSha256':hashlib.file_digest(APK.open('rb'),'sha256').hexdigest(),'synthetic':True,'realPhone':False},indent=2))
        print('STABILITY_PASS '+str(len(checks)),flush=True)
    finally:
        for key,value in original.items():
            if value=='null':adb('shell','settings','delete','system',key)
            else:adb('shell','settings','put','system',key,value)
        adb('reverse','--remove','tcp:4317');process.terminate();process.wait(timeout=10);log.close()

if __name__=='__main__':main()
