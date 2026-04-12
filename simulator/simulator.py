"""
simulator/simulator.py — ingestion logic only.
Data lives in mock_data.py. Run from project root.

Usage:
    python -m simulator.simulator seed
    python -m simulator.simulator live
    python -m simulator.simulator reset
    python -m simulator.simulator manual
"""
import sys
import time
from datetime import datetime, timedelta

from memory.db import init_db, get_conn
from agents import (OpsAgent, TenantAgent,
                    MaintenanceAgent, MarketAgent,
                    CompressionEngine)
from simulator.mock_data import (HISTORY, LIVE_ANOMALY_EVENTS,
                                  MANUAL_ONLY_HISTORY,
                                  AUSTIN_HISTORY, HOUSTON_HISTORY)
from config import BUILDING_ID, LIVE_STREAM_INTERVAL


def _agent_map(building_id: str) -> dict:
    return {
        "ops":         OpsAgent(building_id),
        "tenant":      TenantAgent(building_id),
        "maintenance": MaintenanceAgent(building_id),
        "market":      MarketAgent(building_id),
    }


def _ingest(event: dict, agents: dict, building_id: str):
    e           = dict(event)   # always copy — never mutate original
    agent_key   = e.pop("agent")
    ts_days_ago = e.pop("ts_days_ago", None)

    agents[agent_key].ingest(e)

    if ts_days_ago is not None:
        ts = (datetime.now() - timedelta(days=ts_days_ago)).isoformat()
        conn = get_conn()
        conn.execute("""
            UPDATE episodic SET timestamp = ?
            WHERE id = (SELECT MAX(id) FROM episodic
                        WHERE building_id = ?)
        """, (ts, building_id))
        conn.commit()
        conn.close()


def seed_history(building_id: str = BUILDING_ID):
    print(f"\n{'='*55}")
    print(f"  Seeding {len(HISTORY)} events → {building_id}")
    print(f"{'='*55}\n")
    agents = _agent_map(building_id)

    for i, event in enumerate(HISTORY, 1):
        label = event.get('agent','?').upper()
        floor = event.get('floor','—') or '—'
        text  = event.get('content','')[:50]
        print(f"  [{i:02}/{len(HISTORY)}] {label:12} floor={floor:4} {text}...")
        _ingest(event, agents, building_id)

    print("\n  Compressing episodic → semantic patterns...")
    result = CompressionEngine(building_id).run()

    print("  Writing procedural rules from maintenance history...")
    agents["maintenance"].check_overdue()

    print(f"\n  Seed complete!")
    if result:
        for p in result.get("patterns", []):
            print(f"  ✓ [{p['topic']}] {p.get('urgency','?')} urgency")
    print(f"{'='*55}\n")


def live_stream(building_id: str = BUILDING_ID,
                interval: int = LIVE_STREAM_INTERVAL):
    agents = _agent_map(building_id)
    print(f"\n  Live stream — {len(LIVE_ANOMALY_EVENTS)} events, "
          f"{interval}s apart\n")

    for i, event in enumerate(LIVE_ANOMALY_EVENTS, 1):
        e         = event.copy()
        agent_key = e.pop("agent")
        agents[agent_key].ingest(e)
        print(f"  [LIVE {i}] {event['content'][:65]}")
        if i < len(LIVE_ANOMALY_EVENTS):
            time.sleep(interval)

    print("\n  Re-compressing with live events...")
    CompressionEngine(building_id).run()
    print("  Done\n")


def seed_manual_only(building_id: str = "austin_plaza_b"):
    print(f"\n  Seeding manual-only building: {building_id}\n")
    agents = _agent_map(building_id)
    for event in MANUAL_ONLY_HISTORY:
        _ingest(event, agents, building_id)
    CompressionEngine(building_id).run()
    print("  Manual-only building seeded\n")


def seed_austin(building_id: str = "austin_plaza_b"):
    print(f"\n{'='*55}")
    print(f"  Seeding {len(AUSTIN_HISTORY)} events → {building_id}")
    print(f"{'='*55}\n")
    agents = _agent_map(building_id)
    for i, event in enumerate(AUSTIN_HISTORY, 1):
        label = event.get('agent', '?').upper()
        floor = event.get('floor', '—') or '—'
        text  = event.get('content', '')[:50]
        print(f"  [{i:02}/{len(AUSTIN_HISTORY)}] {label:12} floor={floor:4} {text}...")
        _ingest(event, agents, building_id)
    print("\n  Compressing Austin episodic → semantic patterns...")
    CompressionEngine(building_id).run()
    print(f"  Austin Plaza B seeded!\n{'='*55}\n")


def seed_houston(building_id: str = "houston_center_c"):
    print(f"\n{'='*55}")
    print(f"  Seeding {len(HOUSTON_HISTORY)} events → {building_id}")
    print(f"{'='*55}\n")
    agents = _agent_map(building_id)
    for i, event in enumerate(HOUSTON_HISTORY, 1):
        label = event.get('agent', '?').upper()
        floor = event.get('floor', '—') or '—'
        text  = event.get('content', '')[:50]
        print(f"  [{i:02}/{len(HOUSTON_HISTORY)}] {label:12} floor={floor:4} {text}...")
        _ingest(event, agents, building_id)
    print("\n  Compressing Houston episodic → semantic patterns...")
    CompressionEngine(building_id).run()
    print(f"  Houston Center C seeded!\n{'='*55}\n")


def seed_all():
    """Seed all three buildings — run this on first setup."""
    seed_history()
    seed_austin()
    seed_houston()


def reset(building_id: str = BUILDING_ID):
    print(f"\n  Resetting {building_id}...")
    conn = get_conn()
    for table in ["episodic", "semantic", "procedural"]:
        conn.execute(f"DELETE FROM {table} WHERE building_id=?",
                     (building_id,))
    conn.commit()
    conn.close()
    print("  Memory wiped. Re-seeding...\n")
    seed_history(building_id)


if __name__ == "__main__":
    init_db()
    mode = sys.argv[1] if len(sys.argv) > 1 else "seed"
    modes = {"seed": seed_history, "live": live_stream,
             "manual": seed_manual_only, "reset": reset,
             "seed_austin": seed_austin, "seed_houston": seed_houston,
             "seed_all": seed_all}
    fn = modes.get(mode)
    if fn:
        fn()
    else:
        print(f"Usage: python -m simulator.simulator [{'|'.join(modes)}]")