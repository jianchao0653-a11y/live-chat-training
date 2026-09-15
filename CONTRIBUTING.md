# Contributing

Contributions are welcome when they preserve the project's explicit-consent, account-isolation, and fail-closed behavior.

## Before opening a pull request

1. Use synthetic or authorized, deidentified test data.
2. Keep secrets, private messages, runtime databases, logs, screenshots, APKs, and signing files out of the commit.
3. Add a focused regression check for changes to authentication, isolation, deletion, budget accounting, retry handling, or Android lifecycle behavior.
4. Run the relevant Node, Python, Java policy, and Android checks described in the README.
5. Describe the trigger, previous behavior, new behavior, validation, and any remaining limitation.

## Design constraints

- A user must explicitly approve text before it reaches a remote model.
- The Android IME may insert an edited draft only after the user confirms the person and current input field. It must never send a message.
- Unknown or possibly charged requests must not retry automatically.
- Account, person, host field, and request context changes revoke stale results.
- Deletion and retention fixes must prevent removed data from reappearing after restore.
- UI values use the repository's design-token layers and keep touch targets accessible.

By contributing, you agree that your contribution is licensed under Apache-2.0.

