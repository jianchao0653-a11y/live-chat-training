"""Existing OCR review contracts on the current APK; no paid or real data access.

Instrumentation actions are API contract checks, not physical touch/geometry QA.
Setup/Library login is separately exercised by the owned first.main fixture.
"""
import hashlib
import re
import keyboard_first_qa as first


CONFIGS=(('phone','720x1280','320','1.0'),('large-font','1080x2400','480','1.3'),
         ('wide','1280x720','320','1.0'))


class ActivityQA(first.QA):
    def __init__(self,folder):
        super().__init__(folder)
        self.report.update(suite='design-activity-contract',checks={k:'NOT_RUN' for k,*_ in CONFIGS},
            contractInteraction='instrumentation-contract',notCovered=['OCR dialog physical touches',
            'Activity before/after pixel or geometry comparison','human readability','real phone'])

    def main_flow(self):
        q=first.q
        original={k:q.adb('shell','wm',k) for k in ('size','density')}
        font=q.adb('shell','settings','get','system','font_scale')
        test=q.ROOT/'runtime/android-gradle-build/outputs/apk/androidTest/debug/LensAndroid-debug-androidTest.apk'
        self.report['testApk']={'path':test.relative_to(q.ROOT).as_posix(),
            'sha256':hashlib.sha256(test.read_bytes()).hexdigest()}
        try:
            first.verify_target()
            assert 'Success' in q.adb('install','--no-incremental','-r','-t',test),'Test install failed'
            for label,size,density,scale in CONFIGS:
                self.begin(label)
                first.verify_target()
                q.adb('shell','wm','size',size);q.adb('shell','wm','density',density)
                q.adb('shell','settings','put','system','font_scale',scale)
                result=q.adb('shell','am','instrument','-w','-e','review','true',
                    'com.conversationlens.ime.test/com.conversationlens.ime.OcrTestRunner',timeout=90)
                (q.OUT/(label+'-review.log')).write_text(result,encoding='utf-8')
                assert 'review_ui=PASS' in result and 'cleanup_error=' not in result,result
                self.report.setdefault('configurations',{})[label]={'size':size,'density':density,'fontScale':scale}
                self.passed(label)
        finally:
            first.verify_target()
            q.adb('shell','am','force-stop',first.PACKAGE)
            for key,value in original.items():
                match=re.search(r'Override '+key+r':\s*(\S+)',value)
                q.adb('shell','wm',key,match.group(1) if match else 'reset')
            if font=='null':q.adb('shell','settings','delete','system','font_scale')
            else:q.adb('shell','settings','put','system','font_scale',font)
            assert {k:q.adb('shell','wm',k) for k in original}==original
            assert q.adb('shell','settings','get','system','font_scale')==font
            self.report['displayRestored']=True


if __name__=='__main__':first.main(qa_factory=ActivityQA,output_group='keyboard-design-activity-contract-qa')
