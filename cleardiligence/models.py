from __future__ import annotations

from datetime import date, datetime, timezone
from enum import Enum
from typing import Literal
from uuid import uuid4
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def uid() -> str:
    return uuid4().hex[:12]


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class Verification(str, Enum):
    VERIFIED = "Verified"
    POTENTIAL = "Potential match"
    UNVERIFIED = "Unverified"
    NOT_FOUND = "Not found"


class RiskTier(str, Enum):
    LOW = "Low"
    MODERATE = "Moderate"
    HIGH = "High"
    INSUFFICIENT = "Insufficient Information"


class RegistryJurisdiction(Model):
    country: str = Field(min_length=2, max_length=100)
    region: str = Field(default="", max_length=100)


class ResearchScope(Model):
    fields: list[Literal["business", "location", "industry", "registration", "leadership", "ownership", "alias", "website"]] = Field(default_factory=lambda: ["business", "location", "industry", "registration", "leadership", "ownership", "alias", "website"])
    sources: list[Literal["company", "registries", "sec", "doj", "media"]] = Field(default_factory=lambda: ["company", "registries", "sec", "doj", "media"])
    topics: list[Literal["fraud", "corruption", "regulatory enforcement", "sanctions", "financial misconduct", "material litigation"]] = Field(default_factory=lambda: ["fraud", "corruption", "regulatory enforcement", "sanctions", "financial misconduct", "material litigation"])
    databases: list[Literal["opencorporates", "tloxp", "clear", "factiva"]] = Field(default_factory=list, max_length=4)
    start_date: date | None = None
    end_date: date | None = None
    depth: Literal["basic", "advanced"] = "advanced"
    max_results: int = Field(default=4, ge=2, le=8)
    registry_jurisdiction: str = Field(default="", max_length=100)
    additional_registry_jurisdictions: list[RegistryJurisdiction] = Field(default_factory=list, max_length=3)

    @model_validator(mode="after")
    def validate_scope(self):
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValueError("The research start date must be on or before the end date")
        if not self.sources:
            raise ValueError("Select at least one research source family")
        if not self.topics:
            raise ValueError("Select at least one adverse-media topic")
        return self


