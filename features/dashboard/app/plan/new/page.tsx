"use client";

import type { Autonomy, TimeOfDayWindow, TripRequest, UserProfile } from "@contracts/api";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import {
  Suspense,
  useEffect,
  useMemo,
  useRef,
  useState,
  type InputHTMLAttributes,
  type ReactNode,
} from "react";
import { SwanMark } from "@/components/brand/SwanMark";
import { planningPath } from "@/components/swan/Shell";
import { getClient } from "@/lib/client";
import { formatDateRange, formatMoney, nightsBetween } from "@/lib/format";
import { mapboxPublicToken } from "@/lib/mapboxToken";
import { DESTINATIONS, lookupPlace, matchCity } from "@/lib/places";

const WINDOWS: TimeOfDayWindow[] = ["early_morning", "morning", "afternoon", "evening", "red_eye", "any"];
const WINDOW_LABEL: Record<TimeOfDayWindow, string> = {
  early_morning: "Early morning",
  morning: "Morning",
  afternoon: "Afternoon",
  evening: "Evening",
  red_eye: "Red-eye",
  any: "Any time",
};
const DRAFT = "swan.trip-draft";
const STEPS = 6;

const LAKE = "#0B3D56";
const LAKE_DEEP = "#072A3C";
const MUTED = "#5A7382";
const LINE = "rgba(11, 61, 86, 0.12)";
const ORANGE = "#F05A28";
const EASE = "cubic-bezier(0.22, 1, 0.36, 1)";

type MapHandle = {
  remove: () => void;
  resize: () => void;
  flyTo: (opts: object) => void;
  jumpTo: (opts: object) => void;
  addControl: (control: object, position?: string) => void;
  on: (event: string, handler: (event: { error?: { message?: string } }) => void) => void;
};

function destinationCoords(destination: string): [number, number] {
  const city = matchCity(destination) ?? DESTINATIONS.find((item) => destination.includes(item.label));
  return city ? [city.lng, city.lat] : [135.7681, 35.0116];
}

/** Atmospheric Mapbox backdrop — public token only; falls back to lake gradient. */
function LivingMap({ destination }: { destination: string }) {
  const host = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MapHandle | null>(null);
  const token = useMemo(mapboxPublicToken, []);
  const [failed, setFailed] = useState(!token);
  const [ready, setReady] = useState(false);
  const destRef = useRef(destination);
  destRef.current = destination;

  useEffect(() => {
    if (!token || failed) return;
    const node = host.current;
    if (!node) return;
    let cancelled = false;
    let observer: ResizeObserver | null = null;

    (async () => {
      try {
        const loaded = await import("mapbox-gl");
        await import("mapbox-gl/dist/mapbox-gl.css");
        if (cancelled || !node) return;
        // mapbox-gl CJS/ESM interop — match CinematicTrip
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const mapboxgl: any = (loaded as { default?: unknown }).default ?? loaded;
        mapboxgl.accessToken = token;
        const center = destinationCoords(destRef.current);
        const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
        const map = new mapboxgl.Map({
          container: node,
          style: "mapbox://styles/mapbox/light-v11",
          center,
          zoom: 11.35,
          pitch: reduced ? 0 : 46,
          bearing: reduced ? 0 : -22,
          interactive: false,
          attributionControl: false,
          fadeDuration: reduced ? 0 : 800,
          antialias: true,
        }) as MapHandle;
        map.addControl(new mapboxgl.AttributionControl({ compact: true }), "bottom-right");
        map.on("error", (event) => {
          const message = String(event.error?.message ?? "");
          if (/token|unauthorized|forbidden|401|403/i.test(message)) setFailed(true);
        });
        map.on("load", () => {
          if (!cancelled) setReady(true);
        });
        observer = new ResizeObserver(() => map.resize());
        observer.observe(node);
        mapRef.current = map;
      } catch {
        if (!cancelled) setFailed(true);
      }
    })();

    return () => {
      cancelled = true;
      observer?.disconnect();
      mapRef.current?.remove();
      mapRef.current = null;
      setReady(false);
    };
  }, [token, failed]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    const center = destinationCoords(destination);
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduced) map.jumpTo({ center, zoom: 11.35 });
    else map.flyTo({ center, zoom: 11.35, pitch: 46, bearing: -22, duration: 1600, essential: true });
  }, [destination, ready]);

  return (
    <div aria-hidden className="plan-map-stage">
      {!failed ? <div ref={host} className="plan-map-canvas" /> : <div className="plan-map-fallback" />}
      <div className="plan-map-wash" />
      <div className="plan-map-vignette" />
    </div>
  );
}

