"""
agents/ops_agent.py — Operations Agent.
Ingests sensor/equipment events, detects anomalies, boosts floor patterns.
Broadcasts to MaintenanceAgent and TenantAgent when relevant.
"""
from agents.base import BaseAgent
from memory.db import get_conn

SEVERITY_KEYWORDS = {
    "critical": 1.0, "failure": 0.95, "shutdown": 0.95,
    "emergency": 0.95, "urgent": 0.9, "anomaly": 0.8,
    "alert": 0.75, "warning": 0.65, "offline": 0.6,
}
PATTERN_THRESHOLD    = 3
PATTERN_SALIENCE_MIN = 0.6
PATTERN_BOOST        = 0.2
PATTERN_WINDOW_DAYS  = 7


class OpsAgent(BaseAgent):
    name = "ops_agent"

    def ingest(self, event: dict):
        content    = event.get("content", str(event))
        floor      = event.get("floor")
        event_type = event.get("event_type", "sensor")
        salience   = float(event.get("salience", 0.4))

        if event.get("anomaly"):
            salience = max(salience, 0.8)

        for kw, boost in SEVERITY_KEYWORDS.items():
            if kw in content.lower():
                salience = max(salience, boost)
                break

        self._store(content=content, event_type=event_type,
                    floor=floor, salience=salience, metadata=event)
        print(f"[OpsAgent] salience={salience:.2f} | {content[:60]}")

        if floor:
            self._check_floor_pattern(floor)

        # Broadcast to other agents
        from agents.cross_agent import ops_broadcast
        ops_broadcast(self.building_id, content, floor=floor, salience=salience)

    def _check_floor_pattern(self, floor: str):
        recent = self._recent(limit=20,
                              min_salience=PATTERN_SALIENCE_MIN,
                              floor=floor)
        floor_events = [e for e in recent
                        if e["agent"] == self.name and e["floor"] == floor]

        if len(floor_events) >= PATTERN_THRESHOLD:
            conn = get_conn()
            conn.execute("""
                UPDATE episodic
                SET salience = MIN(1.0, salience + ?)
                WHERE building_id=? AND floor=? AND agent=?
                  AND timestamp > datetime('now', ? || ' days')
            """, (PATTERN_BOOST, self.building_id, floor,
                  self.name, f"-{PATTERN_WINDOW_DAYS}"))
            conn.commit()
            conn.close()
            print(f"[OpsAgent] Pattern floor {floor} "
                  f"({len(floor_events)} events) — salience boosted")

    def get_anomalies(self, min_salience: float = 0.7) -> list:
        return [e for e in self._recent(limit=50, min_salience=min_salience)
                if e["agent"] == self.name]