# apps/web: KAIROS console (P2)

Next.js + React + Tailwind + shadcn/ui + React Flow. The console talks to the backend **only** through [`lib/kairos-client.ts`](lib/kairos-client.ts), which is typed by `@kairos/contracts` (`shared/ts`).

## Bootstrap (once)

```bash
cd apps/web
npx create-next-app@latest . --ts --tailwind --app --eslint --src-dir=false --import-alias "@/*"   # keep lib/kairos-client.ts
npm i @xyflow/react
npm i -D @kairos/contracts@file:../../shared/ts
npx shadcn@latest init
cp .env.local.example .env.local
```

## Develop without the backend

```bash
uv run kairos-mock-gateway --speed 4      # from the repo root → http://localhost:8080
npm run dev
```

The mock replays the whole Apollo run: planner spawns specialists, knowledge is retrieved, the firewall flags an injected email, a sandbox starts, and a `jira.write` syscall **pauses for approval**. Approving it through the UI lets the run finish. That gives you every screen's data before the kernel exists.

## Screens (MVP order)
1. Task composer + live timeline (`/ws/events`)
2. Agent process tree (React Flow; nodes coloured by `AgentState`; legal transitions come from `ALLOWED_TRANSITIONS`)
3. Approval center (the demo's key moment)
4. Audit journal (`RunTimeline`)
5. Knowledge explorer (tree + object view + search with scores, provenance and firewall flags)
6. Resource monitor + sandbox live view

Mobile (stretch) reuses `@kairos/contracts` and the same client.
