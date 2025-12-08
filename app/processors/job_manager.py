# app/processors/job_manager.py
"""
Job management for async PDF processing
Tracks job status, progress, and results in memory
"""

import logging
from datetime import datetime
from typing import Dict, Optional, Any
from threading import Lock
from enum import Enum

from app.models.schemas import (
    JobStatus,
    ProcessResponse,
    Entity,
    create_job_id
)

logger = logging.getLogger(__name__)


class JobState(str, Enum):
    """Job state enum"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class Job:
    """
    Represents a single processing job
    Stores job metadata, status, and results
    """
    
    def __init__(self, job_id: str, file_info: Dict[str, Any]):
        self.job_id = job_id
        self.status = JobState.PENDING
        self.created_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()
        self.progress = 0
        self.message = "Job created, awaiting processing"
        self.error_message: Optional[str] = None
        
        # Store file info
        self.file_info = file_info
        
        # Processing inputs
        self.pdf_path: Optional[str] = None
        self.summary_mode: Optional[str] = None
        self.llm_backend: Optional[str] = None
        self.extract_entities: bool = True
        self.entity_types: Optional[list] = None
        
        # Processing results
        self.extracted_text: Optional[str] = None
        self.summary: Optional[str] = None
        self.entities: list[Entity] = []
        self.metadata: Dict[str, Any] = {}
        self.processing_time: Optional[float] = None
    
    def to_status_response(self, include_result: bool = False) -> Dict[str, Any]:
        """
        Convert job to status response
        
        Args:
            include_result: Whether to include full ProcessResponse
            
        Returns:
            Status response dict
        """
        response = {
            "job_id": self.job_id,
            "status": self.status.value,
            "progress": self.progress,
            "message": self.message,
            "error_message": self.error_message,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "result": None
        }
        
        # Include full result if job is completed and requested
        if include_result and self.status == JobState.COMPLETED:
            response["result"] = {
                "job_id": self.job_id,
                "status": self.status.value,
                "summary": self.summary,
                "entities": [e.model_dump() for e in self.entities],
                "metadata": self.metadata,
                "processing_time_seconds": self.processing_time
            }
        
        return response
    
    def update_status(
        self, 
        status: JobState, 
        progress: Optional[int] = None,
        message: Optional[str] = None,
        error_message: Optional[str] = None
    ):
        """Update job status and metadata"""
        self.status = status
        self.updated_at = datetime.utcnow()
        
        if progress is not None:
            self.progress = progress
        
        if message:
            self.message = message
        
        if error_message:
            self.error_message = error_message
        
        logger.info(f"Job {self.job_id}: {status.value} - {message or 'No message'}")


class JobManager:
    """
    Manages all processing jobs
    Thread-safe in-memory job storage
    """
    
    def __init__(self):
        self.jobs: Dict[str, Job] = {}
        self.lock = Lock()  # Thread-safe access to jobs dict
        logger.info("JobManager initialized")
    
    def create_job(self, file_info: Dict[str, Any]) -> str:
        """
        Create a new job
        
        Args:
            file_info: Information about uploaded file
            
        Returns:
            Job ID
        """
        job_id = create_job_id()
        
        with self.lock:
            job = Job(job_id, file_info)
            self.jobs[job_id] = job
        
        logger.info(f"Created job {job_id} for file: {file_info.get('filename', 'unknown')}")
        return job_id
    
    def get_job(self, job_id: str) -> Optional[Job]:
        """
        Get a job by ID
        
        Args:
            job_id: Job ID
            
        Returns:
            Job object or None if not found
        """
        with self.lock:
            return self.jobs.get(job_id)
    
    def job_exists(self, job_id: str) -> bool:
        """Check if job exists"""
        with self.lock:
            return job_id in self.jobs
    
    def update_job_status(
        self,
        job_id: str,
        status: JobState,
        progress: Optional[int] = None,
        message: Optional[str] = None,
        error_message: Optional[str] = None
    ):
        """
        Update job status
        
        Args:
            job_id: Job ID
            status: New status
            progress: Progress percentage (0-100)
            message: Status message
            error_message: Error message if failed
        """
        job = self.get_job(job_id)
        if job:
            with self.lock:
                job.update_status(status, progress, message, error_message)
    
    def set_job_processing_config(
        self,
        job_id: str,
        pdf_path: str,
        summary_mode: str,
        llm_backend: str,
        extract_entities: bool = True,
        entity_types: Optional[list] = None
    ):
        """Set processing configuration for a job"""
        job = self.get_job(job_id)
        if job:
            with self.lock:
                job.pdf_path = pdf_path
                job.summary_mode = summary_mode
                job.llm_backend = llm_backend
                job.extract_entities = extract_entities
                job.entity_types = entity_types
    
    def set_job_results(
        self,
        job_id: str,
        extracted_text: str,
        summary: str,
        entities: list[Entity],
        metadata: Dict[str, Any],
        processing_time: float
    ):
        """
        Store job processing results
        
        Args:
            job_id: Job ID
            extracted_text: Extracted PDF text
            summary: Generated summary
            entities: Extracted entities
            metadata: Processing metadata
            processing_time: Processing time in seconds
        """
        job = self.get_job(job_id)
        if job:
            with self.lock:
                job.extracted_text = extracted_text
                job.summary = summary
                job.entities = entities
                job.metadata = metadata
                job.processing_time = processing_time
    
    def get_job_status(self, job_id: str, include_result: bool = True) -> Optional[Dict[str, Any]]:
        """
        Get job status response
        
        Args:
            job_id: Job ID
            include_result: Whether to include full result for completed jobs
            
        Returns:
            Status response dict or None if job not found
        """
        job = self.get_job(job_id)
        if job:
            return job.to_status_response(include_result=include_result)
        return None
    
    def get_all_jobs(self) -> Dict[str, Job]:
        """Get all jobs (for debugging/admin purposes)"""
        with self.lock:
            return self.jobs.copy()
    
    def delete_job(self, job_id: str) -> bool:
        """
        Delete a job
        
        Args:
            job_id: Job ID
            
        Returns:
            True if deleted, False if not found
        """
        with self.lock:
            if job_id in self.jobs:
                del self.jobs[job_id]
                logger.info(f"Deleted job {job_id}")
                return True
        return False
    
    def get_stats(self) -> Dict[str, Any]:
        """Get job manager statistics"""
        with self.lock:
            total = len(self.jobs)
            by_status = {
                "pending": 0,
                "processing": 0,
                "completed": 0,
                "failed": 0
            }
            
            for job in self.jobs.values():
                by_status[job.status.value] += 1
            
            return {
                "total_jobs": total,
                "by_status": by_status
            }


# Global job manager instance
job_manager = JobManager()