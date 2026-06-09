#!/usr/bin/env python3
import subprocess
import time
import sys
import requests
import os

def check_ollama():
    try:
        response = requests.get("http://localhost:11434/api/tags", timeout=2)
        print("✅ Ollama running")
        models = [model.get("name") for model in response.json().get("models", [])]
        if "gemma4:31b-cloud" not in models:
            print("   Warning: gemma4:31b-cloud was not found. Run: ollama pull gemma4:31b-cloud")
        return True
    except Exception:
        print("❌ Ollama not running")
        print("   Start with: ollama serve")
        print("   Then: ollama pull gemma4:31b")
        return False

def wait_for_url(url, label, attempts=30, delay=0.5):
    for _ in range(attempts):
        try:
            requests.get(url, timeout=2)
            return True
        except Exception:
            time.sleep(delay)
    print(f"âŒ {label} did not become ready within {attempts * delay:.0f}s")
    return False

def main():
    if not check_ollama():
        sys.exit(1)
    
    print("\n🚀 Starting Medical Assistant...")
    
    # Start backend
    backend = subprocess.Popen(
        ["uv", "run", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    
    if not wait_for_url("http://localhost:8000/health", "Backend"):
        backend.terminate()
        backend.wait()
        sys.exit(1)
    
    # Start frontend
    frontend = subprocess.Popen(
        ["uv", "run", "streamlit", "run", "frontend/streamlit_app.py", "--server.port", "8501"]
    )
    
    if not wait_for_url("http://localhost:8501", "Frontend"):
        backend.terminate()
        frontend.terminate()
        backend.wait()
        frontend.wait()
        sys.exit(1)
    
    print("\n✅ Ready!")
    print("   Backend: http://localhost:8000")
    print("   Frontend: http://localhost:8501")
    print("\nPress Ctrl+C to stop\n")
    
    try:
        backend.wait()
    except KeyboardInterrupt:
        print("\n🛑 Shutting down...")
        backend.terminate()
        frontend.terminate()
        backend.wait()
        frontend.wait()

if __name__ == "__main__":
    main()
