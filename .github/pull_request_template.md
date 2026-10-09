## What
<!-- one or two lines -->

## Split
- [ ] P1 Kernel & Execution · [ ] P2 Knowledge, Memory & Console · [ ] P3 Agents & Models · [ ] P4 Platform, Data & Demo · [ ] shared (contract change)

## Contract change? (only if `shared/` is touched)
- [ ] `CONTRACT_VERSION` bumped
- [ ] `uv run kairos-export-contracts` and `npm --prefix shared/ts run generate` run and committed
- [ ] Fake updated and still passes its contract suite
- [ ] `shared/catalogs/*` and `shared/services/*` updated
- [ ] Breaking? If yes, all four owners approved

## Checks
- [ ] `uv run pytest` green (my contract tests are no longer skipped for what I implemented)
- [ ] `shared/services/<me>.md` status table updated
