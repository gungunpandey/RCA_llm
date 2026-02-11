"""
Failure Report Data Model

Defines the input structure for failure reports submitted to the RCA system.
"""

from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime


class FailureReport(BaseModel):
    """
    Input model for equipment failure reports.
    
    This is the primary input to the RCA system, containing all relevant
    information about a failure event.
    """
    
    equipment_name: str = Field(
        ...,
        description="Name of the equipment that failed (e.g., 'Rotary Kiln', 'ID&HR Fan')",
        examples=["Rotary Kiln", "ID&HR Fan", "Bucket Elevator", "Annular Cooler"]
    )
    
    failure_description: str = Field(
        ...,
        description="Detailed description of the failure event",
        min_length=10
    )
    
    failure_timestamp: datetime = Field(
        ...,
        description="When the failure occurred (ISO 8601 format)"
    )
    
    symptoms: List[str] = Field(
        default_factory=list,
        description="Observable symptoms of the failure",
        examples=[["motor overheating", "unusual vibration", "power loss"]]
    )
    
    error_codes: Optional[List[str]] = Field(
        default=None,
        description="Error codes from control systems (if available)",
        examples=[["E401", "E502"]]
    )
    
    operator_observations: Optional[str] = Field(
        default=None,
        description="Observations from equipment operators"
    )
    
    recent_maintenance: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        description="Recent maintenance activities on this equipment",
        examples=[[
            {
                "date": "2026-01-15",
                "activity": "Bearing replacement",
                "technician": "John Doe"
            }
        ]]
    )
    
    process_parameters: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Process parameters at time of failure (temperature, pressure, flow rates, etc.)",
        examples=[{
            "temperature": 850,
            "pressure": 2.5,
            "flow_rate": 120,
            "rpm": 1450
        }]
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "equipment_name": "ID&HR Fan",
                "failure_description": "Fan motor stopped suddenly during operation",
                "failure_timestamp": "2026-02-06T15:30:00Z",
                "symptoms": ["motor overheating", "unusual vibration", "power loss"],
                "error_codes": ["E401", "E502"],
                "operator_observations": "Noticed burning smell before shutdown",
                "process_parameters": {
                    "temperature": 85,
                    "vibration_level": 12.5,
                    "current_draw": 45
                }
            }
        }
