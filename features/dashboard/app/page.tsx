import { SwanButton } from "@/components/swan/Button";
import { SwanLogo } from "@/components/swan/Logo";
import { SwanTitle } from "@/components/swan/Title";

export default function Landing() {
  return (
    <div className="swan-stage">
      <main className="swan-app swan-column flex min-h-screen flex-col px-6">
        <header className="pt-6">
          <SwanLogo />
        </header>
        <SwanTitle className="pt-8">Where to next.</SwanTitle>
        <div className="mt-auto pb-6 pt-6">
          <SwanButton href="/plan/new" className="w-full">Plan a trip</SwanButton>
        </div>
      </main>
    </div>
  );
}
