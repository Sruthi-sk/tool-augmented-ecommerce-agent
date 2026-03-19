"use client";

import { DetailData } from "@/types/chat";

interface Props {
  data: DetailData;
}

export default function CompatibilityResult({ data }: Props) {
  const isCompatible = data.compatible === true;
  const isIncompatible = data.compatible === false;
  const isModelNotFound = data.model_not_found === true;
  const partName = data.part_name || data.name || data.part_number || "Part";
  const modelLabel = data.model_description
    ? `${data.model_description} (${data.model_number})`
    : data.model_number || "Unknown Model";

  return (
    <div className="bg-white rounded-xl border border-[var(--ps-gray-200)] overflow-hidden">
      {/* Status header */}
      <div
        className={`p-4 ${
          isCompatible
            ? "bg-green-50"
            : isModelNotFound
            ? "bg-amber-50"
            : "bg-red-50"
        }`}
      >
        <div className="flex items-center gap-3">
          <div
            className={`w-10 h-10 rounded-full flex items-center justify-center text-xl flex-shrink-0 ${
              isCompatible
                ? "bg-[var(--ps-green)] text-white"
                : isModelNotFound
                ? "bg-amber-500 text-white"
                : "bg-[var(--ps-red)] text-white"
            }`}
          >
            {isCompatible ? "✓" : isModelNotFound ? "?" : "✗"}
          </div>
          <div>
            <h3 className="font-semibold text-[var(--ps-gray-900)]">
              {isCompatible
                ? "Compatible"
                : isModelNotFound
                ? "Model Not Found"
                : "Not Compatible"}
            </h3>
            <p className="text-sm text-[var(--ps-gray-500)]">
              {partName} + {modelLabel}
            </p>
          </div>
        </div>
      </div>

      {/* Detail rows */}
      <div className="p-4 space-y-3">
        <div className="space-y-2">
          {data.part_number && (
            <div className="flex justify-between text-sm">
              <span className="text-[var(--ps-gray-500)]">Part</span>
              <span className="font-medium font-mono">{data.part_number}</span>
            </div>
          )}
          {partName !== data.part_number && (
            <div className="flex justify-between text-sm">
              <span className="text-[var(--ps-gray-500)]">Part Name</span>
              <span className="font-medium text-right max-w-[60%]">{partName}</span>
            </div>
          )}
          {data.model_number && (
            <div className="flex justify-between text-sm">
              <span className="text-[var(--ps-gray-500)]">Model</span>
              <span className="font-medium font-mono">{data.model_number}</span>
            </div>
          )}
          {data.model_description && (
            <div className="flex justify-between text-sm">
              <span className="text-[var(--ps-gray-500)]">Appliance</span>
              <span className="font-medium text-right max-w-[60%]">{data.model_description}</span>
            </div>
          )}
        </div>

        {/* Compatibility note */}
        {isCompatible && (
          <div className="bg-green-50 rounded-lg p-3 text-sm text-[var(--ps-green)]">
            This part is confirmed to fit model {data.model_number}.
          </div>
        )}
        {isModelNotFound && (
          <div className="bg-amber-50 rounded-lg p-3 text-sm text-amber-700">
            Model {data.model_number} was not found on PartSelect.
            Please double-check your model number.
          </div>
        )}
        {isIncompatible && !isModelNotFound && (
          <div className="bg-red-50 rounded-lg p-3 text-sm text-[var(--ps-red)]">
            This part does not fit model {data.model_number}.
          </div>
        )}
        {!isCompatible && !isIncompatible && !isModelNotFound && data.compatible_models_count !== undefined && data.compatible_models_count > 0 && (
          <div className="bg-amber-50 rounded-lg p-3 text-sm text-amber-700">
            Model {data.model_number} was not found among the models
            indexed in our database.
          </div>
        )}

        {/* Price if available */}
        {data.price && (
          <div className="flex items-center justify-between pt-2 border-t border-[var(--ps-gray-100)]">
            <span className="text-sm text-[var(--ps-gray-500)]">Price</span>
            <span className="text-lg font-bold text-[var(--ps-gray-900)]">
              ${data.price}
            </span>
          </div>
        )}

        {/* CTAs */}
        {isModelNotFound && data.similar_models_url && (
          <a
            href={data.similar_models_url}
            target="_blank"
            rel="noopener noreferrer"
            className="block text-center text-sm font-medium text-white bg-amber-500 hover:bg-amber-600 rounded-lg py-2.5 mt-1 transition-colors"
          >
            Search for Similar Models
          </a>
        )}
        {isModelNotFound && data.find_model_help_url && (
          <a
            href={data.find_model_help_url}
            target="_blank"
            rel="noopener noreferrer"
            className="block text-center text-sm font-medium text-[var(--ps-blue)] border border-[var(--ps-blue)] hover:bg-blue-50 rounded-lg py-2.5 transition-colors"
          >
            Help Finding Your Model Number
          </a>
        )}
        {!isModelNotFound && data.model_details_url && (
          <a
            href={data.model_details_url}
            target="_blank"
            rel="noopener noreferrer"
            className="block text-center text-sm font-medium text-white bg-[var(--ps-blue)] hover:bg-[var(--ps-blue-dark)] rounded-lg py-2.5 mt-1 transition-colors"
          >
            {isIncompatible ? "View Model Details" : "View on PartSelect"}
          </a>
        )}
        {data.source_url && !data.model_details_url && (
          <a
            href={data.source_url}
            target="_blank"
            rel="noopener noreferrer"
            className="block text-center text-sm font-medium text-white bg-[var(--ps-blue)] hover:bg-[var(--ps-blue-dark)] rounded-lg py-2.5 mt-1 transition-colors"
          >
            {isCompatible
              ? "View on PartSelect"
              : "Check Full Compatibility on PartSelect"}
          </a>
        )}
      </div>
    </div>
  );
}