class CompanyInput(Model):
    name: str = Field(min_length=2, max_length=160)
    country: str = Field(min_length=2, max_length=100)
    website: str = Field(default="", max_length=300)
    industry: str = Field(default="", max_length=120)
    purpose: str = Field(default="Vendor onboarding", max_length=300)
    research: ResearchScope = Field(default_factory=ResearchScope)

    @field_validator("name", "country", "website", "industry", "purpose", mode="before")
    @classmethod
    def strip_strings(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator("website")
    @classmethod
    def website_is_http(cls, value):
        if value and (urlparse(value).scheme not in ("http", "https") or not urlparse(value).hostname):
            raise ValueError("Website must be a full http:// or https:// URL")
        return value


class Source(Model):
    id: str = Field(default_factory=uid)
    title: str
    url: str
    content: str
    retrieved_at: str = Field(default_factory=now)
    published_date: str = "Not available"
    synthetic: bool = False
    kind: Literal["web", "official_list", "fixture"] = "web"
    content_sha256: str = ""
    source_family: str = "Public web"
    content_type: str = "Search excerpt"
    date_scope: str = "Not restricted"


class Finding(Model):
    id: str = Field(default_factory=uid)
    category: Literal["profile", "sanctions", "adverse_media"]
    field: str = ""
    claim: str
    source_ids: list[str] = Field(default_factory=list)
    excerpt: str = ""
    extracted_value: str = ""
    verification: Verification = Verification.UNVERIFIED
    relevance: Literal["Supported", "Potential", "Unresolved", "Different entity"] = "Unresolved"
    relevance_reason: str = ""
    nature: Literal["Profile", "Allegation", "Regulatory finding", "Judicial finding", "List record", "Search result"] = "Profile"
    match: Literal["none", "possible", "confirmed"] = "none"
    material: bool = False
    requires_review: bool = False
    evidence_valid: bool = False
    validation_notes: list[str] = Field(default_factory=list)


class Event(Model):
    at: str = Field(default_factory=now)
    stage: str
    status: Literal["running", "complete", "branch", "warning"]
    message: str


class RiskResult(Model):
    tier: RiskTier = RiskTier.INSUFFICIENT
    identity_confidence: str = "Insufficient"
    reasons: list[str] = Field(default_factory=list)
    indicators: list[str] = Field(default_factory=list)
    actions: list[str] = Field(default_factory=list)
    mandatory_escalation: bool = False
    policy_version: str = ""
    policy_snapshot: dict = Field(default_factory=dict)


class ModelAttempt(Model):
    at: str = Field(default_factory=now)
    model: str
    credential: Literal["primary", "backup"] = "primary"
    status: Literal["Succeeded", "Failed"]
    http_status: int | None = None
    message: str


class SearchRun(Model):
    id: str = Field(default_factory=uid)
    at: str = Field(default_factory=now)
    task: str
    label: str
    query: str
    domains: list[str] = Field(default_factory=list)
    fields: list[str] = Field(default_factory=list)
    topic: str = "general"
    start_date: str = ""
    end_date: str = ""
    status: Literal["Planned", "Complete", "Partial", "Failed", "Not requested"] = "Planned"
    source_ids: list[str] = Field(default_factory=list)
    findings_count: int = 0
    message: str = ""
    google_url: str = ""
    source_family: str = ""
    jurisdiction: str = ""
    trigger: str = "Initial scope"
    query_version: str = "legacy"
    search_depth: str = ""
    max_results: int = 0
    retrieval_method: Literal["Search", "Page extraction"] = "Search"
    requested_urls: list[str] = Field(default_factory=list)
    retrieval_status: Literal["Not recorded", "Complete", "Partial", "Failed"] = "Not recorded"
    extraction_status: Literal["Not recorded", "Complete", "Failed"] = "Not recorded"
    model_used: str = ""
    model_attempts: list[ModelAttempt] = Field(default_factory=list)
    recovery_notes: list[str] = Field(default_factory=list)
    rejected_findings_count: int = 0
    retrieval_notes: list[str] = Field(default_factory=list)
    access_notes: list[str] = Field(default_factory=list)
    blocked_urls: list[str] = Field(default_factory=list)


class ManualTask(Model):
    id: str
    title: str
    jurisdiction: str
    registry_url: str = ""
    search_terms: list[str] = Field(default_factory=list)
    reason: str
    access_status: Literal["Manual verification required", "Access barrier observed", "Research unavailable", "No usable indexed record", "Routing unavailable"]
    instructions: list[str] = Field(default_factory=list)
    search_run_ids: list[str] = Field(default_factory=list)
    required: bool = True
    kind: Literal["registry", "database"] = "registry"
    provider: str = ""


class DatabaseCandidate(Model):
    name: str
    company_number: str = ""
    jurisdiction_code: str = ""
    current_status: str = ""
    registered_address: str = ""
    record_url: str
    registry_url: str = ""
    provider_updated_at: str = "Not available"
    source_id: str
    match_status: Literal["Potential match"] = "Potential match"


class DatabaseRun(Model):
    id: str = Field(default_factory=uid)
    at: str = Field(default_factory=now)
    provider: str
    method: Literal["API", "Manual"]
    status: Literal["Complete", "Unavailable", "Failed", "Manual required", "Routing unavailable"]
    jurisdiction: str
    request: dict[str, str | int] = Field(default_factory=dict)
    endpoint: str = ""
    message: str
    total_results: int | None = None
    candidates: list[DatabaseCandidate] = Field(default_factory=list)


class Assessment(Model):
    workflow_version: str = "legacy"
    id: str = Field(default_factory=uid)
    created_at: str = Field(default_factory=now)
    company: CompanyInput
    mode: Literal["Demo", "Live"]
    scenario: str = ""
    sources: list[Source] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)
    events: list[Event] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    coverage: dict[str, str] = Field(default_factory=dict)
    risk: RiskResult = Field(default_factory=RiskResult)
    screening_metadata: dict = Field(default_factory=dict)
    search_runs: list[SearchRun] = Field(default_factory=list)
    database_runs: list[DatabaseRun] = Field(default_factory=list)
    manual_tasks: list[ManualTask] = Field(default_factory=list)
    completed: bool = False


class Review(Model):
    id: str = Field(default_factory=uid)
    assessment_id: str
    finding_id: str = ""
    task_id: str = ""
    reference_url: str = Field(default="", max_length=2000)
    analyst: str = Field(min_length=2, max_length=100)
    action: Literal["Reviewed", "Escalated", "False positive", "Confirmed match", "Proceed", "Hold", "Reject", "Completed", "Unavailable", "Reopened"]
    rationale: str = Field(min_length=10, max_length=4000)
    at: str = Field(default_factory=now)
    actor_type: Literal["human"] = "human"


    @model_validator(mode="after")
    def validate_review_target(self):
        if self.task_id and self.finding_id:
            raise ValueError("A review must target one task or one finding")
        if self.reference_url:
            parsed = urlparse(self.reference_url)
            if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password:
                raise ValueError("Evidence reference must be an http(s) URL without credentials")
        return self
