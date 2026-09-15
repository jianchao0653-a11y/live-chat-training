"""Template geometry and real key touches in synthetic, non-secure SetupActivity."""
import json
import re
import struct
import time
import android_qa as q

PRACTICE='在这里试打 nihao、zhongguo、xiexie'
records=[]

def practice(tree=None):
    tree=tree if tree is not None else q.snapshot()
    fields=[n for n in tree.iter('node') if n.get('package')=='com.conversationlens.ime'
            and n.get('class')=='android.widget.EditText' and n.get('hint')==PRACTICE
            and n.get('password')=='false']
    if len(fields)!=1:raise AssertionError('Only the synthetic practice host is supported')
    return fields[0]

def wait_text(expected):
    deadline=time.monotonic()+8
    while time.monotonic()<deadline:
        if practice_text()==expected:return
        time.sleep(.15)
    raise AssertionError('Actual touch did not produce the expected synthetic text')


def practice_text(tree=None):
    field=practice(tree)
    value=field.get('text','')
    return '' if value==field.get('hint') else value

def viewport(tree):
    signatures={'分词','2 ABC','5 JKL','8 TUV','重输当前拼音','空格','返回文字键盘','q'}
    candidates=[]
    for n in tree.iter('node'):
        if n.get('class')=='android.widget.ScrollView' and any(
                c.get('description') in signatures for c in n.iter('node')):
            if q.has_area(n):candidates.append(n)
    if len(candidates)!=1:raise AssertionError('Expected one visible keyboard scroll viewport')
    return q.node_bounds(candidates[0])

