"use client";

import { useState } from "react";

export function Photo({ src, alt, label, className = "" }: { src?: string | null; alt: string; label: string; className?: string }) {
  const [failed, setFailed] = useState(false);
  if (!src || failed) {
    return (
      <div className={`swan-surface flex items-end p-3 ${className}`} role="img" aria-label={alt}>
        <span className="text-3xl font-bold tracking-tight opacity-30">{label.slice(0, 1).toUpperCase()}</span>
      </div>
    );
  }
  return <img src={src} alt={alt} className={`object-cover grayscale ${className}`} loading="lazy" onError={() => setFailed(true)} />;
}
