// Mirrors assetscope/models.py (json mode) + agent/events.py.

export type SourceType =
  | "clinical_trials"
  | "open_targets"
  | "chembl"
  | "pubmed"
  | "internal";

export interface Citation {
  id: string;
  source_type: SourceType;
  source_id: string;
  title: string;
  url: string;
  snippet: string;
}

export interface Asset {
  asset_name: string;
  company: string;
  target: string;
  mechanism: string;
  indication: string;
  phase: string;
  latest_readout: string;
  source_ids: string[];
  unresolved_source_ids: string[];
  verified: boolean;
}

export type ClaimStatus = "supported" | "unverified" | "dropped";

export interface Claim {
  id: string;
  text: string;
  source_ids: string[];
  status: ClaimStatus;
  guard_note: string;
}

export interface Landscape {
  query: string;
  plan: string[];
  assets: Asset[];
  claims: Claim[];
  narrative: string;
  citations: Citation[];
  tool_calls: number;
  iterations: number;
  dropped_claims: number;
  unverified_claims: number;
  limitations: string;
}

export type EventType =
  | "status"
  | "plan"
  | "message"
  | "tool_call"
  | "tool_result"
  | "guard"
  | "landscape"
  | "error"
  | "done";

export interface AgentEvent {
  type: EventType;
  data: Record<string, any>;
}

export interface LandscapeSummary {
  id: string;
  query: string;
  created_at: string;
  n_assets: number;
  tool_calls: number;
  dropped_claims: number;
}

export interface GuardReport {
  total_claims: number;
  supported_claims: number;
  unverified_claims: number;
  dropped_claims: number;
  flagged_assets: number;
  citation_coverage: number;
  notes: string[];
}
