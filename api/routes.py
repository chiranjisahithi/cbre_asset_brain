"""
api/routes.py — all endpoint logic.
Imported by main.py and registered as a router.
"""
import threading
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional

from memory.db import (get_episodic, get_semantic,
                       get_procedural, get_full_memory,
                       get_semantic_history)
from agents import (OpsAgent, TenantAgent, MaintenanceAgent,
                    MarketAgent, OrchestratorAgent, CompressionEngine)
from simulator.mock_data import LIVE_ANOMALY_EVENTS
from simulator.protocol_simulator import (
    BuildingSignalGenerator, ProtocolParser,
    LiveProtocolStream, get_stream
)
from config import BUILDING_ID

router = APIRouter()

PORTFOLIO = [
    {"id": "dallas_tower_a",   "name": "Dallas Tower A",   "address": "500 Commerce St, Dallas TX",    "floors": 40, "sqft": "850,000"},
    {"id": "austin_plaza_b",   "name": "Austin Plaza B",   "address": "200 Congress Ave, Austin TX",   "floors": 28, "sqft": "520,000"},
    {"id": "houston_center_c", "name": "Houston Center C", "address": "1100 Louisiana St, Houston TX", "floors": 35, "sqft": "680,000"},
]


# ── Pydantic models ───────────────────────────────────────

class EventPayload(BaseModel):
    agent_type: str
    event_type: str
    content:    str
    floor:      Optional[str]   = None
    salience:   Optional[float] = 0.5
    anomaly:    Optional[bool]  = False
    tenant_id:  Optional[str]   = None
    status:     Optional[str]   = None

class QuestionPayload(BaseModel):
    question:    str
    building_id: Optional[str] = None


# ── helpers ───────────────────────────────────────────────

def _agents(building_id: str) -> dict:
    return {
        "ops":         OpsAgent(building_id),
        "tenant":      TenantAgent(building_id),
        "maintenance": MaintenanceAgent(building_id),
        "market":      MarketAgent(building_id),
    }


# ── memory reads ──────────────────────────────────────────

@router.get("/memory/episodic")
def get_episodic_route(limit: int = 40, min_salience: float = 0.0, building_id: Optional[str] = None):
    return get_episodic(building_id or BUILDING_ID, limit=limit, min_salience=min_salience)

@router.get("/memory/semantic")
def get_semantic_route(building_id: Optional[str] = None):
    return get_semantic(building_id or BUILDING_ID)

@router.get("/memory/procedural")
def get_procedural_route(building_id: Optional[str] = None):
    return get_procedural(building_id or BUILDING_ID)

@router.get("/memory/history")
def get_semantic_history_route(topic: Optional[str] = None):
    """Return version history of semantic patterns — shows how memory evolved."""
    return get_semantic_history(BUILDING_ID, topic=topic)

@router.get("/memory/all")
def get_all_memory():
    return get_full_memory(BUILDING_ID)


# ── ingest ────────────────────────────────────────────────

@router.post("/ingest")
def ingest_event(payload: EventPayload):
    event      = payload.dict()
    agent_type = event.pop("agent_type")
    agent      = _agents(BUILDING_ID).get(agent_type)
    if not agent:
        return {"error": f"Unknown agent_type: {agent_type}"}
    agent.ingest(event)
    return {"status": "stored", "agent": agent_type,
            "content": event["content"][:60]}


# ── chat ──────────────────────────────────────────────────

@router.post("/ask")
def ask(payload: QuestionPayload):
    bid = payload.building_id or BUILDING_ID
    return OrchestratorAgent(bid).answer(payload.question)


# ── compression ───────────────────────────────────────────

class CompressPayload(BaseModel):
    building_id: Optional[str] = None

@router.post("/memory/compress")
def compress(payload: Optional[CompressPayload] = None):
    bid = (payload.building_id if payload else None) or BUILDING_ID
    result = CompressionEngine(bid).run()
    return {"status": "done", "result": result}


# ── demo ──────────────────────────────────────────────────

class AnomalyPayload(BaseModel):
    building_id: Optional[str] = None

