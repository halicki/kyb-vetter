# Worker

Batch jobs sharing the MCP image. Today: the daily MF flat file (ADR-0016).

```sh
uv run python -m kyb_vetter_worker flatfile [--date YYYYMMDD] [--force] [--workdir DIR]
```

Downloads `YYYYMMDD.7z` (~250 MB) from `APP_MF_FLATFILE_BASE_URL`, verifies the
published SHA-512 sidecar, streams the 500 MB JSON into a ~60 MB prefix index and
publishes it to the blob store chosen by `APP_FLATFILE_BUCKET` (GCS) or
`APP_FLATFILE_DIR` (local directory). Skips when `flatfile/latest.json` already
names that day. Exit codes: `0` published or skipped, `3` the ministry has not
published that day yet, `1` any other failure (download, integrity, parsing).

In the cloud the job `kyb-vetter-flatfile` runs from Cloud Scheduler at 01:15 and
05:15 Europe/Warsaw; run it by hand with
`gcloud run jobs execute kyb-vetter-flatfile --region europe-west1 --wait`.
