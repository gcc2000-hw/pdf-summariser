
import logging
import time
import shutil
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, UploadFile, File, HTTPException, BackgroundTasks
from datetime import datetime

from app.models.schemas import (
    UploadResponse,
    ProcessRequest,
    ProcessResponse,
    StatusResponse,
    ErrorResponse,
    SummaryMode,
    LLMBackend
)
from app.processors import (
    PDFExtractor,
    EntityExtractor,
    LLMServiceFactory,
    job_manager,
    JobState
)
from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter()

# Temporary directory for uploaded files
UPLOAD_DIR = Path("/tmp/pdf_summarizer_uploads")
UPLOAD_DIR.mkdir(exist_ok=True)


@router.post("/upload", response_model=UploadResponse)
async def upload_pdf(
    file: UploadFile = File(...),
    max_pages: int = 3,
    extract_tables: bool = True
) -> UploadResponse:
    # upload a pdf file and create a processing job



    # Validate file type
    if not file.filename.endswith('.pdf'):
        raise HTTPException(
            status_code=400,
            detail="Only pdf files"
        )
    
    # Validate max_pages
    if max_pages < 1 or max_pages > 3:
        raise HTTPException(
            status_code=400,
            detail="max_pages must be between 1 and 3"
        )
    
    try:
        # Generate unique filename
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        safe_filename = f"{timestamp}_{file.filename}"
        file_path = UPLOAD_DIR / safe_filename
        
        # Save uploaded file
        with file_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        file_size = file_path.stat().st_size
        logger.info(f"Uploaded file: {safe_filename} ({file_size} bytes)")
        
        # Quick pdf validation, extract basic info
        try:
            pdf_extractor = PDFExtractor(max_pages=max_pages)
            pdf_info = pdf_extractor.extract_from_file(file_path, extract_tables=False)
            page_count = pdf_info['page_count']
        except Exception as e:
            # Clean up file if pdf is invalid
            file_path.unlink(missing_ok=True)
            raise HTTPException(
                status_code=400,
                detail=f"Invalid pdf: {str(e)}"
            )
        
        # Create job
        file_info = {
            "filename": file.filename,
            "safe_filename": safe_filename,
            "file_path": str(file_path),
            "size_bytes": file_size,
            "pages": page_count,
            "max_pages": max_pages,
            "extract_tables": extract_tables,
            "uploaded_at": datetime.utcnow().isoformat()
        }
        
        job_id = job_manager.create_job(file_info)
        
        return UploadResponse(
            job_id=job_id,
            status="pending",
            message="pdf uploaded successfully. Use /process to start summarization.",
            file_info=file_info
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Upload failed: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Upload failed: {str(e)}"
        )


@router.post("/process", response_model=ProcessResponse)
async def process_pdf(
    request: ProcessRequest,
    background_tasks: BackgroundTasks
) -> ProcessResponse:
    # Start processing a pdf in the background
    # Validate job exists
    job = job_manager.get_job(request.job_id)
    if not job:
        raise HTTPException(
            status_code=404,
            detail=f"Job {request.job_id} not found"
        )
    
    # Check if already processing or completed
    if job.status == JobState.PROCESSING:
        raise HTTPException(
            status_code=400,
            detail="Job is already being processed"
        )
    
    if job.status == JobState.COMPLETED:
        # Return existing result
        return ProcessResponse(
            job_id=job.job_id,
            status="completed",
            summary=job.summary,
            entities=job.entities,
            metadata=job.metadata,
            processing_time_seconds=job.processing_time
        )
    
    # Set processing configuration
    job_manager.set_job_processing_config(
        job_id=request.job_id,
        pdf_path=job.file_info['file_path'],
        summary_mode=request.summary_mode.value,
        llm_backend=request.llm_backend.value,
        extract_entities=request.extract_entities,
        entity_types=[et.value for et in request.entity_types] if request.entity_types else None
    )
    
    # Start background processing
    background_tasks.add_task(
        process_pdf_background,
        job_id=request.job_id,
        summary_mode=request.summary_mode,
        llm_backend=request.llm_backend,
        extract_entities=request.extract_entities,
        entity_types=request.entity_types
    )
    
    # Update to processing state
    job_manager.update_job_status(
        job_id=request.job_id,
        status=JobState.PROCESSING,
        progress=5,
        message="Processing started"
    )
    
    return ProcessResponse(
        job_id=request.job_id,
        status="processing",
        summary=None,
        entities=[],
        metadata={"message": "Processing started in background. Check /status/{job_id} for updates."},
        processing_time_seconds=None
    )

