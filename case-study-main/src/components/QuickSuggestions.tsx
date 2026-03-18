"use client";

interface Props {
  actions: string[];
  onSelect: (action: string) => void;
}

export default function QuickSuggestions({ actions, onSelect }: Props) {
  if (!actions.length) return null;

  return (
    <div className="flex flex-wrap gap-2 px-4 py-2">
      {actions.map((action) => (
        <button
          key={action}
          onClick={() => onSelect(action)}
          className="text-xs px-3 py-1.5 rounded-full border border-[var(--ps-blue)] text-[var(--ps-blue)] hover:bg-[var(--ps-blue-light)] transition-colors cursor-pointer"
        >
          {action}
        </button>
      ))}
    </div>
  );
}
