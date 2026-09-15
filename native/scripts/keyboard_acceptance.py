"""Read-only binding of current synthetic UI evidence and separate release artifacts.

No device, service, model call, signing or endpoint override is performed here.
Debug UI PASS never means that the HTTPS release APK was exercised on a device.
"""
import hashlib
import json
from pathlib import Path
import re
import zipfile

ROOT = Path(__file__).resolve().parents[2]
REQUIRED_CHECKS = {'normal_nine_key', 'normal_full_pinyin', 'keyboard_customer_create_select',
                   'internal_editor_isolation', 'profile_source_date_observations',
                   'opening_edit_exact_confirmed_insert', 'switch_customer_revokes_old_draft',
                   'new_to_maintain_list', 'customer_memory_panel'}
CONTINUATION_CHECKS = {'explicit_enable_does_not_submit', 'pending_input_and_duplicate_touch_are_blocked',
                       'first_round_exact_approved_payload', 'duplicate_round_has_no_new_model_calls',
                       'next_fragment_without_insertion_unlocks', 'second_round_exact_approved_accumulation',
                       'confirmed_insertion_keeps_current_maintenance', 'stop_clears_temporary_context',
                       'restart_does_not_reuse_stopped_history', 'customer_switch_does_not_mix_context'}
CAPTURE_CHECKS = {'owned_customer_and_local_drafts',
                  'notification_denial_blocks_capture_and_restores_drafts',
                  'projection_cancel_restores_unapproved_drafts', 'explicit_full_screen_system_consent',
                  'returned_keyboard_frame_preview_and_renewed_approval',
                  'capture_service_and_projection_ended', 'discard_keeps_drafts_and_never_calls_models'}
SUITES = {'first': {'directory': 'keyboard-first-qa', 'script': 'keyboard_first_qa.py', 'checks': REQUIRED_CHECKS},
          'continuation': {'directory': 'keyboard-continuation-qa', 'script': 'keyboard_continuation_qa.py', 'checks': CONTINUATION_CHECKS},
          'capture': {'directory': 'keyboard-capture-qa', 'script': 'keyboard_capture_qa.py', 'checks': CAPTURE_CHECKS}}
DEFERRED_LIFECYCLE = ['keyboard_rotation_and_large_font_draft_lifecycle',
                      'keyboard_offline_recovery_and_session_disconnect',
                      'keyboard_image_picker_cancel_return_and_expiry']


