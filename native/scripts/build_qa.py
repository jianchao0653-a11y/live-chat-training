"""Build only the emulator's window-inspection instrumentation APK."""
from build_android import ROOT, SDK, TOOLS, BUILD, OUT, run
from pathlib import Path
import shutil
import zipfile

# JDK 21 ZipFileSystemProvider resolves a JAR path again when closing it.
# Keep Java's paths canonical; the ASCII junction is needed by Ninja, not javac.
# https://github.com/openjdk/jdk21u/blob/master/src/jdk.zipfs/share/classes/jdk/nio/zipfs/ZipFileSystemProvider.java
folder = (BUILD / 'qa').resolve()
folder.mkdir(parents=True,exist_ok=True)
manifest = folder/'AndroidManifest.xml'
manifest.write_text('''<manifest xmlns:android="http://schemas.android.com/apk/res/android" package="com.conversationlens.ime.qa">
<uses-sdk android:minSdkVersion="26" android:targetSdkVersion="36"/>
<application android:label="Lens Synthetic QA" android:testOnly="true"/>
<instrumentation android:name=".DumpRunner" android:targetPackage="com.conversationlens.ime.qa"/>
</manifest>''',encoding='utf-8')
bt=SDK/'build-tools/36.0.0'
android=(SDK/'platforms/android-36/android.jar').resolve()
java=Path(shutil.which('javac')).parent
run([bt/'aapt2.exe','link','-o',folder/'resources.apk','-I',android,'--manifest',manifest])
classes=folder/'classes';classes.mkdir(exist_ok=True)
run([java/'javac.exe','--release','8','-encoding','UTF-8','-classpath',android,'-d',classes.resolve(),(ROOT/'native/android/tests/DumpRunner.java').resolve()])
with zipfile.ZipFile(folder/'classes.jar','w') as jar:
    for source in classes.rglob('*.class'):jar.write(source,source.relative_to(classes).as_posix())
run([java/'java.exe','-cp',bt/'lib/d8.jar','com.android.tools.r8.D8','--lib',android,'--min-api','26','--output',folder,folder/'classes.jar'])
with zipfile.ZipFile(folder/'unsigned.apk','w') as apk, zipfile.ZipFile(folder/'resources.apk') as original:
    for item in original.infolist():apk.writestr(item,original.read(item))
    apk.write(folder/'classes.dex','classes.dex')
run([bt/'zipalign.exe','-f','4',folder/'unsigned.apk',folder/'aligned.apk'])
run([java/'java.exe','-jar',bt/'lib/apksigner.jar','sign','--ks',TOOLS/'lens-local-debug.keystore','--ks-pass','pass:android',
     '--out',OUT/'lens-synthetic-qa.apk',folder/'aligned.apk'])
