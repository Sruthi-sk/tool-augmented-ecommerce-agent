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
  brand?: string;
  availability?: string;
  install_difficulty?: string;
  install_time?: string;
  replace_parts?: string;
  symptoms_text?: string;
  repair_rating?: string;
  installation_steps?: string[];
  symptoms?: string[];

  // compatibility
  compatible?: boolean;
  model_number?: string;
  compatible_models_count?: number;
  model_not_found?: boolean;
  model_description?: string;
  model_details_url?: string;
  similar_models_url?: string;
  find_model_help_url?: string;

  // installation
  steps?: string[];

  // troubleshooting
  causes?: Cause[];
  symptom?: string;
  matched_symptom?: string;
  message?: string;

  // model_overview
  model_title?: string;
  common_symptoms?: string[];
  sections?: string[];
  part_categories?: { name: string; count?: number }[];

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
