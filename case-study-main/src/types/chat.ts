export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  detailData?: DetailData | null;
  responseType?: string | null;
  sourceUrl?: string | null;
  suggestedActions?: string[];
  isLoading?: boolean;
}

export interface DetailData {
  // search_results
  parts?: PartSummary[];
  query?: string;
  appliance_type?: string;

  // product / compatibility / installation
  part_number?: string;
  part_name?: string;
  name?: string;
  price?: string;
  in_stock?: boolean;
  description?: string;
  source_url?: string;
  manufacturer_part_number?: string;
  compatible_models?: string[];

  // compatibility
  compatible?: boolean;
  model_number?: string;
  compatible_models_count?: number;

  // installation
  steps?: string[];

  // troubleshooting
  causes?: Cause[];
  symptom?: string;
  matched_symptom?: string;
  message?: string;

  // error
  error?: string;
}

export interface PartSummary {
  part_number: string;
  name: string;
  price: string;
  url: string;
}

export interface Cause {
  cause: string;
  part_type: string | null;
  likelihood: string;
}

export interface ChatResponse {
  type: string;
  message: string;
  detail_data: DetailData | null;
  response_type: string | null;
  source_url: string | null;
  suggested_actions: string[];
  session_id: string;
}
