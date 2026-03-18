"use client";

import { DetailData } from "@/types/chat";

interface Props {
  data: DetailData;
}

export default function InstallationGuide({ data }: Props) {
  const steps = data.steps || [];

  return (
    <div className="bg-white rounded-xl border border-[var(--ps-gray-200)] overflow-hidden">
      <div className="p-4 border-b border-[var(--ps-gray-200)] bg-[var(--ps-blue-light)]">
        <h3 className="font-semibold text-[var(--ps-blue)]">
          Installation Guide
        </h3>
        {(data.part_name || data.part_number) && (
          <p className="text-xs text-[var(--ps-gray-500)] mt-0.5">
            {data.part_name || data.part_number}
          </p>
        )}
      </div>

      <div className="p-4">
        {steps.length > 0 ? (
          <ol className="space-y-3">
            {steps.map((step, i) => (
              <li key={i} className="flex gap-3">
                <span className="flex-shrink-0 w-6 h-6 rounded-full bg-[var(--ps-blue)] text-white text-xs flex items-center justify-center font-medium">
                  {i + 1}
                </span>
                <p className="text-sm text-[var(--ps-gray-700)] pt-0.5">
                  {step}
                </p>
              </li>
            ))}
          </ol>
        ) : (
          <p className="text-sm text-[var(--ps-gray-500)]">
            No installation steps available for this part.
          </p>
        )}

        {data.source_url && (
          <a
            href={data.source_url}
            target="_blank"
            rel="noopener noreferrer"
            className="block text-center text-sm font-medium text-white bg-[var(--ps-blue)] hover:bg-[var(--ps-blue-dark)] rounded-lg py-2.5 mt-4 transition-colors"
          >
            View Full Guide on PartSelect
          </a>
        )}
      </div>
    </div>
  );
}