@router.post("/demo/anomaly")
def trigger_anomaly(payload: Optional[AnomalyPayload] = None):
    bid = (payload.building_id if payload else None) or BUILDING_ID
    agents = _agents(bid)
    fired  = []

    # 1. Fire legacy mock events
    for event in LIVE_ANOMALY_EVENTS:
        e = event.copy()
        agents[e.pop("agent")].ingest(e)
        fired.append(event["content"][:60])

    # 2. Inject real protocol packets (BACnet + MQTT + Modbus anomaly burst)
    protocol_events = []
    gen    = BuildingSignalGenerator(BUILDING_ID, anomaly_mode=True)
    parser = ProtocolParser()
    for floor in ["12", "7"]:
        for pkt in gen.generate_bacnet_batch(floor):
            evt = parser.parse_bacnet(pkt)
            if evt:
                agents["ops"].ingest(evt)
                protocol_events.append(f"[{evt['protocol']}] {evt['content'][:55]}")
        for pkt in gen.generate_mqtt_batch(floor):
            evt = parser.parse_mqtt(pkt)
            if evt:
                agents["ops"].ingest(evt)
                protocol_events.append(f"[{evt['protocol']}] {evt['content'][:55]}")
        for pkt in gen.generate_modbus_batch(floor):
            evt = parser.parse_modbus(pkt)
            if evt:
                agents["ops"].ingest(evt)
                protocol_events.append(f"[{evt['protocol']}] {evt['content'][:55]}")

    threading.Thread(
        target=lambda: CompressionEngine(bid).run(),
        daemon=True
    ).start()
    return {
        "status": "anomaly triggered",
        "events_fired": len(fired) + len(protocol_events),
        "mock_events": fired,
        "protocol_events": protocol_events,
    }

@router.post("/demo/reset")
def reset_demo():
    from memory.db import get_conn
    conn = get_conn()
    for t in ["episodic", "semantic", "procedural"]:
        conn.execute(f"DELETE FROM {t} WHERE building_id=?",
                     (BUILDING_ID,))
    conn.commit()
    conn.close()
    from simulator.simulator import seed_history
    seed_history(BUILDING_ID)
    return {"status": "reset complete"}


# ── stats (active building) ───────────────────────────────

@router.get("/stats")
def stats():
    eps  = get_episodic(BUILDING_ID, limit=200)
    sem  = get_semantic(BUILDING_ID)
    proc = get_procedural(BUILDING_ID)
    return {
        "building":         BUILDING_ID,
        "episodic_count":   len(eps),
        "semantic_count":   len(sem),
        "procedural_count": len(proc),
        "critical_events":  len([e for e in eps if e["salience"] >= 0.9]),
        "high_events":      len([e for e in eps if 0.7 <= e["salience"] < 0.9]),
    }


# ── stats for any building by id ──────────────────────────

@router.get("/stats/{building_id}")
def stats_for_building(building_id: str):
    eps  = get_episodic(building_id, limit=200)
    sem  = get_semantic(building_id)
    proc = get_procedural(building_id)
    crit = [e for e in eps if e["salience"] >= 0.9]
    high = [e for e in eps if 0.7 <= e["salience"] < 0.9]
    health_score = max(0, 100 - (len(crit) * 15) - (len(high) * 5))
    status = "critical" if len(crit) > 0 else "warning" if len(high) > 0 else "healthy"
    return {
        "building_id":      building_id,
        "episodic_count":   len(eps),
        "semantic_count":   len(sem),
        "procedural_count": len(proc),
        "critical_events":  len(crit),
        "high_events":      len(high),
        "health_score":     health_score,
        "status":           status,
    }


# ── portfolio (all buildings) ─────────────────────────────

@router.get("/portfolio")
def portfolio():
    result = []
    for bldg in PORTFOLIO:
        eps  = get_episodic(bldg["id"], limit=200)
        sem  = get_semantic(bldg["id"])
        proc = get_procedural(bldg["id"])
        crit = len([e for e in eps if e["salience"] >= 0.9])
        high = len([e for e in eps if 0.7 <= e["salience"] < 0.9])
        health = max(0, 100 - (crit * 15) - (high * 5))
        status = "critical" if crit > 0 else "warning" if high > 0 else "healthy"
        # Last event timestamp
        last_event = eps[0]["timestamp"][:10] if eps else None
        result.append({
            **bldg,
            "episodic_count":   len(eps),
            "semantic_count":   len(sem),
            "procedural_count": len(proc),
            "critical_events":  crit,
            "high_events":      high,
            "health_score":     health,
            "status":           status,
            "last_event":       last_event,
        })
    return result


