from langgraph.graph import StateGraph, END
from backend.schema import PatientState, Severity, BiologicalSex
from backend.llm_client import OllamaClient
from pathlib import Path
from langchain_core.runnables import RunnableConfig
import json
from backend.database import save_or_update_report

class MedicalGraph:
    def __init__(self):
        self.llm_client = OllamaClient()
        self.workflow = self._build_workflow()
        
    def _build_workflow(self):
        workflow = StateGraph(PatientState)
        
        # Add nodes
        workflow.add_node("extract", self.extract_node)
        workflow.add_node("severity_check", self.severity_node)
        workflow.add_node("completeness_check", self.completeness_node)
        workflow.add_node("validate", self.validation_node)
        workflow.add_node("report", self.report_node)
        
        # Set entry point
        workflow.set_entry_point("extract")
        
        # Add edges
        workflow.add_edge("extract", "severity_check")
        workflow.add_edge("severity_check", "completeness_check")
        
        # Conditional edges from completeness_check
        workflow.add_conditional_edges(
            "completeness_check",
            self.should_continue_or_end,
            {
                "validate": "validate",
                "report": "report",
                "end": END
            }
        )
        
        return workflow.compile()
    
    async def extract_node(self, state: PatientState) -> PatientState:
        """Extract medical info from latest user message"""
        latest_message = state.latest_user_message
        
        extraction = self.llm_client.extract_medical_info(
            latest_message, 
            state.model_dump(exclude={"conversation_history"})
        )
        
        # --- Update Domain A: Identity & Demographics ---
        if extraction.patient_name:
            state.patient_name = extraction.patient_name
        if extraction.age is not None:
            state.age = extraction.age
        if extraction.biological_sex:
            try:
                state.biological_sex = BiologicalSex(extraction.biological_sex)
            except ValueError:
                pass
        if extraction.residence_area:
            state.residence_area = extraction.residence_area

        # --- Update Domain B: Current Clinical Presentation ---
        if extraction.chief_complaint:
            state.chief_complaint = extraction.chief_complaint
        else:
            # FALLBACK: If no chief complaint but message mentions pain or can't walk
            msg_lower = latest_message.lower()
            if "pain" in msg_lower:
                state.chief_complaint = "pain"
            elif "can't walk" in msg_lower or "cannot walk" in msg_lower:
                state.chief_complaint = "difficulty walking"
        
        if extraction.severity:
            try:
                state.severity = extraction.severity
            except ValueError:
                pass
        
        if extraction.duration:
            state.duration = extraction.duration
        
        if extraction.associated_symptoms:
            state.associated_symptoms.extend(extraction.associated_symptoms)

        if extraction.functional_limitation:
            state.functional_limitation = extraction.functional_limitation

        if extraction.doctor_keyword:
            state.doctor_keyword = extraction.doctor_keyword
        elif not state.doctor_keyword and state.chief_complaint:
            state.doctor_keyword = self._fallback_doctor_keyword(state.chief_complaint)
        
        state.turn_count += 1
        return state
    
    async def severity_node(self, state: PatientState) -> PatientState:
        """Check for emergency and classify severity - overrides if more severe"""
        latest_message = state.latest_user_message
        current_severity = state.severity.value if state.severity else "unknown"
        
        is_emergency, severity_level = self.llm_client.classify_severity_emergency(
            latest_message, 
            current_severity
        )
        
        state.emergency_flag = is_emergency
        
        # Severity priority order (higher number = more severe)
        severity_priority = {
            "mild": 1,
            "moderate": 2, 
            "severe": 3,
            "emergency": 4
        }
        
        current_priority = severity_priority.get(state.severity.value if state.severity else None, 0)
        new_priority = severity_priority.get(severity_level, 0)
        
        # Override if new severity is more severe or no severity exists
        if new_priority > current_priority:
            try:
                state.severity = Severity(severity_level)
            except ValueError:
                pass
        elif not state.severity:
            try:
                state.severity = Severity(severity_level) if severity_level in {s.value for s in Severity} else state.severity
            except ValueError:
                pass
        
        return state
    
    async def completeness_node(self, state: PatientState) -> PatientState:
        """Determine which fields are missing based on a tiered priority constraint"""
        
        # If emergency, no fields are "missing" - we report immediately
        if state.emergency_flag:
            state.missing_fields = []
            return state
        
        missing = []
        
        # Tier 1 Priority: Mandatory Clinical Fields
        if not state.chief_complaint:
            missing.append("chief_complaint")
        if not state.severity:
            missing.append("severity")
        if not state.duration:
            missing.append("duration")
            
        # Tier 2 Priority: High-Value Context Fields (Only seek if Tier 1 is collected)
        if not missing:
            if not state.age:
                missing.append("age")
            if not state.biological_sex:
                missing.append("biological_sex")
            if not state.patient_name:
                missing.append("patient_name")
            if not state.residence_area:
                missing.append("residence_area")
            
        state.missing_fields = missing
        return state
    
    async def validation_node(self, state: PatientState) -> PatientState:
        """Generate a validation question for missing info"""
        return state
    
    async def report_node(self, state: PatientState, config: RunnableConfig = None) -> PatientState:
        """Generate final report summary and save a customized snapshot to SQLite database for auditing"""
        state.session_complete = True
        
        # 1. Retrieve session_id safely from runtime configuration metadata context
        session_id = "unknown_session"
        if config and "configurable" in config and "session_id" in config["configurable"]:
            session_id = config["configurable"]["session_id"]
            
        try:
            # 2. Serialize the Pydantic state context into standard JSON compatible types
            state_data = state.model_dump(mode="json")
            
            # 3. Fire the insertion/upsert query to SQLite database
            save_or_update_report(session_id, state_data)
            
        except Exception as e:
            # Shield main request loop from crashing out if database locked or errored
            print(f"CRITICAL DEBUG ERROR: Failed to write report snapshot to SQL: {e}")
            
        return state
    
    def should_continue_or_end(self, state: PatientState) -> str:
        """Decide next step based on session state metrics"""
        # Emergency: immediate report
        if state.emergency_flag:
            return "report"
        
        # If severity is severe, report immediately (don't ask any questions)
        if state.severity and state.severity.value == "severe":
            return "report"
        
        # Max turns reached
        if state.turn_count >= 4:
            return "report"
        
        # Evaluation using priority tracking
        if not state.chief_complaint:
            if state.severity and state.severity.value == "severe":
                return "report"
            return "validate"
        elif not state.severity or not state.duration:
            return "validate"
            
        # If core presentation fields are satisfied, allow up to max turns for optional demographics
        if state.missing_fields:
            return "validate"
        
        return "report"
    
    async def process_turn(self, user_message: str, current_state: PatientState, session_id: str = "unknown_session") -> tuple[PatientState, str]:
        """Processes a single conversational exchange turn inside the LangGraph pipeline loop context"""
        # 1. Append message to conversation history state layers
        current_state.conversation_history.append({"role": "user", "content": user_message})
        current_state.latest_user_message = user_message
        
        # 2. Build the metadata context block required by LangGraph execution scopes
        config = {"configurable": {"session_id": session_id}}
        
        # 3. Invoke workflow (returns a dictionary representation of the state)
        raw_result = await self.workflow.ainvoke(current_state, config=config)
        
        # 4. Handle conversion: turn the result dict back into a proper Pydantic PatientState object
        if isinstance(raw_result, dict):
            final_state = PatientState(**raw_result)
        else:
            final_state = raw_result
            
        # 5. Extract the last assistant response directly out of history
        bot_response = ""
        if final_state.conversation_history:
            # Look backwards for the last message added by the model/graph
            for msg in reversed(final_state.conversation_history):
                if msg.get("role") in ["assistant", "ai", "bot"]:
                    bot_response = msg.get("content", "")
                    break
        
        # Fallback if no message was added by the workflow nodes
        if not bot_response:
            bot_response = "Thank you for the update. Processing your assessment context."
        
        return final_state, bot_response
    
    def generate_report(self, state: PatientState) -> str:
        """Create final clinical profile and presentation report text"""
        name = state.patient_name or 'Anonymous'
        age = f"{state.age} y/o" if state.age else 'Age not specified'
        sex = state.biological_sex.value if state.biological_sex else 'Sex not specified'
        area = state.residence_area or 'Location not specified'
        
        if state.emergency_flag:
            severity = state.severity.value if state.severity else 'Not specified'
            
            return f"""🚨 **URGENT MEDICAL ATTENTION NEEDED** 🚨

Patient Demographic Profile:
- Name: {name}
- Age/Sex: {age} | {sex}
- Residence: {area}

Patient reports: {state.chief_complaint}
Severity: {severity} (EMERGENCY)
Associated symptoms: {', '.join(state.associated_symptoms) if state.associated_symptoms else 'None reported'}
Functional Limitation: {state.functional_limitation or 'None reported'}

**ACTION REQUIRED: Patient needs immediate emergency care. Do not wait for appointment.**

---
Chat Session Report (for doctor):
- Chief complaint: {state.chief_complaint}
- Severity: {severity}
- Triage recommendation: IMMEDIATE EMERGENCY ROOM
"""
        
        severity = state.severity.value if state.severity else 'Not specified'
        duration = state.duration if state.duration else 'Not specified'
        
        return f"""**Session Complete** - Medical Report

Patient Demographic Profile:
- Name: {name}
- Age/Sex: {age} | {sex}
- Residence: {area}

Patient Summary:
- Chief complaint: {state.chief_complaint or 'Not specified'}
- Severity: {severity}
- Duration: {duration}
- Associated symptoms: {', '.join(state.associated_symptoms) if state.associated_symptoms else 'None'}
- Functional Limitation: {state.functional_limitation or 'None reported'}

Recommendation: Schedule consultation with doctor

---
Full JSON report:
{state.model_dump_json(indent=2)}
"""

    def _fallback_doctor_keyword(self, complaint: str) -> str:
        complaint = complaint.lower()
        if any(term in complaint for term in ["walk", "bone", "joint", "leg", "fracture", "limp"]):
            return "orthopedic"
        if any(term in complaint for term in ["heart", "cardiac", "chest pain"]):
            return "cardiology"
        return "medicine"