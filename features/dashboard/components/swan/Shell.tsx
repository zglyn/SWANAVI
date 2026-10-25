import Link from "next/link";
import { SwanLogo } from "./Logo";

export function SwanShell({
  children,
  step,
  steps,
  aside,
  map,
}: {
  children: React.ReactNode;
  step?: number;
  steps?: number;
  aside?: React.ReactNode;
  wide?: boolean;
  map?: React.ReactNode;
}) {
  // Plan screens may still pass a map. The shell stays a black column and does not paint it.
  void map;

  const progress = step && steps ? (
    <div aria-hidden>
      <div className="swan-progress">
        <div style={{ width: `${(step / steps) * 100}%` }} />
      </div>
      <p className="swan-muted mt-2 text-xs">Step {step} of {steps}</p>
    </div>
  ) : null;

  return (
    <div className="swan-stage">
      <main className="swan-app swan-column">
        <header className="flex items-center justify-between px-6 pt-6">
          <Link href="/" aria-label="Swanavi home">
            <SwanLogo />
          </Link>
          <Link href="/profile" className="swan-muted text-sm">Profile</Link>
        </header>
        {progress ? <div className="px-6 pt-4">{progress}</div> : null}
        <div className="px-6 py-6">{children}</div>
        {aside ? <div className="px-6 pb-10">{aside}</div> : null}
      </main>
    </div>
  );
}

export function phasePath(id: string, phase: string) {
  if (phase === "waiting_attractions") return `/plan/${id}/attractions`;
  if (phase === "waiting_flights") return `/plan/${id}/flights`;
  if (phase === "waiting_hotels") return `/plan/${id}/hotels`;
  return `/plan/${id}/overview`;
}

export function planningPath(id: string, phase: string) {
  return `/plan/${id}/planning?next=${encodeURIComponent(phasePath(id, phase))}`;
}
