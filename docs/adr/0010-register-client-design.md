# ADR-0010: Register client design

Status: Accepted (2026-10-22)

## Context

The white list and KRS are the only data sources in the MVP. Both are
unauthenticated public APIs with per-IP quotas (ADR-0009; KRS about two
requests per second, from secondary sources), both return data about natural
persons (representatives, board members), and every verification must later be
provable in an audit trail (SPEC: `requestId`, timestamp, SHA-256 of the
response).

## Decision

- **Validate locally before any request.** NIP, REGON, NRB and KRS are
  normalised and checksum-checked in `kyb_vetter_core.identifiers`; a bad
  identifier raises `Invalid*Error` and never reaches the network. Sources:
  pl.wikipedia NIP/REGON articles (weights verified against published
  examples and ORLEN's NIP), ISO 13616 mod-97 for NRB with the `PL` prefix
  (verified against the Wikipedia example account). KRS has no check digit;
  shorter numbers are zero-padded to ten digits, as the API itself does.
- **Injected `httpx.AsyncClient`.** Clients hold no connection state; the
  caller owns one pool per process. `respx` mocks the transport in tests.
- **No automatic retries against the white list**, because a retry costs
  quota and a blocked IP blocks every user of the hosted service. The single
  exception is `WL-195` ("data refreshed, repeat the query"), retried exactly
  once. KRS retries once on transport failures and 5xx only.
- **Error mapping** from `WL-xxx` codes and HTTP statuses to a small domain
  hierarchy under `RegistryError` (`DailyLimitExceededError`,
  `RemoteValidationError`, `InvalidDateError`, `RegistryUpdatingError`,
  `RegistryUnavailableError`, `NotFoundError`, ...). Batch calls never raise
  for one bad identifier; per-identifier errors travel in
  `VatBatchResult.errors`.
- **`RegistryReceipt` on every result**: `source`, `request_id` (white list
  only; KRS issues none), `request_datetime` (registry clock for the white
  list, our UTC clock for KRS), `queried_date` and `response_sha256` of the
  raw body. The audit log in M3 stores receipts verbatim.
- **Data minimisation.** PESEL numbers are dropped at parse time. From KRS
  only the masked names from `sklad` (board) are kept, with role and
  suspension flag; free-text fields such as `rodzajProkury`, which were found
  to contain unmasked names and PESELs, are never copied into models.
- **Query date defaults to today in Europe/Warsaw**, because the registry
  answers "as of a day" in Polish local time.

## Alternatives considered

- Generating clients from the Swagger file - rejected: the generated models
  would carry PESELs and raw shapes into the domain; the hand-written surface
  is four calls.
- A generic retry/backoff layer (tenacity) - rejected for the white list
  (quota), unnecessary for KRS at our volumes.

## Consequences

- Clients are stateless, so caching and quota accounting are a separate
  service layer (M3), keyed by `(nip, queried_date)` and `(krs, as_of)`.
- `tzdata` must be present in the Cloud Run image (M4) for `Europe/Warsaw`.
- Live checks against the MF test host and KRS live in `tests/live`, marked
  `live`, excluded by default and run by hand.
