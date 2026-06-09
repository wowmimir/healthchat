from langchain_ollama import ChatOllama
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate
from backend.schema import ExtractionOutput

class OllamaClient:
    def __init__(self, model="minimax-m3:cloud", base_url="http://localhost:11434"):
        self.llm = ChatOllama(
            model=model,
            base_url=base_url,
            temperature=0.2,  # Lower temperature for more consistent extraction
            num_predict=512,
            format="json"
        )
        self.parser = PydanticOutputParser(pydantic_object=ExtractionOutput)

    def _parse_with_fallback(self, raw_response: str) -> ExtractionOutput:
        """If JSON parsing fails, extract using regex"""
        import re
        
        result = ExtractionOutput()
        
        # Look for patterns
        complaint_match = re.search(r'chief_complaint["\s:]+([^"\n]+)', raw_response)
        if complaint_match:
            result.chief_complaint = complaint_match.group(1).strip()
        
        severity_match = re.search(r'severity["\s:]+(\w+)', raw_response)
        if severity_match and severity_match.group(1) in ['mild','moderate','severe','emergency']:
            result.severity = severity_match.group(1)
        
        duration_match = re.search(r'duration["\s:]+([^"\n]+)', raw_response)
        if duration_match:
            result.duration = duration_match.group(1).strip()
        
        return result
        
    def extract_medical_info(self, user_message: str, current_state: dict) -> ExtractionOutput:
        """Extract structured data from user message"""
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", """You are a medical intake assistant. Extract patient information from their message.

    {format_instructions}

    RULES:
    - chief_complaint: Extract the MAIN symptom. For "pain", extract "pain". For "mild pain", extract "pain".
    - severity: Extract "mild", "moderate", "severe", or "emergency" if explicitly stated. If patient says "mild pain", extract "mild".
    - duration: Extract if patient gives time frame like "2 days", "3 hours". Otherwise leave null.
    - associated_symptoms: Extract any additional symptoms mentioned.

    DO NOT leave chief_complaint null if the patient mentions any symptom or pain.

    Current known info: {current_state}
    """),
            ("human", "{user_message}")
        ])
        
        formatted_prompt = prompt.format_messages(
            format_instructions=self.parser.get_format_instructions(),
            current_state=str(current_state),
            user_message=user_message
        )
        
        response = self.llm.invoke(formatted_prompt)
        try:
            return self.parser.parse(response.content)
        except Exception as e:
            print(f"JSON parse failed, using fallback: {e}")
            return self._parse_with_fallback(response.content)
    
    def generate_validation_question(self, missing_fields: list, history: list) -> str:
        """Generate a follow-up question for missing information"""
        
        # Map field names to patient-friendly questions
        field_questions = {
            "chief_complaint": "Can you tell me specifically what symptom you're experiencing? For example: pain, fever, headache, or cough?",
            "severity": "On a scale of 1 to 10, how severe is your discomfort? (1 = very mild, 10 = worst possible)",
            "duration": "How long have you been experiencing this? Please tell me in hours, days, or weeks."
        }
        
        # Prioritize chief_complaint first
        if "chief_complaint" in missing_fields:
            return field_questions["chief_complaint"]
        
        # Then severity
        if "severity" in missing_fields:
            return field_questions["severity"]
        
        # Then duration
        if "duration" in missing_fields:
            return field_questions["duration"]
        
        # Fallback to LLM for any other cases
        prompt = ChatPromptTemplate.from_messages([
            ("system", """You are a medical chatbot for rural patients. Generate ONE short, simple question.

Missing fields: {missing_fields}

Ask about chief_complaint first if missing, then severity, then duration.
Use simple English.
"""),
            ("human", "Generate the next question:")
        ])
        
        formatted_prompt = prompt.format_messages(
            missing_fields=missing_fields,
            history=str(history[-3:])
        )
        
        response = self.llm.invoke(formatted_prompt)
        return response.content.strip()
    
    def classify_severity_emergency(self, user_message: str, current_severity: str) -> tuple[bool, str]:
        """Check for emergency keywords + functional limitation + LLM severity classification"""
        
        msg_lower = user_message.lower()
        
        # Emergency keywords (immediate life threat)
        emergency_keywords = [
            "crushing chest", "can't breathe", "unconscious", "severe bleeding",
            "heart attack", "stroke", "not responding", "gasping", "turning blue"
        ]
        
        for keyword in emergency_keywords:
            if keyword in msg_lower:
                return True, "emergency"
        
        # Functional limitation keywords (override mild/moderate to severe)
        severe_limitations = [
            "can't walk", "cannot walk", "unable to walk", "can't move", 
            "cannot move", "unable to move", "can't stand", "cannot stand",
            "can't get up", "cannot get up", "paralyzed"
        ]
        
        for keyword in severe_limitations:
            if keyword in msg_lower:
                return False, "severe"  # <-- This should trigger
        
        # Pain level override (7-9 = severe, 10 = emergency)
        import re
        pain_match = re.search(r'(\d+)\s*/?\s*10', msg_lower)
        if pain_match:
            pain_level = int(pain_match.group(1))
            if pain_level >= 10:
                return True, "emergency"
            elif pain_level >= 7:
                return False, "severe"
            elif pain_level >= 4:
                return False, "moderate"
            else:
                return False, "mild"
        
        # If not triggered by keywords, use LLM
        prompt = ChatPromptTemplate.from_messages([
            ("system", """Classify severity from patient message. Output ONLY one word: mild, moderate, severe, or emergency.

    IMPORTANT: Override patient's stated severity if they mention functional limitation:
    - "can't walk", "can't move", "can't stand" → severe (even if they say mild)
    - "can't breathe", "crushing chest" → emergency

    Rules:
    - mild: minor issue, normal activity possible
    - moderate: noticeable discomfort, some limitation
    - severe: intense pain, CANNOT walk/move normally
    - emergency: life-threatening

    Current severity in system: {current}
    """),
            ("human", "{message}")
        ])
        
        formatted_prompt = prompt.format_messages(
            current=current_severity,
            message=user_message
        )
        
        response = self.llm.invoke(formatted_prompt)
        severity = response.content.strip().lower()
        
        # Final override check for any missed severe limitations
        for keyword in severe_limitations:
            if keyword in msg_lower:
                return False, "severe"
        
        is_emergency = (severity == "emergency")
        return is_emergency, severity if severity in ["mild","moderate","severe","emergency"] else "moderate"