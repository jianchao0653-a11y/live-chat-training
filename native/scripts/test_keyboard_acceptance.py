"""No-device tests: stale/debug/incomplete evidence must not authorize release."""
import copy
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
import zipfile
from keyboard_acceptance import (REQUIRED_CHECKS, SUITES, bind_keyboard_receipt, sha256, validate_prepared_release,
                                 applicable_keyboard_suites, aggregate_keyboard_receipts, revalidate_keyboard_bundle)


class EvidenceTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='lens-keyboard-evidence-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.native = self.root/'output/native'
        self.native.mkdir(parents=True)
        self.folder = self.root/'output/keyboard-first-qa/current-run'
        self.folder.mkdir(parents=True)
        self.apk = self.native/'conversation-lens-0.18.0-cloud-debug.apk'
        self.write_apk(self.apk, 'http://127.0.0.1:4317')
        self.started = time.time()-2
        self.report = {'status': 'PASS', 'synthetic': True, 'realPhone': False, 'realModel': False,
                       'realTouches': True, 'protectedScreensCaptured': False, 'cleanupErrors': [],
                       'checks': {name: 'PASS' for name in REQUIRED_CHECKS}, 'serial': 'emulator-5556',
                       'api': '36', 'avd': 'LensPreview', 'installedVersionName': '0.18.0-preview',
                       'installedVersionCode': 23, 'apkSha256': sha256(self.apk)}
        self.fixture = {'status': 'STOPPED', 'synthetic': True, 'realProviderCalls': 0, 'temporaryDataRemoved': True}
        self.log = self.root/'run.log'
        self.log.write_text('PASS current-flow\n'+str(self.folder/'report.json')+'\n', encoding='utf-8')

    def write_apk(self, path, endpoint, abis=()):
        with zipfile.ZipFile(path, 'w') as archive:
            archive.writestr('assets/cloud-config.json', json.dumps({'endpoint': endpoint}))
            for abi in abis:
                for library in ('liblens_rime.so', 'libc++_shared.so'):
                    archive.writestr(f'lib/{abi}/{library}', b'synthetic-library')

    def write_receipts(self):
        (self.folder/'report.json').write_text(json.dumps(self.report), encoding='utf-8')
        (self.folder/'fixture-receipt.json').write_text(json.dumps(self.fixture), encoding='utf-8')

    def bind(self):
        self.write_receipts()
        return bind_keyboard_receipt(self.log, self.apk, self.started, 36, 'LensPreview', root=self.root)

    def test_exact_current_run_is_debug_scope_only(self):
        result = self.bind()
        self.assertEqual(result['status'], 'PASS')
        self.assertEqual(result['testedApkSha256'], sha256(self.apk))
        self.assertFalse(result['releaseApkRuntimeAccepted'])
        self.assertFalse(result['qualityAccepted'])
        self.assertFalse(result['productionReady'])

    def test_incomplete_failed_and_future_checks_cannot_pass(self):
        original = copy.deepcopy(self.report)
        for mutation in ('missing', 'failed', 'not_run', 'extra_pending'):
            with self.subTest(mutation=mutation):
                self.report = copy.deepcopy(original)
                if mutation == 'missing':
                    self.report['checks'].pop('customer_memory_panel')
                elif mutation == 'extra_pending':
                    self.report['checks']['new_check'] = 'NOT_RUN'
                else:
                    self.report['checks']['customer_memory_panel'] = 'FAIL' if mutation == 'failed' else 'NOT_RUN'
                with self.assertRaises(ValueError):
                    self.bind()

    def test_old_receipt_cannot_be_relabelled_current(self):
        self.write_receipts()
        os.utime(self.folder/'report.json', (self.started-60, self.started-60))
        with self.assertRaisesRegex(ValueError, 'stale'):
            bind_keyboard_receipt(self.log, self.apk, self.started, 36, 'LensPreview', root=self.root)

    def test_artifact_and_target_mismatches_are_rejected(self):
        original = copy.deepcopy(self.report)
        for key, value in [('apkSha256', '0'*64), ('api', '34'), ('avd', 'OtherAvd'),
                           ('serial', 'emulator-5554'), ('installedVersionName', '0.18.0-preview-other'),
                           ('installedVersionCode', 22)]:
            with self.subTest(key=key):
                self.report = {**copy.deepcopy(original), key: value}
                with self.assertRaises(ValueError):
                    self.bind()

    def test_provider_cleanup_and_touch_scope_are_required(self):
        for key, value in [('status', 'READY'), ('realProviderCalls', 1), ('temporaryDataRemoved', False)]:
            with self.subTest(key=key):
                original = self.fixture.copy()
                self.fixture[key] = value
                with self.assertRaises(ValueError):
                    self.bind()
                self.fixture = original
        self.report['realTouches'] = False
        with self.assertRaises(ValueError):
            self.bind()

    def test_report_pointer_cannot_escape_output(self):
        self.log.write_text(str(self.root/'report.json')+'\n', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'outside'):
            self.bind()

    def test_debug_evidence_cannot_target_https_apk(self):
        self.write_apk(self.apk, 'https://example.invalid')
        self.report['apkSha256'] = sha256(self.apk)
        with self.assertRaisesRegex(ValueError, 'loopback'):
            self.bind()

    def suite_files(self, name, api=36):
        folder = self.root/'output'/SUITES[name]['directory']/'current-run'
        folder.mkdir(parents=True, exist_ok=True)
        report = copy.deepcopy(self.report)
        report.update({'checks': {check: 'PASS' for check in SUITES[name]['checks']},
                       'api': str(api), 'suite': 'keyboard-'+name, 'apkSha256': sha256(self.apk)})
        fixture = copy.deepcopy(self.fixture)
        if name == 'continuation':
            inputs = ['对方：hello', '对方：hello\n\n对方：thanks', '对方：fresh', '对方：other']
            report.update({'observedApprovedModelPayloads': inputs, 'observedSyntheticProviderCalls': 8,
                           'pendingSpinnerTouch': {'actualTouch': True, 'goalStillLockedDuringRequest': True, 'popupOpened': False}})
            fixture['calls'] = [{'taskType': 'REPLY', 'judge': judge, 'goal': '自然接话', 'chat': value}
                                for value in inputs for judge in (False, True)]
        if name == 'capture':
            fixture['calls'] = []
            report.update({'initialNotificationPermissionGranted': False, 'notificationPermissionRestored': True,
                           'notificationDialogChoices': [{'allowed': allowed, 'actualSystemDialog': True} for allowed in (False, True)],
                           'pixelFilesWritten': False, 'ocrRequested': False, 'mockProviderCalls': 0, 'realProviderCalls': 0,
                           'systemCaptureArea': {'fullScreenVerifiedBeforeStart': True},
                           'previewEvidence': {'insideOriginalKeyboard': True, 'imageViews': 1},
                           'captureLifecycle': {phase: {'captureServiceRecords': [], 'projectionExplicitlyNull': True}
                                                for phase in ('before-first-capture', 'after-notification-denial',
                                                              'after-projection-cancel', 'after-preview', 'after-discard')}})
        log = self.root/(name+'-ui.log')
        log.write_text('PASS synthetic-suite\n'+str(folder/'report.json')+'\n', encoding='utf-8')
        return folder, log, report, fixture

    def bound_suite(self, name, api=36, mutation=None):
        folder, log, report, fixture = self.suite_files(name, api)
        if mutation:
            mutation(report, fixture)
        (folder/'report.json').write_text(json.dumps(report), encoding='utf-8')
        (folder/'fixture-receipt.json').write_text(json.dumps(fixture), encoding='utf-8')
        return bind_keyboard_receipt(log, self.apk, self.started, api, 'LensPreview', root=self.root, suite=name)

    def bundle(self, api=36):
        bindings = {name: self.bound_suite(name, api) for name in applicable_keyboard_suites(api)}
        return aggregate_keyboard_receipts(bindings, api, 'LensPreview')

    def test_all_three_suites_are_required_for_complete_prepare_and_sign(self):
        complete = self.bundle()
        self.assertEqual(complete['status'], 'PASS')
        self.assertTrue(complete['mandatoryKeyboardSuitesComplete'])
        self.assertFalse(complete['releaseApkRuntimeAccepted'])
        self.assertEqual(revalidate_keyboard_bundle(complete, self.apk, 36, 'LensPreview', root=self.root), complete)
        for missing in ('continuation', 'capture'):
            with self.subTest(missing=missing):
                bindings = {name: bound for name, bound in complete['suites'].items() if name != missing}
                with self.assertRaisesRegex(ValueError, 'missing'):
                    aggregate_keyboard_receipts(bindings, 36, 'LensPreview', require_complete=True)
        with self.assertRaisesRegex(ValueError, 'lacks'):
            revalidate_keyboard_bundle(complete['suites']['first'], self.apk, 36, 'LensPreview', root=self.root)

    def test_api26_capture_script_is_unimplemented_and_cannot_authorize_delivery(self):
        partial = self.bundle(26)
        self.assertEqual(partial['status'], 'PASS_APPLICABLE_ONLY')
        self.assertFalse(partial['mandatoryKeyboardSuitesComplete'])
        self.assertIn('SCRIPT_NOT_IMPLEMENTED', partial['captureAcceptance'])
        with self.assertRaisesRegex(ValueError, 'API34'):
            applicable_keyboard_suites(26, require_complete=True)
        with self.assertRaisesRegex(ValueError, 'not applicable'):
            self.bound_suite('capture', 26)
        partial.update({'status': 'PASS', 'mandatoryKeyboardSuitesComplete': True})
        with self.assertRaisesRegex(ValueError, 'API34'):
            revalidate_keyboard_bundle(partial, self.apk, 26, 'LensPreview', root=self.root)

    def test_individually_passing_suites_from_different_builds_cannot_mix(self):
        complete = self.bundle()
        complete['suites']['continuation']['testedApkSha256'] = '0'*64
        with self.assertRaisesRegex(ValueError, 'same exact'):
            aggregate_keyboard_receipts(complete['suites'], 36, 'LensPreview', require_complete=True)

    def test_stop_only_capture_receipt_cannot_replace_the_seven_group_suite(self):
        def stop_only(report, _fixture):
            report['checks'] = {'explicit_notification_stop': 'PASS'}
        with self.assertRaisesRegex(ValueError, 'missing'):
            self.bound_suite('capture', mutation=stop_only)

    def test_capture_requires_actual_consent_no_model_and_teardown_evidence(self):
        def no_actual_dialog(report, _fixture):
            report['notificationDialogChoices'][1]['actualSystemDialog'] = False
        def grant_not_restored(report, _fixture):
            report['notificationPermissionRestored'] = False
        def wrong_sharing_area(report, _fixture):
            report['systemCaptureArea']['fullScreenVerifiedBeforeStart'] = False
        def retained_projection(report, _fixture):
            report['captureLifecycle']['after-preview']['projectionExplicitlyNull'] = False
        def auto_model_call(_report, fixture):
            fixture['calls'] = [{'taskType': 'PROFILE'}]
        for mutation in (no_actual_dialog, grant_not_restored, wrong_sharing_area, retained_projection, auto_model_call):
            with self.subTest(mutation=mutation.__name__), self.assertRaises(ValueError):
                self.bound_suite('capture', mutation=mutation)

    def test_continuation_requires_physical_pending_lock_and_exact_approved_inputs(self):
        def no_touch(report, _fixture):
            report['pendingSpinnerTouch']['actualTouch'] = False
        def mixed_customer(_report, fixture):
            fixture['calls'][-1]['chat'] = '对方：unapproved'
        for mutation in (no_touch, mixed_customer):
            with self.subTest(mutation=mutation.__name__), self.assertRaisesRegex(ValueError, 'incomplete'):
                self.bound_suite('continuation', mutation=mutation)

    def test_sign_revalidates_log_report_fixture_and_debug_artifact(self):
        for changed in ('log', 'report', 'fixtureReceipt', 'apk'):
            with self.subTest(changed=changed):
                self.write_apk(self.apk, 'http://127.0.0.1:4317')
                complete = self.bundle()
                if changed == 'apk':
                    with zipfile.ZipFile(self.apk, 'a') as archive:
                        archive.writestr('changed-source-marker', 'new build')
                else:
                    path = self.root/complete['suites']['capture'][changed]
                    if changed == 'log':
                        path.write_text('additional output\n'+path.read_text(encoding='utf-8'), encoding='utf-8')
                    else:
                        value = json.loads(path.read_text(encoding='utf-8'))
                        value['laterEdit'] = True
                        path.write_text(json.dumps(value), encoding='utf-8')
                with self.assertRaises(ValueError):
                    revalidate_keyboard_bundle(complete, self.apk, 36, 'LensPreview', root=self.root)

    def prepared(self, abis=('arm64-v8a', 'x86_64'), embedded='https://example.invalid'):
        path = self.native/'conversation-lens-0.18.0-cloud-unsigned.apk'
        self.write_apk(path, embedded, abis)
        return {'apk': path.name, 'sha256': sha256(path), 'version': '0.18.0', 'versionCode': 23,
                'releaseSigned': False, 'cloudEndpoint': 'https://example.invalid', 'abis': list(abis)}

    def test_release_validation_is_dual_abi_identity_only(self):
        result = validate_prepared_release(self.prepared(), 'https://example.invalid', root=self.root)
        self.assertEqual(result['status'], 'PASS')
        self.assertFalse(result['signatureVerified'])
        self.assertFalse(result['releaseApkRuntimeAccepted'])

    def test_release_rejects_debug_endpoint_and_missing_abi(self):
        for abis, endpoint in [(('x86_64',), 'https://example.invalid'),
                               (('arm64-v8a', 'x86_64'), 'http://127.0.0.1:4317')]:
            with self.subTest(abis=abis, endpoint=endpoint):
                receipt = self.prepared(abis, endpoint)
                with self.assertRaises(ValueError):
                    validate_prepared_release(receipt, 'https://example.invalid', root=self.root)

    def test_release_rejects_changed_artifact(self):
        receipt = self.prepared()
        receipt['sha256'] = '0'*64
        with self.assertRaisesRegex(ValueError, 'hash'):
            validate_prepared_release(receipt, 'https://example.invalid', root=self.root)


def load_tests(loader, tests, _pattern):
    # These pure mock cases also run in the existing local/CI evidence gate.
    # Do not include phase-resume CLI tests here: local_delivery already owns
    # its live delivery lock while invoking this no-device suite.
    from test_local_delivery import SourceReceiptTest, LocalTimeoutTest
    from test_compatibility_qa import CleanupTest
    for case in (SourceReceiptTest, LocalTimeoutTest, CleanupTest):
        tests.addTests(loader.loadTestsFromTestCase(case))
    return tests


if __name__ == '__main__':
    unittest.main()
