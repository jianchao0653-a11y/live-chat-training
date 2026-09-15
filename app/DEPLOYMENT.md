# Preview deployment

This source is version 0.18.0. It is not a hosted service or a production release.
Use Node.js 24. The native API uses per-account SQLite files; the local web
workspace uses its own separate database. Do not expose the web administration
interface to the internet.

## Local synthetic checks

Run `npm test` from the repository root. These tests create temporary synthetic
databases and model substitutes. They do not need provider credentials.

`npm start` starts the local web workspace. For an account-isolated deployment,
review `app/hosted.mjs`, `app/cloud-admin.mjs`, and the example configuration under
`native/deploy` before supplying operator-owned paths and secrets. Never copy a
developer's running data into a new deployment. Keep the authenticated native API
on loopback and expose it through standard-trust HTTPS only.

Provider calls must remain disabled until prices and budgets have been configured.
The example uses zero monetary allowances. A model generation and independent
review may each incur cost; uncertain failures retain their reservations.

Supply the model credential at runtime through `DASHSCOPE_API_KEY`, or set
`LENS_MODEL_KEY_FILE` to an operator-owned file containing only the credential.
Keep that file outside the repository and restrict it to the service account.
The service does not search the project directory for credentials.

## Data and recovery

Accounts, sessions, spend, deletion and customer-change journals live in
`identity.sqlite`; account data lives under `accounts/`. Preserve them together.
Never restore only an old identity ledger or remove a service lock by hand.
See [full checkpoint and recovery boundaries](https://github.com/jianchao0653-a11y/live-chat-training/blob/main/release/RECOVERY.md).

Original Windows deployment helpers are optional operator tools. They are not
required for offline tests. They must not be used against a production installation
without reviewing their explicit paths and operating procedure.

## Android

Build a debug APK for synthetic testing with the commands in the root README.
For user distribution, configure your own HTTPS root and signing identity. The
result must pass installation, login, IME enablement, OCR review, customer selection,
generation, editing, explicit insertion, restart and same-certificate upgrade on
your supported physical devices. Do not treat the debug loopback package as a
phone-ready release.
