from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum
import uuid


class ConfidenceLevel(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ValidationStatus(str, Enum):
    MATCH = "match"
    MISMATCH = "mismatch"
    UNCERTAIN = "uncertain"
    MISSING = "missing"


class DecisionType(str, Enum):
    AUTO_APPROVE = "auto_approve"
    FLAG_FOR_REVIEW = "flag_for_review"
    DRAFT_AMENDMENT = "draft_amendment"


class PipelineStatus(str, Enum):
    PENDING = "pending"
    EXTRACTING = "extracting"
    VALIDATING = "validating"
    ROUTING = "routing"
    COMPLETED = "completed"
    FAILED = "failed"


class ShipmentStatus(str, Enum):
    PROCESSING = "processing"
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    AMENDMENT_REQUESTED = "amendment_requested"
    FAILED = "failed"


def confidence_level(score: float) -> ConfidenceLevel:
    if score >= 0.85:
        return ConfidenceLevel.HIGH
    elif score >= 0.60:
        return ConfidenceLevel.MEDIUM
    return ConfidenceLevel.LOW


def generate_id() -> str:
    return str(uuid.uuid4())[:12]


class ExtractedField(BaseModel):
    field_name: str
    value: Optional[str] = None
    confidence: float = Field(ge=0.0, le=1.0)
    confidence_level: Optional[ConfidenceLevel] = None
    source_location: Optional[str] = None

    def model_post_init(self, __context: Any) -> None:
        if self.confidence_level is None:
            self.confidence_level = confidence_level(self.confidence)


class ExtractionResult(BaseModel):
    document_id: str = Field(default_factory=generate_id)
    document_type: str = "unknown"
    file_name: str = ""
    fields: List[ExtractedField] = []
    raw_text_preview: Optional[str] = None
    extraction_timestamp: datetime = Field(default_factory=datetime.utcnow)
    model_used: str = ""
    processing_time_ms: int = 0
    total_cost_usd: float = 0.0

    def get_field(self, name: str) -> Optional[ExtractedField]:
        for f in self.fields:
            if f.field_name == name:
                return f
        return None

    def get_field_value(self, name: str) -> Optional[str]:
        field = self.get_field(name)
        return field.value if field else None


class FieldValidation(BaseModel):
    field_name: str
    status: ValidationStatus
    extracted_value: Optional[str] = None
    expected_value: Optional[str] = None
    rule_description: str = ""
    confidence: float = 0.0
    reasoning: str = ""


class ValidationResult(BaseModel):
    document_id: str = ""
    customer_id: str = ""
    validations: List[FieldValidation] = []
    overall_score: float = 0.0
    total_fields: int = 0
    matched_fields: int = 0
    mismatched_fields: int = 0
    uncertain_fields: int = 0
    missing_fields: int = 0
    validation_timestamp: datetime = Field(default_factory=datetime.utcnow)
    summary: str = ""

    def model_post_init(self, __context: Any) -> None:
        if self.validations and self.total_fields == 0:
            self.total_fields = len(self.validations)
            self.matched_fields = sum(1 for v in self.validations if v.status == ValidationStatus.MATCH)
            self.mismatched_fields = sum(1 for v in self.validations if v.status == ValidationStatus.MISMATCH)
            self.uncertain_fields = sum(1 for v in self.validations if v.status == ValidationStatus.UNCERTAIN)
            self.missing_fields = sum(1 for v in self.validations if v.status == ValidationStatus.MISSING)


class Discrepancy(BaseModel):
    field_name: str
    found: Optional[str] = None
    expected: Optional[str] = None
    severity: str = "warning"


class RoutingDecision(BaseModel):
    document_id: str = ""
    decision: DecisionType = DecisionType.FLAG_FOR_REVIEW
    reasoning: str = ""
    confidence: float = 0.0
    discrepancies: List[Discrepancy] = []
    amendment_draft: Optional[str] = None
    decision_timestamp: datetime = Field(default_factory=datetime.utcnow)


class PipelineRun(BaseModel):
    run_id: str = Field(default_factory=generate_id)
    document_id: str = ""
    file_name: str = ""
    document_type: str = ""
    customer_id: str = "CUST-001"
    status: PipelineStatus = PipelineStatus.PENDING
    extraction_result: Optional[ExtractionResult] = None
    validation_result: Optional[ValidationResult] = None
    routing_decision: Optional[RoutingDecision] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    error: Optional[str] = None
    processing_time_ms: int = 0
    total_cost_usd: float = 0.0


class CrossValidation(BaseModel):
    rule_name: str
    field_name: str
    status: str = "consistent"
    values_found: Dict[str, Optional[str]] = {}
    reasoning: str = ""


class CrossValidationResult(BaseModel):
    shipment_id: str = ""
    cross_validations: List[CrossValidation] = []
    overall_consistent: bool = True
    summary: str = ""


class ShipmentRecord(BaseModel):
    shipment_id: str = Field(default_factory=generate_id)
    customer_id: str = "CUST-001"
    email_subject: str = ""
    email_from: str = ""
    documents: List[PipelineRun] = []
    cross_validation_result: Optional[CrossValidationResult] = None
    status: ShipmentStatus = ShipmentStatus.PROCESSING
    decision: Optional[DecisionType] = None
    amendment_draft: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    document_count: int = 0


class AgentMetrics(BaseModel):
    agent_name: str
    calls: int = 0
    total_tokens: int = 0
    total_cost_usd: float = 0.0
    avg_latency_ms: float = 0.0
    errors: int = 0
