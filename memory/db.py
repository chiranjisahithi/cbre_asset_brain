"""
memory/db.py — SQLite memory layer.
Three tiers: episodic, semantic, procedural.
All imports use absolute paths from project root.
"""
import sqlite3
import json
from datetime import datetime
from config import DB_PATH, SALIENCE_DECAY_RATE, DECAY_AFTER_DAYS


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = get_conn()
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS episodic (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            building_id TEXT NOT NULL,
            floor       TEXT,
            agent       TEXT NOT NULL,
            event_type  TEXT NOT NULL,
            content     TEXT NOT NULL,
            salience    REAL DEFAULT 0.5,
            timestamp   TEXT NOT NULL,
            metadata    TEXT DEFAULT '{}'
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS semantic (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            building_id      TEXT NOT NULL,
            topic            TEXT NOT NULL,
            summary          TEXT NOT NULL,
            confidence       REAL DEFAULT 0.5,
            source_event_ids TEXT DEFAULT '[]',
            version          INTEGER DEFAULT 1,
            created_at       TEXT NOT NULL,
            updated_at       TEXT NOT NULL
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS semantic_history (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            semantic_id      INTEGER NOT NULL,
            building_id      TEXT NOT NULL,
            topic            TEXT NOT NULL,
            summary          TEXT NOT NULL,
            confidence       REAL DEFAULT 0.5,
            version          INTEGER NOT NULL,
            recorded_at      TEXT NOT NULL
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS procedural (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            building_id       TEXT NOT NULL,
            agent             TEXT NOT NULL,
            rule              TEXT NOT NULL,
            trigger_condition TEXT NOT NULL,
            action            TEXT NOT NULL,
            confidence        REAL DEFAULT 0.5,
            times_applied     INTEGER DEFAULT 0,
            created_at        TEXT NOT NULL
        )
    """)

    conn.commit()
    conn.close()
    print(f"[DB] Initialized at {DB_PATH}")


# ── Episodic ──────────────────────────────────────────────

def write_episodic(building_id, agent, event_type, content,
                   floor=None, salience=0.5, metadata=None):
    conn = get_conn()
    conn.execute("""
        INSERT INTO episodic
        (building_id, floor, agent, event_type, content,
         salience, timestamp, metadata)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        building_id, floor, agent, event_type, content,
        salience, datetime.now().isoformat(),
        json.dumps(metadata or {})
    ))
    conn.commit()
    conn.close()


def get_episodic(building_id, limit=50,
                 min_salience=0.0, floor=None):
    conn = get_conn()
    query  = "SELECT * FROM episodic WHERE building_id=? AND salience>=?"
    params = [building_id, min_salience]
    if floor:
        query  += " AND floor=?"
        params.append(floor)
    query += " ORDER BY timestamp DESC LIMIT ?"
    params.append(limit)
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def decay_episodic(building_id):
    conn = get_conn()
    conn.execute("""
        UPDATE episodic
        SET salience = MAX(0.1, salience - ?)
        WHERE building_id = ?
          AND timestamp < datetime('now', ? || ' days')
    """, (SALIENCE_DECAY_RATE, building_id, f"-{DECAY_AFTER_DAYS}"))
    conn.commit()
    conn.close()


# ── Semantic ──────────────────────────────────────────────

def write_semantic(building_id, topic, summary,
                   confidence=0.7, source_ids=None):
    conn = get_conn()
    now  = datetime.now().isoformat()
    existing = conn.execute(
        "SELECT id, summary, confidence, version FROM semantic WHERE building_id=? AND topic=?",
        (building_id, topic)
    ).fetchone()

    if existing:
        new_version = (existing["version"] or 1) + 1
        # Snapshot the OLD version into history before overwriting
        conn.execute("""
            INSERT INTO semantic_history
            (semantic_id, building_id, topic, summary, confidence, version, recorded_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (existing["id"], building_id, topic,
              existing["summary"], existing["confidence"],
              existing["version"] or 1, now))
        conn.execute("""
            UPDATE semantic
            SET summary=?, confidence=?, source_event_ids=?, updated_at=?, version=?
            WHERE id=?
        """, (summary, confidence,
              json.dumps(source_ids or []), now, new_version, existing["id"]))
    else:
        conn.execute("""
            INSERT INTO semantic
            (building_id, topic, summary, confidence,
             source_event_ids, version, created_at, updated_at)
            VALUES (?,?,?,?,?,?,?,?)
        """, (building_id, topic, summary, confidence,
              json.dumps(source_ids or []), 1, now, now))
    conn.commit()
    conn.close()


def get_semantic(building_id):
    conn = get_conn()
    rows = conn.execute("""
        SELECT * FROM semantic
        WHERE building_id=?
        ORDER BY confidence DESC
    """, (building_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_semantic_history(building_id, topic=None):
    """Return version history for semantic patterns — shows memory evolution."""
    conn = get_conn()
    if topic:
        rows = conn.execute("""
            SELECT * FROM semantic_history
            WHERE building_id=? AND topic=?
            ORDER BY topic, version ASC
        """, (building_id, topic)).fetchall()
    else:
        rows = conn.execute("""
            SELECT * FROM semantic_history
            WHERE building_id=?
            ORDER BY topic, version ASC
        """, (building_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Procedural ────────────────────────────────────────────

def write_procedural(building_id, agent, rule,
                     trigger_condition, action, confidence=0.6):
    conn = get_conn()
    existing = conn.execute(
        "SELECT id FROM procedural WHERE building_id=? AND trigger_condition=?",
        (building_id, trigger_condition)
    ).fetchone()
    if existing:
        conn.execute("""
            UPDATE procedural
            SET rule=?, action=?, confidence=?, times_applied=times_applied+1
            WHERE id=?
        """, (rule, action, confidence, existing["id"]))
    else:
        conn.execute("""
            INSERT INTO procedural
            (building_id, agent, rule, trigger_condition,
             action, confidence, created_at)
            VALUES (?,?,?,?,?,?,?)
        """, (building_id, agent, rule, trigger_condition,
              action, confidence, datetime.now().isoformat()))
    conn.commit()
    conn.close()


def get_procedural(building_id, agent=None):
    conn = get_conn()
    if agent:
        rows = conn.execute("""
            SELECT * FROM procedural
            WHERE building_id=? AND agent=?
            ORDER BY confidence DESC
        """, (building_id, agent)).fetchall()
    else:
        rows = conn.execute("""
            SELECT * FROM procedural
            WHERE building_id=?
            ORDER BY confidence DESC
        """, (building_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Full memory dump ──────────────────────────────────────

def get_full_memory(building_id):
    return {
        "episodic":   get_episodic(building_id, limit=30,
                                   min_salience=0.2),
        "semantic":   get_semantic(building_id),
        "procedural": get_procedural(building_id),
    }