"use client";

import { DetailData } from "@/types/chat";

interface Props {
  data: DetailData;
}

const LIKELIHOOD_COLORS: Record<string, string> = {
  high: "bg-red-50 text-[var(--ps-red)] border-red-200",
  medium: "bg-yellow-50 text-yellow-700 border-yellow-200",
  low: "bg-[var(--ps-gray-50)] text-[var(--ps-gray-500)] border-[var(--ps-gray-200)]",
};

export default function TroubleshootingFlow({ data }: Props) {
  const causes = data.causes || [];

  return (
    <div className="bg-white rounded-xl border border-[var(--ps-gray-200)] overflow-hidden">
      <div className="p-4 border-b border-[var(--ps-gray-200)] bg-orange-50">
        <h3 className="font-semibold text-[var(--ps-orange)]">
          Troubleshooting
        </h3>
        {data.matched_symptom && (
          <p className="text-xs text-[var(--ps-gray-500)] mt-0.5 capitalize">
            {data.appliance_type}: {data.matched_symptom}
          </p>
        )}
      </div>

      <div className="p-4 space-y-3">
        {causes.length > 0 ? (
          causes.map((cause, i) => (
            <div
              key={i}
              className={`rounded-lg border p-3 ${LIKELIHOOD_COLORS[cause.likelihood] || LIKELIHOOD_COLORS.low}`}
            >
              <div className="flex items-start justify-between gap-2">
                <div>
                  <p className="text-sm font-medium">{cause.cause}</p>
                  {cause.part_type && (
                    <p className="text-xs mt-1 opacity-75">
                      Likely part: {cause.part_type}
                    </p>
                  )}
                </div>
                <span className="text-[10px] uppercase font-semibold opacity-60 flex-shrink-0">
                  {cause.likelihood}
                </span>
              </div>
            </div>
          ))
        ) : (
          <p className="text-sm text-[var(--ps-gray-500)]">
            {data.message || "No specific troubleshooting data available."}
          </p>
        )}

        {data.source_url && (
          <a
            href={data.source_url}
            target="_blank"
            rel="noopener noreferrer"
            className="block text-center text-sm font-medium text-white bg-[var(--ps-orange)] hover:opacity-90 rounded-lg py-2.5 mt-2 transition-colors"
          >
            Full Repair Guide on PartSelect
          </a>
        )}
      </div>
    </div>
  );
}
