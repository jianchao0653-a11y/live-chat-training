# Android source preview

The primary supported development target is Android: minSdk 26, targetSdk 36,
version 0.18.0/code23. Physical-device acceptance is pending. iOS is deferred and
is not included in this source preview.

Follow the [root build instructions](https://github.com/jianchao0653-a11y/live-chat-training/blob/main/README.md). Dependencies are pinned in
`dependencies.lock.json`; Java dependencies are locked and checksum verified under
`android/`. Use JDK 21, SDK/Build Tools 36, NDK 28.2.13676358 and Gradle 8.13.
No real model key is needed to compile or run synthetic tests.

The Android app includes Rime text input, customer selection, user-provided text,
image/screen OCR with manual correction, suggested replies, editing and explicit
insertion. The operator must configure an HTTPS endpoint and a signing identity
for user distribution. Never ship a loopback debug APK as a working phone release.

`python native/scripts/test_policy.py` checks Java policies without a phone.
Instrumentation sources under `android/ocrTest/` check Android behavior on an
isolated synthetic emulator. Device scripts must be reviewed for their declared
AVD and port before execution; do not run them against personal devices.

See [deployment](https://github.com/jianchao0653-a11y/live-chat-training/blob/main/app/DEPLOYMENT.md), [acceptance](https://github.com/jianchao0653-a11y/live-chat-training/blob/main/release/ACCEPTANCE.md),
[recovery](https://github.com/jianchao0653-a11y/live-chat-training/blob/main/release/RECOVERY.md), and [licenses](https://github.com/jianchao0653-a11y/live-chat-training/blob/main/THIRD_PARTY_NOTICES.md).
