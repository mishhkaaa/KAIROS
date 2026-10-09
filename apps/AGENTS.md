# apps/ — owner P2 (web console; mobile is a stretch)
- Talk to the backend ONLY through `web/lib/kairos-client.ts`; types come from `@kairos/contracts` (shared/ts). Never hand-write backend shapes.
- Develop against `uv run kairos-mock-gateway`. It replays the full Apollo run, including the approval pause.
- Brief: shared/services/P2-knowledge-console.md (section "Web console").
