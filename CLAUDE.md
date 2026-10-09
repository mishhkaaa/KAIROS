@AGENTS.md

## Claude Code specifics
- **Set your role once:** create `CLAUDE.local.md` (gitignored) in the repo root containing one line, e.g. `@shared/services/P1-kernel-execution.md` or `@shared/services/P2-knowledge-console.md`. Claude then always knows your split, scope and task list.
- Work milestone by milestone from your team doc. A good prompt: *"Do task T5 from my team doc. Write the tests first, then implement until `uv run pytest kernel/tests -rs` is green."*
- Before editing a file, check its owner (AGENTS.md table or the file's `Owner:` docstring line). If it isn't yours, propose the change instead of making it.
- Prefer small commits per task on `p<N>/<topic>` branches. Never commit to `main` directly, never skip hooks, and never force-push.
- When a contract change is needed, stop and draft it: the exact schema/interface diff plus who is affected. The team reviews it before any code depends on it.
