---
layout: default
title: Privacy policy
---

# Privacy policy

*Last updated: 2026-10-31. Draft pending the operator's legal review.*

## Who we are

KYB Vetter is operated by **[OPERATOR LEGAL NAME, ADDRESS]** ("we"). Contact:
[support@kybvetter.dev](mailto:support@kybvetter.dev). We are the data controller for the
account and usage data described below.

## What the service does

The service looks up Polish companies in public registers (the Ministry of Finance VAT white
list, the National Court Register KRS, and CEIDG) on your request, through an MCP connector or
a REST API, and keeps a record of each lookup so that you can prove it happened.

## Data we process

**Account identity.** Sign-in is handled by Auth0 (Okta), hosted in the EU. We receive and
store only your Auth0 subject identifier; your e-mail address and login credentials stay with
Auth0 and your identity provider (for example Google).

**Verification history.** For every lookup we store: your subject identifier (or API key
identifier), the company identifier you asked about (NIP, bank account number), the register
data returned (company name, addresses, VAT status, KRS summary), warnings, timestamps and
register receipts. This is the audit trail the service exists for.

**Data about sole traders.** CEIDG entries concern natural persons. They are passed through to
you and never stored.

**Usage counters.** A per-user count of lookups per day, used to enforce daily limits.

**Operational logs and traces.** Request logs with company and account identifiers redacted,
kept by our hosting provider for up to 30 days.

**This website.** Served by GitHub Pages; GitHub may log visitor IP addresses under its own
privacy statement. We set no cookies and run no analytics.

## Why and on what basis

We process account and history data to provide the service you requested (performance of a
contract) and to keep the audit trail that counterparty verification is for. Verification
records are kept for **five full years counted from the end of the year of the lookup**, which
matches the limitation period for Polish tax liabilities; they are then deleted automatically.
Usage counters are deleted after the day they concern. Logs expire after 30 days.

## Where the data lives

Google Cloud (region `europe-west1`, Belgium) runs the service; Neon (Frankfurt, Germany)
hosts the database; Auth0 (EU region) handles sign-in; Cloudflare provides DNS only. The
public registers we query are operated by the Polish Ministry of Finance, the Ministry of
Justice and the Ministry of Development and Technology; they receive the identifiers you look up.

## Your rights

Under the GDPR you may ask for access to, correction or deletion of your data, restriction of
processing, portability, and you may object to processing. Write to
[support@kybvetter.dev](mailto:support@kybvetter.dev). You may also complain to the Polish
supervisory authority (Urząd Ochrony Danych Osobowych, uodo.gov.pl).

Deleting your account removes your identity link; verification records that we must keep for
the retention period above are kept pseudonymised until they expire.

## Changes

We will update this page and the date above when the policy changes.
