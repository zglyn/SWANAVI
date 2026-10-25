export function SwanLogo({ className = "" }: { className?: string }) {
  return (
    <span className={`swan-logo ${className}`}>
      <svg width="28" height="28" viewBox="0 0 28 28" fill="none" aria-hidden="true">
        <ellipse cx="11.2" cy="20.4" rx="7.4" ry="3.5" fill="currentColor" />
        <path d="M15.4 17.8C14.8 12.4 10 11.2 11 6.5" stroke="currentColor" strokeWidth="2.35" strokeLinecap="round" />
        <path d="M10.2 6.6c1.3-1.7 3.8-1.5 4.8.1l3.6-.6-3.6 2c-1.3-.7-3-.8-4.8-.4z" fill="currentColor" />
      </svg>
      <span className="swan-word">Swanavi</span>
    </span>
  );
}
