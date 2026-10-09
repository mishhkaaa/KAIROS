# shared/ — THE CONTRACT (owned by all four; changes need review)
- Source of truth: `python/kairos_contracts/` (schema, interfaces, fakes, contract suites, mock gateway, examples, util, errors, wiring).
- GENERATED, never edit by hand: `schemas/`, `api/openapi.json`, `fixtures/json/`, `ts/src/kairos.d.ts`, `ts/src/constants.ts`. Regenerate with `uv run kairos-export-contracts` + `npm --prefix shared/ts run generate`.
- FROZEN test data: `fixtures/okf/`, `fixtures/manifests/`. Everyone's contract tests depend on them.
- Every change: bump `CONTRACT_VERSION`, update the fake so it passes its suite, update `catalogs/` and `services/`, run `uv run pytest shared/python/tests`.
- Prefer additive changes (optional fields with defaults). A rename or removal is breaking and needs all four owners.
