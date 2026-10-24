import Link from "next/link";
import { Logo } from "@/components/Logo";

export function SwanShell({
  children,
  step,
  steps,
  map,
}: {
  children: React.ReactNode;
  step?: number;
  steps?: number;
  map?: React.ReactNode;
}) {
  const progress = step && steps ? (
    <div aria-hidden>
      <div className="h-1 overflow-hidden rounded-full" style={{ background: "var(--swan-line)" }}>
        <div className="h-full" style={{ width: `${(step / steps) * 100}%`, background: "var(--swan-fg)" }} />
      </div>
      <p className="swan-muted mt-2 text-xs">Step {step} of {steps}</p>
    </div>
  ) : null;

  if (map) {
    return (
      <main className="swan-app relative min-h-screen" style={{ background: "transparent" }}>
        <div className="fixed inset-0">{map}</div>
        <div className="relative z-10 mx-auto flex min-h-screen max-w-3xl flex-col px-4 pb-4">
          <header className="flex items-center justify-between py-4">
            <Link href="/" className="swan-sheet rounded-full px-3 py-2"><Logo /></Link>
            <Link href="/profile" className="swan-sheet swan-muted rounded-full px-3 py-2 text-sm">Profile</Link>
          </header>
          <section className="swan-sheet mt-auto rounded-3xl px-4 py-5">
            {progress}
            {children}
          </section>
        </div>
      </main>
    );
  }

  return (
    <main className="swan-app min-h-screen">
      <header className="mx-auto flex max-w-3xl items-center justify-between px-4 py-4">
        <Link href="/"><Logo /></Link>
        <Link href="/profile" className="swan-muted text-sm">Profile</Link>
      </header>
      {progress ? <div className="mx-auto max-w-3xl px-4">{progress}</div> : null}
      <div className="mx-auto max-w-3xl px-4 py-6">{children}</div>
    </main>
  );
}

export function phasePath(id: string, phase: string) {
  if (phase === "waiting_attractions") return `/plan/${id}/attractions`;
  if (phase === "waiting_flights") return `/plan/${id}/flights`;
  if (phase === "waiting_hotels") return `/plan/${id}/hotels`;
  return `/plan/${id}/overview`;
}