function StepChrome({
  step,
  title,
  support,
  children,
  action,
  onAction,
  actionDisabled,
  onBack,
}: {
  step: number;
  title: string;
  support?: string;
  children: ReactNode;
  action: string;
  onAction: () => void;
  actionDisabled?: boolean;
  onBack?: () => void;
}) {
  return (
    <div className="plan-sheet" role="region" aria-label="Trip brief">
      <header className="plan-sheet-top">
        <Link href="/" className="plan-brand" aria-label="Swanavi home">
          <SwanMark className="plan-swan" />
          <span className="plan-word">Swanavi</span>
        </Link>
        <Link href="/profile" className="plan-profile">
          Profile
        </Link>
      </header>

      <div
        className="plan-progress"
        role="progressbar"
        aria-valuemin={1}
        aria-valuemax={STEPS}
        aria-valuenow={step}
        aria-label={`${step} of ${STEPS}`}
      >
        <div className="plan-progress-bar" style={{ width: `${(step / STEPS) * 100}%` }} />
      </div>
      <p className="plan-step-count">
        {step} of {STEPS}
      </p>

      {onBack ? (
        <button type="button" className="plan-back" onClick={onBack}>
          Back
        </button>
      ) : null}

      <div key={`${step}-${title}`} className="plan-body">
        <h1 className="plan-title">{title}</h1>
        {support ? <p className="plan-support">{support}</p> : null}
        {children}
      </div>

      <div className="plan-dock">
        <button type="button" className="plan-cta" onClick={onAction} disabled={actionDisabled}>
          {action}
        </button>
      </div>
    </div>
  );
}

function Field(props: InputHTMLAttributes<HTMLInputElement> & { label?: string }) {
  const { label, id, className, ...rest } = props;
  const fieldId = id ?? (label ? `field-${label.replace(/\s+/g, "-").toLowerCase()}` : undefined);
  return (
    <label className="plan-field-wrap" htmlFor={fieldId}>
      {label ? <span className="plan-kicker">{label}</span> : null}
      <input id={fieldId} className={`plan-field ${className ?? ""}`.trim()} {...rest} />
    </label>
  );
}

function Pill({
  pressed,
  onClick,
  children,
}: {
  pressed: boolean;
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <button type="button" className="plan-pill" aria-pressed={pressed} onClick={onClick}>
      {children}
    </button>
  );
}

