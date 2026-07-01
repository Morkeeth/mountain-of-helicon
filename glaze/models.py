from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class ConnectorResult:
    source: str
    source_ref: str
    type: str
    title: str
    content: str
    created_at: str
    tags: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


@dataclass
class GlazeCube:
    id: str
    source: str
    source_ref: str
    type: str
    title: str
    content: str
    content_hash: str
    created_at: str
    valid_from: str
    summary: str = ""
    last_reinforced: str = ""
    confidence: float = 1.0
    review_status: str = "pending"
    review_count: int = 0
    spin_count: int = 0
    novelty_score: float | None = None
    novelty_action: str | None = None
    tags: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    merged_into: str | None = None


@dataclass
class Review:
    id: int | None
    cube_id: str
    decision: str
    notes: str = ""
    time_to_review_seconds: float = 0.0
    cube_age_days: float = 0.0
    cube_type: str = ""
    cube_source: str = ""
    reviewed_at: str = ""
    session_id: str = ""


@dataclass
class Pattern:
    id: str
    name: str
    description: str
    pattern_type: str
    data_points: int = 0
    confidence: float = 0.5
    last_reinforced: str = ""
    last_challenged: str = ""
    created_at: str = ""
    updated_at: str = ""
    evidence: list = field(default_factory=list)
    status: str = "active"
    metadata: dict = field(default_factory=dict)


@dataclass
class AuditResult:
    audit_type: str
    target_type: str
    target_id: str
    finding: str
    severity: str
    proposed_action: str = ""
    human_decision: str | None = None
    details: dict = field(default_factory=dict)
    audited_at: str = ""
    resolved_at: str | None = None
