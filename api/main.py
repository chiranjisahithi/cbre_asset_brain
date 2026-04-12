"""
api/main.py — FastAPI app setup only.

Run from project root:
    python -m uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
"""
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
import os

from api.routes import router
from memory.db import init_db
from config import API_HOST, API_PORT, BUILDING_NAME, BUILDING_ID, LIVE_STREAM_INTERVAL

# Resolve static dir relative to THIS file's location
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC_DIR = os.path.join(BASE_DIR, "static")

app = FastAPI(
    title=f"CBRE Asset Brain — {BUILDING_NAME}",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Root route FIRST — before router and static mount
@app.get("/")
def root():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))

# API routes
app.include_router(router)

@app.on_event("startup")
def startup():
    init_db()
    print(f"[API] CBRE Asset Brain → http://{API_HOST}:{API_PORT}")
    print(f"[API] Static dir: {STATIC_DIR}")
    print(f"[API] index.html exists: {os.path.exists(os.path.join(STATIC_DIR, 'index.html'))}")

    # Auto-seed Austin and Houston if they have no data
    try:
        from memory.db import get_episodic
        from simulator.simulator import seed_austin, seed_houston
        if not get_episodic("austin_plaza_b", limit=1):
            print("[API] Seeding Austin Plaza B...")
            seed_austin()
        if not get_episodic("houston_center_c", limit=1):
            print("[API] Seeding Houston Center C...")
            seed_houston()
    except Exception as e:
        print(f"[API] Warning: could not auto-seed buildings: {e}")

    # Auto-start live protocol stream
    try:
        import simulator.protocol_simulator as ps
        ps._stream = ps.LiveProtocolStream(BUILDING_ID, interval_seconds=LIVE_STREAM_INTERVAL)
        ps._stream.start()
        print(f"[API] Live protocol stream started — firing every {LIVE_STREAM_INTERVAL}s")
    except Exception as e:
        print(f"[API] Warning: could not start protocol stream: {e}")

# Mount static LAST — after all routes
if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
else:
    print(f"[API] WARNING: static dir not found at {STATIC_DIR}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api.main:app", host=API_HOST, port=API_PORT, reload=True)