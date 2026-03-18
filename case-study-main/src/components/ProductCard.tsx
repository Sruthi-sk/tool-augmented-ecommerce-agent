"use client";

import { DetailData } from "@/types/chat";

interface Props {
  data: DetailData;
}

export default function ProductCard({ data }: Props) {
  const name = data.name || data.part_name || "Unknown Part";
  const partNumber = data.part_number || "";

  return (
    <div className="bg-white rounded-xl border border-[var(--ps-gray-200)] overflow-hidden">
      <div className="p-4 border-b border-[var(--ps-gray-200)] bg-[var(--ps-gray-50)]">
        <h3 className="font-semibold text-[var(--ps-gray-900)]">{name}</h3>
        {partNumber && (
          <p className="text-xs text-[var(--ps-gray-500)] mt-0.5">
            Part # {partNumber}
          </p>
        )}
      </div>

      <div className="p-4 space-y-3">
        {data.price && (
          <div className="flex items-center justify-between">
            <span className="text-lg font-bold text-[var(--ps-gray-900)]">
              {data.price}
            </span>
            {data.in_stock !== undefined && (
              <span
                className={`text-xs font-medium px-2 py-1 rounded-full ${
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

        {data.description && (
          <p className="text-sm text-[var(--ps-gray-700)]">{data.description}</p>
        )}

        {data.manufacturer_part_number && (
          <p className="text-xs text-[var(--ps-gray-500)]">
            Mfr # {data.manufacturer_part_number}
          </p>
        )}

        {data.source_url && (
          <a
            href={data.source_url}
            target="_blank"
            rel="noopener noreferrer"
            className="block text-center text-sm font-medium text-white bg-[var(--ps-blue)] hover:bg-[var(--ps-blue-dark)] rounded-lg py-2.5 transition-colors"
          >
            View on PartSelect
          </a>
        )}
      </div>
    </div>
  );
}
