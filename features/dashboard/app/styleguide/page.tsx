import { Logo } from "@/components/Logo";
import { SwanMark } from "@/components/brand/SwanMark";

export default function StyleGuidePage() {
  return (
    <main className="swan-app min-h-screen px-4 py-8">
      <Logo />
      <h1 className="mt-8 text-5xl">Swanavi</h1>
      <p className="swan-muted mt-3 max-w-xl">Black primary buttons, white surfaces, 52px controls, one decision per screen. Sheets sit over the map on a phone and become a side panel on a desktop.</p>
      <div className="mt-8 flex items-end gap-4">
        <SwanMark className="h-4 w-4" />
        <SwanMark className="h-8 w-8" />
        <SwanMark className="h-16 w-16" />
      </div>
      <div className="mt-8 flex flex-wrap gap-3">
        <button type="button" className="swan-btn">Primary</button>
        <button type="button" className="swan-btn-ghost">Secondary</button>
      </div>
      <p className="mt-8 font-mono text-5xl">1,240</p>
      <p className="swan-muted text-sm">Projector numbers use the mono face at this size.</p>
    </main>
  );
}