@router.get("/health")
def health():
    return {"status": "ok", "building": BUILDING_ID}


# ── Protocol stream ───────────────────────────────────────

@router.get("/protocols/scan")
def protocol_scan(floor: Optional[str] = None):
    """Run a single protocol scan (BACnet + MQTT + Modbus) and ingest results."""
    gen    = BuildingSignalGenerator(BUILDING_ID)
    parser = ProtocolParser()
    scan   = gen.generate_full_scan(floor)
    agents = _agents(BUILDING_ID)
    ingested = []

    for pkt_dict in scan["bacnet"]:
        from simulator.protocol_simulator import BACnetPacket
        # Re-parse from dict for ingestion
        pass  # raw dicts already in scan

    # Parse and ingest all protocols
    for pkt in gen.generate_bacnet_batch(scan["floor"]):
        evt = parser.parse_bacnet(pkt)
        if evt:
            agents["ops"].ingest(evt)
            ingested.append({"protocol": "BACnet/IP", "content": evt["content"][:70]})

    for pkt in gen.generate_mqtt_batch(scan["floor"]):
        evt = parser.parse_mqtt(pkt)
        if evt:
            agents["ops"].ingest(evt)
            ingested.append({"protocol": "MQTT", "content": evt["content"][:70]})

    for pkt in gen.generate_modbus_batch(scan["floor"]):
        evt = parser.parse_modbus(pkt)
        if evt:
            agents["ops"].ingest(evt)
            ingested.append({"protocol": "Modbus TCP", "content": evt["content"][:70]})

    return {
        "status":   "scan complete",
        "floor":    scan["floor"],
        "ingested": ingested,
        "raw_scan": scan,
    }


@router.get("/protocols/stream/status")
def stream_status():
    """Get status of the live protocol stream and recent packets."""
    stream = get_stream(BUILDING_ID)
    if stream is None:
        return {"running": False, "recent_packets": []}
    return {
        "running":        stream._running,
        "recent_packets": stream.get_recent_packets(20),
    }


@router.post("/protocols/stream/start")
def start_stream():
    """Start the live protocol stream (fires every 30s in background)."""
    stream = get_stream(BUILDING_ID)
    if stream is None:
        import simulator.protocol_simulator as ps
        ps._stream = LiveProtocolStream(BUILDING_ID, interval_seconds=30)
        stream = ps._stream
    stream.start()
    return {"status": "stream started", "interval_seconds": stream.interval}


@router.post("/protocols/stream/stop")
def stop_stream():
    stream = get_stream(BUILDING_ID)
    if stream:
        stream.stop()
    return {"status": "stream stopped"}


# ── manual signal log (no-sensor buildings) ───────────────

class ManualLogPayload(BaseModel):
    building_id: str
    signal_type: str   # complaint | observation | maintenance | market
    content:     str
    floor:       Optional[str] = None
    reported_by: Optional[str] = None  # tenant name / manager name

@router.post("/log")
def manual_log(payload: ManualLogPayload):
    """
    Manual signal input — for buildings without sensors.
    Property managers, tenants, or staff log observations here.
    """
    agent_map = {
        "complaint":   TenantAgent(payload.building_id),
        "observation": OpsAgent(payload.building_id),
        "maintenance": MaintenanceAgent(payload.building_id),
        "market":      MarketAgent(payload.building_id),
    }
    agent = agent_map.get(payload.signal_type, OpsAgent(payload.building_id))

    prefix = f"[Manual log by {payload.reported_by}] " if payload.reported_by else "[Manual log] "
    event = {
        "event_type": "manual_signal",
        "content":    prefix + payload.content,
        "floor":      payload.floor,
        "salience":   0.7,
        "tenant_id":  payload.reported_by,
    }
    agent.ingest(event)

    # auto-compress after manual log so pattern shows immediately
    def _compress():
        CompressionEngine(payload.building_id).run()
    threading.Thread(target=_compress, daemon=True).start()

    return {
        "status":      "logged",
        "building_id": payload.building_id,
        "signal_type": payload.signal_type,
        "content":     payload.content[:80],
        "message":     "Signal stored in memory. Pattern analysis running in background."
    }