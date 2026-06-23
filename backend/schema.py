from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Dict
from enum import Enum

class Severity(str, Enum):
    MILD = "mild"
    MODERATE = "moderate"
    SEVERE = "severe"
    EMERGENCY = "emergency"

class BiologicalSex(str, Enum):
    MALE = "male"
    FEMALE = "female"
    OTHER = "other"

class PatientState(BaseModel):
    # Domain A: Identity & Demographics
    patient_name: Optional[str] = Field(None, description="Name of the patient")
    age: Optional[int] = Field(None, description="Age of the patient in years")
    biological_sex: Optional[BiologicalSex] = Field(None, description="Biological sex of the patient")
    residence_area: Optional[str] = Field(None, description="General locality or area where the patient resides")

    # Domain B: Current Clinical Presentation
    chief_complaint: Optional[str] = Field(None, description="Main symptom or problem")
    severity: Optional[Severity] = Field(None, description="Severity level of the complaint")
    duration: Optional[str] = Field(None, description="How long the problem has existed")
    associated_symptoms: List[str] = Field(default_factory=list, description="Other symptoms mentioned")
    functional_limitation: Optional[str] = Field(None, description="What the patient cannot do due to their condition")

    # Operational/System Meta-properties
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
    # Domain A
    patient_name: Optional[str] = None
    age: Optional[int | str] = None  # Flexible type to allow LLM string captures before cleaning
    biological_sex: Optional[str] = None  # Kept as string here so validation handles loose text gracefully
    residence_area: Optional[str] = None

    # Domain B
    chief_complaint: Optional[str] = None
    severity: Optional[Severity] = None
    duration: Optional[str] = None
    associated_symptoms: List[str] = []
    functional_limitation: Optional[str] = None
    doctor_keyword: Optional[str] = None

    @field_validator("age")
    @classmethod
    def validate_and_coerce_age(cls, v):
        if v is None:
            return None
        if isinstance(v, int):
            return v if 0 <= v <= 125 else None
        # Coerce strings like "35 years old" or "40" cleanly
        import re
        match = re.search(r'\d+', str(v))
        if match:
            num = int(match.group())
            return num if 0 <= num <= 125 else None
        return None

    @field_validator("biological_sex")
    @classmethod
    def normalize_sex(cls, v):
        if not v:
            return None
        v_low = str(v).lower().strip()
        if v_low in ["male", "m", "man", "boy"]:
            return "male"
        if v_low in ["female", "f", "woman", "girl"]:
            return "female"
        if v_low in ["other", "intersex"]:
            return "other"
        return None