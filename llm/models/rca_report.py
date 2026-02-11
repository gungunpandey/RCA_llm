"""
RCA Report Data Model

Defines the final output structure for comprehensive RCA reports.
"""

from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime
from .tool_results import (
    FiveWhysResult,
    FishboneResult,
    FaultTreeResult,
    TimelineResult,
    SimilarFailuresResult
)


class RootCause(BaseModel):
    """Individual root cause with confidence score."""
    cause: str = Field(..., description="Root cause description")
    category: str = Field(..., description="Category (mechanical, electrical, process, control)")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score (0-1)")
    supporting_evidence: List[str] = Field(default_factory=list, description="Evidence from analysis")


class Recommendation(BaseModel):
    """Actionable recommendation to prevent recurrence."""
    action: str = Field(..., description="Recommended action")
    priority: str = Field(..., description="Priority level: critical, high, medium, low")
    timeframe: str = Field(..., description="Suggested timeframe for implementation")
    responsible_party: Optional[str] = Field(None, description="Who should implement this")
    estimated_cost: Optional[str] = Field(None, description="Estimated cost if applicable")


class RCAReport(BaseModel):
    """
    Final comprehensive RCA report.
    
    This is the primary output of the RCA system, containing all analysis results
    and recommendations.
    """
    
    failure_id: str = Field(..., description="Unique identifier for this failure analysis")
    equipment_name: str = Field(..., description="Equipment that failed")
    
    # Root causes ranked by confidence
    root_causes: List[RootCause] = Field(..., description="Identified root causes, ranked by confidence")
    contributing_factors: List[str] = Field(default_factory=list, description="Contributing factors")
    
    # Analysis results from all tools
    five_whys_analysis: Optional[FiveWhysResult] = Field(None, description="5 Whys analysis results")
    fishbone_analysis: Optional[FishboneResult] = Field(None, description="Fishbone diagram results")
    fault_tree_analysis: Optional[FaultTreeResult] = Field(None, description="Fault tree analysis results")
    timeline_analysis: Optional[TimelineResult] = Field(None, description="Timeline analysis results")
    similar_failures: Optional[SimilarFailuresResult] = Field(None, description="Similar failures found")
    
    # Recommendations
    recommendations: List[Recommendation] = Field(..., description="Actionable recommendations")
    
    # Metadata
    confidence_score: float = Field(..., ge=0.0, le=1.0, description="Overall confidence in analysis")
    generated_at: datetime = Field(default_factory=datetime.utcnow, description="Report generation timestamp")
    analysis_duration_seconds: Optional[float] = Field(None, description="Time taken for analysis")
    
    # Agent information
    agents_involved: List[str] = Field(default_factory=list, description="Domain agents that contributed")
    tools_used: List[str] = Field(default_factory=list, description="Analysis tools used")
    
    class Config:
        json_schema_extra = {
            "example": {
                "failure_id": "RCA-2026-02-08-001",
                "equipment_name": "ID&HR Fan",
                "root_causes": [
                    {
                        "cause": "Cooling fan belt not replaced at scheduled maintenance",
                        "category": "maintenance",
                        "confidence": 0.85,
                        "supporting_evidence": ["5 Whys analysis", "Maintenance log review"]
                    }
                ],
                "contributing_factors": [
                    "Inadequate preventive maintenance tracking",
                    "Lack of condition monitoring on cooling system"
                ],
                "recommendations": [
                    {
                        "action": "Implement automated maintenance scheduling system",
                        "priority": "high",
                        "timeframe": "Within 30 days",
                        "responsible_party": "Maintenance Manager"
                    }
                ],
                "confidence_score": 0.82,
                "agents_involved": ["Electrical Agent", "Mechanical Agent"],
                "tools_used": ["5 Whys", "Fishbone", "Similar Failures"]
            }
        }
