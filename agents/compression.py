"""
agents/compression.py — Memory Compression Engine.
Step 1: Compress episodic -> semantic patterns (via Claude).
Step 2: Derive procedural rules from semantic patterns (logic-based, no API needed).
Applies decay.
"""
from agents.base import call_claude, parse_json
from memory.db import (get_episodic, get_semantic,
                       write_semantic, write_procedural, decay_episodic)
from config import BUILDING_ID

SEMANTIC_SYSTEM = """You are a memory compression engine for a CBRE commercial building AI.
You receive recent building events from 4 agents:
- ops_agent: sensor data, equipment alerts
- tenant_agent: tenant complaints and requests
- maintenance_agent: work orders, inspection notes
- market_agent: lease dates, market signals

Extract 2-4 meaningful patterns. The BEST patterns connect signals
from DIFFERENT agents — these are the cross-domain insights CBRE needs.

Respond ONLY with valid JSON, no markdown:
{
  "patterns": [
    {
      "topic": "snake_case_topic",
      "summary": "2-3 sentences. What signals led to this? Why does it matter to CBRE?",
      "confidence": 0.0-1.0,
      "urgency": "low|medium|high|critical",
      "agents_involved": ["ops_agent", "tenant_agent"]
    }
  ]
}"""

# ── Rule templates: derived from pattern keywords, no API needed ────────────
RULE_TEMPLATES = [
    {
        "keywords": ["hvac", "temperature", "heating", "cooling", "air"],
        "agent": "maintenance_agent",
        "rule": "HVAC anomalies linked to tenant complaints require immediate dispatch",
        "trigger_condition": "HVAC/temperature event with salience >= 0.7 AND concurrent tenant complaint on same floor",
        "action": "Dispatch maintenance within 2 hours. Notify tenant relations. Log work order.",
        "confidence": 0.82,
    },
    {
        "keywords": ["lease", "renewal", "expir", "not renewing", "terminate"],
        "agent": "market_agent",
        "rule": "Tenants signalling lease risk must be escalated to leasing team within 24h",
        "trigger_condition": "Tenant complaint containing lease-risk language OR market signal within 90 days of expiry",
        "action": "Alert leasing team. Schedule retention call. Review competitor offers in area.",
        "confidence": 0.88,
    },
    {
        "keywords": ["elevator", "lift", "escalator"],
        "agent": "maintenance_agent",
        "rule": "Repeated elevator incidents on same floor trigger engineering inspection",
        "trigger_condition": "2+ elevator-related events on same floor within 7 days",
        "action": "Escalate to building engineering. Take unit offline if safety risk. Notify tenants.",
        "confidence": 0.85,
    },
    {
        "keywords": ["competitor", "free rent", "incentive", "other building"],
        "agent": "market_agent",
        "rule": "Competitor incentive signals require proactive tenant outreach",
        "trigger_condition": "Market signal mentioning competitor offering OR free rent in same submarket",
        "action": "Brief property manager. Prepare retention package. Identify at-risk tenants.",
        "confidence": 0.79,
    },
    {
        "keywords": ["flood", "leak", "water", "pipe"],
        "agent": "ops_agent",
        "rule": "Water/leak events must trigger cross-floor inspection immediately",
        "trigger_condition": "Any water or leak event with salience >= 0.6",
        "action": "Inspect floor above and below. Notify insurance if damage. Evacuate if structural risk.",
        "confidence": 0.91,
    },
    {
        "keywords": ["power", "electrical", "outage", "offline", "shutdown"],
        "agent": "ops_agent",
        "rule": "Electrical failures require tenant notification and backup activation",
        "trigger_condition": "Power/electrical event affecting tenant floors with salience >= 0.7",
        "action": "Activate backup systems. Notify affected tenants within 15 min. Log for insurance.",
        "confidence": 0.87,
    },
    {
        "keywords": ["complaint", "frustrated", "angry", "escalate", "unacceptable"],
        "agent": "tenant_agent",
        "rule": "High-severity tenant complaints trigger same-day property manager response",
        "trigger_condition": "Tenant complaint scored high or critical severity",
        "action": "Property manager contacts tenant within 4 hours. Document resolution. Follow-up in 48h.",
        "confidence": 0.84,
    },
    {
        "keywords": ["vacancy", "occupancy", "empty", "available"],
        "agent": "market_agent",
        "rule": "Vacancy spikes in a building require pricing and marketing review",
        "trigger_condition": "Occupancy drop signal OR 2+ lease terminations in same quarter",
        "action": "Review asking rents vs market. Launch targeted outreach. Consider broker incentives.",
        "confidence": 0.76,
    },
]


class CompressionEngine:

    def __init__(self, building_id: str = BUILDING_ID):
        self.building_id = building_id

    def run(self) -> dict | None:
        print(f"[Compression] Running for {self.building_id}...")
        episodes = get_episodic(self.building_id, limit=40, min_salience=0.25)

        if len(episodes) < 3:
            print("[Compression] Need 3+ episodes to compress")
            return None

        # ── Step 1: Semantic compression via Claude ────────────────
        data = None
        try:
            lines = [
                f"- [{e['timestamp'][:10]}] [{e['agent']}] "
                f"Floor {e['floor'] or 'N/A'} "
                f"(salience {e['salience']:.2f}): {e['content']}"
                for e in episodes
            ]
            user = (f"Building: {self.building_id}\n"
                    f"Events ({len(episodes)} total):\n"
                    + "\n".join(lines)
                    + "\n\nExtract 2-4 cross-domain patterns.")

            raw  = call_claude(SEMANTIC_SYSTEM, user, max_tokens=900)
            data = parse_json(raw)

            if data and "patterns" in data:
                source_ids = [e["id"] for e in episodes[:10]]
                for p in data["patterns"]:
                    write_semantic(
                        building_id=self.building_id,
                        topic=p["topic"],
                        summary=p["summary"],
                        confidence=p.get("confidence", 0.7),
                        source_ids=source_ids,
                    )
                    print(f"[Compression] semantic [{p['topic']}] urgency={p.get('urgency','?')}")
                decay_episodic(self.building_id)
                print("[Compression] Decay applied")
            else:
                print("[Compression] No patterns returned from Claude")

        except Exception as ex:
            print(f"[Compression] Semantic step error: {ex}")

        # ── Step 2: Procedural rules — logic-based, always runs ────
        # This runs whether or not Step 1 succeeded
        self._derive_procedural_rules()

        return data

    def _derive_procedural_rules(self):
        """
        Derive IF-THEN rules from semantic patterns using keyword matching.
        No API call needed — works deterministically from what's in memory.
        """
        patterns = get_semantic(self.building_id)
        if not patterns:
            print("[Compression] No semantic patterns yet — skipping rule derivation")
            return

        # Build a combined text blob from all pattern summaries + topics
        pattern_text = " ".join(
            f"{p['topic']} {p['summary']}"
            for p in patterns
        ).lower()

        rules_written = 0
        for template in RULE_TEMPLATES:
            # Check if any keyword from this template appears in the patterns
            if not any(kw in pattern_text for kw in template["keywords"]):
                continue

            try:
                write_procedural(
                    building_id=self.building_id,
                    agent=template["agent"],
                    rule=template["rule"],
                    trigger_condition=template["trigger_condition"],
                    action=template["action"],
                    confidence=template["confidence"],
                )
                print(f"[Compression] procedural rule: {template['rule'][:65]}")
                rules_written += 1
            except Exception as ex:
                print(f"[Compression] Rule write error: {ex}")

        print(f"[Compression] {rules_written} procedural rules written/updated")