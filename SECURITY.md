# Security policy

## Supported versions

Keel does not yet cut releases — `CHANGELOG.md` has one `[Unreleased]`
section and the template is instantiated from `master`. Until v1.0 ships
(Phase 18), only `master` is supported: fixes land there, not on a matrix of
version branches.

## Reporting a vulnerability

Please use GitHub's [private vulnerability reporting](https://docs.github.com/en/code-security/security-advisories/guidance-on-reporting-and-writing/privately-reporting-a-security-vulnerability)
on this repository (Security tab → **Report a vulnerability**) rather than a
public issue. That opens a private advisory only the maintainer can see
until a fix is ready.

Please include:

- What you found and where (file, endpoint, or flow)
- Steps to reproduce, or a minimal proof of concept
- What you think the impact is (data exposure, privilege escalation, etc.)

## Response time

This is a solo-maintained project. There is no SLA, and "24 hours" would be
a promise this project cannot keep — **best effort** is the honest answer.
In practice: an acknowledgement within a few days, and a fix or mitigation
plan once the report is understood. If you have not heard back after a week,
a follow-up comment on the advisory is welcome.

## Scope

This policy covers the code in this repository. Keel integrates with
third-party services (Stripe, Sentry, PostHog, R2/S3-compatible storage,
OAuth providers) — vulnerabilities in those services belong to their own
security teams, not this repository.
