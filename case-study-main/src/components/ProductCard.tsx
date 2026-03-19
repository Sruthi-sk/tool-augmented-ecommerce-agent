"use client";

import { DetailData } from "@/types/chat";

interface Props {
  data: DetailData;
}

export default function ProductCard({ data }: Props) {
  const name = data.name || data.part_name || "Unknown Part";
  const partNumber = data.part_number || "";
  const compatibleModels = data.compatible_models || [];
  const symptoms = data.symptoms || [];
  const installSteps = data.installation_steps || [];

  return (
    <div className="space-y-4">
      {/* Header card */}
      <div className="bg-white rounded-xl border border-[var(--ps-gray-200)] overflow-hidden">
        <div className="p-4 border-b border-[var(--ps-gray-200)] bg-[var(--ps-gray-50)]">
          <h3 className="font-semibold text-lg text-[var(--ps-gray-900)]">
            {name}
          </h3>
          <div className="flex items-center gap-2 mt-1">
            {partNumber && (
              <span className="text-xs text-[var(--ps-gray-500)]">
                Part # {partNumber}
              </span>
            )}
            {data.manufacturer_part_number && (
              <>
                <span className="text-xs text-[var(--ps-gray-300)]">•</span>
                <span className="text-xs text-[var(--ps-gray-500)]">
                  Mfr # {data.manufacturer_part_number}
                </span>
              </>
            )}
          </div>
        </div>

        <div className="p-4 space-y-4">
          {/* Price & stock row */}
          {data.price && (
            <div className="flex items-center justify-between">
              <span className="text-2xl font-bold text-[var(--ps-gray-900)]">
                ${data.price}
              </span>
              {data.in_stock !== undefined && (
                <span
                  className={`text-xs font-medium px-2.5 py-1 rounded-full ${
                    data.in_stock
                      ? "bg-green-50 text-[var(--ps-green)]"
                      : "bg-red-50 text-[var(--ps-red)]"
                  }`}
                >
                  {data.in_stock ? "In Stock" : "Out of Stock"}
                </span>
              )}
            </div>
          )}

          {/* Quick specs */}
          <div className="grid grid-cols-2 gap-2">
            {data.brand && (
              <div className="bg-[var(--ps-gray-50)] rounded-lg px-3 py-2">
                <p className="text-[10px] uppercase tracking-wider text-[var(--ps-gray-500)]">
                  Brand
                </p>
                <p className="text-sm font-medium text-[var(--ps-gray-900)]">
                  {data.brand}
                </p>
              </div>
            )}
            {data.appliance_type && (
              <div className="bg-[var(--ps-gray-50)] rounded-lg px-3 py-2">
                <p className="text-[10px] uppercase tracking-wider text-[var(--ps-gray-500)]">
                  Appliance
                </p>
                <p className="text-sm font-medium text-[var(--ps-gray-900)] capitalize">
                  {data.appliance_type}
                </p>
              </div>
            )}
            {data.install_difficulty && (
              <div className="bg-[var(--ps-gray-50)] rounded-lg px-3 py-2">
                <p className="text-[10px] uppercase tracking-wider text-[var(--ps-gray-500)]">
                  Difficulty
                </p>
                <p className="text-sm font-medium text-[var(--ps-gray-900)]">
                  {data.install_difficulty}
                </p>
              </div>
            )}
            {data.install_time && (
              <div className="bg-[var(--ps-gray-50)] rounded-lg px-3 py-2">
                <p className="text-[10px] uppercase tracking-wider text-[var(--ps-gray-500)]">
                  Install Time
                </p>
                <p className="text-sm font-medium text-[var(--ps-gray-900)]">
                  {data.install_time}
                </p>
              </div>
            )}
          </div>

          {/* Description */}
          {data.description && (
            <div>
              <p className="text-xs font-medium text-[var(--ps-gray-500)] uppercase tracking-wider mb-1">
                Description
              </p>
              <p className="text-sm text-[var(--ps-gray-700)] leading-relaxed">
                {data.description}
              </p>
            </div>
          )}

          {/* Symptoms this part fixes */}
          {symptoms.length > 0 && (
            <div>
              <p className="text-xs font-medium text-[var(--ps-gray-500)] uppercase tracking-wider mb-2">
                Fixes These Symptoms
              </p>
              <div className="flex flex-wrap gap-1.5">
                {symptoms.map((s, i) => (
                  <span
                    key={i}
                    className="text-xs bg-orange-50 text-[var(--ps-orange)] px-2 py-1 rounded-full"
                  >
                    {s.replace(/-/g, " ")}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Compatible models preview */}
          {compatibleModels.length > 0 && (
            <div>
              <p className="text-xs font-medium text-[var(--ps-gray-500)] uppercase tracking-wider mb-2">
                Some Compatible Models
              </p>
              <div className="flex flex-wrap gap-1.5">
                {compatibleModels.slice(0, 8).map((m, i) => (
                  <span
                    key={i}
                    className="text-xs bg-blue-50 text-[var(--ps-blue)] px-2 py-1 rounded font-mono"
                  >
                    {m}
                  </span>
                ))}
                {compatibleModels.length > 8 && (
                  <span className="text-xs text-[var(--ps-gray-500)] px-2 py-1">
                    + more
                  </span>
                )}
              </div>
            </div>
          )}

          {/* Installation preview */}
          {installSteps.length > 0 && (
            <div>
              <p className="text-xs font-medium text-[var(--ps-gray-500)] uppercase tracking-wider mb-2">
                Installation Reviews
              </p>
              <ol className="space-y-1.5">
                {installSteps.slice(0, 3).map((step, i) => (
                  <li key={i} className="flex gap-2 text-sm text-[var(--ps-gray-700)]">
                    <span className="flex-shrink-0 w-5 h-5 rounded-full bg-[var(--ps-blue-light)] text-[var(--ps-blue)] text-xs flex items-center justify-center font-medium">
                      {i + 1}
                    </span>
                    <span className="leading-5">{step}</span>
                  </li>
                ))}
                {installSteps.length > 3 && (
                  <li className="text-xs text-[var(--ps-gray-500)] ml-7">
                    +{installSteps.length - 3} more steps
                  </li>
                )}
              </ol>
            </div>
          )}

          {/* CTA */}
          {data.source_url && (
            <a
              href={data.source_url}
              target="_blank"
              rel="noopener noreferrer"
              className="block text-center text-sm font-medium text-white bg-[var(--ps-blue)] hover:bg-[var(--ps-blue-dark)] rounded-lg py-2.5 transition-colors mt-2"
            >
              View on PartSelect
            </a>
          )}
        </div>
      </div>
    </div>
  );
}
