# features/dashboard — Owner D

Next.js (App Router) + Tailwind split-screen UI. Spec: `docs/SPEC.md` §4.5.

- Left: chat, quote cards (price vs. Viator, savings, verified badge), policy sliders, "Book itinerary".
- Right: live inspector of `InspectorEvent`s (blocked = big red), 2-of-2 signer status, explorer links, balance & savings.
- Demo buttons: Simulate Malicious Upsell / Simulate Rainstorm at 2 PM / Reset.
- Types: import from `contracts/ts/api.ts`. Mock mode `NEXT_PUBLIC_USE_MOCKS=1` replays `contracts/fixtures/events.json`.

## Getting started
`pnpm create next-app@latest . --ts --tailwind --app` inside this folder, then add a `@contracts/*` path alias to `../../contracts/ts/*`.
