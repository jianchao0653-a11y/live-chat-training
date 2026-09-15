# Remaining acceptance gates

Source preview and production readiness are separate decisions. Record every
result against a source manifest, APK SHA-256, backend source/version and test
driver version. Keep failures and superseded receipts; never reuse them for a
different binary.

| Gate | Minimal evidence | Current status |
|---|---|---|
| Real Android use | Supported OEM/API/App list; install/login/IME selection; customer switching; input/OCR correction; generation/edit/insert; memory correction/deletion | Pending physical devices |
| Recovery | Drop a create success response, restart and retry same operation; consume ticket then fail host insertion; check draft recovery and no automatic insertion | Backend/panel synthetic checks; full host failure pending |
| Network/upgrade | Wi-Fi/mobile data, offline/timeout/cancel, interrupted response, same-signature upgrade and restart | Pending signed current-version package |
| OCR | Authorized deidentified screenshots, fixed speaker labels, exact text accuracy, correction time and exclusions | Real quality pending |
| PROFILE/OPENING/REPLY | 20–50 authorized samples, two independent human reviewers, source fidelity and no invented first-person facts; task-specific acceptance thresholds | Pending samples/reviewers |
| Pilot | 3 people × 7 days, then a second cohort after fixes; failures and recovery recorded without private prose | Pending participants |
| Disaster recovery | Independent current ledger, deletion replay, spend reconciliation, signing/key recovery and single active writer | Pending operator infrastructure |

Do not submit private chats or credentials in public issues. Supply deidentified
reproductions and aggregate findings. Model self-review and synthetic fixtures
cannot substitute for the human and physical-device gates above.
