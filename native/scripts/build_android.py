"""Build a local debug APK using official CMake/NDK, aapt2, javac, D8 and apksigner.

No Gradle installation, global configuration, network access or private database
access is required during this build. Run prepare_tools.py/prepare_sources.py first.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import zipfile
import tempfile
import sys

SOURCE_ROOT = Path(__file__).resolve().parents[2]
# Android's bundled Ninja emits Windows response files in the active code page.
# An ASCII junction avoids corrupting Chinese workspace paths at link time.
# This creates only a directory link, never copies/moves the project or changes PATH.
ROOT = SOURCE_ROOT
if os.name == 'nt' and not str(SOURCE_ROOT).isascii():
    link = Path(tempfile.gettempdir()) / ('lens-native-' + hashlib.sha256(str(SOURCE_ROOT).encode()).hexdigest()[:10])
    if not link.exists():
        environment = {**os.environ, 'LENS_LINK':str(link), 'LENS_SOURCE':str(SOURCE_ROOT)}
        subprocess.run(['powershell.exe', '-NoProfile', '-Command',
            'New-Item -ItemType Junction -Path $env:LENS_LINK -Target $env:LENS_SOURCE | Out-Null'], env=environment, check=True)
    if link.resolve() != SOURCE_ROOT:
        raise RuntimeError('Existing ASCII build link points to another project')
    ROOT = link
APP = ROOT / 'native/android'
TOOLS = ROOT / 'runtime/android-tools'
SDK = Path(os.environ.get('ANDROID_SDK_ROOT', os.environ.get('ANDROID_HOME', str(TOOLS / 'sdk'))))
NDK_HOST = 'windows-x86_64' if os.name == 'nt' else ('darwin-x86_64' if sys.platform == 'darwin' else 'linux-x86_64')
BUILD = ROOT / 'runtime/native-build-ascii'
VENDOR = ROOT / 'runtime/native-sources'
OUT = ROOT / 'output/native'

def run(args, **kwargs):
    args = list(map(str, args))
    if os.name != 'nt' and args[0].endswith('.exe'): args[0] = args[0][:-4]
    print('Run ' + Path(args[0]).name + ' ' + ' '.join(args[1:3]), flush=True)
    subprocess.run(args, check=True, **kwargs)

def notices():
    specs = [
        ('librime 1.17.0 — BSD-3-Clause', 'librime/LICENSE'),
        ('Boost 1.85.0 — BSL-1.0', 'boost/LICENSE_1_0.txt'),
        ('yaml-cpp 0.8.0 — MIT', 'yaml-cpp/LICENSE'),
        ('LevelDB 1.23 — BSD-3-Clause', 'leveldb/LICENSE'),
        ('marisa-trie 0.3.1 — BSD-2-Clause option selected', 'marisa-trie/COPYING.md'),
        ('OpenCC 1.1.9 — Apache-2.0', 'OpenCC/LICENSE'),
        ('Rime pinyin-simp / Android PinyinIME dictionary — Apache-2.0', 'rime-pinyin-simp/LICENSE'),
        ('Darts-clone (bundled by librime) — BSD-3-Clause', 'librime/include/COPYING.darts-clone'),
        ('utf8cpp (bundled by librime) — BSL-1.0, notice in header', 'librime/include/utf8.h'),
        ('X11 keysym definitions (bundled by librime) — upstream notices', 'librime/include/X11/keysym.h'),
        ('X11 keysyms — upstream notices', 'librime/include/X11/keysymdef.h'),
        ('RapidJSON 1.1.0 (bundled by OpenCC) — MIT, notice in header', 'OpenCC/deps/rapidjson-1.1.0/rapidjson/rapidjson.h'),
    ]
    text = 'Conversation Lens Android local preview\nNo Trime frontend code is included.\n\n'
    for title, filename in specs:
        content = (VENDOR / filename).read_text(encoding='utf-8')
        # Header files retain their full license block, not the implementation.
        if filename.endswith(('.h',)):
            if '/X11/' in filename:
                content = content[:content.index('#define')]
            elif '#ifndef' in content:
                content = content[:content.index('#ifndef')]
        text += '\n=== ' + title + ' ===\n' + content + '\n'
    text += '\n=== RapidJSON full license and third-party notices ===\n' + (ROOT / 'native/licenses/RapidJSON-1.1.0.txt').read_text(encoding='utf-8')
    text += '\n=== Android libc++ runtime ===\nApache-2.0 with LLVM exceptions; full bundled toolchain notices are in NDK-NOTICES.txt in this package.\n'
    text += '\nDependency commits and source archive checksums:\n' + (ROOT / 'native/dependencies.lock.json').read_text()
    return text

def build(abis, native_only=False):
    OUT.mkdir(parents=True, exist_ok=True)
    TOOLS.mkdir(parents=True, exist_ok=True)
    BUILD.mkdir(parents=True, exist_ok=True)
    cmake = SDK / 'cmake/3.22.1/bin/cmake.exe'
    ninja = SDK / ('cmake/3.22.1/bin/ninja.exe' if os.name == 'nt' else 'cmake/3.22.1/bin/ninja')
    ndk = SDK / 'ndk/28.2.13676358'
    for abi in abis:
        folder = BUILD / abi
        run([cmake, '-S', APP, '-B', folder, '-G', 'Ninja', f'-DCMAKE_MAKE_PROGRAM={ninja.as_posix()}',
             f'-DCMAKE_TOOLCHAIN_FILE={(ndk / "build/cmake/android.toolchain.cmake").as_posix()}',
             '-DCMAKE_BUILD_TYPE=Release', f'-DANDROID_ABI={abi}', '-DANDROID_PLATFORM=android-26', '-DANDROID_STL=c++_shared'])
        run([cmake, '--build', folder, '--target', 'lens_rime', 'rime_smoke', '--parallel', '4'])
    if native_only: return
    assets = BUILD / 'assets'
    shutil.copytree(APP / 'assets', assets, dirs_exist_ok=True)
    shutil.copy2(VENDOR / 'rime-pinyin-simp/pinyin_simp.dict.yaml', assets / 'rime')
    (assets / 'THIRD_PARTY_NOTICES.txt').write_text(notices(), encoding='utf-8')
    ndk_notices = (ndk / 'NOTICE.toolchain').read_text(encoding='utf-8')
    (assets / 'NDK-NOTICES.txt').write_text(ndk_notices, encoding='utf-8')
    shutil.copy2(assets / 'THIRD_PARTY_NOTICES.txt', OUT)
    shutil.copy2(assets / 'NDK-NOTICES.txt', OUT)
    generated = BUILD / 'generated'
    classes = BUILD / 'classes'
    dex = BUILD / 'dex'
    for folder in [generated, classes, dex]: folder.mkdir(exist_ok=True)
    bt = SDK / 'build-tools/36.0.0'
    android_jar = SDK / 'platforms/android-36/android.jar'
    run([bt / 'aapt2.exe', 'compile', '--dir', APP / 'res', '-o', BUILD / 'resources.zip'])
    unsigned = BUILD / 'unsigned.apk'
    resources_apk = BUILD / 'resources.apk'
    run([bt / 'aapt2.exe', 'link', '-o', resources_apk, '-I', android_jar,
         '--manifest', APP / 'AndroidManifest.xml', '--java', generated,
         '-A', assets, BUILD / 'resources.zip'])
    java = Path(shutil.which('javac')).parent
    sources = list((APP / 'java').rglob('*.java')) + list(generated.rglob('*.java'))
    source_list = BUILD / 'sources.txt'
    source_list.write_text('\n'.join('"' + x.as_posix() + '"' for x in sources), encoding='utf-8')
    # Use Java 8's compiler bootstrap (including LambdaMetafactory); D8 desugars
    # lambdas against the Android API library for minSdk 26.
    run([java / 'javac.exe', '-encoding', 'UTF-8', '--release', '8', '-classpath', android_jar,
         '-d', classes, '@' + str(source_list)])
    classes_jar = BUILD / 'classes.jar'
    with zipfile.ZipFile(classes_jar, 'w') as jar:
        for file in classes.rglob('*.class'): jar.write(file, file.relative_to(classes).as_posix())
    run([java / 'java.exe', '-cp', bt / 'lib/d8.jar', 'com.android.tools.r8.D8',
         '--lib', android_jar, '--min-api', '26', '--output', dex, classes_jar])
    # Repack instead of appending: Python/aapt2 disagree on UTF-8 header flags
    # when editing an existing zip central directory. Repacking keeps both equal.
    with zipfile.ZipFile(unsigned, 'w', compression=zipfile.ZIP_DEFLATED) as apk:
        with zipfile.ZipFile(resources_apk) as original:
            for item in original.infolist(): apk.writestr(item, original.read(item))
        apk.write(dex / 'classes.dex', 'classes.dex')
        triples = {'arm64-v8a':'aarch64-linux-android', 'x86_64':'x86_64-linux-android'}
        for abi in abis:
            library = BUILD / abi / 'liblens_rime.so'
            stripped = BUILD / abi / 'liblens_rime-stripped.so'
            run([ndk / f'toolchains/llvm/prebuilt/{NDK_HOST}/bin/llvm-strip.exe', '--strip-unneeded', '-o', stripped, library])
            apk.write(stripped, f'lib/{abi}/liblens_rime.so')
            apk.write(ndk / f'toolchains/llvm/prebuilt/{NDK_HOST}/sysroot/usr/lib/{triples[abi]}/libc++_shared.so', f'lib/{abi}/libc++_shared.so')
    aligned = BUILD / 'aligned.apk'
    run([bt / 'zipalign.exe', '-f', '-P', '16', '4', unsigned, aligned])
    keystore = TOOLS / 'lens-local-debug.keystore'
    if not keystore.exists():
        run([java / 'keytool.exe', '-genkeypair', '-keystore', keystore, '-storepass', 'android', '-keypass', 'android',
             '-alias', 'androiddebugkey', '-keyalg', 'RSA', '-keysize', '2048', '-validity', '3650',
             '-dname', 'CN=Conversation Lens Local Debug,O=Local Test,C=CN'])
    apk = OUT / 'conversation-lens-0.15.1-debug.apk'
    signer = [java / 'java.exe', '-jar', bt / 'lib/apksigner.jar']
    run(signer + ['sign', '--ks', keystore, '--ks-pass', 'pass:android', '--key-pass', 'pass:android', '--out', apk, aligned])
    run(signer + ['verify', '--verbose', apk])
    run([bt / 'zipalign.exe', '-c', '-P', '16', '4', apk])
    receipt = {'apk':apk.name, 'sha256':hashlib.file_digest(apk.open('rb'), 'sha256').hexdigest(),
        'abis':abis, 'minSdk':26, 'targetSdk':36, 'runtimeVerified':False,
        'tools':json.loads((TOOLS / 'receipts.json').read_text()) if (TOOLS / 'receipts.json').exists() else {'source':'CI Android SDK','sdk':str(SDK)},
        'dependencies':json.loads((ROOT / 'native/dependencies.lock.json').read_text())}
    (OUT / 'build-receipt.json').write_text(json.dumps(receipt, indent=2), encoding='utf-8')
    print('Built: ' + str(apk), flush=True)

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--abis', nargs='+', default=['arm64-v8a', 'x86_64'], choices=['arm64-v8a', 'x86_64'])
    parser.add_argument('--native-only', action='store_true')
    args = parser.parse_args()
    build(args.abis, args.native_only)
