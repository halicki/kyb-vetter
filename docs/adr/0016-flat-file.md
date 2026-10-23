# ADR-0016: Daily MF flat file as the primary source for account checks

Status: Accepted (2026-10-23)

## Context

The white-list `check` endpoint allows 5 000 calls per day per IP. The
ministry also publishes, every day, a "flat file": SHA-512 digests of every
(date, NIP, account) pair of active and exempt taxpayers, plus bank masks for
virtual accounts, meant for bulk verification without quota. Facts verified
on 2026-10-23 against the specification (edition 2026-09-07) and the real
file: `https://wykazpodatnikowvat.mf.gov.pl/plikplaski/YYYYMMDD.7z` (~250 MB
7z: 500 MB JSON + `<date>.json.sha512sum` sidecar), 3.33 M active and 0.35 M
exempt digests, 1 506 masks, digests sorted ascending, 30 days of history,
publication around 22:10 UTC the evening before the file's date. Digest =
SHA-512 re-applied 5 000 times to the lowercase hex text; both official test
vectors and the owner's own company pass.

## Decision

- **Compact index in object storage, not rows in Postgres.** The worker
  reduces each digest to its 16-byte prefix (unique in practice; collision
  odds ~1e-26) and stores the sorted prefixes as two blocks plus the masks in
  a self-describing binary (`KVFF1`), ~60 MB per day, under
  `flatfile/<date>.idx` with a `flatfile/latest.json` manifest. Neon stays
  small; lookups are binary searches in memory.
- **Worker = Cloud Run job + Cloud Scheduler** (01:15 and 05:15 Europe/Warsaw;
  the second run is the retry for a late publication). Steps: download
  (streaming), extract (py7zr), verify the sidecar SHA-512, stream-parse with
  ijson, publish index then manifest. Idempotent: skips when `latest.json`
  already names that day. Exit codes: 0 ok, 3 not published yet, 1 error.
- **Service side.** `FlatFileProvider` loads the manifest at most every 15
  minutes and swaps the index when the date changes. `check_bank_account`
  (without an explicit date) asks the index first: the plain pair, then every
  mask of the account's bank, active before exempt. A hit answers offline
  (`via = flat_file`, no quota, receipt with the file's SHA-512 bound to the
  matched digest). A miss is **not** conclusive (the specification says so),
  so it falls back to the live API and adds `FLAT_FILE_MISS`. An explicit
  `date` always uses the API: the file describes one day only.
- **Blob store port** (`memory`, local directory, GCS) chosen by
  `APP_FLATFILE_BUCKET` / `APP_FLATFILE_DIR`; the GCS implementation is
  exercised by the deployed job and a `live` test, not by unit tests.
- Service memory raised to 1 GiB for the in-memory index.
- **Build note.** py7zr's codecs (`pybcj`, `pyppmd`, `inflate64`) publish no
  cp315 wheels yet, so the image's builder stage installs `gcc` and compiles
  them; the runtime stage stays slim. This is the first exception to the
  "wheels for every dependency" check in ADR-0002; a Python 3.14 fallback was
  considered unnecessary (the owner allowed it) because the build works.

## Consequences

- Positive account checks no longer consume the 5 000/day quota; the quota
  guard still protects negatives and explicit-date checks.
- The index is as fresh as the last successful job; `/health` reports the
  loaded date. A stale index (job failures) degrades to the API path.
- NIP-only digests (taxpayers without accounts) are in the file and could
  serve VAT-status checks without quota; not used yet (see problems).
- Local runs: `APP_FLATFILE_DIR` + `python -m kyb_vetter_worker flatfile`
  build the index from the real file in ~2 minutes and ~1.3 GB RSS.
