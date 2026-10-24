export function Logo({ className = "" }: { className?: string }) {
  return (
    <span className={`inline-flex items-center gap-2 font-semibold tracking-tight ${className}`}>
      <svg viewBox="0 0 32 32" className="h-7 w-7" aria-hidden>
        <rect width="32" height="32" rx="8" className="fill-torii" />
        {/* torii gate */}
        <path d="M6 10.5c3.5 1 16.5 1 20 0v2.4c-3.5.9-16.5.9-20 0z" fill="#fff" />
        <rect x="8" y="15" width="16" height="1.8" rx=".5" fill="#fff" />
        <rect x="10" y="12" width="2" height="13" rx=".6" fill="#fff" />
        <rect x="20" y="12" width="2" height="13" rx=".6" fill="#fff" />
      </svg>
      <span>
        Roam<span className="text-torii">402</span>
      </span>
    </span>
  );
}
