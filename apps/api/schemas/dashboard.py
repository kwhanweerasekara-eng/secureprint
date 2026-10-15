from pydantic import BaseModel


class DashboardStats(BaseModel):
    documents_processed: int
    public_count: int
    internal_count: int
    confidential_count: int
    restricted_count: int
    sensitive_detections: int
    blocked_jobs: int
    masked_jobs: int
    successful_jobs: int
    average_risk_score: float
    average_processing_time_ms: float
    classification_distribution: dict[str, int]
    risk_score_distribution: dict[str, int]
    detections_by_category: dict[str, int]
    jobs_over_time: list[dict]
    blocked_vs_allowed: dict[str, int]
    top_detected_categories: list[dict]
    recent_jobs: list[dict]
    recent_events: list[dict]
