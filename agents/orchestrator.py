"""
agents/orchestrator.py — Orchestrator Agent.
Reasons over all 3 memory tiers to answer property manager questions.

RETRIEVAL: Context-sensitive — question keywords filter which episodic
events and semantic patterns are surfaced, so memory actually shapes
what the agent sees before it answers.
"""
from agents.base import BaseAgent, call_claude, parse_json
from memory.db import get_episodic, get_semantic, get_procedural

# Keywords that map question intent → episodic agent filter
INTENT_MAP = {
    "hvac":        ["ops_agent", "maintenance_agent"],
    "temperature": ["ops_agent", "maintenance_agent"],
    "tenant":      ["tenant_agent", "market_agent"],
    "lease":       ["market_agent", "tenant_agent"],
    "complaint":   ["tenant_agent"],
    "maintenance": ["maintenance_agent"],
    "elevator":    ["maintenance_agent", "ops_agent"],
    "market":      ["market_agent"],
    "power":       ["ops_agent"],
    "water":       ["ops_agent", "maintenance_agent"],
    "floor":       None,   # no agent filter — any floor match
}

SYSTEM = """You are the AI brain of a CBRE-managed commercial building.
You have persistent memory across three tiers:

EPISODIC — specific events (date, agent, floor, salience 0-1)
  High salience (0.8+) = important/recent. Low (0.2) = fading.
  These were PRE-FILTERED by question context — most relevant events first.

SEMANTIC — patterns Claude compressed from many events (versioned).
  Higher confidence = more evidence. version > 1 = pattern has evolved.

PROCEDURAL — IF-THEN rules the system learned. These MUST influence your answer:
  If a relevant rule exists, your recommended_action must reference it.

Answer the property manager's question using ALL THREE tiers.
Rules:
1. Cite specific memories that informed your answer
2. Cross-reference across agents — connecting ops+tenant+market is the most valuable
3. Be direct and actionable
4. If a procedural rule fires, explicitly say so in your answer
5. Explain WHICH memory tier most drove your answer

Respond ONLY with valid JSON, no markdown:
{
  "answer": "2-4 sentence answer",
  "citations": ["[agent date floor sal=X]: brief content", "..."],
  "urgency": "low|medium|high|critical",
  "recommended_action": "one specific next step",
  "cross_domain_insight": "how signals from different agents connect",
  "memory_tier_used": "episodic|semantic|procedural|all",
  "procedural_rule_fired": "rule text or null",
  "retrieval_context": "what keywords filtered memory for this question"
}"""


def _context_retrieve(building_id: str, question: str) -> dict:
    """
    Context-sensitive retrieval: question keywords determine which agents
    and floors are prioritised. This makes retrieval visibly drive decisions.
    """
    q_lower = question.lower()

    # Detect floor mentioned in question
    floor_filter = None
    for word in q_lower.split():
        if word.isdigit() and 1 <= int(word) <= 50:
            floor_filter = word
            break
        if word.startswith("floor"):
            digits = word.replace("floor", "").strip()
            if digits.isdigit():
                floor_filter = digits

    # Detect intent → agent filter
    matched_agents = set()
    matched_keywords = []
    for kw, agents in INTENT_MAP.items():
        if kw in q_lower:
            matched_keywords.append(kw)
            if agents:
                matched_agents.update(agents)

    # Episodic: context-filtered first, then broad fallback
    if matched_agents or floor_filter:
        # Targeted fetch
        targeted = get_episodic(
            building_id, limit=20, min_salience=0.3, floor=floor_filter
        )
        if matched_agents:
            targeted = [e for e in targeted if e["agent"] in matched_agents]
        # Pad with recent high-salience events if we got fewer than 8
        if len(targeted) < 8:
            broad = get_episodic(building_id, limit=30, min_salience=0.5)
            seen  = {e["id"] for e in targeted}
            targeted += [e for e in broad if e["id"] not in seen]
        episodic = targeted[:20]
    else:
        episodic = get_episodic(building_id, limit=20, min_salience=0.3)

    # Semantic: filter by keyword match in topic/summary
    all_semantic = get_semantic(building_id)
    if matched_keywords:
        relevant_sem = [
            p for p in all_semantic
            if any(kw in (p["topic"] + " " + p["summary"]).lower()
                   for kw in matched_keywords)
        ]
        # Pad with high-confidence patterns
        seen = {p["id"] for p in relevant_sem}
        relevant_sem += [p for p in all_semantic
                         if p["id"] not in seen and p["confidence"] >= 0.7]
        semantic = relevant_sem[:10]
    else:
        semantic = all_semantic

    # Procedural: filter rules relevant to question
    all_proc = get_procedural(building_id)
    if matched_agents:
        relevant_proc = [r for r in all_proc if r["agent"] in matched_agents]
        if not relevant_proc:
            relevant_proc = all_proc
    else:
        relevant_proc = all_proc

    return {
        "episodic":         episodic,
        "semantic":         semantic,
        "procedural":       relevant_proc,
        "retrieval_filter": {
            "keywords":    matched_keywords,
            "agents":      list(matched_agents),
            "floor":       floor_filter,
        }
    }


