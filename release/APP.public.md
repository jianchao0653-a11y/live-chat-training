# Service and local workspace

Run Node.js 24 from the repository root. `npm test` uses isolated synthetic data;
`npm start` starts the local web workspace and writes data under ignored `runtime/`.

The local web workspace manages people, confirmed memories, feedback, explicit
analysis and deletion. It is a separate route from the per-account native API.
Never expose web administration through a public proxy.

For native account hosting, read [deployment](https://github.com/jianchao0653-a11y/live-chat-training/blob/main/app/DEPLOYMENT.md). The source includes
budget enforcement, explicit request identifiers, account isolation, expiring
sessions and insertion tickets. Mobile clients approve supplied text and edit
suggestions before explicit insertion; insertion does not send a message.

See [evaluation tools](https://github.com/jianchao0653-a11y/live-chat-training/blob/main/app/evals/README.md) and [recovery](https://github.com/jianchao0653-a11y/live-chat-training/blob/main/release/RECOVERY.md).
Passing synthetic tests does not establish real OCR or model quality.
