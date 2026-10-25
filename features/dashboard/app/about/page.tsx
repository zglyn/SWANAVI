import { SwanButton } from "@/components/swan/Button";
import { SwanLogo } from "@/components/swan/Logo";
import { SwanTitle } from "@/components/swan/Title";

export default function AboutPage() {
  return (
    <div className="swan-stage">
      <main className="swan-app swan-landing">
        <div className="swan-wrap">
          <header className="swan-bar">
            <SwanLogo />
          </header>
          <SwanTitle className="swan-landing-title">Where to next.</SwanTitle>
          <p className="swan-muted">Swanavi plans the trip. A cryptographic leash settles the local bookings on the XRP Ledger.</p>
          <SwanButton href="/">Start from the prompt</SwanButton>
        </div>
      </main>
    </div>
  );
}
