# Security policy

## Reporting a vulnerability
Do not open a public issue containing exploit details, credentials, customer information or private data. Contact the repository maintainer privately and include the affected route/file, impact and safe reproduction steps. Rotate any exposed secret immediately.

## Operational baseline
Keep dependencies updated, use HTTPS, configure a strong secret key and password hash, store secrets only in hosting environment settings, use shared rate-limit storage for multi-worker deployments, restrict repository/hosting access with MFA, and maintain tested backups. No software can guarantee that a deployed site is breach-proof.
