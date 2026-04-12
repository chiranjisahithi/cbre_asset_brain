# cbre-memory-agent
AI agent with intelligent memory for CBRE hackathon
# CBRE Asset Brain

Intelligent memory system for commercial real estate.
Multi-agent AI that remembers, learns, and explains decisions.

## Setup

```bash
cd cbre_brain
pip install -r requirements.txt
export ANTHROPIC_API_KEY=your_key_here
```

## Run

```bash
# 1. Seed 2 weeks of building history (run once)
python -m simulator.simulator seed

# 2. Start the server
python -m uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload

# 3. Open dashboard
open http://localhost:8000
```

## Demo Flow

1. Dashboard loads — 16 events in feed, 3-4 semantic patterns, 1 procedural rule
2. Ask quick questions via chat buttons
3. Hit **TRIGGER LIVE ANOMALY** — watch 3 events fire live
4. Hit **COMPRESS** — watch semantic memory update in real time
5. Ask "What is the biggest risk now?" — answer changes based on new memory

## Reset between demo runs

```bash
python -m simulator.simulator reset
# or hit POST /demo/reset from dashboard
```

## Folder Structure

```
cbre_brain/
├── config.py                  ← all settings
├── requirements.txt
├── .gitignore
├── memory/
│   ├── __init__.py
│   └── db.py                  ← SQLite, 3 memory tiers
├── agents/
│   ├── __init__.py            ← clean public imports
│   ├── base.py                ← BaseAgent + call_claude()
│   ├── ops_agent.py           ← sensors, anomalies
│   ├── tenant_agent.py        ← complaints, lease risk
│   ├── maint_agent.py         ← work orders, rules
│   ├── market_agent.py        ← leases, competitors
│   ├── orchestrator.py        ← answers questions
│   └── compression.py         ← episodic → semantic
├── api/
│   ├── __init__.py
│   ├── main.py                ← FastAPI app setup
│   └── routes.py              ← all 11 endpoints
├── simulator/
│   ├── __init__.py
│   ├── mock_data.py           ← all fake events (data only)
│   └── simulator.py           ← seed/live/reset logic
└── static/
    └── index.html             ← single-file dashboard
```

## Git Branches

| Branch                  | Owner    | Files                              |
|-------------------------|----------|------------------------------------|
| feature/memory-layer    | Person 1 | memory/db.py                       |
| feature/agents          | Person 2 | agents/*.py                        |
| feature/api-simulator   | Person 3 | api/*.py, simulator/*.py, config.py|
| feature/dashboard       | Person 4 | static/index.html                  |

Merge order: `feature/*` → `develop` → `main`