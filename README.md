# Medical Chatbot LLM Integration - Implementation Plan

## Project Overview
Add an intelligent LLM loop to an existing medical chatbot that actively validates patient information and generates structured session reports for doctors.

**Core Innovation:** Self-updating schema that asks validation questions when information is vague, with emergency detection capabilities.

---

## Technology Stack

| Component | Technology | Purpose |
|-----------|------------|---------|
| Package Manager | `uv` | Fast Python package management |
| Backend Framework | FastAPI | REST API endpoints |
| Orchestration | LangGraph | State machine for conversation flow |
| LLM | Gemma4:31b (via Ollama) | Local inference, no cloud costs |
| Output Parsing | LangChain + Pydantic | Structured JSON extraction |
| Frontend | Streamlit | Simple chat interface |
| Language | English (Phase 1) | Translation layer added later |

---

## Project Structure

```
medical_chatbot_llm/
├── backend/
│   ├── __init__.py
│   ├── main.py              # FastAPI application
│   ├── graph.py             # LangGraph workflow nodes
│   ├── schema.py            # Pydantic models
│   └── llm_client.py        # Ollama wrapper + parsing
├── frontend/
│   └── streamlit_app.py     # Chat interface
├── pyproject.toml           # UV dependencies
├── uv.lock                  # Lockfile
├── run.py                   # Launcher script
└── README.md                # This file
```

---

## Data Schema (MVP)

### Required Fields (Demo)
- `chief_complaint` (string) - Main symptom or problem
- `severity` (enum) - mild/moderate/severe/emergency  
- `duration` (string) - How long (e.g., "2 days", "3 hours")

### Optional Fields
- `associated_symptoms` (list) - Additional symptoms mentioned

### Session State
- `emergency_flag` (boolean) - Life-threatening detected
- `session_complete` (boolean) - Report ready
- `turn_count` (integer) - Max 4 turns for demo
- `conversation_history` (list) - For context

---

## LangGraph Workflow

```
[Start] → [Extract Node] → [Severity Node] → [Completeness Node]
                                                    ↓
                                    ┌───────────────┴───────────────┐
                                    ↓                               ↓
                            [Validate Node]                  [Report Node]
                                    ↓                               ↓
                              [Wait for User]                    [END]
```

### Node Responsibilities

| Node | Input | Output | LLM Called? |
|------|-------|--------|--------------|
| Extract | User message + current state | Updated schema fields | Yes |
| Severity | User message + current severity | emergency_flag + severity level | Partial (keyword check first) |
| Completeness | Current schema | List of missing fields | No |
| Validate | Missing fields list | One follow-up question | Yes |
| Report | Final schema | JSON + plain text summary | No (template-based) |

### Decision Logic

**After Completeness Node:**
- If `emergency_flag = true` → Go to Report
- If `turn_count >= 4` → Go to Report  
- If `missing_fields = []` → Go to Report
- Else → Go to Validate

---

## Break-Test Scenarios

Test these exact inputs to validate the system:

| # | Patient Input | Expected Behavior |
|---|---------------|--------------------|
| 1 | "pain" | Ask: "Where exactly do you feel the pain?" |
| 2 | "chest pain for 3 days" | Fill all fields → Generate report |
| 3 | "crushing chest pain, can't breathe" | 🚨 Emergency alert + Immediate report |
| 4 | "fever" | Ask: "How long have you had the fever?" |
| 5 | "fever since yesterday" | Ask: "On a scale of 1-10, how severe?" |
| 6 | "I don't want to say" | After 4 turns → Partial report |
| 7 | "headache and vomiting" | Extract both symptoms |
| 8 | "8/10 pain" | severity = "severe" |
| 9 | "can't breathe properly" | emergency_flag = true |
| 10 | (empty message) | Ask again (max 2 times) |

---

## Setup Instructions

### 1. Prerequisites

```bash
# Install UV
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Pull Gemma model
ollama pull gemma4:31b

# Start Ollama server (keep this terminal open)
ollama serve
```

### 2. Project Initialization

```bash
# Create project
mkdir medical_chatbot_llm
cd medical_chatbot_llm

# Initialize UV
uv init

# Add dependencies
uv add fastapi uvicorn langchain langgraph langchain-ollama pydantic streamlit requests python-multipart

# Create virtual environment
uv venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
```

### 3. Implementation Order

Follow this sequence to test each component independently:

**Phase 1: Core Schema (30 min)**
- Create `backend/schema.py`
- Define Pydantic models
- Test with Python REPL

**Phase 2: Ollama Integration (30 min)**
- Create `backend/llm_client.py`
- Test extraction with simple prompts
- Implement JSON fallback parser

**Phase 3: LangGraph Workflow (45 min)**
- Create `backend/graph.py`
- Implement all nodes
- Test state transitions with mock inputs

**Phase 4: FastAPI Backend (20 min)**
- Create `backend/main.py`
- Add session management
- Test with curl

