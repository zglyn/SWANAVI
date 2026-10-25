import { Logo } from "@/components/Logo";
import { SwanMark } from "@/components/brand/SwanMark";

export default function StyleGuidePage() {
  return (
    <main className="swan-app min-h-screen px-4 py-8">
      <Logo />
      <h1 className="mt-8 text-5xl">Swanavi</h1>
      <p className="swan-muted mt-3 max-w-xl">Lake text on a feather page, one beak-coloured action, and mist chips. Every pair below clears WCAG AA.</p>
      <ul className="mt-6 flex flex-col gap-2 text-sm">
        <li className="rounded-lg px-3 py-2" style={{ background: "var(--swan-feather)", color: "var(--swan-lake)" }}>Lake on feather, 12.7 to 1</li>
        <li className="rounded-lg px-3 py-2" style={{ background: "var(--swan-feather)", color: "var(--swan-lake-2)" }}>Secondary on feather, 6.1 to 1</li>
        <li className="rounded-lg px-3 py-2" style={{ background: "var(--swan-beak)", color: "var(--swan-surface)" }}>White on beak, 5.2 to 1</li>
        <li className="rounded-lg px-3 py-2" style={{ background: "var(--swan-feather)", color: "var(--swan-reed)" }}>Reed on feather, 6.0 to 1</li>
      </ul>
      <div className="mt-8 flex items-end gap-4">
        <SwanMark className="h-4 w-4" />
        <SwanMark className="h-8 w-8" />
        <SwanMark className="h-16 w-16" />
      </div>
      <div className="mt-8 flex flex-wrap gap-3">
        <button type="button" className="swan-btn">Primary</button>
        <button type="button" className="swan-btn-ghost">Secondary</button>
      </div>
      <p className="mt-8 tabular-nums text-5xl">1,240</p>
      <p className="swan-muted text-sm">Projector numbers use the mono face at this size.</p>
    </main>
  );
}
