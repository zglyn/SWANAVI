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
  // Plan screens may still pass a map. It stays hidden until the finished overview.
  void map;

  const progress = step && steps ? (
    <div className="swan-progress-block" aria-hidden>
      <div className="swan-progress">
        <div style={{ width: `${(step / steps) * 100}%` }} />
      </div>
      <p className="swan-muted swan-step-count">Step {step} of {steps}</p>
    </div>
  ) : null;

  return (
    <div className="swan-stage">
      <main className="swan-app">
        <div className="swan-wrap">
          <header className="swan-bar">
            <Link href="/" aria-label="Swanavi home">
              <SwanLogo />
            </Link>
            <Link href="/profile" className="swan-muted swan-profile">Profile</Link>
          </header>
          {progress}
          <div className="swan-body">{children}</div>
          {aside ? <div className="swan-aside">{aside}</div> : null}
        </div>
      </main>
    </div>
  );
}

