# Security Policy

## Supported versions

Only the latest commit on `main` receives security fixes.

## Reporting a vulnerability

Please **do not open a public issue**. Report it privately through
[GitHub's private vulnerability reporting](https://github.com/adeelbandesha/langgraph-agent-starterkit/security/advisories/new)
(Security tab → "Report a vulnerability").

Include what you found, how to reproduce it, and the impact you expect. You should get a
reply within 7 days, and a fix or a plan once the report is confirmed.

## Scope

`--execute` runs model-written code on your machine and is documented as **not** a
sandbox (see [Security in the README](README.md#security)). Running untrusted code
without a container is expected behavior, not a vulnerability. Ways around the
documented safeguards are in scope, for example:

- generated code reading API keys or other environment secrets,
- a model-chosen filename escaping `--output-dir`,
- the timeout failing to kill child processes,
- model output injecting terminal formatting.
