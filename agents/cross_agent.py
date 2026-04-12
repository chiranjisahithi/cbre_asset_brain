"""
agents/cross_agent.py — Cross-Agent Communication Bus.

When one agent ingests an event, it can broadcast a signal to other agents
so they can react with their own perspective. This is what makes the system
a true multi-agent memory network rather than 4 isolated silos.

Examples:
  - OpsAgent detects HVAC failure → notifies MaintenanceAgent to log work order
                                  → notifies TenantAgent to watch for complaints
  - TenantAgent gets lease-risk complaint → notifies MarketAgent to flag renewal
  - MaintenanceAgent logs overdue repair → notifies OpsAgent to raise alert salience
  - MarketAgent sees competitor offer → notifies TenantAgent to watch churn risk
"""

from memory.db import get_episodic, write_episodic
from datetime import datetime


# ── Keyword triggers for cross-agent reactions ─────────────────────────────

OPS_TO_MAINT = ["hvac", "elevator", "failure", "shutdown", "leak",
                 "electrical", "power", "equipment", "offline", "alert"]

OPS_TO_TENANT = ["temperature", "temp", "air quality", "noise",
                  "water", "outage", "smoke"]

TENANT_TO_MARKET = ["lease risk", "not renewing", "moving out",
                     "looking at other", "alternatives", "competitor",
                     "terminate", "vacate"]

TENANT_TO_MAINT = ["too warm", "too cold", "warm", "cold", "hvac",
                    "broken", "leak", "noise", "elevator", "smell"]

MAINT_TO_OPS = ["overdue", "emergency repair", "critical", "failed",
                 "structural", "fire", "flood"]

MARKET_TO_TENANT = ["competitor offering", "free rent", "incentive",
                     "lease expir", "not renewing"]


def _matches(content: str, keywords: list) -> bool:
    lower = content.lower()
    return any(k in lower for k in keywords)


def _cross_write(building_id: str, agent: str, content: str,
                 event_type: str, floor=None, salience: float = 0.65):
    """Write a cross-agent reaction event into episodic memory."""
    write_episodic(
        building_id=building_id,
        agent=agent,
        event_type=event_type,
        content=content,
        floor=floor,
        salience=salience,
        metadata={"cross_agent": True, "generated_at": datetime.now().isoformat()}
    )
    print(f"[CrossAgent] {agent} reacted → {content[:70]}")


# ── Public interface ────────────────────────────────────────────────────────

def ops_broadcast(building_id: str, content: str, floor=None, salience: float = 0.5):
    """Called by OpsAgent after ingesting an event."""

    if _matches(content, OPS_TO_MAINT):
        _cross_write(
            building_id=building_id,
            agent="maintenance_agent",
            content=f"[Auto-flagged by OpsAgent] Equipment issue may require work order: {content}",
            event_type="cross_agent_alert",
            floor=floor,
            salience=min(1.0, salience + 0.1),
        )

    if _matches(content, OPS_TO_TENANT):
        _cross_write(
            building_id=building_id,
            agent="tenant_agent",
            content=f"[Auto-flagged by OpsAgent] Environmental issue may impact tenant comfort: {content}",
            event_type="cross_agent_alert",
            floor=floor,
            salience=min(0.8, salience + 0.05),
        )


def tenant_broadcast(building_id: str, content: str, floor=None, salience: float = 0.6):
    """Called by TenantAgent after ingesting an event."""

    if _matches(content, TENANT_TO_MARKET):
        _cross_write(
            building_id=building_id,
            agent="market_agent",
            content=f"[Auto-flagged by TenantAgent] Lease retention risk detected: {content}",
            event_type="cross_agent_alert",
            floor=floor,
            salience=min(1.0, salience + 0.1),
        )

    if _matches(content, TENANT_TO_MAINT):
        _cross_write(
            building_id=building_id,
            agent="maintenance_agent",
            content=f"[Auto-flagged by TenantAgent] Tenant complaint suggests physical issue: {content}",
            event_type="cross_agent_alert",
            floor=floor,
            salience=min(0.85, salience + 0.05),
        )


def maint_broadcast(building_id: str, content: str, floor=None, salience: float = 0.5):
    """Called by MaintenanceAgent after ingesting an event."""

    if _matches(content, MAINT_TO_OPS):
        _cross_write(
            building_id=building_id,
            agent="ops_agent",
            content=f"[Auto-flagged by MaintenanceAgent] Critical repair may affect building systems: {content}",
            event_type="cross_agent_alert",
            floor=floor,
            salience=min(1.0, salience + 0.15),
        )


def market_broadcast(building_id: str, content: str, floor=None, salience: float = 0.5):
    """Called by MarketAgent after ingesting an event."""

    if _matches(content, MARKET_TO_TENANT):
        _cross_write(
            building_id=building_id,
            agent="tenant_agent",
            content=f"[Auto-flagged by MarketAgent] Market pressure may increase churn risk: {content}",
            event_type="cross_agent_alert",
            floor=floor,
            salience=min(0.85, salience + 0.1),
        )