class OrchestratorAgent(BaseAgent):
    name = "orchestrator_agent"

    def answer(self, question: str) -> dict:
        # Context-sensitive retrieval
        memory = _context_retrieve(self.building_id, question)
        rf     = memory["retrieval_filter"]

        episodic_text = "\n".join([
            f"  [{e['timestamp'][:10]}] [{e['agent']}] "
            f"Floor {e['floor'] or 'Bldg'} "
            f"(sal {e['salience']:.2f}): {e['content']}"
            for e in memory["episodic"]
        ]) or "  None yet."

        semantic_text = "\n".join([
            f"  [{p['topic']}] conf={p['confidence']:.2f} v{p.get('version',1)}: {p['summary']}"
            for p in memory["semantic"]
        ]) or "  None yet — run compression."

        procedural_text = "\n".join([
            f"  RULE [{r['agent']}] (fired {r['times_applied']}x): {r['rule']}\n"
            f"    Trigger: {r['trigger_condition']}\n"
            f"    Action:  {r['action']}"
            for r in memory["procedural"]
        ]) or "  None yet."

        retrieval_note = (
            f"Retrieval filtered by: keywords={rf['keywords']}, "
            f"agents={rf['agents']}, floor={rf['floor']}"
        )

        user = f"""Building: {self.building_id}
{retrieval_note}

=== EPISODIC ({len(memory['episodic'])} context-filtered events) ===
{episodic_text}

=== SEMANTIC ({len(memory['semantic'])} patterns, versioned) ===
{semantic_text}

=== PROCEDURAL ({len(memory['procedural'])} rules) ===
{procedural_text}

=== QUESTION ===
{question}"""

        try:
            raw    = call_claude(SYSTEM, user, max_tokens=1400)
            result = parse_json(raw)
            if not result:
                raise ValueError("Empty JSON")
            result["memory_used"] = {
                "episodic_count":   len(memory["episodic"]),
                "semantic_count":   len(memory["semantic"]),
                "procedural_count": len(memory["procedural"]),
                "retrieval_filter": rf,
            }
            return result
        except Exception as ex:
            print(f"[Orchestrator] Error: {ex}")
            return {
                "answer": f"Error: {ex}. Is ANTHROPIC_API_KEY set?",
                "citations": [], "urgency": "low",
                "recommended_action": "Check server logs",
                "cross_domain_insight": "",
                "memory_tier_used": "none",
                "procedural_rule_fired": None,
                "retrieval_context": retrieval_note,
                "memory_used": {
                    "episodic_count":   len(memory["episodic"]),
                    "semantic_count":   len(memory["semantic"]),
                    "procedural_count": len(memory["procedural"]),
                    "retrieval_filter": rf,
                },
            }