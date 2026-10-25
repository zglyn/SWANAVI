export function SwanTitle({
  children,
  className = "",
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return <h1 className={`swan-title ${className}`.trim()}>{children}</h1>;
}
