"""Owned synthetic baseline/current keyboard touches and reproducible geometry.

Reuses established keyboard_ui_qa scenarios. Protected screens are never captured.
This does not approve human text readability, OEM behavior or OCR/model quality.
"""
import re
import keyboard_first_qa as first
import keyboard_ui_qa as ui


class KeyboardQA(first.QA):
    def __init__(self, folder):
        super().__init__(folder)
        self.report.update(suite='design-keyboard', checks={k:'NOT_RUN' for k in
            ('portrait','landscape','large-font','max-font')}, geometry={})

    def main_flow(self):
        q=first.q
        original={key:q.adb('shell','settings','get','system',key) for key in
            ('accelerometer_rotation','user_rotation','font_scale')}
        original_size=q.adb('shell','wm','size')
        capture=ui.screenshot
        def checkpoint(name):
            size=capture(name)
            tree=q.snapshot(name+'-tree')
            attrs=('class','text','description','hint','bounds','enabled','clickable','checked','focused')
            # IME window only; host clock/caret state cannot mask key differences.
            nodes=self.ime_window(tree).iter('node')
            self.report['geometry'][name]=[{k:n.get(k,'') for k in attrs} for n in nodes]
            self.save()
            return size
        ui.screenshot=checkpoint
        try:
            first.verify_target()
            q.adb('shell','wm','size','720x1280')
            for scenario in [('portrait',0,1.0),('landscape',1,1.0),('large-font',0,1.3),('max-font',0,2.0)]:
                self.begin(scenario[0])
                first.verify_target()
                ui.run_scenario(*scenario)
                self.passed(scenario[0])
            self.report['realTouches']=ui.records
        finally:
            ui.screenshot=capture
            first.verify_target()
            q.adb('shell','am','force-stop',first.PACKAGE)
            for key,value in original.items():
                if value=='null':q.adb('shell','settings','delete','system',key)
                else:q.adb('shell','settings','put','system',key,value)
            match=re.search(r'Override size:\s*(\S+)',original_size)
            q.adb('shell','wm','size',match.group(1) if match else 'reset')
            restored={key:q.adb('shell','settings','get','system',key) for key in original}
            assert restored==original and q.adb('shell','wm','size')==original_size,'Display restore mismatch'
            self.report['displayRestored']=True


if __name__=='__main__':
    first.main(qa_factory=KeyboardQA,output_group='keyboard-design-main-qa')
