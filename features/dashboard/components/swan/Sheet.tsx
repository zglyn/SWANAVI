export function SwanSheet({
  children,
  className = "",
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return <section className={`swan-sheet ${className}`.trim()}>{children}</section>;
}
