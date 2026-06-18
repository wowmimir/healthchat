import json
import os
from pathlib import Path
from typing import Any

import requests
from pydantic import BaseModel, Field


DOCTOR_API_URL = "https://app.peerlessgjct.co.in/api/chatbot/doctors"
DEFAULT_LIMIT = 5


class Doctor(BaseModel):
    id: int
    name: str
    profile_image: str = ""
    experience: int | None = None
    app_url: str = ""
    web_url: str = ""
    specialities: list[dict[str, Any]] = Field(default_factory=list)
    speciality_names: str = ""
    availability_status: str = ""
    next_available_date: str = ""
    next_available_time: str = ""
    next_available_slot: str = ""


class DoctorLookupResult(BaseModel):
    keyword: str
    doctors: list[Doctor] = Field(default_factory=list)
    error: str | None = None


class DoctorClient:
    def __init__(self, token: str | None = None, timeout: int = 10):
        self.token = token or os.getenv("CHATBOT_DOCTOR_TOKEN") or self._load_demo_token()
        self.timeout = timeout

    def lookup(self, keyword: str, limit: int = DEFAULT_LIMIT) -> DoctorLookupResult:
        clean_keyword = (keyword or "medicine").strip() or "medicine"
        if not self.token:
            return DoctorLookupResult(keyword=clean_keyword, error="Doctor API token missing")

        try:
            response = requests.post(
                DOCTOR_API_URL,
                headers={
                    "X-Chatbot-Token": self.token,
                    "Content-Type": "application/json",
                },
                json={"keyword": clean_keyword, "limit": limit},
                timeout=self.timeout,
            )
            response.raise_for_status()
            payload = response.json()
            doctors = [Doctor.model_validate(item) for item in payload.get("data", [])]
            return DoctorLookupResult(keyword=payload.get("keyword") or clean_keyword, doctors=doctors)
        except Exception as exc:
            return DoctorLookupResult(keyword=clean_keyword, error=str(exc))

    def _load_demo_token(self) -> str | None:
        api_doc = Path(__file__).resolve().parents[1] / "apiendpoint.json"
        try:
            payload = json.loads(api_doc.read_text(encoding="utf-8"))
            headers = payload["item"][0]["request"]["header"]
            for header in headers:
                if header.get("key") == "X-Chatbot-Token":
                    return header.get("value")
        except Exception:
            return None
        return None
