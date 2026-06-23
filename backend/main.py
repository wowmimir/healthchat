from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool
from typing import Dict

from backend.database import init_db  # Import your DB initializer
from backend.doctor_client import Doctor, DoctorClient
from backend.graph import MedicalGraph
from backend.schema import PatientState

# 1. Define the lifespan context manager
@asynccontextmanager
async def lifespan(app: FastAPI):
    # This block executes BEFORE the server starts accepting requests
    print("STARTUP: Initializing SQLite Database...")
    init_db() 
    
    yield  # The application runs and processes requests here
    
    # This block executes AFTER the server receives a shutdown signal
    print("SHUTDOWN: Cleaning up app resources...")

# 2. Pass the lifespan handler directly into your FastAPI initialization instance
app = FastAPI(lifespan=lifespan)

@app.exception_handler(Exception)
async def unhandled(request, exc):
    return JSONResponse(status_code=500, content={"detail": str(exc), "type": type(exc).__name__})

# CORS for local frontends
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:8501"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Store sessions in memory (use Redis for production)
sessions: Dict[str, PatientState] = {}
medical_graph = MedicalGraph()
doctor_client = DoctorClient()

class ChatRequest(BaseModel):
    session_id: str
    message: str

class ChatResponse(BaseModel):
    response: str
    session_complete: bool
    emergency: bool
    current_schema: dict
    doctor_keyword: str | None = None
    doctors: list[Doctor] = Field(default_factory=list)
    doctor_lookup_error: str | None = None

@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    if request.session_id not in sessions:
        sessions[request.session_id] = PatientState()
    
    current_state = sessions[request.session_id]
    current_state.latest_user_message = request.message
    
    updated_state, bot_response = await medical_graph.process_turn(
        request.message,
        current_state,
        session_id=request.session_id
    )
    
    sessions[request.session_id] = updated_state

    doctor_keyword = updated_state.doctor_keyword or updated_state.chief_complaint or "medicine"
    doctors = []
    doctor_lookup_error = None

    if updated_state.session_complete and not updated_state.emergency_flag:
        lookup = await run_in_threadpool(doctor_client.lookup, doctor_keyword)
        doctors = lookup.doctors
        doctor_lookup_error = lookup.error
        
        if not doctors and not doctor_lookup_error and doctor_keyword != "medicine":
            print(f"DEBUG: '{doctor_keyword}' returned 0 results. Falling back to general medicine.")
            fallback_keyword = "medicine"
            fallback_lookup = await run_in_threadpool(doctor_client.lookup, fallback_keyword)
            
            if fallback_lookup.doctors:
                doctor_keyword = fallback_lookup.keyword
                doctors = fallback_lookup.doctors
                doctor_lookup_error = fallback_lookup.error
            else:
                doctor_keyword = lookup.keyword
    
    return ChatResponse(
        response=bot_response,
        session_complete=updated_state.session_complete,
        emergency=updated_state.emergency_flag,
        current_schema=updated_state.model_dump(mode="json"),
        doctor_keyword=doctor_keyword if updated_state.session_complete else None,
        doctors=doctors,
        doctor_lookup_error=doctor_lookup_error,
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