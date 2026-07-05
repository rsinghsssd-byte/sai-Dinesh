from __future__ import annotations
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from . import database as db
from .routes.analyze import router as analyze_router

app = FastAPI(
    title="GitHub Commit Plagiarism Detection System",
    description="Analyzes multiple GitHub repositories for commit-level and file-level code similarity.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(analyze_router)


@app.on_event("startup")
def on_startup():
    db.init_db()


@app.get("/api/health")
def health():
    return {"status": "ok"}


# Serve the frontend (static SPA) at the root path. Must be mounted last so
# /api/* routes above take precedence.
# FRONTEND_DIR env var lets Docker (where the frontend is copied to a fixed
# path) and local dev (where it's a sibling of backend/) both resolve correctly.
_frontend_dir = os.environ.get(
    "FRONTEND_DIR",
    os.path.join(os.path.dirname(__file__), "..", "..", "frontend"),
)
if os.path.isdir(_frontend_dir):
    app.mount("/", StaticFiles(directory=_frontend_dir, html=True), name="frontend")
