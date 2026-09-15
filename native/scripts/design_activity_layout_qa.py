"""Same synthetic Activity/OCR scenes on both APKs; real touches, no screenshots."""
import hashlib
import re
import subprocess
import time
import keyboard_first_qa as first

CONFIGS=(('portrait','720x1280','1.0'),('large','720x1280','2.0'),
         ('narrow','640x1136','1.0'),('landscape','1280x720','1.0'))
ATTRS=('class','text','description','hint','bounds','enabled','clickable','checked','focused')
TITLE='逐条校对截图'


class ActivityLayoutQA(first.QA):
    def __init__(self,folder):
        super().__init__(folder)
        self.report.update(suite='design-activity-layout',checks={k:'NOT_RUN' for k,*_ in CONFIGS},
            geometry={},touchRegions={},comparisonRule='v2: same scene/config; canonical endpoints for every sampled window and OCR field/inclusion touch; exact hierarchy and clipped bounds; zero pixels',
            notCovered=['protected pixels','all Activity subpages','all scroll offsets','OEM/human legibility'])

    def window(self,tree,anchor):
        found=[n for n in tree.findall('node') if n.get('package')==first.PACKAGE
               and any(c.get('text')==anchor for c in n.iter('node'))]
        if len(found)!=1:raise AssertionError('Ambiguous activity/dialog window: '+anchor)
        return found[0]

    def checkpoint(self,name,anchor,end=False,save=True):
        previous=None;stable=0
        for attempt in range(28):
            tree=self.tree();window=self.window(tree,anchor)
            shape=[{k:n.get(k,'') for k in ATTRS} for n in window.iter('node')]
            stable=stable+1 if shape==previous else 0;previous=shape
            if stable>=2:break
            scrolls=[self.clipped(n,tree) for n in window.iter('node') if n.get('class')=='android.widget.ScrollView']
            scrolls=[r for r in scrolls if r[2]-r[0]>40 and r[3]-r[1]>40]
            if scrolls:
                left,top,right,bottom=max(scrolls,key=lambda r:(r[2]-r[0])*(r[3]-r[1]))
                first.q.adb('shell','input','swipe',left+4,top+int((bottom-top)*(.85 if end else .15)),
                    left+4,top+int((bottom-top)*(.15 if end else .85)),400)
                self.record('canonical_scroll',name)
            time.sleep(.25)
        else:raise AssertionError('Activity endpoint did not stabilize: '+name)
        if save:
            self.report['geometry'][name]=shape
            self.tree(name);self.save()

    def hit(self,name,text,kind='text'):
        node,rect=self.reach(text,kind=kind,scope='activity')
        self.report['touchRegions'][name]=list(rect)
        first.q.adb('shell','input','tap',(rect[0]+rect[2])//2,(rect[1]+rect[3])//2)
        self.record('actual_touch',name);time.sleep(.2)

    def hide_ime(self):
        tree=self.tree()
        # Helper editors hide the mode tabs. Detect the keyboard's system-switch
        # button instead, which exists in both ordinary and helper input states.
        if any(n.get('description')=='切换输入法' for n in tree.iter('node')):
            first.q.adb('shell','input','keyevent','BACK');time.sleep(.3)
            self.wait(lambda tree:not any(n.get('description')=='切换输入法' for n in tree.iter('node')),'Keyboard did not hide')

    def ocr(self,config,action):
        q=first.q;first.verify_target()
        log_path=self.folder/(config+'-'+action+'-instrumentation.log')
        with log_path.open('w',encoding='utf-8') as log:
            process=subprocess.Popen([str(q.ADB),'-s',q.SERIAL,'shell','am','instrument','-w','-e',
                'design_action',action,'com.conversationlens.ime.test/com.conversationlens.ime.OcrTestRunner'],
                stdout=log,stderr=subprocess.STDOUT)
            try:
                self.wait_label(TITLE,35)
                self.hide_ime()
                if action=='cancel':self.checkpoint(config+'-ocr-top',TITLE)
                # At 2x font the first field is below the viewport at the top,
                # but its last 48px are reachable at the bottom. Other configs
                # expose the first field at the top. Both are clamped endpoints.
                self.checkpoint(config+'-'+action+'-field-position',TITLE,end=config=='large',save=False)
                self.hit(config+'-'+action+'-field','第1条校对文字',kind='hint')
                q.adb('shell','input','keyevent','KEYCODE_MOVE_END')
                q.adb('shell','input','keyevent','KEYCODE_DEL')
                self.wait(lambda tree:any(n.get('hint')=='第1条校对文字' and n.get('text')=='明天再' for n in tree.iter('node')),
                    'Physical key deletion did not update synthetic OCR text')
                self.hide_ime()
                self.checkpoint(config+'-'+action+'-include-position',TITLE,end=True,save=False)
                self.hit(config+'-'+action+'-include','第2条纳入分析',kind='description')
                if action=='approve':self.checkpoint(config+'-ocr-bottom',TITLE,end=True)
                self.hit(config+'-'+action+'-button','取消' if action=='cancel' else '已逐条核对，回填')
                process.wait(timeout=20)
                result=log_path.read_text(encoding='utf-8')
                assert process.returncode==0 and 'design_touch=PASS' in result and 'cleanup_error=' not in result,result
                self.report.setdefault('ocrContracts',{})[config+'-'+action]='PASS'
            finally:
                if process.poll() is None:
                    first.verify_target();q.adb('shell','am','force-stop',first.PACKAGE)
                    try:process.wait(timeout=8)
                    except subprocess.TimeoutExpired:process.terminate();process.wait(timeout=5)

    def main_flow(self):
        q=first.q
        size=q.adb('shell','wm','size');font=q.adb('shell','settings','get','system','font_scale')
        test=q.ROOT/'runtime/android-gradle-build/outputs/apk/androidTest/debug/LensAndroid-debug-androidTest.apk'
        self.report['testApk']={'path':test.relative_to(q.ROOT).as_posix(),'sha256':hashlib.sha256(test.read_bytes()).hexdigest()}
        try:
            first.verify_target()
            assert 'Success' in q.adb('install','--no-incremental','-r','-t',test)
            for config,dimensions,scale in CONFIGS:
                self.begin(config);first.verify_target()
                q.adb('shell','am','force-stop',first.PACKAGE)
                q.adb('shell','wm','size',dimensions);q.adb('shell','settings','put','system','font_scale',scale)
                self.screen=tuple(map(int,dimensions.split('x')))
                self.report.setdefault('configurations',{})[config]={'size':q.adb('shell','wm','size'),
                    'font':q.adb('shell','settings','get','system','font_scale'),'density':q.adb('shell','wm','density')}
                q.adb('shell','am','start','-W','-n',first.PACKAGE+'/.SetupActivity')
                q.adb('shell','ime','set',first.COMPONENT)
                self.wait_label('观微输入法');self.hide_ime()
                self.checkpoint(config+'-setup','观微输入法')
                self.hit(config+'-login','登录与人物资料')
                self.wait_label('新建人物')
                self.hit(config+'-new','新建人物')
                self.wait_label('保存人物');self.hide_ime()
                self.checkpoint(config+'-library','新建人物',end=True)
                self.hit(config+'-library-cancel','取消')
                self.wait_label('人物与聊天记忆')
                # AssistantActivity is intentionally not exported; enter by the
                # existing real keyboard action, never weaken the manifest.
                from keyboard_ui_qa import open_practice
                open_practice();q.tap_key(description='建议')
                self.wait(lambda tree:any(n.get('hint')=='聊天片段（可粘贴、输入或从截图提取）' for n in tree.iter('node')),'Suggestion page did not open')
                self.hide_ime();self.checkpoint(config+'-assistant','观微 · 聊天建议')
                self.ocr(config,'cancel');self.ocr(config,'approve')
                self.passed(config)
        finally:
            first.verify_target();q.adb('shell','am','force-stop',first.PACKAGE)
            match=re.search(r'Override size:\s*(\S+)',size)
            q.adb('shell','wm','size',match.group(1) if match else 'reset')
            if font=='null':q.adb('shell','settings','delete','system','font_scale')
            else:q.adb('shell','settings','put','system','font_scale',font)
            assert q.adb('shell','wm','size')==size and q.adb('shell','settings','get','system','font_scale')==font
            self.report['displayRestored']=True


if __name__=='__main__':first.main(qa_factory=ActivityLayoutQA,output_group='keyboard-design-activity-layout-qa')