def scroll(tree,down=True):
    left,top,right,bottom=viewport(tree)
    if right-left<80 or bottom-top<80:raise AssertionError('Keyboard viewport is too small to touch')
    start=top+int((bottom-top)*(.75 if down else .25))
    end=top+int((bottom-top)*(.25 if down else .75))
    q.adb('shell','input','swipe',str((left+right)//2),str(start),str((left+right)//2),str(end),'250')
    time.sleep(.2)

def reach(description,enabled=True):
    # Scroll only the keyboard's own viewport. Never swipe through system bars
    # or use accessibility performClick as a substitute for a physical touch.
    for attempt in range(12):
        tree=q.snapshot()
        left,top,right,bottom=viewport(tree)
        matches=q.key_nodes(tree=tree,description=description,enabled=enabled)
        for n in matches:
            x1,y1,x2,y2=q.node_bounds(n)
            if left <= x1 < x2 <= right and top <= y1 < y2 <= bottom:
                return n
        scroll(tree,down=attempt<6)
    raise AssertionError('Keyboard key not reachable: '+description)

def touch(description):
    q.tap_node(reach(description))
    time.sleep(.15)

def wait_header():
    deadline=time.monotonic()+20
    previous=None;stable=0
    while time.monotonic()<deadline:
        tree=q.snapshot()
        if q.key_nodes('建议',tree,enabled=True) and q.key_nodes(tree=tree,description='切换输入法',enabled=True):
            geometry=tuple((n.get('description'),q.node_bounds(n)) for n in q.key_nodes(tree=tree))
            stable=stable+1 if geometry==previous else 0
            previous=geometry
            if stable>=2:return tree
        else:previous=None;stable=0
        time.sleep(.2)
    raise AssertionError('Keyboard toolbar did not become usable')

def wait_layout(description):
    deadline=time.monotonic()+20
    while time.monotonic()<deadline:
        tree=wait_header()
        if q.key_nodes(tree=tree,description=description,enabled=True):return tree
    raise AssertionError('Keyboard layout switch did not finish')

def focus_visible_practice():
    # A focused editor may report bounds behind the IME. Do not touch through it.
    for attempt in range(12):
        tree=q.snapshot()
        try:field=practice(tree)
        except AssertionError:
            # Activity/window replacement can briefly expose only system bars.
            # Wait for the same synthetic host; do not send another touch.
            time.sleep(.2);continue
        ime_windows=[n for n in tree.findall('node') if any(
            child.get('description')=='切换输入法' for child in n.iter('node'))]
        if field.get('focused')=='true' and ime_windows:return tree
        if field.get('focused')=='true' and attempt<2:
            time.sleep(.2);continue
        hosts=[n for n in tree.iter('node')
               if n.get('class')=='android.widget.ScrollView'
               and any(c.get('hint')==PRACTICE for c in n.iter('node'))]
        if len(hosts)!=1:raise AssertionError('Expected one synthetic host scroll viewport')
        left,top,right,bottom=q.node_bounds(hosts[0])
        host_bottom=bottom
        # Exclude the separately reported status/navigation windows.
        for window in tree.findall('node'):
            if window.get('package')=='com.conversationlens.ime':continue
            x1,y1,x2,y2=q.node_bounds(window)
            if not x1 <= (left+right)//2 < x2:continue
            if y1<=top and y2<host_bottom/2:top=max(top,y2)
            elif y2>=host_bottom and y1>host_bottom/2:bottom=min(bottom,y1)
        if ime_windows:bottom=min(bottom,min(q.node_bounds(n)[1] for n in ime_windows))
        x1,y1,x2,y2=q.node_bounds(field)
        visible_top=max(top,y1);visible_bottom=min(bottom,y2)
        if min(right,x2)-max(left,x1)>=8 and visible_bottom-visible_top>=8:
            # One focus touch, restricted to the visible host intersection.
            q.adb('shell','input','tap',str((max(left,x1)+min(right,x2))//2),
                  str((visible_top+visible_bottom)//2))
            deadline=time.monotonic()+5
            while time.monotonic()<deadline:
                current=q.snapshot()
                try:focused=practice(current).get('focused')=='true'
                except AssertionError:focused=False
                if focused:return current
                time.sleep(.15)
            raise AssertionError('Synthetic practice editor did not gain focus')
        if bottom-top<80:raise AssertionError('Synthetic host has no safe scroll area')
        # Scroll only inside the host area above the IME.
        down=y1>=bottom
        start=top+int((bottom-top)*(.75 if down else .25))
        end=top+int((bottom-top)*(.25 if down else .75))
        q.adb('shell','input','swipe',str((left+right)//2),str(start),
              str((left+right)//2),str(end),'250')
        time.sleep(.2)
    raise AssertionError('Synthetic practice editor is not reachable')


def open_practice():
    # Each scenario/helper return starts clean; force-stop preserves prefs.
    q.adb('shell','am','force-stop','com.conversationlens.ime')
    q.adb('shell','am','start','-W','-n','com.conversationlens.ime/.SetupActivity')
    q.adb('shell','ime','set','com.conversationlens.ime/.LensImeService')
    focus_visible_practice()
    tree=wait_header()
    if practice_text(tree) or q.candidate_buttons(tree):
        raise AssertionError('A new synthetic host must contain no text or composition')
    if q.key_nodes(tree=tree,description='切换九宫格',enabled=True):
        q.tap_key(description='切换九宫格',tree=tree)
    return wait_layout('切换全键盘')

def screenshot(name):
    # No screenshots of AssistantActivity/LibraryActivity/OCR review windows.
    # Their FLAG_SECURE policy is never changed for visual QA.
    practice()
    activity=q.adb('shell','dumpsys','activity','activities')
    resumed=[line for line in activity.splitlines() if 'mResumedActivity' in line or 'topResumedActivity' in line]
    if not any('com.conversationlens.ime/.SetupActivity' in line for line in resumed):
        raise AssertionError('Screenshot requires the synthetic SetupActivity in foreground')
    q.screenshot(name)
    data=(q.OUT/(name+'.png')).read_bytes()
    if data[:8]!=b'\x89PNG\r\n\x1a\n':raise AssertionError('Expected PNG screenshot')
    return struct.unpack('>II',data[16:24])

def template_shape(tree):
    def one(desc):
        found=q.key_nodes(tree=tree,description=desc)
        if len(found)!=1:raise AssertionError('Missing template key: '+desc)
        return q.node_bounds(found[0])
    grid=[one(d) for d in ['分词','2 ABC','3 DEF','4 GHI','5 JKL','6 MNO','7 PQRS','8 TUV','9 WXYZ']]
    marks=[one(d) for d in ['，','。','？','！']]
    actions=[one(d) for d in ['退格','重输当前拼音','0']]
    bottom=[one(d) for d in ['符','123','空格','切换到英文','换行']]
    assert max(r[2] for r in marks)<=min(r[0] for r in grid),'Punctuation must be left of nine-key grid'
    assert max(r[2] for r in grid)<=min(r[0] for r in actions),'Actions must be right of nine-key grid'
    for row in [grid[:3],grid[3:6],grid[6:],bottom]:
        assert all(a[2]<=b[0] for a,b in zip(row,row[1:])),'Template keys overlap or are out of order'
    assert grid[2][3]<=grid[3][1] and grid[5][3]<=grid[6][1],'Nine-key rows overlap'
    assert max(r[3] for r in grid)<=min(r[1] for r in bottom),'Bottom row must follow nine-key grid'
    for desc in ['建议','切换全键盘','切换输入法']:
        assert one(desc)[3]<=min(r[1] for r in grid),'Toolbar must stay above keys'
    assert not any('简体拼音 · 离线' in n.get('text','') or '不记录学习' in n.get('text','') for n in tree.iter('node'))

def run_scenario(name,rotation,font):
    print('RUN keyboard '+name,flush=True)
    q.adb('shell','settings','put','system','accelerometer_rotation','0')
    q.adb('shell','settings','put','system','user_rotation',str(rotation))
    q.adb('shell','settings','put','system','font_scale',str(font))
    time.sleep(1)
    tree=open_practice()
    # A newly created keyboard starts at the top; avoid unnecessary swipes
    # over keys when the compact landscape viewport already fits all rows.
    size=screenshot('keyboard-template-'+name)
    if name=='portrait':
        template_shape(tree)
        q.tap_key(description='切换全键盘',tree=tree)
        wait_layout('切换九宫格')
        screenshot('keyboard-template-portrait-full')
        q.tap_key(description='切换九宫格')
        wait_layout('切换全键盘')
    # Probe each physical region once; detailed pinyin/reset/paging behavior
    # remains in nine_key_qa.py and android_qa.py rather than duplicated here.
    prefix=practice_text()
    for description,literal in [('，','，'),('0','0'),('空格',' ')]:
        touch(description);prefix+=literal;wait_text(prefix)
    touch('符');touch('？');prefix+='？';wait_text(prefix);touch('返回文字键盘')
    touch('123');touch('7');prefix+='7';wait_text(prefix);touch('返回文字键盘')
    touch('切换到英文');touch('a');prefix+='a';wait_text(prefix);touch('切换到中文')
    touch('换行');prefix+='\n';wait_text(prefix)
    screenshot('keyboard-touched-'+name)
    # The fixed top action must open the protected helper by an actual touch.
    q.tap_key(description='建议')
    deadline=time.monotonic()+8
    while time.monotonic()<deadline:
        activity=q.adb('shell','dumpsys','activity','activities')
        if any('AssistantActivity' in line for line in activity.splitlines()
               if 'mResumedActivity' in line or 'topResumedActivity' in line):break
        time.sleep(.2)
    else:raise AssertionError('Top suggestion action did not open the helper')
    records.append({'scenario':name,'rotation':rotation,'fontScale':font,
                    'screenPixels':size,'realTouches':True,'suggestionOpened':True})
    print('PASS keyboard '+name,flush=True)
    # No helper form is filled or approved; return to the synthetic host.
    open_practice()

def main():
    q.wait_boot()
    original={key:q.adb('shell','settings','get','system',key)
              for key in ['accelerometer_rotation','user_rotation','font_scale']}
    try:
        for scenario in [('portrait',0,1.0),('landscape',1,1.0),('large-font',0,1.3),('max-font',0,2.0)]:
            run_scenario(*scenario)
        package=q.adb('shell','dumpsys','package','com.conversationlens.ime')
        version_name=re.search(r'versionName=([^\s]+)',package)
        version_code=re.search(r'versionCode=(\d+)',package)
        if not version_name or not version_code:raise AssertionError('Installed APK version not reported')
        (q.OUT/'keyboard-template-receipt.json').write_text(json.dumps({
            'status':'PASS','checks':records,'synthetic':True,'realPhone':False,
            'api':q.adb('shell','getprop','ro.build.version.sdk'),
            'installedVersionName':version_name.group(1),'installedVersionCode':int(version_code.group(1)),
            'protectedScreensCaptured':False,
            'apkSha256':q.hashlib.file_digest(q.APK.open('rb'),'sha256').hexdigest()
        },ensure_ascii=False,indent=2),encoding='utf-8')
        print('KEYBOARD_TEMPLATE_PASS '+str(len(records)))
    finally:
        for key,value in original.items():
            if value=='null':q.adb('shell','settings','delete','system',key)
            else:q.adb('shell','settings','put','system',key,value)

if __name__=='__main__':main()