@router.post("/summarize-sync")
async def summarize_pdf_sync(
    file: UploadFile = File(...),
    summary_mode: SummaryMode = SummaryMode.BRIEF,
    llm_backend: LLMBackend = LLMBackend.OPENAI,
    max_pages: int = 3
):
    # Synchronous endpoint for task purposes only 
    # blocks until processing is done
    # async /upload + /process + /status endpoints will be better 

    import tempfile
    import time
    
    # Validate
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(400, "Only PDF files supported")
    
    if max_pages < 1 or max_pages > 10:
        raise HTTPException(400, "max_pages must be 1-10")
    
    start_time = time.time()
    
    try:
        # Save uploaded file temporarily
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp:
            shutil.copyfileobj(file.file, tmp)
            tmp_path = Path(tmp.name)
        
        # extract text
        pdf_extractor = PDFExtractor(max_pages=max_pages)
        pdf_result = pdf_extractor.extract_from_file(tmp_path, extract_tables=False)
        extracted_text = pdf_result['text']
        
        # extract entities
        entity_extractor = EntityExtractor()
        entities = entity_extractor.extract_entities(extracted_text)
        
        # generate summary
        llm_service = LLMServiceFactory.create(llm_backend)
        summary = llm_service.summarize(extracted_text, mode=summary_mode)
        model_info = llm_service.get_model_info()
        
        # clean up tmp file
        tmp_path.unlink(missing_ok=True)
        
        processing_time = time.time() - start_time
        
        # Return result (Task 10 format)
        return {
            "document": file.filename,
            "summary": summary,
            "entities": [
                {
                    "type": e.type.value,
                    "text": e.text,
                    "value": e.value,
                    "confidence": e.confidence
                }
                for e in entities
            ],
            "metadata": {
                "model": model_info['model'],
                "backend": model_info['backend'],
                "summary_mode": summary_mode.value,
                "entity_count": len(entities),
                "text_length": len(extracted_text),
                "pages_processed": pdf_result['page_count'],
                "processing_time_seconds": round(processing_time, 2)
            }
        }
        
    except Exception as e:
        # Clean up on error
        if 'tmp_path' in locals():
            tmp_path.unlink(missing_ok=True)
        raise HTTPException(500, f"Processing failed: {str(e)}")
    

async def process_pdf_background(
    job_id: str,
    summary_mode: SummaryMode,
    llm_backend: LLMBackend,
    extract_entities: bool,
    entity_types: Optional[list]
):

    start_time = time.time()
    
    try:
        job = job_manager.get_job(job_id)
        if not job:
            logger.error(f"Job {job_id} not found in background task")
            return
        
        file_path = Path(job.file_info['file_path'])
        max_pages = job.file_info['max_pages']
        extract_tables = job.file_info['extract_tables']
        
        # Extract PDF text
        job_manager.update_job_status(
            job_id=job_id,
            status=JobState.PROCESSING,
            progress=10,
            message="Extracting text from pdf"
        )
        
        pdf_extractor = PDFExtractor(max_pages=max_pages)
        pdf_result = pdf_extractor.extract_from_file(file_path, extract_tables=extract_tables)
        extracted_text = pdf_result['text']
        
        logger.info(f"Job {job_id}: Extracted {len(extracted_text)} characters")
        
        # Extract entities 
        entities = []
        if extract_entities:
            job_manager.update_job_status(
                job_id=job_id,
                status=JobState.PROCESSING,
                progress=30,
                message="Extracting entities from document"
            )
            
            entity_extractor = EntityExtractor()
            
            # Convert entity type strings back to enum if provided
            entity_type_filter = None
            if entity_types:
                from app.models.schemas import EntityType
                entity_type_filter = entity_types
            
            entities = entity_extractor.extract_entities(
                extracted_text,
                entity_types=entity_type_filter
            )
            
            logger.info(f"Job {job_id}: Extracted {len(entities)} entities")
        
        # Generate summary
        job_manager.update_job_status(
            job_id=job_id,
            status=JobState.PROCESSING,
            progress=50,
            message=f"Generating summary using {llm_backend.value}"
        )
        
        llm_service = LLMServiceFactory.create(llm_backend)
        summary = llm_service.summarize(extracted_text, mode=summary_mode)
        model_info = llm_service.get_model_info()
        
        logger.info(f"Job {job_id}: Generated summary ({len(summary)} chars)")
        
        # Store results
        job_manager.update_job_status(
            job_id=job_id,
            status=JobState.PROCESSING,
            progress=90,
            message="Finalizing results"
        )
        
        processing_time = time.time() - start_time
        
        metadata = {
            "model_used": model_info['model'],
            "backend": model_info['backend'],
            "summary_mode": summary_mode.value,
            "entity_count": len(entities),
            "text_length": len(extracted_text),
            "pages_processed": pdf_result['page_count'],
            "tables_extracted": len(pdf_result.get('tables', []))
        }
        
        job_manager.set_job_results(
            job_id=job_id,
            extracted_text=extracted_text,
            summary=summary,
            entities=entities,
            metadata=metadata,
            processing_time=processing_time
        )
        
        # mark as completed
        job_manager.update_job_status(
            job_id=job_id,
            status=JobState.COMPLETED,
            progress=100,
            message="Processing completed successfully"
        )
        
        logger.info(f"Job {job_id}: Completed in {processing_time:.2f}s")
        
    except Exception as e:
        # or mark as failed
        logger.error(f"Job {job_id} failed: {str(e)}")
        job_manager.update_job_status(
            job_id=job_id,
            status=JobState.FAILED,
            message="Processing failed",
            error_message=str(e)
        )


@router.get("/status/{job_id}", response_model=StatusResponse)
async def get_job_status(job_id: str) -> StatusResponse:
    # Get status of a processing job
    status = job_manager.get_job_status(job_id, include_result=True)
    
    if not status:
        raise HTTPException(
            status_code=404,
            detail=f"Job {job_id} not found"
        )
    
    # Convert to StatusResponse format
    response = StatusResponse(
        job_id=status['job_id'],
        status=status['status'],
        progress=status['progress'],
        message=status['message'],
        result=status.get('result'),
        error_message=status.get('error_message'),
        created_at=status['created_at'],
        updated_at=status['updated_at']
    )
    
    return response