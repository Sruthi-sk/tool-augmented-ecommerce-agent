"use client";

import { DetailData } from "@/types/chat";

interface Props {
  data: DetailData;
}

export default function CompatibilityResult({ data }: Props) {
  const isCompatible = data.compatible === true;

  return (
    <div className="bg-white rounded-xl border border-[var(--ps-gray-200)] overflow-hidden">
      <div
        className={`p-4 ${
          isCompatible ? "bg-green-50" : "bg-red-50"
        }`}
      >
        <div className="flex items-center gap-3">
          <div
            className={`w-10 h-10 rounded-full flex items-center justify-center text-xl ${
              isCompatible
                ? "bg-[var(--ps-green)] text-white"
                : "bg-[var(--ps-red)] text-white"
            }`}
          >
            {isCompatible ? "✓" : "✗"}
          </div>
          <div>
            <h3 className="font-semibold text-[var(--ps-gray-900)]">
              {isCompatible ? "Compatible" : "Not Compatible"}
            </h3>
            <p className="text-sm text-[var(--ps-gray-500)]">
              {data.part_name || data.part_number} + {data.model_number}
            </p>
          </div>
        </div>
      </div>

      <div className="p-4 space-y-2">
        {data.part_number && (
          <div className="flex justify-between text-sm">
            <span className="text-[var(--ps-gray-500)]">Part</span>
            <span className="font-medium">{data.part_number}</span>
          </div>
        )}
        {data.model_number && (
          <div className="flex justify-between text-sm">
            <span className="text-[var(--ps-gray-500)]">Model</span>
            <span className="font-medium">{data.model_number}</span>
          </div>
        )}
        {data.compatible_models_count !== undefined && (
          <div className="flex justify-between text-sm">
            <span className="text-[var(--ps-gray-500)]">Total Compatible Models</span>
            <span className="font-medium">{data.compatible_models_count}</span>
          </div>
        )}

        {data.source_url && (
          <a
            href={data.source_url}
            target="_blank"
            rel="noopener noreferrer"
            className="block text-center text-sm font-medium text-white bg-[var(--ps-blue)] hover:bg-[var(--ps-blue-dark)] rounded-lg py-2.5 mt-3 transition-colors"
          >
            View on PartSelect
          </a>
        )}
      </div>
    </div>
  );
}
