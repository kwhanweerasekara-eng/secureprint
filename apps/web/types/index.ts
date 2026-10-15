export type UserRole = "USER" | "ADMIN";

export interface User {
  id: string;
  email: string;
  username: string;
  full_name: string;
  role: UserRole;
  is_active: boolean;
}

export interface ApiToken {
  id: string;
  name: string;
  token_prefix: string;
  created_at: string;
  last_used_at: string | null;
  revoked: boolean;
}

export interface ApiTokenCreated extends ApiToken {
  token: string;
}

export interface SecurityAlert {
  id: string;
  event_type: string;
  message: string;
  created_at: string;
  job_id: string | null;
  filename: string | null;
  risk_score: number | null;
  classification: string | null;
  status: string | null;
  categories: Record<string, number>;
}

export type JobStatus =
  | "UPLOADED"
  | "QUEUED"
  | "ANALYZING"
  | "DETECTED"
  | "CLASSIFIED"
  | "AWAITING_DECISION"
  | "SANITIZING"
  | "READY"
  | "PRINTING"
  | "COMPLETED"
  | "BLOCKED"
  | "CANCELLED"
  | "FAILED";

export type JobAction = "PENDING" | "ALLOW_PRINT" | "MASK_AND_PRINT" | "CANCELLED" | "BLOCKED";
export type Classification = "PUBLIC" | "INTERNAL" | "CONFIDENTIAL" | "RESTRICTED";

export interface DetectionSummary {
  category: string;
  count: number;
}

export interface AuditEvent {
  id: string;
  job_id: string | null;
  user_id: string | null;
  event_type: string;
  message: string;
  event_metadata: Record<string, unknown>;
  created_at: string;
}

export interface Job {
  id: string;
  original_filename: string;
  status: JobStatus;
  action: JobAction;
  block_reason: string;
  status_message: string;
  risk_score: number | null;
  classification: Classification | null;
  page_count: number;
  has_text_layer: boolean;
  processing_time_ms: number | null;
  printer_id: string | null;
  created_at: string;
  updated_at: string;
  user_id: string;
}

export interface JobDetail extends Job {
  detections: DetectionSummary[];
  events: AuditEvent[];
}

export interface DashboardStats {
  documents_processed: number;
  public_count: number;
  internal_count: number;
  confidential_count: number;
  restricted_count: number;
  sensitive_detections: number;
  blocked_jobs: number;
  masked_jobs: number;
  successful_jobs: number;
  average_risk_score: number;
  average_processing_time_ms: number;
  classification_distribution: Record<string, number>;
  risk_score_distribution: Record<string, number>;
  detections_by_category: Record<string, number>;
  jobs_over_time: { date: string; count: number }[];
  blocked_vs_allowed: Record<string, number>;
  top_detected_categories: { category: string; count: number }[];
  recent_jobs: {
    id: string;
    filename: string;
    risk_score: number | null;
    classification: string | null;
    status: string;
    created_at: string;
  }[];
  recent_events: {
    id: string;
    job_id: string | null;
    event_type: string;
    message: string;
    created_at: string;
  }[];
}

export interface DetectionRule {
  id: string;
  name: string;
  category: string;
  pattern: string;
  description: string;
  priority: number;
  requires_keyword_context: boolean;
  context_keywords: string;
  enabled: boolean;
}

export interface Keyword {
  id: string;
  category: string;
  term: string;
  enabled: boolean;
}

export interface RiskWeight {
  id: string;
  category: string;
  label: string;
  weight: number;
  enabled: boolean;
}

export interface Policy {
  id: string;
  classification: Classification;
  min_score: number;
  max_score: number;
  require_alert: boolean;
  require_masking: boolean;
  require_watermark: boolean;
  require_footer: boolean;
  allow_printing: boolean;
}

export type PrinterProtocol = "IPP" | "SOCKET";

export interface Printer {
  id: string;
  name: string;
  location: string;
  protocol: PrinterProtocol;
  host: string;
  port: number;
  ipp_path: string;
  use_tls: boolean;
  status: "ONLINE" | "OFFLINE" | "UNKNOWN";
  last_tested_at: string | null;
  last_test_message: string;
  created_at: string;
}
