import Link from "next/link";
import { Logo } from "@/components/Logo";

export function SwanShell({
  children,
  step,
  steps,
  aside,
  wide = false,
}: {
  children: React.ReactNode;
  step?: number;
  steps?: number;
  aside?: React.ReactNode;
  wide?: boolean;
}) {
  const progress = step && steps ? (
    <div>
      <div className="swan-progress" aria-hidden="true"><span style={{ width: `${(step / steps) * 100}%` }} /></div>
      <p className="swan-step mt-2" aria-live="polite">Step {step} of {steps}</p>
    </div>
  ) : null;
  const width = wide ? "max-w-6xl" : aside ? "max-w-5xl" : "max-w-3xl";

  return (
    <main className="swan-app min-h-screen">
      <header className={`mx-auto flex ${width} items-center justify-between px-4 py-4 sm:px-6`}>
        <Link href="/" aria-label="Swanavi home"><Logo /></Link>
        <Link href="/profile" className="swan-muted text-sm underline-offset-4 hover:underline">Profile</Link>
      </header>
      <div className={`mx-auto ${width} px-4 pb-10 sm:px-6 ${aside ? "lg:grid lg:grid-cols-[minmax(0,1fr)_360px] lg:gap-10" : ""}`}>
        <div>
          {progress}
          <div className="py-6">{children}</div>
        </div>
        {aside ? <aside className="swan-card mt-4 h-fit p-5 lg:sticky lg:top-6 lg:mt-14">{aside}</aside> : null}
      </div>
    </main>
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
