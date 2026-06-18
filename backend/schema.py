from pydantic import BaseModel, Field
from typing import Optional, List, Dict
from enum import Enum

class Severity(str, Enum):
    MILD = "mild"
    MODERATE = "moderate"
    SEVERE = "severe"
    EMERGENCY = "emergency"

class PatientState(BaseModel):
    chief_complaint: Optional[str] = Field(None, description="Main symptom or problem")
    severity: Optional[Severity] = Field(None, description="Severity level of the complaint")
    duration: Optional[str] = Field(None, description="How long the problem has existed")
    associated_symptoms: List[str] = Field(default_factory=list, description="Other symptoms mentioned")
    doctor_keyword: Optional[str] = Field(None, description="Keyword for doctor speciality lookup")
    emergency_flag: bool = Field(default=False, description="True if emergency detected")
    session_complete: bool = Field(default=False, description="True when report is ready")
    turn_count: int = Field(default=0, description="Number of exchanges so far")
    missing_fields: List[str] = Field(default_factory=list, description="Fields still needed")
    latest_user_message: str = Field(default="", description="Most recent user input")
    conversation_history: List[Dict[str, str]] = Field(default_factory=list)

# For LangChain structured output
class ExtractionOutput(BaseModel):
    """LLM output for schema extraction"""
    chief_complaint: Optional[str] = None
    severity: Optional[Severity] = None
    duration: Optional[str] = None
    associated_symptoms: List[str] = []
    doctor_keyword: Optional[str] = None
