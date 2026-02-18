"""
Tool Result Models for RCA System

Defines data models for tool execution results.
"""

from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from datetime import datetime


class WhyStep(BaseModel):
    """Single step in 5 Whys analysis."""
    step_number: int = Field(..., description="Step number (1-5)")
    question: str = Field(..., description="The 'why' question asked")
    answer: str = Field(..., description="Answer to the why question")
    supporting_documents: List[str] = Field(default_factory=list, description="Documents cited in this step")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence in this answer (0-1)")


class FiveWhysResult(BaseModel):
    """Result from 5 Whys analysis."""
    why_steps: List[WhyStep] = Field(..., description="The 5 why steps")
    root_cause: str = Field(..., description="Identified root cause")
    root_cause_confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence in root cause")
    corrective_actions: List[str] = Field(default_factory=list, description="Recommended corrective actions")
    documents_used: List[str] = Field(default_factory=list, description="All documents referenced")
    analysis_timestamp: datetime = Field(default_factory=datetime.now, description="When analysis was performed")


class DomainFinding(BaseModel):
    """Single finding from a domain-specific agent."""
    area: str = Field(..., description="Analysis area (e.g., 'Bearing Condition', 'Motor Protection')")
    observation: str = Field(..., description="What was found")
    severity: str = Field(..., description="Severity level: critical, warning, normal")
    evidence: str = Field(..., description="Supporting evidence for this finding")


class DomainAnalysisResult(BaseModel):
    """Result from a domain-specific agent analysis."""
    domain: str = Field(..., description="Domain: mechanical, electrical, or process")
    findings: List[DomainFinding] = Field(..., description="Domain-specific observations")
    root_cause_hypothesis: str = Field(..., description="Agent's root cause hypothesis")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence in hypothesis")
    recommended_checks: List[str] = Field(default_factory=list, description="Physical checks to verify")
    documents_used: List[str] = Field(default_factory=list, description="RAG sources referenced")
    analysis_timestamp: datetime = Field(default_factory=datetime.now, description="When analysis was performed")


class DomainInsightsSummary(BaseModel):
    """
    Aggregated insights from all domain agents.
    
    Used to provide domain-specific context to the 5 Whys analysis.
    """
    agents_analyzed: List[str] = Field(
        ..., 
        description="List of domain agents that ran (e.g., ['mechanical_agent', 'electrical_agent'])"
    )
    
    domain_analyses: List[DomainAnalysisResult] = Field(
        ...,
        description="Full results from each domain agent"
    )
    
    key_findings: List[str] = Field(
        ...,
        description="Top critical findings across all domains (max 10)"
    )
    
    suspected_root_causes: List[Dict[str, Any]] = Field(
        ...,
        description="Hypotheses from each domain with confidence scores"
    )
    
    recommended_checks: List[str] = Field(
        ...,
        description="Physical verification checks from all domains (max 10)"
    )
    
    documents_used: List[str] = Field(
        ...,
        description="All OEM manuals referenced by domain agents"
    )
    
    overall_confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Weighted average confidence across domains"
    )
    
    analysis_timestamp: datetime = Field(
        default_factory=datetime.now,
        description="When domain analysis was performed"
    )


class ToolResult(BaseModel):
    """Generic result from any RCA tool."""
    tool_name: str = Field(..., description="Name of the tool that was executed")
    success: bool = Field(..., description="Whether tool execution succeeded")
    result: Dict[str, Any] = Field(default_factory=dict, description="Tool-specific result data")
    error: Optional[str] = Field(None, description="Error message if failed")
    execution_time_seconds: float = Field(..., description="Time taken to execute")
    tokens_used: int = Field(0, description="LLM tokens consumed")
    cost_usd: float = Field(0.0, description="Cost in USD")
    timestamp: datetime = Field(default_factory=datetime.now, description="When tool was executed")
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
