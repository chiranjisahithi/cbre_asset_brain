"""
simulator/mock_data.py — pure data, zero logic.
All fake building events for Dallas Tower A.
"""
from datetime import datetime, timedelta


def days_ago(n: int) -> str:
    return (datetime.now() - timedelta(days=n)).isoformat()


HISTORY = [
    # ── WEEK 2 AGO ────────────────────────────────────────
    {"agent": "ops",    "floor": "12", "event_type": "sensor",
     "content": "Chiller unit temp variance +3.2°C above baseline. Minor anomaly logged.",
     "salience": 0.4, "ts_days_ago": 14},

    {"agent": "ops",    "floor": "7",  "event_type": "sensor",
     "content": "Occupancy sensor offline — floor 7 east wing. Auto-reset attempted.",
     "salience": 0.3, "ts_days_ago": 13},

    {"agent": "market", "floor": None, "event_type": "market_signal",
     "content": "Tenant 7B lease expires in 90 days. No renewal discussion initiated.",
     "salience": 0.85, "ts_days_ago": 13},

    {"agent": "maintenance", "floor": "5", "event_type": "maintenance",
     "content": "Scheduled filter replacement floors 4-6 completed. No issues.",
     "salience": 0.2, "status": "completed", "ts_days_ago": 12},

    {"agent": "tenant", "floor": "12", "event_type": "tenant_signal",
     "content": "Our office has been uncomfortably warm for the past week. Please advise.",
     "salience": 0.75, "tenant_id": "12B", "ts_days_ago": 11},

    {"agent": "maintenance", "floor": "12", "event_type": "maintenance",
     "content": "Routine inspection floor 12 HVAC. Minor vibration noted on chiller. No action taken.",
     "salience": 0.4, "status": "logged", "ts_days_ago": 10},

    {"agent": "market", "floor": None, "event_type": "market_signal",
     "content": "Downtown Dallas Class-A office avg rent down 2.1% YoY. Tenant leverage increasing.",
     "salience": 0.55, "ts_days_ago": 10},

    # ── WEEK 1 AGO ────────────────────────────────────────
    {"agent": "ops",    "floor": "12", "event_type": "sensor",
     "content": "Chiller unit temp variance +5.1°C. Second anomaly in 6 days. Efficiency down 11%.",
     "salience": 0.7, "anomaly": True, "ts_days_ago": 8},

    {"agent": "tenant", "floor": "7",  "event_type": "tenant_signal",
     "content": "We have not heard back on lease renewal. Beginning to look at competing buildings.",
     "salience": 0.9, "tenant_id": "7B", "ts_days_ago": 7},

    {"agent": "maintenance", "floor": "3", "event_type": "maintenance",
     "content": "EMERGENCY: Elevator 2 stuck between floors 3-4. Technician dispatched. Occupants assisted safely.",
     "salience": 0.95, "status": "emergency", "ts_days_ago": 6},

    {"agent": "tenant", "floor": "12", "event_type": "tenant_signal",
     "content": "Temperature issue still unresolved after 10 days. This is becoming unacceptable for our staff.",
     "salience": 0.9, "tenant_id": "12B", "ts_days_ago": 5},

    {"agent": "market", "floor": None, "event_type": "market_signal",
     "content": "Comparable office vacancy in downtown Dallas up 4.2% this quarter. Tenants have more options.",
     "salience": 0.6, "ts_days_ago": 5},

    # ── THIS WEEK ─────────────────────────────────────────
    {"agent": "ops",    "floor": "12", "event_type": "sensor",
     "content": "Chiller unit temp variance +8.7°C. Third anomaly in 11 days. Efficiency down 22%. Urgent review required.",
     "salience": 0.95, "anomaly": True, "ts_days_ago": 3},

    {"agent": "maintenance", "floor": "12", "event_type": "maintenance",
     "content": "Work order #4421 raised — floor 12 chiller. Vendor ABC HVAC scheduled next week. Status: pending.",
     "salience": 0.7, "status": "pending", "ts_days_ago": 2},

    {"agent": "tenant", "floor": "7",  "event_type": "tenant_signal",
     "content": "Third follow-up on lease renewal. Need formal response by end of week or we move to alternatives.",
     "salience": 0.95, "tenant_id": "7B", "ts_days_ago": 1},

    {"agent": "market", "floor": None, "event_type": "market_signal",
     "content": "Competitor at 500 Main St offering 2 months free rent on 5-year leases. Direct risk to Tenant 7B.",
     "salience": 0.85, "ts_days_ago": 1},
]

