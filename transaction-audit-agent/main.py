"""
Transaction Audit Agent — FastAPI application entry point.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path

from backend.utils.database import init_db
from backend.routes.api import router

# Initialize the database on startup
init_db()

app = FastAPI(
    title="Transaction Audit Agent",
    description="AI-powered financial transaction audit system",
    version="1.0.0",
)

# Allow all origins for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API routes under /api prefix
app.include_router(router, prefix="/api")

# Serve the frontend static files
frontend_path = Path(__file__).parent / "frontend"
app.mount("/static", StaticFiles(directory=str(frontend_path)), name="static")


@app.get("/")
def serve_index():
    return FileResponse(str(frontend_path / "index.html"))


@app.get("/health")
def health():
    return {"status": "ok"}
