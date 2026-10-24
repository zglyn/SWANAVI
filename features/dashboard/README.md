# features/dashboard — Owner D

> **Full spec: [`SPEC.md`](SPEC.md)** — everything you need to build this feature without waiting on anyone.

Next.js (App Router) + Tailwind split-screen UI. Spec: `docs/SPEC.md` §4.5.

- Left: chat, quote cards (price vs. Viator, savings, verified badge), policy sliders, "Book itinerary".
- Right: live inspector of `InspectorEvent`s (blocked = big red), 2-of-2 signer status, explorer links, balance & savings.
- Demo buttons: Simulate Malicious Upsell / Simulate Rainstorm at 2 PM / Reset.
- Types: import from `contracts/ts/api.ts`. Mock mode (default) replays `contracts/fixtures/events.json`.

## Run it

```bash
cd features/dashboard
pnpm install
pnpm dev            # http://localhost:3000 (landing) and /dashboard: mock data by default
NEXT_PUBLIC_USE_MOCKS=0 pnpm dev   # talk to the real gateway at NEXT_PUBLIC_GATEWAY_URL (default :8000)
```

## Layout

- `app/page.tsx`: landing page · `app/dashboard/page.tsx`: the demo
- `lib/client.ts`: `RoamClient` interface; `lib/mock.ts` (in-browser gateway using `contracts/fixtures`), `lib/real.ts` (REST + SSE)
- `lib/useDemo.ts`: all UI state is derived from the `InspectorEvent` stream, so mock and real behave the same
- `components/dashboard/`: policy card, chat, itinerary, inspector
