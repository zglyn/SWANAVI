# Spec: Conversational trip planner (new website design)

> Status: **Draft v0.1**, for review. Applies to `features/dashboard` (UI) and `features/agent` (gateway + planner).
> Builds on the code merged in PR #105 (`claude/integrate-into-dev`). Open questions are in §12.

## 1. Summary
Replace the multi-page form flow (`/plan/new` → attractions → flights → hotels → overview) with **one prompt box in
the middle of the page**, like a search engine. The traveller types where and when they want to go. The AI asks a few
follow-up questions until it knows enough, then proposes a complete trip: **flights, hotels and attractions**. Every item
can be **accepted, modified or rejected**. The whole itinerary is always visible on the existing **Mapbox trip map**.

Visual style: an **Airbnb-inspired** layout (photo-led cards, a list beside a map, a sticky booking summary) with
**search-engine simplicity** on the home page, in a warm colour palette built around the **Swan logo**. Not black and white.

## 2. Goals and non-goals
**Goals**
1. A first-time user can go from an empty page to a full proposed trip by typing, in under 2 minutes, with no forms.
2. The AI asks only for what it's missing, a few questions at a time, and states the assumptions it makes.
3. Every suggestion (flight, hotel, attraction, transfer) has **Accept / Modify / Reject**, and the trip updates live, including the map.
4. Typed changes ("make day 2 more relaxed", "cheaper hotel") work at any time.
5. Reuse what works: the `TripMap` component (Mapbox, with an OpenFreeMap fallback), the trip models (`TravelPackage`,
   `FlightOffer`, `HotelOffer`), and the planner tools (flight search, hotel search, attractions, routing).

**Non-goals (this spec)**
- Payment and the XRPL checkout itself (covered by the payments track; this spec only defines the hand-off to it).
- Account sign-up flows beyond what exists (`/signin`, demo profile).
- Native mobile apps.

## 3. Design direction
### 3.1 Borrow from Airbnb (patterns, not assets)
| Pattern | Where we use it |
|---|---|
| A single prominent **search pill** with generous whitespace | Home prompt box |
| **Photo-led cards**, 4:3 images, 12–16 px radius, title + 1–2 meta lines + price | Hotel, attraction and flight cards |
| **List beside a sticky map**, with card ↔ marker hover linking | Proposal workspace |
| A sticky **"reservation" summary card** with total and primary action | Trip summary + "Book accepted" |
| **Category chips** in a horizontal scroll | Quick replies, filters in the Modify sheet |
| Calm, airy typography; soft shadows instead of borders | Everywhere |

**Do not copy:** Airbnb's name, logo, wordmark, illustrations, its proprietary typeface, its brand colour ("Rausch"
pink/coral), or any of its copy or photos. The product is **Swanavi** with the Swan mark (`components/brand/SwanMark.tsx`).
The page must never look like it *is* Airbnb.

### 3.2 Borrow from a search engine
- The home page is **only** the logo, the prompt box, a few suggestion chips, and a small profile button. No hero copy, no feature sections above the fold.
- The prompt box is centred vertically and horizontally, ~640 px wide on desktop, and focused on load.
- On submit, the box **animates to the bottom** of the conversation view, so the conversation feels like it grows from the prompt.

