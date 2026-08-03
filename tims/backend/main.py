"""
TIMS - Transport Management System
Golden Smiles Freight and Distribution
FastAPI entrypoint.
"""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles


@asynccontextmanager
async def lifespan(app: FastAPI):
    from backend.database import Base, engine, ensure_booking_tracking_columns, seed_demo_accounts
    from backend.seed import seed as seed_demo_records

    Base.metadata.create_all(bind=engine)
    ensure_booking_tracking_columns()
    seed_demo_accounts()
    seed_demo_records()
    yield


app = FastAPI(
    title="TIMS - Golden Smiles Freight and Distribution",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from backend.routers import auth_router, partners, bookings, loading, offloading, tracking, dashboard

app.include_router(auth_router.router)
app.include_router(partners.router)
app.include_router(bookings.router)
app.include_router(loading.router)
app.include_router(offloading.router)
app.include_router(tracking.router)
app.include_router(dashboard.router)

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

    @app.get("/")
    def serve_index():
        return FileResponse(str(FRONTEND_DIR / "index.html"))


@app.get("/api/health")
def health_check():
    return {"status": "ok", "system": "TIMS", "company": "Golden Smiles Freight and Distribution"}
