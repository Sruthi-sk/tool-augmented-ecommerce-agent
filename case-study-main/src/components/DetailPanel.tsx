"use client";

import { DetailData } from "@/types/chat";
import ProductCard from "./ProductCard";
import CompatibilityResult from "./CompatibilityResult";
import InstallationGuide from "./InstallationGuide";
import TroubleshootingFlow from "./TroubleshootingFlow";
import SearchResults from "./SearchResults";
import ModelOverview from "./ModelOverview";

interface Props {
  responseType: string | null;
  data: DetailData | null;
}

export default function DetailPanel({ responseType, data }: Props) {
  if (!data || !responseType) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-center px-6">
        <div className="w-16 h-16 rounded-full bg-[var(--ps-blue-light)] flex items-center justify-center mb-4">
          <svg className="w-8 h-8 text-[var(--ps-blue)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9.75 3.104v5.714a2.25 2.25 0 01-.659 1.591L5 14.5M9.75 3.104c-.251.023-.501.05-.75.082m.75-.082a24.301 24.301 0 014.5 0m0 0v5.714c0 .597.237 1.17.659 1.591L19.8 15.3M14.25 3.104c.251.023.501.05.75.082M19.8 15.3l-1.57.393A9.065 9.065 0 0112 15a9.065 9.065 0 00-6.23.693L5 14.5m14.8.8l1.402 1.402c1.232 1.232.65 3.318-1.067 3.611A48.309 48.309 0 0112 21c-2.773 0-5.491-.235-8.135-.687-1.718-.293-2.3-2.379-1.067-3.61L5 14.5" />
          </svg>
        </div>
        <h3 className="font-semibold text-[var(--ps-gray-900)] mb-2">
          PartSelect Assistant
        </h3>
        <p className="text-sm text-[var(--ps-gray-500)] max-w-xs">
          Ask me about refrigerator or dishwasher parts. I can help with part lookup, compatibility, installation, and troubleshooting.
        </p>
        <div className="mt-6 space-y-2 text-left w-full max-w-xs">
          <p className="text-xs font-medium text-[var(--ps-gray-500)] uppercase tracking-wide">Try asking:</p>
          <div className="space-y-1.5">
            {[
              "Find a water filter for my Whirlpool fridge",
              "Is PS11752778 compatible with WDT780SAEM1?",
              "My ice maker isn't working",
            ].map((example) => (
              <p key={example} className="text-xs text-[var(--ps-gray-500)] bg-[var(--ps-gray-50)] rounded-lg px-3 py-2">
                &quot;{example}&quot;
              </p>
            ))}
          </div>
        </div>
      </div>
    );
  }

  switch (responseType) {
    case "product":
      return <ProductCard data={data} />;
    case "compatibility":
      return <CompatibilityResult data={data} />;
    case "installation":
      return <InstallationGuide data={data} />;
    case "troubleshooting":
      return <TroubleshootingFlow data={data} />;
    case "search_results":
      return <SearchResults data={data} />;
    case "model_overview":
      return <ModelOverview data={data} />;
    default:
      return <ProductCard data={data} />;
  }
}
