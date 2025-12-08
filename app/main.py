
# app main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime
import logging

from app import __version__
from app.api import router
from app.models.schemas import HealthCheckResponse
from app.processors import job_manager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

# Create fastapi app
app = FastAPI(
    title="PDF summarizer api",
    description="MultiLLM pdf summarization and entity extraction",
    version=__version__,
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(router, prefix="/api", tags=["PDF Processing"])


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "PDF Summarizer",
        "version": __version__,
        "docs": "/docs",
        "endpoints": {
            "upload": "/api/upload",
            "process": "/api/process",
            "status": "/api/status/{job_id}"
        }
    }


@app.get("/health", response_model=HealthCheckResponse)
async def health_check():
    stats = job_manager.get_stats()
    
    return HealthCheckResponse(
        status="healthy",
        timestamp=datetime.utcnow(),
        version=__version__,
        services={
            "jobs_total": str(stats['total_jobs']),
            "jobs_pending": str(stats['by_status']['pending']),
            "jobs_processing": str(stats['by_status']['processing']),
            "jobs_completed": str(stats['by_status']['completed']),
            "jobs_failed": str(stats['by_status']['failed'])
        }
    )


@app.on_event("startup")
async def startup_event():
    logger.info(f"Starting PDF Summarizer v{__version__}")


@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Shutting down PDF Summarizer")