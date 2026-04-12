"""
agents/tenant_agent.py — Tenant Agent.
Scores complaint severity, flags lease risk, tracks per-tenant history.
Broadcasts to MarketAgent and MaintenanceAgent when relevant.
"""
from agents.base import BaseAgent

CRITICAL_WORDS  = ["break lease", "terminate", "legal", "lawyer",
                   "unacceptable", "demand", "vacate"]
HIGH_WORDS      = ["urgent", "escalate", "frustrated", "angry",
                   "formal complaint", "compensation"]
MEDIUM_WORDS    = ["unhappy", "issue", "problem", "concern",
                   "uncomfortable", "warm", "cold", "noisy"]
LEASE_RISK_WORDS = ["looking at other", "alternatives", "competitor",
                    "other buildings", "moving out", "not renewing",
                    "reconsidering"]


def _score(content: str) -> tuple:
    lower = content.lower()
    for w in CRITICAL_WORDS:
        if w in lower: return 0.95, "critical"
    for w in HIGH_WORDS:
        if w in lower: return 0.82, "high"
    for w in MEDIUM_WORDS:
        if w in lower: return 0.70, "medium"
    return 0.60, "low"

def _lease_risk(content: str) -> bool:
    return any(w in content.lower() for w in LEASE_RISK_WORDS)


class TenantAgent(BaseAgent):
    name = "tenant_agent"

    def ingest(self, event: dict):
        raw_content = event.get("content", str(event))
        floor       = event.get("floor")
        tenant_id   = event.get("tenant_id", "unknown")

        salience, severity = _score(raw_content)
        if "salience" in event:
            salience = max(salience, float(event["salience"]))

        risk_flag = ""
        if _lease_risk(raw_content):
            risk_flag = " [LEASE RISK]"
            salience  = max(salience, 0.9)

        content = f"[Tenant {tenant_id}]{risk_flag} {raw_content}"

        self._store(content=content, event_type="tenant_signal",
                    floor=floor, salience=salience,
                    metadata={**event, "severity": severity,
                               "lease_risk": bool(risk_flag)})
        print(f"[TenantAgent] {severity.upper()}"
              f"{' LEASE RISK' if risk_flag else ''} "
              f"from {tenant_id}: {raw_content[:50]}")

        # Broadcast to other agents
        from agents.cross_agent import tenant_broadcast
        tenant_broadcast(self.building_id, raw_content, floor=floor, salience=salience)

    def get_tenant_history(self, tenant_id: str) -> list:
        return [e for e in self._recent(limit=200)
                if tenant_id.lower() in e["content"].lower()
                and e["agent"] == self.name]

    def get_lease_risks(self) -> list:
        return [e for e in self._recent(limit=100, min_salience=0.85)
                if "LEASE RISK" in e["content"]
                and e["agent"] == self.name]