function Planner() {
  const router = useRouter();
  const params = useSearchParams();
  const step = Math.min(STEPS, Math.max(1, Number(params.get("step") || "1")));
  const client = useMemo(getClient, []);
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [draft, setDraft] = useState<TripRequest | null>(null);
  const [query, setQuery] = useState("Kyoto");
  const [originQuery, setOriginQuery] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const saved = sessionStorage.getItem(DRAFT);
    client
      .getProfile()
      .then((found) => {
        setProfile(found);
        if (saved) {
          const parsed = JSON.parse(saved) as TripRequest;
          setDraft(parsed);
          const city = matchCity(parsed.destination);
          if (city) setQuery(city.label);
          return;
        }
        const autonomy = found?.autonomy ?? {
          attractions: "swan_decides",
          hotels: "swan_decides",
          flights: "swan_decides",
        };
        setDraft({
          destination: "Kyoto, Japan",
          origin: { from_home: true, place: null, airport_codes: found?.home.airport_codes ?? [] },
          start_date: "2026-11-14",
          end_date: "2026-11-16",
          outbound_window: "morning",
          return_window: "evening",
          travellers: 1,
          budget: "2500",
          autonomy,
          notes: null,
        });
      })
      .catch(() => setProfile(null));
  }, [client]);

  useEffect(() => {
    if (draft) sessionStorage.setItem(DRAFT, JSON.stringify(draft));
  }, [draft]);

  function go(next: number) {
    router.push(`/plan/new?step=${next}`);
  }

  async function confirm() {
    if (!draft || busy) return;
    setBusy(true);
    try {
      const created = await client.requestTrip(draft);
      sessionStorage.removeItem(DRAFT);
      router.push(planningPath(created.plan_id, created.phase));
    } finally {
      setBusy(false);
    }
  }

  if (!draft) {
    return (
      <main className="plan-root">
        <LivingMap destination="Kyoto, Japan" />
        <StepChrome step={1} title="Where to?" action="Continue" onAction={() => undefined} actionDisabled>
          <p className="plan-muted">Loading your profile…</p>
        </StepChrome>
        <PlanStyles />
      </main>
    );
  }

  const windows = WINDOWS.filter((item) => item !== "red_eye" || !profile?.flights.avoid_red_eye);
  const matches = DESTINATIONS.filter((city) => city.label.toLowerCase().includes(query.toLowerCase()));
  const homeAirports = (profile?.home.airport_codes ?? draft.origin.airport_codes).filter(Boolean);
  const originLabel = draft.origin.from_home
    ? ["Home", homeAirports.join(" · ")].filter(Boolean).join(" · ")
    : [draft.origin.place, draft.origin.airport_codes.join(" · ")].filter(Boolean).join(" · ") || "Somewhere else";
  const nights = nightsBetween(draft.start_date, draft.end_date);

  const meta: Record<number, { title: string; support?: string }> = {
    1: { title: "Where to?", support: "Choose a city. Swanavi shapes the days around it." },
    2: { title: "From where?", support: "Home airports when you can — elsewhere when you need." },
    3: { title: "When?", support: "Arrive, leave, and how many are travelling." },
    4: { title: "Fly windows", support: "Time of day only — not a flight search." },
    5: {
      title: "How much should Swanavi handle?",
      support: "Swanavi chooses with ranked rules. You can take any layer.",
    },
    6: { title: "Confirm", support: "A quiet brief before the plan unfolds." },
  };

  return (
    <main className="plan-root">
      <LivingMap destination={draft.destination} />
      <StepChrome
        step={step}
        title={meta[step]?.title ?? "Plan"}
        support={meta[step]?.support}
        action={step === STEPS ? (busy ? "Starting…" : "Confirm") : "Continue"}
        onAction={step === STEPS ? confirm : () => go(step + 1)}
        actionDisabled={step === STEPS && busy}
        onBack={step > 1 ? () => go(step - 1) : undefined}
      >
        {step === 1 && (
          <section className="plan-section">
            <Field
              aria-label="Destination"
              placeholder="Search a city"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              className="plan-search"
            />
            <ul className="plan-dest-list">
              {matches.map((city) => {
                const value = ["London", "Paris", "New York", "Los Angeles"].includes(city.label)
                  ? city.label
                  : `${city.label}, Japan`;
                const selected = draft.destination === value;
                return (
                  <li key={city.label}>
                    <button
                      type="button"
                      className="plan-dest"
                      aria-pressed={selected}
                      onClick={() => {
                        setDraft({ ...draft, destination: value });
                        setQuery(city.label);
                      }}
                    >
                      <span className="plan-dest-name">{city.label}</span>
                      {selected ? <span className="plan-dest-mark" aria-hidden /> : null}
                    </button>
                  </li>
                );
              })}
            </ul>
            <p className="plan-muted">Going to {draft.destination}</p>
          </section>
        )}

        {step === 2 && (
          <section className="plan-section">
            <div className="plan-stack">
              <button
                type="button"
                className="plan-row"
                aria-pressed={draft.origin.from_home}
                onClick={() =>
                  setDraft({
                    ...draft,
                    origin: { from_home: true, place: null, airport_codes: profile?.home.airport_codes ?? [] },
                  })
                }
              >
                <span>
                  From home
                  <span className="plan-sub">
                    {(profile?.home.airport_codes ?? []).join(", ") || "your home airports"}
                  </span>
                </span>
              </button>
              <button
                type="button"
                className="plan-row"
                aria-pressed={!draft.origin.from_home}
                onClick={() =>
                  setDraft({
                    ...draft,
                    origin: {
                      from_home: false,
                      place: draft.origin.place,
                      airport_codes: draft.origin.from_home ? [] : draft.origin.airport_codes,
                    },
                  })
                }
              >
                Somewhere else
              </button>
            </div>
            {!draft.origin.from_home ? (
              <div className="plan-gap">
                <Field
                  label="City or address"
                  aria-label="Other origin"
                  value={originQuery}
                  onChange={(event) => setOriginQuery(event.target.value)}
                  onBlur={async () => {
                    const hit = await lookupPlace(originQuery);
                    if (!hit) return;
                    setDraft({
                      ...draft,
                      origin: { from_home: false, place: hit.label, airport_codes: hit.airports },
                    });
                  }}
                />
                {draft.origin.place ? (
                  <p className="plan-muted">
                    {draft.origin.place} · {draft.origin.airport_codes.join(" · ")}
                  </p>
                ) : null}
              </div>
            ) : null}
          </section>
        )}

        {step === 3 && (
          <section className="plan-section plan-dates">
            <Field
              label="Arrive"
              type="date"
              value={draft.start_date}
              onChange={(event) => setDraft({ ...draft, start_date: event.target.value })}
            />
            <Field
              label="Leave"
              type="date"
              value={draft.end_date}
              onChange={(event) => setDraft({ ...draft, end_date: event.target.value })}
            />
            <Field
              label="Travellers"
              type="number"
              min={1}
              value={draft.travellers}
              onChange={(event) => setDraft({ ...draft, travellers: Math.max(1, Number(event.target.value)) })}
            />
            <p className="plan-muted">
              {nights} night{nights === 1 ? "" : "s"}
            </p>
          </section>
        )}

        {step === 4 && (
          <>
            <section className="plan-section">
              <p className="plan-kicker">Fly in</p>
              <div className="plan-pills">
                {windows.map((item) => (
                  <Pill
                    key={`out-${item}`}
                    pressed={draft.outbound_window === item}
                    onClick={() => setDraft({ ...draft, outbound_window: item })}
                  >
                    {WINDOW_LABEL[item]}
                  </Pill>
                ))}
              </div>
            </section>
            <section className="plan-section">
              <p className="plan-kicker">Fly out</p>
              <div className="plan-pills">
                {windows.map((item) => (
                  <Pill
                    key={`ret-${item}`}
                    pressed={draft.return_window === item}
                    onClick={() => setDraft({ ...draft, return_window: item })}
                  >
                    {WINDOW_LABEL[item]}
                  </Pill>
                ))}
              </div>
            </section>
          </>
        )}

        {step === 5 && (
          <>
            {(["attractions", "hotels", "flights"] as const).map((key) => (
              <section key={key} className="plan-section">
                <p className="plan-kicker">{key.charAt(0).toUpperCase() + key.slice(1)}</p>
                <div className="plan-pills">
                  {(["swan_decides", "i_choose"] as Autonomy[]).map((item) => (
                    <Pill
                      key={item}
                      pressed={draft.autonomy[key] === item}
                      onClick={() => setDraft({ ...draft, autonomy: { ...draft.autonomy, [key]: item } })}
                    >
                      {item === "swan_decides" ? "Swanavi decides" : "I choose"}
                    </Pill>
                  ))}
                </div>
              </section>
            ))}
            <section className="plan-section">
              <Field
                label="Budget for the whole trip"
                inputMode="decimal"
                value={draft.budget ?? ""}
                onChange={(event) => setDraft({ ...draft, budget: event.target.value })}
              />
            </section>
          </>
        )}

        {step === 6 && (
          <section className="plan-section">
            <p className="plan-summary">{draft.destination}</p>
            <p className="plan-muted">
              {formatDateRange(draft.start_date, draft.end_date)} · {nights} night{nights === 1 ? "" : "s"} ·{" "}
              {draft.travellers} traveller{draft.travellers === 1 ? "" : "s"}
            </p>
            <p className="plan-muted">
              Fly {WINDOW_LABEL[draft.outbound_window].toLowerCase()} in,{" "}
              {WINDOW_LABEL[draft.return_window].toLowerCase()} out.
            </p>
            <p className="plan-muted">From {originLabel}.</p>
            <p className="plan-muted">Budget {draft.budget ? formatMoney(draft.budget, "USD") : "Open"}</p>
          </section>
        )}
      </StepChrome>
      <PlanStyles />
    </main>
  );
}

