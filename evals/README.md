# Deterministic tool evals

Each file in `scenarios/` describes one tool call against mocked registers and
the properties the result must have. They run in the default `pytest` run and
in CI (marker `eval`), with no network and no LLM. Model-in-the-loop evals
(does an agent pick the right tool and read the result correctly?) are a later
milestone.

Scenario format:

```json
{
  "name": "active company with KRS entry",
  "tool": "verify_company",
  "arguments": {"nip": "1234563218"},
  "mocks": [
    {"url": "https://mf.example/api/search/nip/1234563218", "status": 200,
     "fixture": "whitelist/search_found", "patch": {"result.subject.krs": "0000028860"}}
  ],
  "expect": {
    "is_error": false,
    "structured": {"found": true, "vat.status": "active"},
    "warnings": ["VAT_NOT_ACTIVE"],
    "error_contains": "midnight",
    "forbidden_substrings": ["pesel"]
  }
}
```

- `fixture` is relative to `packages/core/tests/fixtures`; `json` may be given inline instead.
- `patch` applies dotted-path overrides to the loaded fixture.
- `structured` compares dotted paths of `structured_content`; `warnings` is the exact list of warning codes.
- Hosts are always `https://mf.example` and `https://krs.example`.
