from pydantic import BaseModel, Field
from typing import Optional


class FormalConditions(BaseModel):
    deadline: Optional[str] = None
    deposit: Optional[str] = None
    penalties: Optional[str] = None
    experience_required: Optional[str] = None


class ExtractedTender(BaseModel):
    """Stage 1 output — extracted facts from tender text."""
    subject: str
    tech_categories: list[str] = Field(default_factory=list)
    required_certs: list[str] = Field(default_factory=list)
    buyer_sector: str = ""
    formal_conditions: FormalConditions = Field(default_factory=FormalConditions)
    location: str = ""
    estimated_value: Optional[str] = None


class ScoringResult(BaseModel):
    """Stage 2 output — final scoring result."""
    match_score: int = Field(ge=0, le=100)
    is_relevant: bool
    reasoning: str
    key_requirements: list[str] = Field(max_length=5)
    strategic_advantage: str
    risk_factors: list[str] = Field(default_factory=list)


class AnalyzeRequest(BaseModel):
    """API input."""
    tender_text: str = Field(min_length=50, description="Raw tender text")


class AnalyzeResponse(BaseModel):
    """Full API response — both stages combined."""
    extracted: ExtractedTender
    scoring: ScoringResult