### 3.3 Visual tokens
**The Swan logo sets the look.** The palette comes from a swan on a lake: white feathers, deep water, an orange beak.
This **replaces the earlier black-and-white direction** (UI epic #41).

| Token | Role | Starting value (tune in `/styleguide`) |
|---|---|---|
| `--swan-feather` | page background | `#FBFAF7` (warm off-white) |
| `--swan-surface` | cards, sheets, prompt box | `#FFFFFF` |
| `--swan-lake` | primary text, primary buttons, **the logo**, map routes | `#14324A` (deep lake blue) |
| `--swan-lake-2` | secondary text | `#4A6275` |
| `--swan-mist` | tints, selected states, chip backgrounds | `#E8F0F5` |
| `--swan-beak` | **one accent:** "Accept", the "Book" button, the active day, map highlight | `#C2410C` (burnt orange; white text passes AA) |
| `--swan-reed` | success ("accepted", "booked") | `#2F6B4F` |
| `--swan-line` | dividers, card borders on hover | `#E4E1DA` |

- **Logo:** the existing `SwanMark` silhouette in `--swan-lake` on light backgrounds and white on dark. An optional
  two-tone version adds a small `--swan-beak` beak, used only at large sizes (home page, favicon, app icon).
- **Accent discipline:** `--swan-beak` is used for **one primary action per screen** plus highlights, never for large areas.
- **Dark mode:** later. Tokens make it possible, but it isn't in scope.
- **Contrast:** every text/background pair must meet WCAG AA. Check the starting values in the styleguide before using them.
- **Type:** one sans-serif family for everything, with large, bold headings in `--swan-lake`. Use mono only for confirmation codes and ledger data.
- **Radius:** 12 px (cards), 16 px (sheets), 999 px (pills, the prompt box).
- **Elevation:** one soft shadow for cards and sheets; a stronger one for the floating prompt box.
- **Spacing:** 8 px grid; card gutters 16–24 px.
- **Imagery:** real photos where we have them (attractions, hotels). Flights use an airline name + route line, not stock photos.

## 4. Information architecture
| Route | Purpose | Replaces |
|---|---|---|
| `/` | Home: the centred prompt | current landing page (marketing content moves to `/about`) |
| `/trip/[id]` | **One page** for the conversation, the proposal workspace and review, switching by phase | `/plan/new`, `/plan/[id]/attractions`, `/plan/[id]/flights`, `/plan/[id]/hotels`, `/plan/[id]/overview`, `/plan/[id]/planning`, `/plan`, `/plan/[id]`, `/plan/[id]/pick` (redirect old URLs to `/trip/[id]`) |
| `/trips` | The user's trips (cards with a map thumbnail) | — |
| `/profile` | Saved preferences, editable (learned from conversations too) | keeps the current page |
| `/about` | The product and guardrail story for judges | content from the current landing page |
| `/demo` | The XRPL/guardrail inspector demo (current `/dashboard`) | `/dashboard` |

Phases of `/trip/[id]`: **`chatting` → `planning` → `proposal` → `review` → `booked`**. The URL doesn't change between phases; the phase comes from the server (§9).

## 5. Screens
### 5.1 Home (`/`)
```
┌──────────────────────────────────────────────────────────────────────────┐
│ (Swan) Swanavi                                         [My trips] (●)    │
│                                                                          │
│                                                                          │
│                         (Swan)  Swanavi                                  │
│        ┌──────────────────────────────────────────────────────────┐      │
│        │  Where do you want to go?                          [ ↑ ] │      │
│        └──────────────────────────────────────────────────────────┘      │
│     [Kyoto in November, 4 days]  [A warm beach week under $2k]           │
│     [Tokyo food trip with a friend]  [Surprise me]                       │
│                                                                          │
└──────────────────────────────────────────────────────────────────────────┘
```
- The placeholder rotates through examples every 4 s (paused while focused or typing; disabled with reduced motion).
- Chips fill the box; they don't submit. Enter or ↑ submits.
- The box accepts long free text ("me and my partner, from SF, 5 days in Kyoto in late Nov, love temples and food, ~$3k").
- Signed-out users can start; they're asked to sign in (or use the demo profile) only before booking.
- On submit: `POST /api/trips {message}` → navigate to `/trip/{id}`, with the box animating into the conversation composer.

### 5.2 Conversation (`/trip/[id]`, phase `chatting`)
```
┌──────────────────────────────────────────────────────────────────────────┐
│ (Swan)                         Kyoto · Nov 14–17 · 2 travellers   (●)    │
│ ┌──────────────────────────────────────────────────────────────────────┐ │
│ │ ✓ Kyoto  ✓ Nov 14–17  ✓ From SFO  ○ Travellers  ○ Budget  ○ Pace   │ │  ← trip brief strip
│ └──────────────────────────────────────────────────────────────────────┘ │
│                      You: Kyoto in late November, 4 days                 │
│   Swan: Lovely season for it. A couple of quick questions:               │
│         How many people are going?   [Just me] [2] [3] [4+]              │
│         Roughly what budget per person?  ━━━━━●━━━━  $1,500              │
│                                                                          │
│                                         [Plan it now with what you have] │
│        ┌──────────────────────────────────────────────────────────┐      │
│        │  Reply…                                            [ ↑ ] │      │
│        └──────────────────────────────────────────────────────────┘      │
└──────────────────────────────────────────────────────────────────────────┘
```
- Messages sit in a centred column (max 720 px). The composer is pinned at the bottom.
- **Brief strip:** the facts gathered so far, as chips. ✓ = known, ○ = still open. Tapping a chip edits that fact inline.
- **Inline controls** inside assistant messages, so users can answer without typing: quick-reply chips, a date-range picker, a traveller stepper, a budget slider, an airport picker, time-of-day chips (outbound/return), and interest tiles. Answering a control sends a structured answer (§9.2) and also shows as a user message.
- **"Plan it now"** appears once the required facts are known (§7.1). It skips the remaining optional questions; the AI states the defaults it uses.
- Assistant replies stream word by word. A typing indicator shows while tools run, with short status lines ("Checking flights from SFO…").

### 5.3 Planning (phase `planning`)
- The conversation stays visible. A progress card shows what the agent is doing, driven by the `plan.tool_call` events that already exist: "Finding flights", "Choosing a hotel near your picks", "Building day 2".
- The map fades in on the right (desktop) or at the top (mobile), showing the destination.
- Target: under 20 s with the live LLM, under 5 s in scripted mode.

### 5.4 Proposal workspace (phase `proposal`): the core screen
```
┌───────────────────────────────────────────────┬──────────────────────────┐
│ Your Kyoto trip · Nov 14–17 · 2 travellers    │                          │
│ ┌───────────────────────────────────────────┐ │                          │
│ │ $2,940 total · 6 accepted · 3 to review   │ │      TripMap (Mapbox)    │
│ │ [Accept all remaining]  [Book accepted →] │ │   flight arc SFO→KIX,    │
│ └───────────────────────────────────────────┘ │   hotel (H), day routes, │
│ Flights                                       │   numbered stops         │
│ ┌ JAL · SFO → KIX · Fri 14 Nov 09:05 → 13:10+1┐│                          │
│ │ Nonstop · 11h · $680  why: your airline,    ││                          │
│ │ lands in the afternoon                      ││    sticky; hover a card  │
│ │            [✓ Accept] [✎ Modify] [✕ Reject] ││    to highlight it       │
│ └─────────────────────────────────────────────┘│                          │
│ Stay                                          │                          │
│ ┌ [photo] Hyatt Place Arashiyama · 3 nights  ┐│                          │
│ │ $180/night · 12 min avg to your stops       ││                          │
│ │            [✓ Accept] [✎ Modify] [✕ Reject] ││                          │
│ └─────────────────────────────────────────────┘│                          │
│ Days   [Fri 14] [Sat 15] [Sun 16] [Mon 17]     │                          │
│  09:30 [photo] Tenryū-ji · 1h · Free   ✓ ✎ ✕   │                          │
│   ↓ walk 8 min                                 │                          │
│  11:00 [photo] Bamboo bike rental · $15 ✓ ✎ ✕  │                          │
│ ┌──────────────────────────────────────────┐   │                          │
│ │ Ask Swan to change anything…       [ ↑ ] │   │                          │
│ └──────────────────────────────────────────┘   │                          │
└───────────────────────────────────────────────┴──────────────────────────┘
```
- **Layout:** the list on the left (~56%, scrolls), the **`TripMap` on the right (sticky, full height)**. On mobile, the map is a collapsible panel at the top (peek height 30% of the screen; tap to expand).
- **Summary card** (sticky at the top of the list): total, savings vs aggregators for Swan merchant items, and counts by status. **Accept all remaining** and **Book accepted** live here.
- **Sections:** Flights (outbound and return), Stay (one card per hotel stay; split stays in order), Days (day tabs, then a timeline of stops with the travel legs between them).
- **The composer stays available** at the bottom for typed changes ("swap day 2 and 3", "add a ramen place for dinner").
  Typed changes produce the same kind of update as the buttons (§8).
- **Map ↔ list linking:**
  - hovering a card highlights its marker (`TripMap` `highlight` prop); clicking a marker scrolls to and highlights its card (`onSelect`)
  - switching day tabs reframes the map to that day (`focus`, `dayLabel`)

### 5.5 Suggestion card states
| State | Look | Actions |
|---|---|---|
| `proposed` | default card, outline marker on the map | Accept · Modify · Reject |
| `accepted` | ✓ badge, solid marker | Undo · Modify |
| `modifying` | card raised, Modify sheet open, alternatives shown as ghost markers | (in the sheet) |
| `rejected` | collapses to one line "Removed: Tenryū-ji · Undo" (attractions), or "Finding another flight…" then replaced (flights and hotels, which are required) | Undo |
| `replaced` | brief highlight + "Updated" label, then behaves as `proposed` | Accept · Modify · Reject |
| `booked` | lock icon + confirmation code | — (changes go through re-planning) |

### 5.6 Modify sheet (right side sheet on desktop, bottom sheet on mobile)
1. **Swan's alternatives:** 3 ranked options as cards, each with "why" chips (existing `FlightOffer.why`, `HotelOffer.why`).
2. **Fine-tune controls** by type:
   - **Flight:** time of day (outbound/return), airline, max stops, cabin, price range
   - **Hotel:** price per night, area (pick on the map), brand, stars, must-haves
   - **Attraction:** time slot, duration, "something similar", "more food / more nature" chips
3. **Free text:** "Make it cheaper", "Closer to Gion".
- Picking an alternative **accepts it** and closes the sheet. Changing a control refreshes the alternatives.
- The map previews the selected alternative (ghost marker plus a dashed route change).

### 5.7 Reject flow
- One tap rejects. An optional reason chip row appears for 5 s: *Too expensive · Not my style · Bad time · Too far · Other*.
- **Flights and hotels** are required, so the AI immediately proposes a replacement (the card shows "Finding another…").
- **Attractions** are removed and the day reflows (later stops shift earlier and travel legs are recomputed). The AI may suggest a filler if a large gap opens.
- Reasons are saved as soft preferences on the profile (e.g. "avoids early flights").

### 5.8 Review & book (phase `review`)
- A checklist of every accepted item, grouped by how it's paid:
  - **Swan merchants** (activities, merchant hotels): paid from the wallet through the XRPL checkout. One button, with the guardrail co-sign shown.
  - **External** (airline, chain hotel): "Book on <provider>" links, or the booking master when available.
- Progress like "3 of 5 booked". Each row shows its status (booked ✓ / failed ✕ with retry / needs your input).
- This reuses the booking route from `docs/handoff/agentcore-gateway-brief.md` (`POST /api/plans/{id}/book`) and the payments track's `POST /api/checkout`.

## 6. Mobile (390 px)
- Home: the same centred prompt; chips wrap to two rows.
- Conversation: full-width messages; the composer sits above the keyboard.
- Proposal: the map as a top panel; cards full width; Accept / Modify / Reject stay as visible buttons (no swipe-only actions); the summary card becomes a sticky bottom bar ("$2,940 · Book accepted").
- Every tap target is at least 44 px. No horizontal scrolling except chip rows.

## 7. Conversation design (AI behaviour)
### 7.1 Facts to gather (`TripRequest`, extended)
| Fact | Required? | Default if skipped (said aloud) |
|---|---|---|
| Destination | **yes** | — |
| Dates, or month + length | **yes** | — |
| Origin | **yes** | profile home airport ("From SFO, right?") |
| Travellers | **yes** | 1 |
| Budget | no | profile budget level |
| Pace | no | profile pace, else "balanced" |
| Interests / must-sees | no | profile interests |
| Flight times (outbound/return windows) | no | "any", avoiding red-eyes if the profile says so |
| Hotel style / area | no | profile hotel preferences |
| How much Swan decides (autonomy) | no | profile `AutonomyDefaults` |

### 7.2 Rules for the AI
- Extract every fact the user already gave before asking anything. Never re-ask a known fact; **confirm** facts taken from the profile instead.
- Ask **at most 2 questions per turn**, most important first, each with an inline control where possible.
- After **at most 4 assistant turns**, or as soon as the required facts are known and the user seems ready, offer to plan. State the assumptions ("I'll assume a mid-range budget and a balanced pace; you can change either later").
- **Never invent prices, times or availability.** Every number shown comes from a tool result (flight search, hotel search, merchant quotes, routing).
- Tone: warm, brief, concrete. No more than ~3 sentences before the controls.
- If the user asks for something outside travel planning, answer briefly and steer back.

### 7.3 How it's built
- The agent is the **Strands planner** (ticket #4 / #63), extended with a conversation phase. It uses the existing tools (`get_transport_profile`, `search_attractions`, `get_weather`, `get_travel_matrix`, `optimize_route`, `search_flights`, `search_hotels`) and the merchant directory over MCP.
- Each assistant turn returns structured output alongside the streamed text (§9.2), so the UI can render controls and update the brief strip without parsing prose.
- Proposals still go through `propose_itinerary` validation. Modify and reject trigger a **targeted** replan of the affected item and the stops after it, not a full re-plan.
- A **scripted mode** (`ROAM_SCRIPTED_AGENT=1`) replays a fixed Kyoto conversation, so the demo never depends on the LLM.

## 8. One update mechanism for buttons and typed changes
Every change, whether from a button, the Modify sheet or typed text, becomes the same server-side operation:
```
SuggestionAction { suggestion_id, action: accept | reject | modify | undo,
                   reason?, alternative_id?, constraints?, text? }
```
- Typed changes are interpreted by the AI into one or more `SuggestionAction`s, plus itinerary operations (`move_stop`, `swap_days`, `add_stop`).
- The server applies them, re-validates the itinerary, and emits `suggestion.updated` / `itinerary.reflowed` events (§9.3). The UI only renders state; it never computes the itinerary itself.
- This replaces today's `PlanRevision {actions: accept | swap | remove}` and stays compatible with it: `swap` = `modify` with an alternative, `remove` = `reject`.

## 9. API and data (changes to `contracts/`)
These are additive. Python models and the TS mirror change together in one PR.

### 9.1 Models
- `TripConversation`: `trip_id`, `phase` (`chatting | planning | proposal | review | booked`), `messages: list[ChatMessage]`, `brief: TripRequest` (partial while chatting), `missing: list[str]`
- `ChatMessage`: `id`, `role` (`user | assistant`), `text`, `controls: list[Control]`, `answers?`, `created_at`
- `Control`: `slot` (`travellers | dates | budget | origin | pace | interests | outbound_window | return_window | …`), `type` (`chips | date_range | stepper | slider | airport | tiles`), `options?`, `min?/max?`, `value?`
- `Suggestion`: `id`, `kind` (`flight | hotel | attraction | transfer`), `status` (§5.5), `item` (`FlightOffer | HotelStay | Stop`), `why: list[str]`, `alternatives_available: bool`, `required: bool`
- `Proposal`: `trip_id`, `package: TravelPackage` (unchanged), `suggestions: list[Suggestion]`, `totals`
- `SuggestionAction`: as in §8

### 9.2 Gateway routes
| Method | Path | Body → Response |
|---|---|---|
| POST | `/api/trips` | `{message}` → `{trip_id}` (starts the conversation) |
| GET | `/api/trips/{id}` | → `TripConversation` + `Proposal?` |
| POST | `/api/trips/{id}/messages` | `{text}` or `{answer: {slot, value}}` → `{ok}`; the reply streams as events |
| POST | `/api/trips/{id}/plan` | → `{ok}` ("Plan it now") |
| GET | `/api/trips/{id}/suggestions/{sid}/alternatives` | `?constraints=…` → `list[Suggestion]` |
| POST | `/api/trips/{id}/suggestions/{sid}` | `SuggestionAction` → `{ok}` |
| POST | `/api/trips/{id}/accept-all` | → `{ok}` |
| POST | `/api/trips/{id}/book` | → `{ok}` (hands off to `/api/plans/{id}/book` + `/api/checkout`) |

### 9.3 Events (add to `EVENT_TYPES`)
`chat.delta` (streamed text chunk), `chat.message` (final message with controls), `brief.updated`, `plan.tool_call`
(exists), `proposal.ready`, `suggestion.updated`, `itinerary.reflowed`, plus the booking events from the AgentCore brief.

### 9.4 Mock mode
`contracts/fixtures/conversation_kyoto.json`: a scripted 3-turn conversation (destination + dates → travellers +
budget → "Plan it now") that ends in `package_kyoto.json` wrapped as a `Proposal`, plus scripted results for one
accept, one modify (hotel → cheaper alternative) and one reject (an attraction removed, the day reflowed). The dashboard runs fully on this with `NEXT_PUBLIC_USE_MOCKS=1`.

## 10. Reuse and retire
| Keep | Change | Retire |
|---|---|---|
| `components/map3d/*` (`TripMap`: arcs, stops, day focus, highlight, `onSelect`, 2D/3D, Mapbox token + OpenFreeMap fallback) | Marker states for proposed / accepted / ghost (alternatives) | — |
| `components/swan/Photo.tsx`, `SwanMark` | `Shell.tsx` gets the new header (logo, trip title, profile) | `BrandPrompt.tsx`, `ChoiceLayout.tsx` once their screens are gone |
| `roam_agent/autopilot.py`, `flight_search`, `hotel_search`, `routing`, `attractions` | Autopilot exposes per-item alternatives and targeted replans | — |
| `/profile`, `/signin`, demo profile | Profile learns from conversation answers and reject reasons | `/onboarding` becomes optional (the conversation asks instead) |
| `/dashboard` | Moves to `/demo` | `/plan/*` routes (redirect to `/trip/[id]`) |

## 11. Accessibility and quality
- All actions are reachable by keyboard; the Modify sheet traps focus and closes with Esc; status changes are announced (`aria-live`).
- Every map state has a list equivalent (the list *is* the accessible view of the map).
- Status never relies on colour alone: icons + text (✓ accepted, ✕ rejected, ✎ modifying), even with the colour palette.
- Animations respect `prefers-reduced-motion` (no prompt-to-composer animation, no map fly-throughs).
- Performance: home page interactive in under 1.5 s; the map loads lazily only on `/trip/[id]`.

## 12. Open questions
1. ~~Colour~~ **Decided:** a Swan-logo palette (§3.3), not black and white.
2. **Sign-in timing:** allow chatting signed out and ask at "Book" (default), or require sign-in first?
3. **Required items:** must a trip always include flights and a hotel, or can users plan "activities only" (e.g. locals)?
4. **Autonomy:** with "Swan decides" set for everything, should items arrive already `accepted`, or still need one "Accept all" tap? Default: still `proposed`, plus "Accept all remaining".
5. **Old routes:** delete `/plan/*` pages, or keep them behind a flag until the new flow is stable? Default: redirect, delete after the demo.

## 13. Milestones (each is a ticket-sized chunk)
1. **Contracts + mock conversation fixture** (§9): unblocks everything else.
2. **Home page** (§5.1) with the prompt-to-composer animation.
3. **Conversation view** (§5.2): messages, inline controls, brief strip, "Plan it now", streaming, all in mock mode.
4. **Proposal workspace** (§5.4–5.5): list + sticky `TripMap`, cards with states, map ↔ list linking.
5. **Modify sheet and reject flow** (§5.6–5.7).
6. **Review & book** (§5.8): wired to the booking and checkout routes.
7. **Gateway conversation routes + Strands conversation phase** (§7, §9.2): the real AI behind the mock.
8. **Targeted replans and alternatives** in the planner (§8).
9. **Mobile pass + accessibility pass** (§6, §11).
10. **Retire old routes** (§10).

## 14. Done when (for the whole spec)
- [ ] From `/`, typing "Kyoto in late November, 4 days, 2 of us, love food" leads to at most 2 rounds of questions, then a full proposal with flights, a hotel and 3 days of stops on the map
- [ ] Accept, Modify (choose an alternative) and Reject each work on a flight, a hotel and an attraction, and the map updates within 1 s of the server event
- [ ] A typed change ("make day 2 more relaxed") updates the right items without resetting accepted ones
- [ ] "Book accepted" hands Swan merchant items to the XRPL checkout and external items to the booking route
- [ ] Works end to end in mock mode with no backend; works at 390 px; keyboard-only run-through passes
