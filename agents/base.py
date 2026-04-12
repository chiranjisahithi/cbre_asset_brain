"""
agents/base.py — shared utilities all agents inherit from.
"""
import json
import requests
from memory.db import write_episodic, get_episodic
from config import ANTHROPIC_API_KEY, MODEL, MAX_TOKENS


def call_claude(system_prompt: str, user_prompt: str,
                max_tokens: int = MAX_TOKENS) -> str:
    if not ANTHROPIC_API_KEY:
        raise ValueError("ANTHROPIC_API_KEY not set. Run: export ANTHROPIC_API_KEY=your_key")

    resp = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key":         ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type":      "application/json",
        },
        json={
            "model":      MODEL,
            "max_tokens": max_tokens,
            "system":     system_prompt,
            "messages":   [{"role": "user", "content": user_prompt}],
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["content"][0]["text"]


def parse_json(raw: str) -> dict:
    clean = raw.strip()
    if clean.startswith("```"):
        parts = clean.split("```")
        clean = parts[1]
        if clean.startswith("json"):
            clean = clean[4:]
    try:
        return json.loads(clean.strip())
    except json.JSONDecodeError as e:
        print(f"[parse_json] Failed: {e} | Raw: {raw[:200]}")
        return {}


class BaseAgent:
    name = "base_agent"

    def __init__(self, building_id: str):
        self.building_id = building_id

    def _store(self, content: str, event_type: str,
               floor: str | None = None, salience: float = 0.5,
               metadata: dict | None = None):
        write_episodic(
            building_id=self.building_id,
            agent=self.name,
            event_type=event_type,
            content=content,
            floor=floor,
            salience=min(1.0, max(0.0, salience)),
            metadata=metadata or {},
        )

    def _recent(self, limit: int = 20,
                min_salience: float = 0.0,
                floor: str | None = None) -> list:
        return get_episodic(
            self.building_id,
            limit=limit,
            min_salience=min_salience,
            floor=floor,
        )

    def ingest(self, event: dict):
        raise NotImplementedError(f"{self.__class__.__name__} must implement ingest()")

    def __repr__(self):
        return f"<{self.__class__.__name__} building={self.building_id}>"