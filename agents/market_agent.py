"""
agents/market_agent.py — Market Agent.
Lease expiry scoring, competitor signals, vacancy trends.
Broadcasts to TenantAgent when market pressure is detected.
"""
import re
from agents.base import BaseAgent

LEASE_EXPIRY_SALIENCE = {30: 1.0, 60: 0.90, 90: 0.85, 180: 0.65}
HIGH_WORDS   = ["competitor", "free rent", "incentive", "vacancy up",
                "not renewing", "lease risk", "subletting"]
MEDIUM_WORDS = ["lease expir", "renewal", "market rate", "vacancy",
                "comparable", "rent down"]


def _score(content: str, base: float) -> float:
    lower = content.lower()
    for w in HIGH_WORDS:
        if w in lower: return max(base, 0.85)
    for w in MEDIUM_WORDS:
        if w in lower: return max(base, 0.65)
    return base


def _days_to_expiry(content: str):
    m = re.search(r'(\d+)\s*days?', content.lower())
    return int(m.group(1)) if m else None


class MarketAgent(BaseAgent):
    name = "market_agent"

    def ingest(self, event: dict):
        content  = event.get("content", str(event))
        floor    = event.get("floor")
        salience = _score(content, float(event.get("salience", 0.5)))

        days = _days_to_expiry(content)
        if days is not None:
            for threshold, s in sorted(LEASE_EXPIRY_SALIENCE.items()):
                if days <= threshold:
                    salience = max(salience, s)
                    break

        self._store(content=content, event_type="market_signal",
                    floor=floor, salience=salience,
                    metadata={**event, "days_to_expiry": days})
        print(f"[MarketAgent] salience={salience:.2f} | {content[:60]}")

        # Broadcast to other agents
        from agents.cross_agent import market_broadcast
        market_broadcast(self.building_id, content, floor=floor, salience=salience)

    def get_lease_risks(self) -> list:
        return [e for e in self._recent(limit=50, min_salience=0.7)
                if e["agent"] == self.name
                and any(w in e["content"].lower()
                        for w in ["lease", "renewal", "expir"])]

    def get_competitor_signals(self) -> list:
        return [e for e in self._recent(limit=50, min_salience=0.6)
                if e["agent"] == self.name
                and any(w in e["content"].lower()
                        for w in ["competitor", "free rent", "incentive"])]