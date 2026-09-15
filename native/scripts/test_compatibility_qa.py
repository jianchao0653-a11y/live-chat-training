"""No-device failures must retain a failed receipt and attempt all owned cleanup."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import compatibility_qa as compatibility


class CleanupTest(unittest.TestCase):
    original = {'size': 'Physical size: 720x1280\nOverride size: 1080x2400',
                'density': 'Physical density: 320', 'fontScale': 'null'}

    def test_first_restore_failure_still_attempts_density_and_font_and_revokes_pass(self):
        calls = []
        def adb(*args):
            calls.append(args)
            if args[1:3] == ('wm', 'size'):
                raise subprocess.CalledProcessError(1, 'synthetic-adb')
        report = {'status': 'PASS'}
        errors = compatibility.restore_display(report, adb, self.original)
        self.assertEqual(len(calls), 3)
        self.assertEqual(calls[1], ('shell', 'wm', 'density', 'reset'))
        self.assertEqual(calls[2], ('shell', 'settings', 'delete', 'system', 'font_scale'))
        self.assertEqual(errors, [{'setting': 'size', 'errorType': 'CalledProcessError'}])
        self.assertEqual(report['status'], 'FAIL')
        self.assertFalse(report['settingsRestorationCommandsSucceeded'])

    def test_successful_restore_does_not_erase_an_earlier_failure(self):
        report = {'status': 'FAIL', 'failureType': 'TimeoutExpired'}
        calls = []
        compatibility.restore_display(report, lambda *args: calls.append(args), {**self.original, 'fontScale': '1.3'})
        self.assertEqual(report['status'], 'FAIL')
        self.assertEqual(report['failureType'], 'TimeoutExpired')
        self.assertEqual(report['cleanupErrors'], [])
        self.assertEqual(calls[-1], ('shell', 'settings', 'put', 'system', 'font_scale', '1.3'))

    def test_child_timeout_is_failed_with_cleanup_unverified_and_display_commands_attempted(self):
        with tempfile.TemporaryDirectory(prefix='lens-compatibility-mock-') as directory:
            root = Path(directory)
            apk = root/'output/native/conversation-lens-0.18.0-cloud-debug.apk'
            apk.parent.mkdir(parents=True)
            apk.write_bytes(b'synthetic artifact; no install')
            calls = []
            def adb(cmd, **_kwargs):
                args = tuple(map(str, cmd[3:]))
                calls.append(args)
                values = {('shell', 'getprop', 'ro.kernel.qemu'): '1',
                          ('shell', 'getprop', 'ro.build.version.sdk'): '36',
                          ('emu', 'avd', 'name'): 'LensPreview\nOK',
                          ('shell', 'wm', 'size'): self.original['size'],
                          ('shell', 'wm', 'density'): self.original['density'],
                          ('shell', 'settings', 'get', 'system', 'font_scale'): 'null'}
                return values.get(args, '')
            with patch.object(compatibility, 'ROOT', root), patch.object(compatibility.sys, 'argv', ['qa', '--api', '36']), \
                    patch.object(compatibility, 'wait_boot'), \
                    patch.object(compatibility.subprocess, 'check_output', side_effect=adb), \
                    patch.object(compatibility.subprocess, 'run', side_effect=subprocess.TimeoutExpired('synthetic-qa', 900)):
                with self.assertRaises(subprocess.TimeoutExpired):
                    compatibility.main()
            receipts = list((root/'output/compatibility').glob('*/report.json'))
            self.assertEqual(len(receipts), 1)
            report = json.loads(receipts[0].read_text(encoding='utf-8'))
            self.assertEqual(report['status'], 'FAIL')
            self.assertEqual(report['timeout']['step'], 'keyboard-first-ui')
            self.assertEqual(report['timeout']['childCleanup'], 'NOT_VERIFIED_AFTER_FORCED_TIMEOUT')
            self.assertEqual(report['cleanupErrors'], [])
            self.assertEqual(calls[-3:], [('shell', 'wm', 'size', '1080x2400'),
                                          ('shell', 'wm', 'density', 'reset'),
                                          ('shell', 'settings', 'delete', 'system', 'font_scale')])


if __name__ == '__main__':
    unittest.main()
