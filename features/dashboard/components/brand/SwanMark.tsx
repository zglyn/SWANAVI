export function SwanMark({ className = "h-7 w-7" }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" className={className} aria-hidden>
      <path
        fill="currentColor"
        d="M5 23.5c2.2-6.8 6.4-10.2 10.2-11.2 1.2-.3 2.3.6 2.4 1.8.1 1.6-1.2 2.8-2.8 2.9 3.4.4 6.6 2.2 8.6 5.2 1 1.6-.2 3.3-2 3.3H7.2c-1.8 0-3-1.4-2.2-2zM19.2 9.2c1.8-2.6 4.6-3.6 6.4-2.6.8.5.4 1.6-.5 1.8-1.6.3-3.2 1.2-4.6 2.6-.6-.8-.8-1.4-1.3-1.8z"
      />
    </svg>
  );
}
