# app/main.py
"""
FastAPI main application
PDF Summarizer Pro API
"""

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

# Create FastAPI app
app = FastAPI(
    title="PDF Summarizer Pro API",
    description="Multi-LLM PDF summarization and entity extraction service",
    version=__version__,
    docs_url="/docs",
    redoc_url="/redoc"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
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
        "message": "PDF Summarizer Pro API",
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
    """Health check endpoint with system status"""
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
    """Run on application startup"""
    logger.info(f"Starting PDF Summarizer Pro API v{__version__}")
    logger.info("API documentation available at /docs")


@app.on_event("shutdown")
async def shutdown_event():
    """Run on application shutdown"""
    logger.info("Shutting down PDF Summarizer Pro API")