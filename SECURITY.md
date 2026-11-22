# Security Policy

## Supported versions

| Version | Supported |
|---------|-----------|
| 0.2.x   | ✅        |
| < 0.2   | ❌        |

## Reporting a vulnerability

Please **do not open a public issue** for security problems.

Report privately by email to the maintainer (`jds068888@gmail.com`) with:

- a description of the issue and its impact,
- the affected version or commit,
- steps to reproduce, and
- any suggested mitigation.

You can expect an acknowledgement within 7 days. If a fix is warranted, it
will be released on `main` and, when relevant, as a new patch version on PyPI.

## Scope notes

This library reads public datasets (OpenStreetMap, Korean public data APIs)
and runs locally. It does not ship credentials, and API keys are read from
environment variables (see `.env.example`). Vulnerabilities in third-party
dependencies should be reported to those projects first.
