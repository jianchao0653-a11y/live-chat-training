from pathlib import Path
import shutil
import subprocess
import os

root = Path(__file__).resolve().parents[2]
output = root / 'runtime/native-tests'
output.mkdir(parents=True, exist_ok=True)
java = Path(shutil.which('javac')).parent
suffix = '.exe' if os.name == 'nt' else ''
subprocess.run([str(java/('javac'+suffix)), '-encoding', 'UTF-8', '-d', str(output),
    str(root/'native/android/java/com/conversationlens/ime/EditorPolicy.java'),
    str(root/'native/android/tests/EditorPolicyTest.java')], check=True)
subprocess.run([str(java/('java'+suffix)), '-cp', str(output), 'com.conversationlens.ime.EditorPolicyTest'], check=True)
subprocess.run([str(java/('javac'+suffix)), '-encoding', 'UTF-8', '-d', str(output),str(root/'native/android/java/com/conversationlens/ime/FramePixels.java'),str(root/'native/android/tests/FramePixelsTest.java')],check=True)
subprocess.run([str(java/('java'+suffix)),'-cp',str(output),'com.conversationlens.ime.FramePixelsTest'],check=True)
subprocess.run([str(java/('javac'+suffix)),'-encoding','UTF-8','-d',str(output),str(root/'native/android/java/com/conversationlens/ime/OcrReview.java'),str(root/'native/android/tests/OcrReviewTest.java')],check=True)
subprocess.run([str(java/('java'+suffix)),'-cp',str(output),'com.conversationlens.ime.OcrReviewTest'],check=True)
subprocess.run([str(java/('javac'+suffix)),'-encoding','UTF-8','-d',str(output),str(root/'native/android/java/com/conversationlens/ime/ImageDecodePolicy.java'),str(root/'native/android/tests/ImageDecodePolicyTest.java')],check=True)
subprocess.run([str(java/('java'+suffix)),'-cp',str(output),'com.conversationlens.ime.ImageDecodePolicyTest'],check=True)