function PlanStyles() {
  const css = `
.plan-root {
  --lake: ${LAKE};
  --lake-deep: ${LAKE_DEEP};
  --muted: ${MUTED};
  --line: ${LINE};
  --orange: ${ORANGE};
  --ease: ${EASE};
  position: relative;
  min-height: 100dvh;
  overflow: hidden;
  color: var(--ink, #0E2430);
  background: var(--lake-deep);
  font-family: var(--font-outfit), "Outfit", sans-serif;
  -webkit-font-smoothing: antialiased;
}
.plan-map-stage {
  position: absolute;
  inset: 0;
  z-index: 0;
}
.plan-map-canvas,
.plan-map-fallback {
  position: absolute;
  inset: 0;
}
.plan-map-fallback {
  background:
    radial-gradient(120% 80% at 70% 20%, rgba(120, 180, 210, 0.35), transparent 55%),
    radial-gradient(90% 70% at 20% 80%, rgba(40, 90, 120, 0.45), transparent 50%),
    linear-gradient(160deg, #1a5a78 0%, #0b3d56 42%, #062433 100%);
}
.plan-map-wash {
  position: absolute;
  inset: 0;
  background:
    linear-gradient(180deg, rgba(7, 42, 60, 0.18) 0%, rgba(7, 42, 60, 0.08) 35%, rgba(7, 42, 60, 0.55) 100%),
    linear-gradient(90deg, rgba(7, 42, 60, 0.42) 0%, transparent 48%);
  pointer-events: none;
}
.plan-map-vignette {
  position: absolute;
  inset: 0;
  box-shadow: inset 0 0 120px rgba(4, 24, 36, 0.35);
  pointer-events: none;
}
.plan-map-stage .mapboxgl-ctrl-attrib {
  background: rgba(244, 248, 251, 0.55) !important;
  backdrop-filter: blur(8px);
  font-size: 10px;
}
.plan-map-stage .mapboxgl-ctrl-bottom-right { bottom: 10px; right: 10px; }

.plan-sheet {
  position: relative;
  z-index: 2;
  display: flex;
  flex-direction: column;
  box-sizing: border-box;
  width: min(100%, 440px);
  min-height: min(72dvh, 720px);
  max-height: min(92dvh, 860px);
  margin: max(12px, env(safe-area-inset-top)) 12px 12px;
  margin-left: auto;
  margin-right: auto;
  padding: 22px 22px 18px;
  border-radius: 28px 28px 22px 22px;
  background: linear-gradient(180deg, rgba(255,255,255,0.72) 0%, rgba(244,248,251,0.88) 100%);
  border: 1px solid rgba(255,255,255,0.55);
  box-shadow:
    0 24px 80px rgba(4, 24, 36, 0.28),
    0 1px 0 rgba(255,255,255,0.65) inset;
  backdrop-filter: blur(28px) saturate(1.35);
  -webkit-backdrop-filter: blur(28px) saturate(1.35);
  overflow: hidden;
}

.plan-sheet-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 18px;
}
.plan-brand {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  color: var(--lake);
  text-decoration: none;
}
.plan-swan { width: 28px; height: 28px; color: var(--lake); }
.plan-word {
  font-size: 15px;
  font-weight: 500;
  letter-spacing: 0.14em;
  text-transform: uppercase;
}
.plan-profile {
  color: var(--muted);
  font-size: 13px;
  letter-spacing: 0.06em;
  text-decoration: none;
}

.plan-progress {
  height: 2px;
  border-radius: 999px;
  background: rgba(11, 61, 86, 0.1);
  overflow: hidden;
}
.plan-progress-bar {
  height: 100%;
  background: var(--lake);
  transition: width 480ms var(--ease);
}
.plan-step-count {
  margin: 10px 0 0;
  color: var(--muted);
  font-size: 11px;
  letter-spacing: 0.14em;
  text-transform: uppercase;
}
.plan-back {
  align-self: flex-start;
  margin: 16px 0 0;
  padding: 0;
  border: 0;
  background: transparent;
  color: var(--muted);
  font: inherit;
  font-size: 12px;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  cursor: pointer;
}

.plan-body {
  flex: 1;
  overflow: auto;
  margin-top: 18px;
  padding-bottom: 12px;
  animation: plan-rise 420ms var(--ease) both;
  scrollbar-width: thin;
}
.plan-title {
  margin: 0;
  max-width: 12ch;
  font-family: var(--font-fraunces), "Fraunces", Georgia, serif;
  font-size: clamp(40px, 9vw, 56px);
  font-weight: 500;
  letter-spacing: -0.045em;
  line-height: 0.98;
  color: var(--lake-deep);
}
.plan-support {
  margin: 12px 0 0;
  max-width: 28ch;
  color: var(--muted);
  font-size: 15px;
  line-height: 1.45;
}

.plan-section { margin-top: 28px; }
.plan-gap { margin-top: 16px; }
.plan-dates { display: grid; gap: 18px; }
.plan-kicker {
  display: block;
  margin: 0 0 10px;
  color: var(--muted);
  font-size: 11px;
  font-weight: 500;
  letter-spacing: 0.14em;
  text-transform: uppercase;
}
.plan-field-wrap { display: block; }
.plan-field {
  width: 100%;
  height: 52px;
  padding: 0 2px;
  border: 0;
  border-bottom: 1px solid var(--line);
  border-radius: 0;
  background: transparent;
  color: #0E2430;
  font: inherit;
  font-size: 18px;
  letter-spacing: -0.01em;
  outline: none;
  transition: border-color 280ms var(--ease);
}
.plan-field:focus { border-color: var(--lake); }
.plan-field::placeholder { color: var(--muted); }
.plan-field.plan-search {
  height: 44px;
  font-size: 15px;
  font-weight: 450;
  letter-spacing: 0.01em;
  color: var(--muted);
}

.plan-dest-list {
  list-style: none;
  margin: 8px 0 0;
  padding: 0;
}
.plan-dest {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  width: 100%;
  padding: 14px 0;
  border: 0;
  border-bottom: 1px solid var(--line);
  background: transparent;
  color: #0E2430;
  font-family: var(--font-fraunces), "Fraunces", Georgia, serif;
  font-size: clamp(28px, 7vw, 40px);
  font-weight: 500;
  letter-spacing: -0.04em;
  line-height: 1.05;
  text-align: left;
  cursor: pointer;
  transition: color 280ms var(--ease);
}
.plan-dest[aria-pressed="true"] { color: var(--lake); }
.plan-dest-mark {
  width: 8px;
  height: 8px;
  border-radius: 999px;
  background: var(--lake);
  flex: none;
}
.plan-muted {
  margin: 14px 0 0;
  color: var(--muted);
  font-size: 14px;
  line-height: 1.5;
}
.plan-summary {
  margin: 0;
  font-family: var(--font-fraunces), "Fraunces", Georgia, serif;
  font-size: clamp(32px, 7vw, 44px);
  font-weight: 500;
  letter-spacing: -0.04em;
  line-height: 1.05;
  color: var(--lake-deep);
}

.plan-stack { display: flex; flex-direction: column; }
.plan-row {
  display: flex;
  width: 100%;
  padding: 16px 0;
  border: 0;
  border-bottom: 1px solid var(--line);
  background: transparent;
  color: #0E2430;
  font: inherit;
  font-size: 17px;
  font-weight: 500;
  letter-spacing: -0.01em;
  text-align: left;
  cursor: pointer;
}
.plan-row[aria-pressed="true"] { color: var(--lake); }
.plan-sub {
  display: block;
  margin-top: 4px;
  color: var(--muted);
  font-size: 13px;
  font-weight: 400;
}

.plan-pills {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.plan-pill {
  padding: 10px 15px;
  border: 1px solid var(--line);
  border-radius: 999px;
  background: rgba(255,255,255,0.35);
  color: #0E2430;
  font: inherit;
  font-size: 13px;
  font-weight: 500;
  letter-spacing: 0.01em;
  cursor: pointer;
  transition: background-color 280ms var(--ease), color 280ms var(--ease), border-color 280ms var(--ease);
}
.plan-pill[aria-pressed="true"] {
  border-color: var(--lake);
  background: var(--lake);
  color: #F4F8FB;
}

.plan-dock {
  margin-top: auto;
  padding-top: 16px;
}
.plan-cta {
  width: 100%;
  height: 54px;
  border: 0;
  border-radius: 999px;
  background: var(--orange);
  color: #fff;
  font: inherit;
  font-size: 16px;
  font-weight: 560;
  letter-spacing: 0.02em;
  cursor: pointer;
  box-shadow: 0 10px 28px rgba(240, 90, 40, 0.28);
  transition: transform 280ms var(--ease), opacity 280ms var(--ease), box-shadow 280ms var(--ease);
}
.plan-cta:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: 0 14px 32px rgba(240, 90, 40, 0.34);
}
.plan-cta:disabled {
  opacity: 0.45;
  cursor: default;
  box-shadow: none;
}

@keyframes plan-rise {
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: none; }
}

@media (min-width: 900px) {
  .plan-root {
    display: grid;
    grid-template-columns: minmax(380px, 440px) 1fr;
  }
  .plan-map-stage {
    position: absolute;
    inset: 0;
  }
  .plan-sheet {
    position: relative;
    z-index: 2;
    width: 100%;
    min-height: calc(100dvh - 40px);
    max-height: calc(100dvh - 40px);
    margin: 20px 0 20px 20px;
    border-radius: 28px;
  }
  .plan-map-wash {
    background:
      linear-gradient(90deg, rgba(7, 42, 60, 0.5) 0%, rgba(7, 42, 60, 0.12) 36%, transparent 58%),
      linear-gradient(180deg, rgba(7, 42, 60, 0.12) 0%, transparent 40%, rgba(7, 42, 60, 0.2) 100%);
  }
  .plan-cta { width: auto; min-width: 180px; }
}

@media (max-width: 899px) {
  .plan-root {
    display: flex;
    flex-direction: column;
    justify-content: flex-end;
  }
  .plan-sheet {
    width: calc(100% - 24px);
    margin-top: auto;
  }
}

@media (prefers-reduced-motion: reduce) {
  .plan-body,
  .plan-progress-bar,
  .plan-cta,
  .plan-pill,
  .plan-dest,
  .plan-field {
    animation: none !important;
    transition: none !important;
  }
}
`;
  return <style dangerouslySetInnerHTML={{ __html: css }} />;
}

export default function PlanNewPage() {
  return (
    <Suspense
      fallback={
        <main className="plan-root">
          <div className="plan-map-fallback" style={{ position: "absolute", inset: 0 }} />
          <div className="plan-sheet" style={{ margin: 20 }}>
            <p className="plan-muted" style={{ color: MUTED }}>
              Loading…
            </p>
          </div>
          <PlanStyles />
        </main>
      }
    >
      <Planner />
    </Suspense>
  );
}
