# Security policy

## Reporting a vulnerability

If GitHub's private vulnerability reporting feature is enabled, use it. Otherwise open a public issue requesting a private reporting channel without including vulnerability details or sensitive evidence. Include the affected version, a minimal reproduction, impact, and a proposed mitigation when available.

Do not place credentials, invitation codes, signing material, private chats, personal data, production database excerpts, or unredacted logs in a public issue. For ordinary bugs that contain no sensitive data, open a regular GitHub issue.

## Supported version

The current `0.18.x` source line receives security fixes. This is a research preview and has not completed physical-device, human-quality, or long-duration production acceptance.

## Deployment boundary

- Keep model credentials on the service and outside source control and Android packages.
- Expose only the authenticated native API through HTTPS. Keep local administration routes on loopback.
- Use a dedicated production signing identity and protect its private key outside the repository.
- Back up identity, budget, deletion, and account data according to the operator's data policy; never use repository history as a backup.

