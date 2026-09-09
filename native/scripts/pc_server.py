"""Start hidden local service or request graceful stop; never kill an arbitrary PID."""
from pathlib import Path
import subprocess,sys,os,json,time,urllib.request
ROOT=Path(__file__).resolve().parents[2]
STATE=ROOT/'runtime/pc-server'

def receipt():
    try:return json.loads((STATE/'service.json').read_text(encoding='utf-8'))
    except (OSError,ValueError):return {}

def health():
    try:
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open('http://127.0.0.1:4318/api/native/health',timeout=2) as response:
            return json.load(response).get('status')=='ok'
    except Exception:return False

def main():
    action=sys.argv[1] if len(sys.argv)==2 else ''
    if action not in ['start','stop','status']:raise SystemExit('Usage: pc_server.py start|stop|status')
    current=receipt()
    if action=='status':print(json.dumps({'service':current,'loopbackResponding':health()}));return
    if action=='stop':
        if current.get('status')!='running':print('No running PC service receipt.');return
        (STATE/'stop.json').write_text(json.dumps({'instance':current['instance']}),encoding='utf-8')
        for _ in range(240):
            if receipt().get('status')=='stopped':print('PC service stopped gracefully.');return
            time.sleep(.5)
        raise SystemExit('Stop not confirmed. No process was forcibly killed; inspect the local service log.')
    if current.get('status')=='running' and health():print('PC API is already responding.');return
    STATE.mkdir(parents=True,exist_ok=True)
    logpath=STATE/('service-'+str(time.time_ns())+'.log')
    with logpath.open('wb') as log:
        process=subprocess.Popen(['node','--disable-warning=ExperimentalWarning',str(ROOT/'app/pc-server.mjs')],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
    for _ in range(40):
        if process.poll() is not None:raise SystemExit('Start failed. Inspect '+str(logpath))
        current=receipt()
        if current.get('pid')==process.pid and current.get('status')=='running' and health():
            print('PC service running on loopback:4318. Model spending is governed by the local budget configuration.');return
        time.sleep(.25)
    raise SystemExit('Startup not confirmed. Inspect '+str(logpath))

if __name__=='__main__':main()