**Phase 5: Streamlit Frontend (25 min)**
- Create `frontend/streamlit_app.py`
- Add sidebar for schema visualization
- Test end-to-end

**Phase 6: Integration Testing (20 min)**
- Run all break-test scenarios
- Fix edge cases
- Document failures

---

## Key Technical Decisions

### Why LangGraph over LangChain?
- Conversation is a **graph problem** with conditional routing
- Need explicit control over when to ask vs. when to report
- Emergency detection requires bypassing normal flow

### Why Gemma4:31b locally?
- No API costs for demo
- Patient data never leaves your machine
- Sufficient for structured extraction

### Why Pydantic + LangChain?
- Automatic JSON validation
- Retry logic on malformed output
- Clear schema contracts

### Why 4-turn limit?
- Prevent infinite loops
- Force report generation for demo
- Realistic for rural patients (short conversations)

---

## API Specification

### Endpoint: `POST /chat`

**Request:**
```json
{
  "session_id": "uuid-string",
  "message": "I have chest pain"
}
```

**Response:**
```json
{
  "response": "How long have you had this chest pain?",
  "session_complete": false,
  "emergency": false,
  "current_schema": {
    "chief_complaint": "chest pain",
    "severity": null,
    "duration": null,
    "associated_symptoms": [],
    "emergency_flag": false,
    "session_complete": false,
    "turn_count": 1,
    "missing_fields": ["severity", "duration"]
  }
}
```

### Endpoint: `DELETE /session/{session_id}`
Clears session state from memory.

### Endpoint: `GET /health`
Returns `{"status": "healthy"}` for monitoring.

---

## Running the System

### Development Mode (Two Terminals)

**Terminal 1 - Backend:**
```bash
cd medical_chatbot_llm
uv run uvicorn backend.main:app --reload --port 8000
```

**Terminal 2 - Frontend:**
```bash
cd medical_chatbot_llm
uv run streamlit run frontend/streamlit_app.py --server.port 8501
```

### Production Mode (Single Command)

```bash
uv run python run.py
```

Visit: http://localhost:8501

---

## Fallback Strategies

### If Gemma fails JSON parsing:
1. Lower temperature to 0.2
2. Use regex extraction fallback
3. Add `format=json` to Ollama call

### If Ollama is slow:
1. Reduce `num_predict` to 256
2. Use smaller model: `gemma4:9b`
3. Add timeout handling in FastAPI

### If LangGraph version mismatch:
```bash
uv add "langgraph>=0.1.0,<0.3.0"
```

---

## Demo Script (For Company Presentation)

**Scenario 1: Normal Flow**
> Patient: "I have chest pain for 2 days"  
> Bot: "On a scale of 1-10, how severe is the pain?"  
> Patient: "About 6"  
> Bot: *Generates report with chief complaint, duration, severity*

**Scenario 2: Emergency Detection**
> Patient: "Crushing chest pain, can't breathe"  
> Bot: *Immediately shows red alert: "SEEK EMERGENCY CARE"*  
> Bot: *Generates emergency report without further questions*

**Scenario 3: Vague Patient (4-turn limit)**
> Turn 1: "I feel sick" → Ask: "Where is the problem?"  
> Turn 2: "Everywhere" → Ask: "How long?"  
> Turn 3: "Long time" → Ask: "On scale 1-10?"  
> Turn 4: "I don't know" → *Forces partial report*

---

## Known Limitations (Phase 1)

- English only (Bengali translation layer planned for Phase 2)
- No persistent storage (in-memory sessions only)
- No authentication
- Single-threaded (use Redis for production)
- Gemma may occasionally produce malformed JSON

---

## Next Steps After Demo

1. **Add multilingual support** - Integrate IndicTrans2 or GPT-4o for Bengali
2. **Persistent storage** - PostgreSQL for session history
3. **Doctor notification** - Email/SMS integration
4. **Voice input** - Reconnect existing speech recognition
5. **Production deployment** - Docker + Kubernetes

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| `ModuleNotFoundError` | Run `uv sync` to install dependencies |
| Ollama connection refused | Verify `ollama serve` is running |
| JSON parse errors | Check fallback parser in `llm_client.py` |
| LangGraph import error | Check version: `uv run python -c "import langgraph; print(langgraph.__version__)"` |
| Streamlit blank page | Clear browser cache, restart with `--server.enableCORS false` |

---

## Success Criteria

✅ System starts with `python run.py`  
✅ Streamlit interface loads at localhost:8501  
✅ Schema sidebar updates after each turn  
✅ Emergency detection triggers within 1 turn  
✅ All 10 break-test scenarios pass  
✅ Report generates by turn 4 maximum  
✅ No JSON parsing crashes  

---

## File Reference

Complete code for each file is available in the implementation guide. Start with `schema.py` and proceed in order.

**Estimated total implementation time:** 2.5 hours

---

*Last updated: 2026-06-09*  
*Status: Ready for implementation*