"use client";

import { DetailData } from "@/types/chat";

interface Props {
  data: DetailData;
}

export default function SearchResults({ data }: Props) {
  const parts = data.parts || [];

  return (
    <div className="bg-white rounded-xl border border-[var(--ps-gray-200)] overflow-hidden">
      <div className="p-4 border-b border-[var(--ps-gray-200)] bg-[var(--ps-gray-50)]">
        <h3 className="font-semibold text-[var(--ps-gray-900)]">
          Search Results
        </h3>
        {data.query && (
          <p className="text-xs text-[var(--ps-gray-500)] mt-0.5">
            &quot;{data.query}&quot; — {data.appliance_type || "all"}
          </p>
        )}
      </div>

      <div className="divide-y divide-[var(--ps-gray-200)]">
        {parts.length > 0 ? (
          parts.slice(0, 5).map((part) => (
            <div
              key={part.part_number}
              className="p-3 hover:bg-[var(--ps-gray-50)] transition-colors"
            >
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium text-[var(--ps-gray-900)]">
                    {part.name}
                  </p>
                  <p className="text-xs text-[var(--ps-gray-500)]">
                    {part.part_number}
                  </p>
                </div>
                {part.price && (
                  <span className="text-sm font-semibold text-[var(--ps-gray-900)]">
                    {part.price}
                  </span>
                )}
              </div>
            </div>
          ))
        ) : (
          <div className="p-4">
            <p className="text-sm text-[var(--ps-gray-500)]">
              No parts found matching your search.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
