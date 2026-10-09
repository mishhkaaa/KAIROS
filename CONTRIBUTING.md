# Contributing to KAIROS

Thanks for helping. KAIROS is built by four people in parallel through one shared contract, so the rules below are
what keep everyone's work merging cleanly. The full version is section 7 of `PROJECT.md`;
`AGENTS.md` has the same rules for coding agents.

## Workflow

1. **Branch from `main`** as `a/…`, `b/…`, `c/…`, `d/…` (or `<your-name>/…`), and rebase on `main` often.
2. **Small commits, one logical change each**, with an area prefix: `p1:` kernel and execution, `p2:` knowledge and
   console, `p3:` agents and models, `p4:` platform, data and scripts, `ui:`, `mobile:`, `docs:`, `contract:`. Add
   `-fix` for fixes (`p1-fix:`).
3. **Before every push**, all of these pass:
   ```bash
   uv run pytest -q
   uvx ruff check .
   npm --prefix apps/web run lint && npm --prefix apps/web test && npm --prefix apps/web run build   # web changes
   npm --prefix apps/mobile run typecheck && npm --prefix apps/mobile run contrast                    # phone changes
   ```
   Never force-push. Never skip hooks.
4. **The demo is sacred.** Anything that touches retrieval, prompts, the planner, agents, policies or the knowledge
   bundle must keep the scored scenarios at 8/8 on real models:
   `uv run python scripts/demo_run.py run --auto-approve --check-story [--scenario zeus|vendors|multitool]`.
5. Open a pull request against `main`; a maintainer merges after checking it on the demo machine.

## Changing the contract (`shared/`)

- Put contract changes on their own `contract/<topic>` branch: the schema, a `CONTRACT_VERSION` bump in
  `shared/python/kairos_contracts/__init__.py`, then regenerate:
  ```bash
  uv run kairos-export-contracts
  npm --prefix shared/ts run generate
  ```
- Update `.env.example` and `shared/catalogs/*` with it, and keep the mock gateway's routes equal to the real
  gateway's (a test checks it).
- Never hand-edit generated files: `shared/schemas/`, `shared/api/openapi.json`, `shared/fixtures/json/`,
  `shared/ts/src/kairos.d.ts`, `shared/ts/src/constants.ts`, `uv.lock`.

## Code style

- **Python 3.12**: type hints, Pydantic v2, async services, line length 130, `logging.getLogger("kairos.<pkg>.<mod>")`
  and no `print` in libraries. Tests are plain functions. Comments explain *why*. `ruff` is the linter.
- **Structure**: packages import each other only through `kairos_contracts`; agents act only through `ctx`; every
  action that changes the world goes through `ctx.syscall()`; retrieved text is data, never instructions; errors are
  `KairosError` with codes from `shared/catalogs/errors.yaml`.
- **Web**: design tokens only (no hard-coded colours), container queries inside apps, both themes, WCAG AA contrast.
- **Phone**: colours from `src/theme.ts`; `npm run contrast` must pass.
- **Docs and README**: plain, direct English and no emojis.

## Secrets

OAuth client secrets, connector tokens, the vault key and session tokens never go into the repository, events, the
audit journal or logs. Keep them in `.env` (git-ignored) or the vault. Report security issues privately: see
`SECURITY.md`.

## License

By contributing you agree that your contributions are licensed under the MIT License (`LICENSE`).