LIVE_ANOMALY_EVENTS = [
    {"agent": "ops",    "floor": "12", "event_type": "sensor",
     "content": "LIVE ALERT: Chiller temp variance +9.8°C — efficiency critical at 31% below normal. Failure risk HIGH.",
     "salience": 0.98, "anomaly": True},

    {"agent": "tenant", "floor": "12", "event_type": "tenant_signal",
     "content": "URGENT: Staff working in 30°C heat. Formally considering lease termination if not resolved today.",
     "salience": 1.0, "tenant_id": "12B"},

    {"agent": "ops",    "floor": "12", "event_type": "sensor",
     "content": "LIVE ALERT: Chiller vibration sensor triggered. Compressor shutdown risk elevated. Inspect immediately.",
     "salience": 0.95, "anomaly": True},
]

MANUAL_ONLY_HISTORY = [
    {"agent": "maintenance", "floor": "4", "event_type": "maintenance",
     "content": "Manager note: Plumbing issue reported in floor 4 kitchen. Vendor called.",
     "salience": 0.6, "ts_days_ago": 10},

    {"agent": "tenant", "floor": "4", "event_type": "tenant_signal",
     "content": "Water pressure very low in floor 4 kitchen for 2 weeks.",
     "salience": 0.7, "tenant_id": "4A", "ts_days_ago": 7},

    {"agent": "maintenance", "floor": "4", "event_type": "maintenance",
     "content": "Manager inspection: pipe corrosion visible under floor 4 kitchen sink. May affect floors 3-5.",
     "salience": 0.8, "ts_days_ago": 3},
]

# ── Austin Plaza B — seed history ────────────────────────
AUSTIN_HISTORY = [
    {"agent": "market",  "floor": None,  "event_type": "lease_signal",
     "content": "Tenant 3A lease expires in 120 days. No renewal intent communicated.",
     "salience": 0.75, "ts_days_ago": 14},

    {"agent": "ops",     "floor": "8",   "event_type": "sensor",
     "content": "Elevator 2 door sensor intermittent fault — 3 incidents this week.",
     "salience": 0.70, "ts_days_ago": 10},

    {"agent": "tenant",  "floor": "3",   "event_type": "tenant_signal",
     "content": "Tenant 3A: WiFi dead zones on floor 3 affecting video calls. Requesting fix.",
     "salience": 0.65, "tenant_id": "3A", "ts_days_ago": 7},

    {"agent": "maintenance", "floor": "8", "event_type": "maintenance",
     "content": "Elevator 2 door sensor replaced. Monitoring for recurrence.",
     "salience": 0.55, "ts_days_ago": 5},

    {"agent": "market",  "floor": None,  "event_type": "market_signal",
     "content": "New co-working space opened 2 blocks away — competitive pressure on short-term leases.",
     "salience": 0.72, "ts_days_ago": 3},

    {"agent": "ops",     "floor": "15",  "event_type": "sensor",
     "content": "AHU-3 filter pressure drop exceeding threshold — replacement due within 7 days.",
     "salience": 0.68, "ts_days_ago": 1},
]


# ── Houston Center C — seed history ──────────────────────
HOUSTON_HISTORY = [
    {"agent": "ops",     "floor": "22",  "event_type": "sensor",
     "content": "Cooling tower pump #2 showing reduced flow rate — 18% below baseline.",
     "salience": 0.82, "ts_days_ago": 20},

    {"agent": "tenant",  "floor": "22",  "event_type": "tenant_signal",
     "content": "Tenant 22C: Office consistently warm since last week. Productivity impacted.",
     "salience": 0.80, "tenant_id": "22C", "ts_days_ago": 15},

    {"agent": "maintenance", "floor": "22", "event_type": "maintenance",
     "content": "Work order raised: cooling tower pump #2 inspection scheduled.",
     "salience": 0.70, "ts_days_ago": 13},

    {"agent": "market",  "floor": None,  "event_type": "lease_signal",
     "content": "Tenant 22C lease renewal in 60 days. Satisfaction score declining.",
     "salience": 0.88, "ts_days_ago": 10},

    {"agent": "ops",     "floor": "22",  "event_type": "sensor",
     "content": "Cooling tower pump #2 replaced. System returning to baseline flow.",
     "salience": 0.60, "ts_days_ago": 7},

    {"agent": "tenant",  "floor": "5",   "event_type": "tenant_signal",
     "content": "Tenant 5B: Noise complaints from HVAC unit above ceiling tiles — disruptive during calls.",
     "salience": 0.73, "tenant_id": "5B", "ts_days_ago": 4},

    {"agent": "maintenance", "floor": "5", "event_type": "maintenance",
     "content": "HVAC vibration isolators inspected — 2 worn mounts replaced on floor 5.",
     "salience": 0.65, "ts_days_ago": 2},
]