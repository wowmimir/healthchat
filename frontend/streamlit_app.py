import streamlit as st
import requests
import uuid
import json

# Initialize session
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())
if "messages" not in st.session_state:
    st.session_state.messages = []
if "session_complete" not in st.session_state:
    st.session_state.session_complete = False
if "current_schema" not in st.session_state:
    st.session_state.current_schema = {}
if "last_response" not in st.session_state:
    st.session_state.last_response = None

API_URL = "http://localhost:8000/chat"
SESSION_URL = "http://localhost:8000/session"

st.set_page_config(page_title="Medical Assistant", page_icon="🏥", layout="wide")

# Sidebar with schema status - This will auto-update on each rerun
with st.sidebar:
    st.title("📋 Patient Schema")
    
    if st.session_state.current_schema:
        # Display schema with better formatting
        st.subheader("Current Patient Data")
        
        # Show key fields prominently
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Chief Complaint", st.session_state.current_schema.get("chief_complaint") or "❓")
        with col2:
            severity = st.session_state.current_schema.get("severity")
            if severity == "emergency":
                st.metric("Severity", severity, delta="🚨 URGENT", delta_color="inverse")
            else:
                st.metric("Severity", severity or "❓")
        
        st.metric("Duration", st.session_state.current_schema.get("duration") or "❓")
        
        if st.session_state.current_schema.get("associated_symptoms"):
            st.write("**Associated Symptoms:**")
            for sym in st.session_state.current_schema["associated_symptoms"]:
                st.write(f"- {sym}")
        
        # Full JSON expander
        with st.expander("View Full JSON"):
            st.json(st.session_state.current_schema)
        
        # Show missing fields
        missing = st.session_state.current_schema.get("missing_fields", [])
        if missing:
            st.warning(f"Missing: {', '.join(missing)}")
    else:
        st.info("No data yet. Start chatting!")
    
    st.divider()
    
    if st.button("🔄 New Session"):
        try:
            requests.delete(f"{SESSION_URL}/{st.session_state.session_id}", timeout=2)
        except Exception:
            pass
        st.session_state.session_id = str(uuid.uuid4())
        st.session_state.messages = []
        st.session_state.session_complete = False
        st.session_state.current_schema = {}
        st.rerun()

# Main chat area
st.title("🏥 Rural Medical Assistant")
st.caption("Your health companion - I'll help document your symptoms for the doctor")

# Display chat history
chat_container = st.container()
with chat_container:
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
            
            # Show JSON for assistant messages that completed session
            if message["role"] == "assistant" and "json_report" in message:
                with st.expander("View JSON Report"):
                    st.json(message["json_report"])

# Chat input
if not st.session_state.session_complete:
    if prompt := st.chat_input("Describe your problem..."):
        # Add user message
        st.session_state.messages.append({"role": "user", "content": prompt})
        
        # Call API
        with st.chat_message("assistant"):
            with st.spinner("Analyzing your symptoms..."):
                try:
                    response = requests.post(
                        API_URL,
                        json={
                            "session_id": st.session_state.session_id,
                            "message": prompt
                        },
                        timeout=30
                    )
                    
                    if response.status_code == 200:
                        data = response.json()
                        
                        # Update session state BEFORE displaying
                        st.session_state.session_complete = data["session_complete"]
                        st.session_state.current_schema = data["current_schema"]
                        
                        # Display bot response
                        st.markdown(data["response"])
                        
                        # Store message
                        msg_data = {"role": "assistant", "content": data["response"]}
                        if data["session_complete"]:
                            msg_data["json_report"] = data["current_schema"]
                        
                        st.session_state.messages.append(msg_data)
                        
                        # Show emergency alert
                        if data["emergency"]:
                            st.error("🚨 EMERGENCY DETECTED - Seek immediate medical care! 🚨")
                            st.balloons()
                        
                        # Force immediate rerun to update sidebar
                        st.rerun()
                        
                    else:
                        st.error(f"Error: {response.status_code}")
                        st.session_state.messages.pop()  # Remove the user message
                        
                except requests.exceptions.Timeout:
                    st.error("⏰ The model is taking too long. Please try again.")
                    st.session_state.messages.pop()
                except Exception as e:
                    st.error(f"Connection error: {e}")
                    st.session_state.messages.pop()
else:
    st.success("✅ Session complete! Report ready for doctor.")
    
    # Display final report prominently
    if st.session_state.current_schema:
        with st.expander("📄 Final Medical Report", expanded=True):
            if st.session_state.current_schema.get("emergency_flag"):
                st.error("**URGENT: Emergency Detected**")
            
            st.json(st.session_state.current_schema)
    
    if st.button("Start New Session", type="primary"):
        try:
            requests.delete(f"{SESSION_URL}/{st.session_state.session_id}", timeout=2)
        except Exception:
            pass
        st.session_state.session_id = str(uuid.uuid4())
        st.session_state.messages = []
        st.session_state.session_complete = False
        st.session_state.current_schema = {}
        st.rerun()

# Footer
st.divider()
st.caption("⚠️ This is a demonstration tool. Always consult a real doctor for medical advice.")