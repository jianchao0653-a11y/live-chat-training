"""Optional, isolated AOSP Android 16 emulator for synthetic input tests."""
import concurrent.futures
import json
from prepare_tools import install, TOOLS

PACKAGES = [
    ('emulator-windows_x64-15917651.zip', '54fa750822ff462d57e04fc8e98e60f08df2bb61', 'sdk/emulator', True),
    ('x86_64-36_r02.zip', '829c076e8ff448a336097ae25a355b495ba36e2c', 'sdk/system-images/android-36/default/x86_64', True,
     'https://dl.google.com/android/repository/sys-img/android/x86_64-36_r02.zip'),
]
if __name__ == '__main__':
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        receipts = list(pool.map(install, PACKAGES))
    (TOOLS / 'emulator-receipts.json').write_text(json.dumps(receipts, indent=2), encoding='utf-8')
