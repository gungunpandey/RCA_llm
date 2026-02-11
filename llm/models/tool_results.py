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
