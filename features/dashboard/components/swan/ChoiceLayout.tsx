"use client";

import Link from "next/link";
import { useState } from "react";
import { Logo } from "@/components/Logo";

export function ChoiceLayout({
  eyebrow,
  title,
  map,
  footer,
  children,
}: {
  eyebrow?: string;
  title: string;
  map: React.ReactNode;
  footer: React.ReactNode;
  children: React.ReactNode;
}) {
  const [showMap, setShowMap] = useState(false);
  return (
    <main className="swan-app min-h-screen">
      <header className="mx-auto flex max-w-7xl items-center justify-between px-4 py-4 sm:px-6">
        <Link href="/" aria-label="Swanavi home"><Logo /></Link>
        <div className="flex items-center gap-3">
          <button type="button" className="swan-filter lg:hidden" aria-pressed={showMap} onClick={() => setShowMap((value) => !value)}>
            {showMap ? "List" : "Map"}
          </button>
          <Link href="/profile" className="swan-muted text-sm underline-offset-4 hover:underline">Profile</Link>
        </div>
      </header>
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:grid lg:grid-cols-[minmax(0,1fr)_minmax(360px,42%)] lg:gap-8">
        <div className={showMap ? "hidden lg:block" : ""}>
          {eyebrow ? <p className="swan-eyebrow">{eyebrow}</p> : null}
          <h1 className="mt-2 text-4xl sm:text-5xl">{title}</h1>
          <div className="mt-6 pb-28">{children}</div>
        </div>
        <div className={`${showMap ? "block" : "hidden"} h-[60vh] overflow-hidden rounded-3xl lg:sticky lg:top-4 lg:block lg:h-[calc(100vh-2rem)]`}>
          {map}
        </div>
      </div>
      <div className="swan-sticky fixed inset-x-0 bottom-0 z-20">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-3 px-4 py-3 sm:px-6">{footer}</div>
      </div>
    </main>
  );
}

export function WhyChips({ reasons }: { reasons: string[] }) {
  if (!reasons.length) return null;
  return (
    <ul className="mt-3 flex flex-wrap gap-1.5" aria-label="Why">
      {reasons.map((reason) => <li key={reason} className="swan-reason">{reason}</li>)}
    </ul>
  );
}
