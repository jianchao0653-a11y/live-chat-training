"""Run bundled OCR on 30 synthetic images with emulator connectivity disabled.

Capability and exact-text quality are reported separately. A capability pass is
never human quality acceptance. Requires matching installed debug/test APKs.
"""
from android_qa import adb, OUT
wifi=adb('shell','settings','get','global','wifi_on')
data=adb('shell','settings','get','global','mobile_data')
try:
    adb('shell','svc','wifi','disable');adb('shell','svc','data','disable')
    result=adb('shell','am','instrument','-w','com.conversationlens.ime.test/com.conversationlens.ime.OcrTestRunner',timeout=180)
    (OUT/'ocr-offline-test.txt').write_text(result,encoding='utf-8')
    print(result)
    if 'offline_capability=PASS' not in result:raise SystemExit('Offline OCR capability failed')
finally:
    if wifi=='1':adb('shell','svc','wifi','enable')
    if data=='1':adb('shell','svc','data','enable')
