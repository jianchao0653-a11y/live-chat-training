"""Compatibility entry point for the verified local delivery pipeline."""
from pathlib import Path
import subprocess,sys
if len(sys.argv)!=2:raise SystemExit('Usage: build_release.py https://DEPLOYED-DOMAIN')
raise SystemExit(subprocess.call([sys.executable,str(Path(__file__).with_name('local_delivery.py')),'--endpoint',sys.argv[1]]))
