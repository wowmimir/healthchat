from langgraph.graph import StateGraph, END
from backend.schema import PatientState, Severity
from backend.llm_client import OllamaClient

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
        
        # Update state
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
        """Determine which fields are missing"""
        
        # If emergency, no fields are "missing" - we report immediately
        if state.emergency_flag:
            state.missing_fields = []
            return state
        
        missing = []
        
        if not state.chief_complaint:
            missing.append("chief_complaint")
        if not state.severity:
            missing.append("severity")
        if not state.duration:
            missing.append("duration")
            
        state.missing_fields = missing
        return state
    
    async def validation_node(self, state: PatientState) -> PatientState:
        """Generate a validation question for missing info"""
        return state
    
    async def report_node(self, state: PatientState) -> PatientState:
        """Generate final report"""
        state.session_complete = True
        return state
    
    def should_continue_or_end(self, state: PatientState) -> str:
        """Decide next step"""
        # Emergency: immediate report
        if state.emergency_flag:
            return "report"
        
        # If severity is severe, report immediately (don't ask any questions)
        if state.severity and state.severity.value == "severe":
            return "report"
        
        # Max turns reached
        if state.turn_count >= 4:
            return "report"
        
        # Determine missing fields in priority order
        missing = []
        if not state.chief_complaint:
            # If severity is severe but no chief complaint, still report
            if state.severity and state.severity.value == "severe":
                return "report"
            missing.append("chief_complaint")
        elif not state.severity:
            missing.append("severity")
        elif not state.duration:
            missing.append("duration")
        
        state.missing_fields = missing
        
        if not missing:
            return "report"
        
        return "validate"
    
    async def process_turn(self, user_message: str, current_state: PatientState) -> tuple[PatientState, str]:
        """Process one user message and return updated state + bot response"""
        if user_message.strip() == "":
            return current_state, "Could you tell me a bit more about your symptoms?"
        
        # Store message with history
        current_state.latest_user_message = user_message
        current_state.conversation_history.append({"role": "user", "content": user_message})
        
        # Run the graph until completion
        final_state = await self.workflow.ainvoke(current_state)
        if isinstance(final_state, dict):
            final_state = PatientState.model_validate(final_state)
        
        # Generate response based on final state
        if final_state.session_complete:
            response = self.generate_report(final_state)
        elif final_state.missing_fields:
            response = self.llm_client.generate_validation_question(
                final_state.missing_fields,
                final_state.conversation_history
            )
        else:
            response = "I understand. Please continue or tell me more about your symptoms."
            
        return final_state, response
    
    def generate_report(self, state: PatientState) -> str:
        """Create final report text"""
        if state.emergency_flag:
            severity = state.severity.value if state.severity else 'Not specified'
            
            return f"""🚨 **URGENT MEDICAL ATTENTION NEEDED** 🚨

Patient reports: {state.chief_complaint}
Severity: {severity} (EMERGENCY)
Associated symptoms: {', '.join(state.associated_symptoms) if state.associated_symptoms else 'None reported'}

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

Patient Summary:
- Chief complaint: {state.chief_complaint or 'Not specified'}
- Severity: {severity}
- Duration: {duration}
- Associated symptoms: {', '.join(state.associated_symptoms) if state.associated_symptoms else 'None'}

Recommendation: Schedule consultation with doctor

---
Full JSON report:
{state.model_dump_json(indent=2)}
"""