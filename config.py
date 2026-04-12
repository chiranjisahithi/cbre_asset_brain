"""
config.py — single source of truth for all settings.
Every file imports from here. Never hardcode these elsewhere.
"""
import os
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────
ROOT_DIR   = Path(__file__).parent
DB_PATH    = ROOT_DIR / "memory" / "brain.db"
STATIC_DIR = ROOT_DIR / "static"

# ── Building ──────────────────────────────────────────────
BUILDING_ID   = "dallas_tower_a"
BUILDING_NAME = "Dallas Tower A"

# ── Anthropic ─────────────────────────────────────────────
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
MODEL             = "claude-sonnet-4-20250514"
MAX_TOKENS        = 1000

# ── Memory tuning ─────────────────────────────────────────
EPISODIC_FETCH_LIMIT = 40
SALIENCE_DECAY_RATE  = 0.05
DECAY_AFTER_DAYS     = 3
MIN_SALIENCE_DISPLAY = 0.2

# ── Simulator ─────────────────────────────────────────────
LIVE_STREAM_INTERVAL = 45

# ── API ───────────────────────────────────────────────────
API_HOST = "0.0.0.0"
API_PORT = 8001