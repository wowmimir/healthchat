from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Dict
from backend.graph import MedicalGraph
from backend.schema import PatientState

app = FastAPI()

@app.exception_handler(Exception)
async def unhandled(request, exc):
    return JSONResponse(status_code=500, content={"detail": str(exc), "type": type(exc).__name__})

# CORS for Streamlit
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8501"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Store sessions in memory (use Redis for production)
sessions: Dict[str, PatientState] = {}
medical_graph = MedicalGraph()

class ChatRequest(BaseModel):
    session_id: str
    message: str

class ChatResponse(BaseModel):
    response: str
    session_complete: bool
    emergency: bool
    current_schema: dict

@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    # Get or create session
    if request.session_id not in sessions:
        sessions[request.session_id] = PatientState()
    
    current_state = sessions[request.session_id]
    current_state.latest_user_message = request.message
    
    # Process message through graph
    updated_state, bot_response = await medical_graph.process_turn(
        request.message,
        current_state
    )
    
    # Update session
    sessions[request.session_id] = updated_state
    
    return ChatResponse(
        response=bot_response,
        session_complete=updated_state.session_complete,
        emergency=updated_state.emergency_flag,
        current_schema=updated_state.model_dump(mode="json")
    )

@app.delete("/session/{session_id}")
async def end_session(session_id: str):
    if session_id in sessions:
        del sessions[session_id]
    return {"status": "session ended"}

@app.get("/health")
async def health_check():
    return {"status": "healthy", "ollama": "checking..."}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
