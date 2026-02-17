"""
Pixel Agent - FastAPI Backend
Display Specialist Agent for electronics distributors.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.pst_import import router as pst_router
from api.chat import router as chat_router
from api.training import router as training_router
from config import settings

app = FastAPI(
    title="Pixel Agent API",
    description="Trainable Display Specialist Agent - Backend API",
    version="0.1.0",
)

# CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(pst_router)
app.include_router(chat_router)
app.include_router(training_router)


@app.get("/")
async def root():
    return {
        "agent": settings.AGENT_NAME,
        "role": settings.AGENT_ROLE,
        "version": "0.1.0",
        "status": "running",
    }


@app.get("/health")
async def health():
    """Health check endpoint."""
    from db.connection import engine
    from sqlalchemy import text

    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        db_status = "connected"
    except Exception as e:
        db_status = f"error: {str(e)}"

    return {
        "status": "healthy" if db_status == "connected" else "degraded",
        "database": db_status,
        "agent": settings.AGENT_NAME,
    }
