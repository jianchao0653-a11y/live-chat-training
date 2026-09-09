"""Optional, isolated AOSP Android 16 emulator for synthetic input tests."""
import concurrent.futures
import json
import argparse
from prepare_tools import install, TOOLS

PACKAGES = [
    ('emulator-windows_x64-15917651.zip', '54fa750822ff462d57e04fc8e98e60f08df2bb61', 'sdk/emulator', True),
    ('x86_64-36_r02.zip', '829c076e8ff448a336097ae25a355b495ba36e2c', 'sdk/system-images/android-36/default/x86_64', True,
     'https://dl.google.com/android/repository/sys-img/android/x86_64-36_r02.zip'),
]
if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--api', type=int, choices=[26,34,36], default=36)
    args = parser.parse_args()
    images = {26:('x86_64-26_r01.zip','432f149c048bffce7f9de526ec65b336daf7a0a3'),34:('x86_64-34_r04.zip','5f6a249f9bc3b1b4c459b13ce2eb646c9680bed1'),36:('x86_64-36_r02.zip','829c076e8ff448a336097ae25a355b495ba36e2c')}
    name, checksum = images[args.api]
    PACKAGES[1] = (name, checksum, f'sdk/system-images/android-{args.api}/default/x86_64', True, 'https://dl.google.com/android/repository/sys-img/android/'+name)
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        receipts = list(pool.map(install, PACKAGES))
    (TOOLS / f'emulator-receipts-api{args.api}.json').write_text(json.dumps(receipts, indent=2), encoding='utf-8')
