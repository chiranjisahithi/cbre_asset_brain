"""
agents/maint_agent.py — Maintenance Agent.
Status-based salience, detects floor patterns, writes procedural rules.
Broadcasts to OpsAgent when critical repairs are found.
"""
from agents.base import BaseAgent
from memory.db import write_procedural, get_procedural

STATUS_SALIENCE = {
    "emergency": 0.95, "critical": 0.92, "overdue": 0.85,
    "pending": 0.65, "scheduled": 0.50, "logged": 0.45,
    "completed": 0.20,
}
RULE_THRESHOLD = 3


class MaintenanceAgent(BaseAgent):
    name = "maintenance_agent"

    def ingest(self, event: dict):
        content  = event.get("content", str(event))
        floor    = event.get("floor")
        status   = event.get("status", "logged").lower()
        salience = STATUS_SALIENCE.get(status, 0.5)

        if any(w in content.lower()
               for w in ["emergency", "critical", "urgent"]):
            salience = max(salience, 0.9)

        self._store(content=content, event_type="maintenance",
                    floor=floor, salience=salience,
                    metadata={**event, "status": status})
        print(f"[MaintenanceAgent] [{status.upper()}] {content[:60]}")

        if floor:
            self._check_floor_pattern(floor)

        # Broadcast to other agents
        from agents.cross_agent import maint_broadcast
        maint_broadcast(self.building_id, content, floor=floor, salience=salience)

    def _check_floor_pattern(self, floor: str):
        recent = self._recent(limit=50, min_salience=0.3)
        floor_maint = [e for e in recent
                       if e["agent"] == self.name
                       and e["floor"] == floor]

        if len(floor_maint) < RULE_THRESHOLD:
            return

        existing = get_procedural(self.building_id, agent=self.name)
        for rule in existing:
            if floor in rule.get("trigger_condition", ""):
                return

        write_procedural(
            building_id=self.building_id,
            agent=self.name,
            rule=f"Recurring maintenance pattern on floor {floor}",
            trigger_condition=f"{RULE_THRESHOLD}+ maintenance events floor {floor} within 30 days",
            action=f"Auto-schedule preventive inspection floor {floor}. Escalate if unresolved.",
            confidence=0.78,
        )
        print(f"[MaintenanceAgent] Procedural rule written for floor {floor}")

    def check_overdue(self):
        recent = self._recent(limit=100, min_salience=0.3)
        maint  = [e for e in recent if e["agent"] == self.name]
        if len(maint) < 5:
            return
        existing = get_procedural(self.building_id, agent=self.name)
        if not existing:
            write_procedural(
                building_id=self.building_id,
                agent=self.name,
                rule="Preventive maintenance reduces emergency callouts",
                trigger_condition="Any floor with 2+ maintenance events in 30 days",
                action="Schedule preventive inspection. Prioritise floors with co-occurring tenant complaints.",
                confidence=0.82,
            )
            print("[MaintenanceAgent] Portfolio-level procedural rule written")