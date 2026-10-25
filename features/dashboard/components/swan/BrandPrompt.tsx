"use client";

export function BrandPrompt({
  question,
  options,
  chosen,
  onToggle,
}: {
  question: string;
  options: string[];
  chosen: string[];
  onToggle: (value: string) => void;
}) {
  if (!options.length) return null;
  return (
    <div className="swan-surface mt-5 rounded-2xl p-4">
      <p className="font-medium">{question} <span className="swan-muted font-normal">We&apos;ll remember.</span></p>
      <div className="mt-3 flex flex-wrap gap-2">
        {options.map((option) => (
          <button key={option} type="button" className="swan-filter" aria-pressed={chosen.includes(option)} onClick={() => onToggle(option)}>
            {option}
          </button>
        ))}
      </div>
    </div>
  );
}
