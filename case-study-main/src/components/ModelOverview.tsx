"use client";

import { DetailData } from "@/types/chat";

interface Props {
  data: DetailData;
}

export default function ModelOverview({ data }: Props) {
  const symptoms = data.common_symptoms || [];
  const categories = data.part_categories || [];
  const sections = data.sections || [];

  return (
    <div className="bg-white rounded-xl border border-[var(--ps-gray-200)] overflow-hidden">
      {/* Header */}
      <div className="p-4 border-b border-[var(--ps-gray-200)] bg-[var(--ps-blue-light)]">
        <h3 className="font-semibold text-[var(--ps-blue)]">
          Model Overview
        </h3>
        {data.model_title && (
          <p className="text-sm text-[var(--ps-gray-700)] mt-0.5">
            {data.model_title}
          </p>
        )}
      </div>

      <div className="p-4 space-y-4">
        {/* Brand & Type */}
        {(data.brand || data.appliance_type) && (
          <div className="flex gap-2 flex-wrap">
            {data.brand && (
              <span className="text-xs font-medium bg-[var(--ps-gray-50)] text-[var(--ps-gray-700)] border border-[var(--ps-gray-200)] rounded-full px-3 py-1">
                {data.brand}
              </span>
            )}
            {data.appliance_type && (
              <span className="text-xs font-medium bg-[var(--ps-blue-light)] text-[var(--ps-blue)] border border-blue-200 rounded-full px-3 py-1 capitalize">
                {data.appliance_type}
              </span>
            )}
          </div>
        )}

        {/* Common Symptoms */}
        {symptoms.length > 0 && (
          <div>
            <h4 className="text-xs font-semibold text-[var(--ps-gray-500)] uppercase tracking-wide mb-2">
              Common Symptoms
            </h4>
            <div className="flex flex-wrap gap-1.5">
              {symptoms.slice(0, 10).map((symptom, i) => (
                <span
                  key={i}
                  className="text-xs bg-orange-50 text-[var(--ps-orange)] border border-orange-200 rounded-lg px-2.5 py-1"
                >
                  {symptom}
                </span>
              ))}
            </div>
          </div>
        )}

        {/* Part Categories */}
        {categories.length > 0 && (
          <div>
            <h4 className="text-xs font-semibold text-[var(--ps-gray-500)] uppercase tracking-wide mb-2">
              Part Categories
            </h4>
            <div className="space-y-1">
              {categories.slice(0, 12).map((cat, i) => (
                <div
                  key={i}
                  className="flex items-center justify-between text-sm text-[var(--ps-gray-700)] py-1 px-2 rounded hover:bg-[var(--ps-gray-50)] transition-colors"
                >
                  <span>{cat.name}</span>
                  {cat.count != null && (
                    <span className="text-xs text-[var(--ps-gray-400)]">
                      {cat.count}
                    </span>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Sections */}
        {sections.length > 0 && symptoms.length === 0 && categories.length === 0 && (
          <div>
            <h4 className="text-xs font-semibold text-[var(--ps-gray-500)] uppercase tracking-wide mb-2">
              Available Sections
            </h4>
            <div className="space-y-1">
              {sections.slice(0, 10).map((section, i) => (
                <p key={i} className="text-sm text-[var(--ps-gray-600)] py-0.5">
                  {section}
                </p>
              ))}
            </div>
          </div>
        )}

        {/* Source link */}
        {data.source_url && (
          <div className="pt-2 border-t border-[var(--ps-gray-200)]">
            <a
              href={data.source_url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-xs text-[var(--ps-blue)] hover:underline"
            >
              View on PartSelect &rarr;
            </a>
          </div>
        )}
      </div>
    </div>
  );
}