def sha256(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def read_bounded_json(path):
    path = Path(path)
    if path.stat().st_size > 2_000_000:
        raise ValueError('Acceptance receipt exceeds the bounded file size')
    return json.loads(path.read_text(encoding='utf-8'))


def applicable_keyboard_suites(api, *, require_complete=False):
    if int(api) not in (26, 34, 36):
        raise ValueError('Unsupported keyboard acceptance API')
    if int(api) < 34:
        if require_complete:
            raise ValueError('Delivery requires API34+ capture acceptance; API26 capture is untested')
        return ('first', 'continuation')
    return ('first', 'continuation', 'capture')


def bind_keyboard_receipt(log, apk, started_at, api, avd, *, root=ROOT, suite='first'):
    """Only accept this invocation's complete receipt for the exact debug APK."""
    root = Path(root).resolve()
    if suite not in applicable_keyboard_suites(api):
        raise ValueError('Keyboard suite is not applicable to this API')
    spec = SUITES[suite]
    log = Path(log).resolve()
    if not log.is_relative_to(root) or log.stat().st_size > 2_000_000:
        raise ValueError('Keyboard QA log is outside the project or exceeds its bound')
    lines = log.read_text(encoding='utf-8').splitlines()
    if not lines:
        raise ValueError('Keyboard QA did not produce a receipt pointer')
    report_path = Path(lines[-1].strip()).resolve()
    permitted = (root/'output'/spec['directory']).resolve()
    if not report_path.is_relative_to(permitted) or report_path.name != 'report.json':
        raise ValueError('Keyboard QA receipt is outside the current synthetic evidence directory')
    fixture_path = report_path.parent/'fixture-receipt.json'
    for path in (report_path, fixture_path):
        if not path.resolve().is_relative_to(permitted) or path.stat().st_mtime < started_at-1:
            raise ValueError('Keyboard QA evidence is stale or escaped its evidence directory')
    report = read_bounded_json(report_path)
    fixture = read_bounded_json(fixture_path)
    checks = report.get('checks')
    if report.get('status') != 'PASS' or not isinstance(checks, dict) or not spec['checks'].issubset(checks) or any(value != 'PASS' for value in checks.values()):
        raise ValueError('Keyboard QA has failed, missing or unexecuted checks')
    if suite != 'first' and report.get('suite') != 'keyboard-'+suite:
        raise ValueError('Keyboard QA receipt belongs to another suite')
    if (report.get('synthetic') is not True or report.get('realPhone') is not False
            or report.get('realModel') is not False or report.get('realTouches') is not True
            or report.get('protectedScreensCaptured') is not False or report.get('cleanupErrors') != []):
        raise ValueError('Keyboard QA synthetic/touch/privacy/cleanup scope is not proven')
    if (report.get('serial') != 'emulator-5556' or str(report.get('api')) != str(api)
            or report.get('avd') != avd or not re.fullmatch(r'LensPreview(?:Api\d+)?', avd)):
        raise ValueError('Keyboard QA target does not match this acceptance run')
    if report.get('installedVersionName') not in ('0.18.0', '0.18.0-preview') or report.get('installedVersionCode') != 23:
        raise ValueError('Keyboard QA installed version does not match 0.18.0/code23')
    digest = sha256(apk)
    if report.get('apkSha256') != digest:
        raise ValueError('Keyboard QA belongs to a different APK')
    with zipfile.ZipFile(apk) as archive:
        if json.loads(archive.read('assets/cloud-config.json')).get('endpoint') != 'http://127.0.0.1:4317':
            raise ValueError('Synthetic keyboard evidence requires the loopback test APK')
    if (fixture.get('status') != 'STOPPED' or fixture.get('synthetic') is not True
            or fixture.get('realProviderCalls') != 0 or fixture.get('temporaryDataRemoved') is not True):
        raise ValueError('Owned fake provider and temporary-data cleanup were not confirmed')
    if suite == 'capture':
        choices = report.get('notificationDialogChoices', [])
        if (report.get('notificationPermissionRestored') is not True
                or report.get('initialNotificationPermissionGranted') is not False
                or [choice.get('allowed') for choice in choices] != [False, True]
                or any(choice.get('actualSystemDialog') is not True for choice in choices)
                or report.get('pixelFilesWritten') is not False or report.get('ocrRequested') is not False
                or report.get('mockProviderCalls') != 0 or report.get('realProviderCalls') != 0 or fixture.get('calls') != []
                or report.get('systemCaptureArea', {}).get('fullScreenVerifiedBeforeStart') is not True):
            raise ValueError('Capture consent/full-screen/no-model/cleanup boundary is not proven')
        lifecycle = report.get('captureLifecycle', {})
        for phase in ('before-first-capture', 'after-notification-denial', 'after-projection-cancel', 'after-preview', 'after-discard'):
            state = lifecycle.get(phase, {})
            if state.get('captureServiceRecords') != [] or state.get('projectionExplicitlyNull') is not True:
                raise ValueError('Capture service and projection teardown are not proven')
        if (report.get('previewEvidence', {}).get('insideOriginalKeyboard') is not True
                or report.get('previewEvidence', {}).get('imageViews') != 1):
            raise ValueError('Capture preview did not return to the original keyboard')
    if suite == 'continuation':
        pending = report.get('pendingSpinnerTouch', {})
        calls = fixture.get('calls', [])
        inputs = ['对方：hello', '对方：hello\n\n对方：thanks', '对方：fresh', '对方：other']
        if (pending.get('actualTouch') is not True or pending.get('goalStillLockedDuringRequest') is not True
                or pending.get('popupOpened') is not False
                or report.get('observedSyntheticProviderCalls') != 8 or len(calls) != 8
                or report.get('observedApprovedModelPayloads') != inputs
                or [call.get('chat') for call in calls if call.get('judge') is False] != inputs
                or [call.get('chat') for call in calls if call.get('judge') is True] != inputs
                or any(call.get('taskType') != 'REPLY' or call.get('goal') != '自然接话' for call in calls)):
            raise ValueError('Continuation pending-touch/provider-call evidence is incomplete')
    return {'status': 'PASS', 'scope': 'loopback-debug-keyboard-ui', 'suite': suite,
            'log': log.relative_to(root).as_posix(), 'logSha256': sha256(log), 'startedAt': started_at,
            'report': report_path.relative_to(root).as_posix(), 'reportSha256': sha256(report_path),
            'fixtureReceipt': fixture_path.relative_to(root).as_posix(), 'fixtureReceiptSha256': sha256(fixture_path),
            'testedApkSha256': digest, 'api': str(api), 'avd': avd, 'checks': sorted(checks),
            'releaseApkRuntimeAccepted': False, 'qualityAccepted': False, 'productionReady': False}


def aggregate_keyboard_receipts(bindings, api, avd, *, require_complete=False):
    required = applicable_keyboard_suites(api, require_complete=require_complete)
    if not isinstance(bindings, dict) or set(bindings) != set(required):
        raise ValueError('Mandatory keyboard suite evidence is missing or inapplicable')
    digests = set()
    for name, bound in bindings.items():
        if (bound.get('status') != 'PASS' or bound.get('suite') != name or bound.get('api') != str(api)
                or bound.get('avd') != avd or bound.get('releaseApkRuntimeAccepted') is not False
                or bound.get('qualityAccepted') is not False or bound.get('productionReady') is not False):
            raise ValueError('Keyboard suite evidence scope or target is inconsistent')
        digests.add(bound.get('testedApkSha256'))
    if len(digests) != 1 or not re.fullmatch(r'[0-9a-f]{64}', next(iter(digests)) or ''):
        raise ValueError('Keyboard suites must exercise the same exact debug APK')
    complete = 'capture' in bindings
    return {'status': 'PASS' if complete else 'PASS_APPLICABLE_ONLY', 'scope': 'loopback-debug-keyboard-ui',
            'suites': bindings, 'api': str(api), 'avd': avd, 'testedApkSha256': next(iter(digests)),
            'mandatoryKeyboardSuitesComplete': complete,
            'captureAcceptance': 'PASS' if complete else 'NOT_APPLICABLE_API26_SCRIPT_NOT_IMPLEMENTED',
            'releaseApkRuntimeAccepted': False, 'qualityAccepted': False, 'productionReady': False}


def revalidate_keyboard_bundle(bundle, apk, api, avd, *, root=ROOT):
    """Signing may only reuse unchanged reports from the fully accepted prepare."""
    root = Path(root).resolve()
    if not isinstance(bundle, dict) or not isinstance(bundle.get('suites'), dict):
        raise ValueError('Prepared delivery lacks mandatory keyboard suite evidence')
    current = {}
    for name, bound in bundle['suites'].items():
        if name not in SUITES or not isinstance(bound, dict) or not isinstance(bound.get('startedAt'), (int, float)):
            raise ValueError('Prepared keyboard suite binding is invalid')
        log = root/bound.get('log', '')
        current[name] = bind_keyboard_receipt(log, apk, bound['startedAt'], api, avd, root=root, suite=name)
    checked = aggregate_keyboard_receipts(current, api, avd, require_complete=True)
    if checked != bundle:
        raise ValueError('Prepared keyboard evidence changed; prepare again')
    return checked


def validate_prepared_release(receipt, endpoint, *, root=ROOT):
    """Bind the separate unsigned, dual-ABI HTTPS artifact without executing it."""
    if (receipt.get('apk') != 'conversation-lens-0.18.0-cloud-unsigned.apk'
            or receipt.get('version') != '0.18.0' or receipt.get('versionCode') != 23
            or receipt.get('releaseSigned') is not False or receipt.get('cloudEndpoint') != endpoint
            or sorted(receipt.get('abis', [])) != ['arm64-v8a', 'x86_64']):
        raise ValueError('Prepared HTTPS release identity or required dual-ABI contract changed')
    if not endpoint.startswith('https://'):
        raise ValueError('Release verification cannot reuse the loopback synthetic endpoint')
    apk = Path(root)/'output/native'/receipt['apk']
    digest = sha256(apk)
    if receipt.get('sha256') != digest:
        raise ValueError('Prepared release APK hash changed')
    with zipfile.ZipFile(apk) as archive:
        if json.loads(archive.read('assets/cloud-config.json')).get('endpoint') != endpoint:
            raise ValueError('Prepared release APK embeds a different endpoint')
        for abi in ('arm64-v8a', 'x86_64'):
            for library in ('liblens_rime.so', 'libc++_shared.so'):
                if f'lib/{abi}/{library}' not in archive.namelist():
                    raise ValueError('Prepared release is missing a required ABI library')
    return {'status': 'PASS', 'scope': 'unsigned-release-identity-endpoint-and-dual-abi',
            'apkSha256': digest, 'endpoint': endpoint, 'abis': ['arm64-v8a', 'x86_64'],
            'signatureVerified': False, 'releaseApkRuntimeAccepted': False}
