"""
TIMS - Transport Management System
Golden Smiles Freight and Distribution
Shop 6L, 148 Chiremba Rd, Queensdale, Harare

FastAPI entrypoint. Run with:
    uvicorn backend.main:app --reload
"""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from backend.database import Base, engine, ensure_booking_tracking_columns, seed_demo_accounts
from backend.routers import auth_router, partners, bookings, loading, offloading, tracking, dashboard

# ------------------------------------------------------------------------
# 🚀 LIFESPAN EVENT HANDLER (Ensures clean database seeding on startup)
# ------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    # This runs exactly when the server finishes booting up completely
    try:
        Base.metadata.create_all(bind=engine)
        ensure_booking_tracking_columns()
        seed_demo_accounts() # Executes perfectly without circular import locks
    except Exception as e:
        print(f"[Lifespan Error] Database initialization failed: {e}")
    yield
    # This runs when the server shuts down
    pass
# ------------------------------------------------------------------------

app = FastAPI(
    title="TIMS - Golden Smiles Freight and Distribution",
    description="Transport Management System for multi-vehicle mineral/commodity freight brokering.",
    version="1.0.0",
    lifespan=lifespan # Injects the lifespan configurations
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router.router)
app.include_router(partners.router)
app.include_router(bookings.router)
app.include_router(loading.router)
app.include_router(offloading.router)
app.include_router(tracking.router)
app.include_router(dashboard.router)

# ---- serve the frontend dashboard -----------------------------------------
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

    @app.get("/")
    def serve_index():
        return FileResponse(str(FRONTEND_DIR / "index.html"))


@app.get("/api/health")
def health_check():
    return {"status": "ok", "system": "TIMS", "company": "Golden Smiles Freight and Distribution"}
