from langchain_ollama import ChatOllama
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate
from backend.schema import ExtractionOutput

class OllamaClient:
    def __init__(self, model="gemma4:31b-cloud", base_url="http://localhost:11434"):
        self.llm = ChatOllama(
            model=model,
            base_url=base_url,
            temperature=0.2,  # Lower temperature for more consistent extraction
            num_predict=512,
            format="json"
        )
        self.parser = PydanticOutputParser(pydantic_object=ExtractionOutput)

    def _parse_with_fallback(self, raw_response: str) -> ExtractionOutput:
        """If JSON parsing fails, robustly extract using flexible regex patterns"""
        import re
        from backend.schema import Severity
        
        result = ExtractionOutput()
        
        # Clean quotes and strip extra wrapping characters to make matching cleaner
        clean_text = raw_response.replace('\\"', '"').replace("'", '"')
        
        # 1. Chief Complaint Match
        complaint_match = re.search(r'chief_complaint["\s:]+([^"\n,}\]]+)', clean_text, re.IGNORECASE)
        if complaint_match:
            result.chief_complaint = complaint_match.group(1).strip()
            
        # 2. Severity Match
        severity_match = re.search(r'severity["\s:]+["\s]*(\w+)', clean_text, re.IGNORECASE)
        if severity_match:
            sev_val = severity_match.group(1).lower().strip()
            if sev_val in ['mild', 'moderate', 'severe', 'emergency']:
                result.severity = Severity(sev_val)
                
        # 3. Duration Match
        duration_match = re.search(r'duration["\s:]+([^"\n,}\]]+)', clean_text, re.IGNORECASE)
        if duration_match:
            result.duration = duration_match.group(1).strip()
            
        # 4. Doctor Keyword Match
        keyword_match = re.search(r'doctor_keyword["\s:]+([^"\n,}\]]+)', clean_text, re.IGNORECASE)
        if keyword_match:
            result.doctor_keyword = keyword_match.group(1).strip()
            
        # 5. Functional Limitation Match
        lim_match = re.search(r'functional_limitation["\s:]+([^"\n,}\]]+)', clean_text, re.IGNORECASE)
        if lim_match:
            result.functional_limitation = lim_match.group(1).strip()

        # 6. Demographics Fallbacks (Domain A)
        name_match = re.search(r'patient_name["\s:]+([^"\n,}\]]+)', clean_text, re.IGNORECASE)
        if name_match:
            result.patient_name = name_match.group(1).strip()

        age_match = re.search(r'age["\s:]+["\s]*(\d+)', clean_text, re.IGNORECASE)
        if age_match:
            try:
                result.age = int(age_match.group(1))
            except ValueError:
                pass

        residence_match = re.search(r'residence_area["\s:]+([^"\n,}\]]+)', clean_text, re.IGNORECASE)
        if residence_match:
            result.residence_area = residence_match.group(1).strip()
            
        return result
        
    def extract_medical_info(self, user_message: str, current_state: dict) -> ExtractionOutput:
        """Extract structured data from user message"""
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", """You are a medical intake assistant. Extract patient demographics and presentation information from their message.

    {format_instructions}

    RULES:
    - patient_name: Extract the patient's name if they mention it.
    - age: Extract their age if explicitly or implicitly mentioned.
    - biological_sex: Extract biological sex clues (e.g., "male", "female", "man", "woman", "boy", "girl").
    - residence_area: Extract the locality, village, town, or area where they reside.
    - chief_complaint: Extract the MAIN symptom. For "leg pain", extract "pain" or "leg pain".
    - severity: Extract "mild", "moderate", "severe", or "emergency" if explicitly stated.
    - duration: Extract if patient gives a time frame like "2 days", "3 hours". Otherwise leave null.
    - associated_symptoms: Extract any additional symptoms mentioned into an array.
    - functional_limitation: Extract clear descriptions of what physical task they cannot perform because of the ailment (e.g., "cannot bear weight", "can't walk", "unable to move arm").
    - doctor_keyword: Extract one short doctor/speciality search keyword. Use "medicine" for fever, cough, general weakness, chest pain, or unclear general illness. Use "orthopedic" for bone/joint/breaking/walking issues. Use "cardiology" for heart-specific complaints. Use the chief complaint if unsure.

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
        
        # Prioritize core clinical presentation fields first
        if "chief_complaint" in missing_fields:
            return field_questions["chief_complaint"]
        
        if "severity" in missing_fields:
            return field_questions["severity"]
        
        if "duration" in missing_fields:
            return field_questions["duration"]
        
        # Fallback to LLM for demographic or complex presentation fields
        prompt = ChatPromptTemplate.from_messages([
            ("system", """You are a medical chatbot for patients. Generate ONE short, simple question to ask the patient for missing details.

Missing fields to pick from: {missing_fields}

Guidelines:
- If 'age' or 'patient_name' or 'biological_sex' or 'residence_area' is requested, ask for it in a warm, friendly manner.
- Only ask for ONE piece of information at a time.
- Use simple English.
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
                return False, "severe"
        
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
    - "can't walk", "can't move", "can't stand", "unable to move" → severe (even if they say mild)
    - "can't breathe", "crushing chest" → emergency

    Rules:
    - mild: minor issue, normal activity possible
    - moderate: noticeable discomfort, some limitation
    - severe: intense pain, CANNOT walk/move/use a limb normally
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