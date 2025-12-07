from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from enum import Enum
from datetime import datetime

class SummaryMode(str, Enum):
    # summary modes
    BRIEF = "brief"      
    DETAILED = "detailed"      
    BULLET_POINTS = "bullets" 

class LLMBackend(str, Enum):
    # Models
    OPENAI = "openai"
    HUGGINGFACE = "hf"

class EntityType(str, Enum):
    # Extractables
    DATE = "date"
    MONEY = "money"
    PERSON = "person"
    ORGANIZATION = "organization"
    LOCATION = "location"


class Entity(BaseModel):
    # Extracted entitiy from the doc
    type: EntityType
    text: str = Field(..., description="Excerpt from the document")
    value: Optional[Any] = Field(None, description="Normalized value (eg datetime object for dates)")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="confidence score")
    
    class Config:
        json_schema_extra = {
            "example": {
                "type": "date",
                "text": "February, 2025",
                "value": "2025-02-13",
                "confidence": 0.95
            }
        }


class JobStatus(BaseModel):
    # Tracks the status of an async job
    job_id: str
    status: str = Field(..., description="pending / processing / completed / failed")
    created_at: datetime
    updated_at: datetime
    progress: Optional[int] = Field(None, ge=0, le=100, description="Progress percentage")
    error_message: Optional[str] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "job_id": "abc123",
                "status": "processing",
                "created_at": "2025-02-13T09:15:27Z",
                "updated_at": "2025-02-13T10:30:05Z",
                "progress": 45,
                "error_message": None
            }
        }


# Request/Response Models        

class UploadRequest(BaseModel):
    # Request model for uploading a pdf
    # The actual file is gonna be handled by FastAPI's UploadFile this model is for additional metadata
    max_pages: Optional[int] = Field(3, ge=1, le=10, description="Maximum pages to process")
    extract_tables: bool = Field(True, description="Extract tables using pdfplumber ?")
    
    class Config:
        json_schema_extra = {
            "example": {
                "max_pages": 3,
                "extract_tables": True
            }
        }


class UploadResponse(BaseModel):
    # Upload reposnse for pdf upload
    job_id: str
    status: str
    message: str
    file_info: Dict[str, Any] = Field(default_factory=dict, description="Metadata about uploaded file")
    
    class Config:
        json_schema_extra = {
            "example": {
                "job_id": "abc123",
                "status": "pending",
                "message": "pdf uploaded. Use /process to start summarization.",
                "file_info": {
                    "filename": "contract.pdf",
                    "size_bytes": 245680,
                    "pages": 3
                }
            }
        }


class ProcessRequest(BaseModel):
    # Request model for processing a pdf
    job_id: str
    summary_mode: SummaryMode = Field(default=SummaryMode.BRIEF)
    llm_backend: LLMBackend = Field(default=LLMBackend.OPENAI)
    extract_entities: bool = Field(True, description="Whether to extract entities")
    entity_types: Optional[List[EntityType]] = Field(
        None, 
        description="Specific entity types to extract. If None, extracts all types."
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "job_id": "job_abc123",
                "summary_mode": "brief",
                "llm_backend": "openai",
                "extract_entities": True,
                "entity_types": ["date", "money", "organization"]
            }
        }


class ProcessResponse(BaseModel):
    #response after processing is done
    job_id: str
    status: str
    summary: Optional[str] = None
    entities: List[Entity] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Processing metadata")
    processing_time_seconds: Optional[float] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "job_id": "job_abc123",
                "status": "completed",
                "summary": "This contract outlines the terms between Party A and Party B",
                "entities": [
                    {
                        "type": "date",
                        "text": "January 15, 2024",
                        "value": "2024-01-15",
                        "confidence": 0.95
                    },
                    {
                        "type": "money",
                        "text": "$50,000",
                        "value": 50000.0,
                        "confidence": 0.98
                    }
                ],
                "metadata": {
                    "model_used": "gpt-3.5-turbo",
                    "summary_mode": "brief",
                    "total_entities": 12
                },
                "processing_time_seconds": 4.5
            }
        }


class StatusResponse(BaseModel):
    #Response for job status
    job_id: str
    status: str
    progress: Optional[int] = None
    message: Optional[str] = None
    result: Optional[ProcessResponse] = Field(None, description="Available when status is 'completed'")
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    
    class Config:
        json_schema_extra = {
            "example": {
                "job_id": "job_abc123",
                "status": "processing",
                "progress": 65,
                "message": "Extracting entities from document",
                "result": None,
                "error_message": None,
                "created_at": "2024-01-15T10:30:00Z",
                "updated_at": "2024-01-15T10:30:15Z"
            }
        }

class ErrorResponse(BaseModel):
    # error response model
    error: str
    detail: Optional[str] = None
    job_id: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        json_schema_extra = {
            "example": {
                "error": "Processing failed",
                "detail": "PDF file is corrupted or unreadable",
                "job_id": "job_abc123",
                "timestamp": "2024-01-15T10:30:00Z"
            }
        }


class HealthCheckResponse(BaseModel):
    # health chck
    status: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    version: str = "1.0.0"
    services: Dict[str, str] = Field(default_factory=dict)
    
    class Config:
        json_schema_extra = {
            "example": {
                "status": "healthy",
                "timestamp": "2024-01-15T10:30:00Z",
                "version": "1.0.0",
                "services": {
                    "openai": "connected",
                    "huggingface": "connected"
                }
            }
        }


# helper functions

def create_job_id() -> str:
    # gen uid for job
    import uuid
    return f"job_{uuid.uuid4().hex[:12]}"


def format_entity_value(entity: Entity) -> str:
    # format the entity 
    if entity.type == EntityType.MONEY and isinstance(entity.value, (int, float)):
        return f"${entity.value:,.2f}"
    elif entity.type == EntityType.DATE and entity.value:
        return str(entity.value)
    else:
        return entity.text
    # app/models/schemas.py

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from enum import Enum
from datetime import datetime

__all__ = [
    # enums
    "SummaryMode",
    "LLMBackend", 
    "EntityType",
    # models
    "Entity",
    "JobStatus",
    "UploadRequest",
    "UploadResponse",
    "ProcessRequest",
    "ProcessResponse",
    "StatusResponse",
    "ErrorResponse",
    "HealthCheckResponse",
    # helpers
    "create_job_id",
    "format_entity_value",
]