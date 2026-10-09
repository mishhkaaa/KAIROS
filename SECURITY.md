# Security policy

KAIROS governs what AI agents may do with an organization's data, so security reports matter to us. Please report
vulnerabilities privately, never in a public issue, pull request or discussion.

## How to report

Use GitHub's private vulnerability reporting: on the repository, open **Security**, then **Report a vulnerability**
(https://github.com/mishhkaaa/KAIROS/security/advisories/new). Only the maintainers can see the report.

Please include:
- what an attacker can do, and against which component (gateway, kernel, policy engine, sandbox, firewall, identity,
  vault, phone app, KAIROS OS);
- the steps or a proof of concept, and the commit you tested;
- whether it needs a signed-in user, and which role.

We aim to acknowledge a report within 3 working days and to agree on a fix and a disclosure date with you. We credit
reporters in the fix's release notes unless you ask us not to.

## In scope

- Getting around policy, approvals, roles or the audit hash chain (an action that should have needed a person and
  did not, a write that left no audit entry, a viewer who could act).
- Prompt injection that makes an agent act on retrieved text as instructions despite the context firewall.
- Sandbox escape, or a sandbox reaching the network when its spec says none.
- Reading connector tokens out of the vault, or secrets appearing in events, logs or the audit journal.
- Session or sign-in flaws: forged Google tokens accepted, reusable one-time codes, sessions that outlive sign-out.
- SQL that gets past the kernel's statement checks.

## Not in scope

- Dev mode (`KAIROS_AUTH=dev`) trusting the `X-Kairos-User` header: that is its documented purpose. Production uses
  `KAIROS_AUTH=google`.
- The demo data, the mock gateway and the built-in connector mocks.
- Findings that need an attacker who already controls the host machine.

## Supported versions

Only `main` is supported. KAIROS is beta software; see the README's maturity status.
