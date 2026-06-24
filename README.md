# Rural Medical Intake Assistant Documentation

A high-performance, resilient multi-turn symptom screening chat application designed for rural health intake. The platform dynamically collects clinical indicators, maps them against safety parameters, flags high-priority emergencies, isolates functional limitations, and matches individuals with local care providers using an intelligent state-machine runtime.

---

# 1. System Setup & Installation

## Initializing Environment
1. Clone the repository to your local machine.
2. Initialize and create the virtual environment using `uv`:
   ```
   uv init
   uv venv
3. Activate the virtual environment:

    #### On Windows (Command Prompt/PowerShell)
    ```.venv\Scripts\activate```

    #### On macOS/Linux
    ```source .venv/bin/activate```



4. Install all python dependencies from the requirements manifest file:
```uv add -r req.txt```




## Ollama Core Setup

1. Download and install [Ollama](https://ollama.com).
2. Pull the designated diagnostic intake model:
```ollama pull gemma4:31b-cloud```


3. Verify that the Ollama background daemon is active and serving traffic locally at: `http://localhost:11434`

---

# 2. Running the Application

### Running Frontend

```cd vite-frontend``` followed by ```bun dev```

*The React user interface will spin up locally at:* **`http://localhost:5173`**

### Running Backend

```uv run uvicorn backend.main:app --reload --port 8000```

*The FastAPI middleware layer will bind locally at:* **`http://localhost:8000`**

---

# 3. Architecture Breakdowns

## A. Backend Architecture

### Libraries & Tools Used

* **FastAPI & Uvicorn**: High-throughput Asynchronous Server Gateway Interface (ASGI) routing engine.
* **LangGraph**: State machine orchestrator used to build cyclic/acyclic computational graphs.
* **Pydantic v2**: Strict data validation layer enforcing type safety on the incoming message objects and internal states.
* **SQLite (via sqlite3)**: Embedded relational file system utilizing Write-Ahead Logging (WAL mode) for asset auditing and transaction reliability.

### How it Works (Core Logic)

The backend utilizes a **LangGraph State Machine** to manage the lifecycle of a patient interview session.

1. **Intake & Extraction**: The incoming message is fed into an extraction node. The LLM processes the message to perform slot-filling across discrete tiers (Domain A: Demographics; Domain B: Clinical presentation).
2. **Fallback Regex Layer**: If the model experiences syntax anomalies or returns incomplete JSON delimiters, a secondary regular expression fallback engine dissects the string to recover clinical fields.
3. **Emergency Scanning**: Critical phrase lists filter user context. If explicit danger metrics or profound functional limitations (e.g., "cannot stand/walk", "crushing chest pain") are encountered, the engine flags an emergency state.
4. **Conditional Routing**: A completeness tracker assesses missing fields. If severe or emergency indicators are logged, the router immediately short-circuits the conversation. Otherwise, it generates custom questions to gather missing details.
5. **Lifespan Storage**: On session finalization, the complete conversational graph converts back into a Pydantic object and commits structural columns along with a full raw metadata JSON document to a **SQLite database**.

### Expected Output Payload

Upon receiving a POST request to `/chat`, the backend guarantees a strictly structured JSON response:

````json
{
    "response": "Could you please tell me your area of residence?",
    "session_complete": false,
    "emergency": false,
    "current_schema": {
        "patient_name": "Maria",
        "age": 29,
        "biological_sex": "female",
        "residence_area": null,
        "chief_complaint": "fever",
        "severity": "moderate",
        "duration": "2 days",
        "associated_symptoms": ["weakness", "exhaustion"],
        "functional_limitation": null,
        "doctor_keyword": "medicine",
        "emergency_flag": false,
        "turn_count": 1
    },
    "doctor_keyword": null,
    "doctors": [],
    "doctor_lookup_error": null
}
````


## B. Frontend Architecture

### Libraries & Tools Used

* **React (Vite-Powered)**: Reactive UI runtime optimized for asset loading speeds and lightweight DOM adjustments.
* **Tailwind CSS**: Utility-first CSS layout styling engine providing a clean, accessible interface.
* **Bun**: Fast JavaScript bundler and workspace runtime environment.

### How it Works (Core Logic)

1. **Session Control**: Generates a completely unique `crypto.randomUUID()` on app boot to partition chat memory. Clicking "New Session" fires an async DELETE request to empty backend caches before recycling the state hooks.
2. **Timeline Isolation & Regex Suppression**: When processing API text arrays, the application utilizes text string interceptors (`includes('Patient Summary:')`, `includes('URGENT MEDICAL ATTENTION')`). If the AI responds with a structural diagnostic report or triage assessment block, the frontend suppresses it from rendering as a standard speech bubble, storing it silently in a background state instead.
3. **Dynamic Presentation Layers**: Monitors real-time boolean updates from the API. If `emergency: true`, it flashes a warning element and renders an emergency hotline dashboard. If `session_complete: true`, it safely locks the input bar and maps the provider index.

### Expected UI Render Components

* **Active Intake Module**: Renders classic scrolling dual-role chat timelines with customized background color tags (Emerald for users, Slate for the digital assistant).
* **Emergency Dashboard Module**: Replaces standard advice text blocks with animated critical alert indicators and high-contrast helpline cards.
* **Provider Allocation Module**: Loops over available doctor payloads to build booking directory cards detailing name, specialization, experience metrics, availability date slots, and external web navigation paths.

---

# 4. End-to-End Chat User Flow

1. **Initialization**: The user accesses the web portal. The frontend instantiates an individual tracking UUID and displays an introductory context box welcoming input.
2. **Initial Complaint**: The patient inputs their primary symptoms (e.g., *"Hi, my name is John Doe. I am 42 years old from West End village. I've had severe throbbing headache for 3 days and now I'm completely unable to open my right eye because it hurts too much."*).
3. **Triage Threshold Check**:
* **Scenario Alpha (Critical/Severe Life Threat)**: The pipeline flags severe pain or inability to open the eye. The system switches `session_complete` to `true`, halts validation prompts, updates the SQLite ledger, and pushes critical helpline modules immediately onto the screen on Turn 1.
* **Scenario Beta (Routine Consultation)**: The criteria are marked as mild/moderate. The graph detects that the user provided their name, age, and duration, but omitted their biological sex. It continues the interview loop, generating an interview question: *"Could you share your biological sex for the doctor summary?"*


4. **Iterative Collection Loop**: The user answers the specific query. The system slots the new field into place while maintaining absolute retention of previous details across the turn.
5. **Session Convergence**: Once all slots are resolved—or if the graph hits the maximum interaction floor of 4 turns—the loop breaks.
6. **Provider Matching & Closeout**: The backend resolves the proper medical specialization keyword (e.g., `"neurology"`, `"orthopedic"`, or general `"medicine"` fallback), queries local clinics, stores the finalized asset to the database, and locks the interface, presenting the patient with localized booking choices.
