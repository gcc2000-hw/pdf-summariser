# PDF Summarizer
## **Task 10 with async api (Task 2)**

---
## Project Overview

A FastAPI based PDF summarization and entity extraction app with multi LLM backend support, async processing, and comprehensive RESTful API. Processes contracts, invoices, and other documents to generate summaries and extract key entities like (dates, money, people, organizations, locations).

### Key Features:
- **Multi LLM Support**: openai gpt-3.5-turbo + huggingface BART
- **Async Processing**: Background task processing with status tracking in realtime
- **Entity Extraction**: Dates, money, people, organizations, locations using spacy NER + regex
- **Multiple Summary Modes**: BRIEF (2-3 sentences), DETAILED (comprehensive), BULLET_POINTS
- **Complete RESTful API**: 6 endpoints for upload, processing, status tracking, and job management
- **CLI Tool**: command line interface made with click
- **Job Management**: Thread safe in-memory job tracking with progress updates

---

## Architecture Overview

```
User Request → FastAPI → Background Task → Results
                ↓
         [PDF Extraction] → [Entity Extraction] → [LLM Summarization]
                ↓                   ↓                      ↓
            PyMuPdf            spacy + rggex        openai/huggingface
```

**Processing Pipeline:**
1. pdf upload and validation
2. Text extraction (PyMupdf + pdfplumber(for tables))
3. Entity extraction (spacy NER + custom regex)
4. LLM summarization (openai or huggingFace)
5. Results storage with metadata

---

## API Endpoints

### Core Endpoints:

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/upload` | Upload PDF, get job_id |
| `POST` | `/api/process` | Start async processing |
| `GET` | `/api/status/{job_id}` | Check status and get results |
| `POST` | `/api/summarize-sync` | Synchronous processing (blocks) |
| `GET` | `/api/jobs` | List all jobs (admin) |
| `DELETE` | `/api/jobs/{job_id}` | Delete job and cleanup |

### Additional Endpoints:
- `GET /` - API information
- `GET /health` - Health check with job statistics
---

## Setup Instructions
**NOTE: this was developed on linux and as such these instructions will follow that process**

### Prerequisites
- Python 3.11+
- Conda and pip
- openai api key

### 1. Clone the Repository
```bash
git clone https://github.com/gcc2000-hw/pdf-summariser.git
cd pdf-summariser
```

### 2. Create Conda Environment
```bash
conda create -n [env_name] python=3.11 -y
conda activate [env_name]
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt --break-system-packages
python -m spacy download en_core_web_sm
```

### 4. Configure Environment Variables

Create a `.env` file in the project root:

```bash
cp env.template .env
```

Edit `.env` and add your api key:

```bash
OPENAI_API_KEY=your_openai_api_key_here
```


### Usage - CLI Tool
**1. Start uvicorn on one terminal**
```bash
uvicorn app.main:app --reload
```
**NOTE- If it says: "ERROR:    [Errno 98] Address already in use" ,**
**Run: lsof -i :8000 and find the pid and then kill it manually using kill -9 [pid].**

**2. Open another terminal and switch to your conda env. You can use the CLI here. check below:**

**Basic usage:**
```bash
python pdf_cli.py summarize invoice.pdf

python pdf_cli.py summarize contract.pdf --mode detailed --backend hf

python pdf_cli.py summarize doc.pdf --mode bullets --output result.json

python pdf_cli.py summarize invoice.pdf --sync

python pdf_cli.py status job_abc123

python pdf_cli.py list-jobs

python pdf_cli.py health
```

**CLI Options:**
- `--mode`, `-m`: Summary mode (`brief`, `detailed`, `bullets`)
- `--backend`, `-b`: LLM backend (`openai`, `hf`)
- `--max-pages`, `-p`: Max pages to process (1-3, default 3)
- `--output`, `-o`: Save output to JSON file
- `--sync`: Use synchronous processing
- `--entities/--no-entities`: Extract entities (default: yes)

---

## Project Structure

```
pdf_summarizer_pro/
├── app/
│   ├── __init__.py              # App version and metadata
│   ├── main.py                  # Fastapi application entry point
│   ├── config.py                # Configuration management (Pydantic)
│   │
│   ├── api/
│   │   ├── __init__.py
│   │   └── routes.py            # api endpoints
│   │
│   ├── models/
│   │   ├── __init__.py
│   │   └── schemas.py           # Pydantic models for requests/responses
│   │
│   └── processors/
│       ├── __init__.py
│       ├── pdf_extractor.py     # Pdf text extraction (PyMuPdf + pdfplumber)
│       ├── entity_extractor.py  # Entity extraction (spacy + regex)
│       ├── entity_filters.py    # Helper entity filtering logic
│       ├── llm_service.py       # LLM integration (Openai + Huggingface)
│       └── job_manager.py       # Async job management
│
├── pdf_cli.py                   # CLI tool
├── requirements.txt             # Python dependencies
├── .env.template                # Environment variable template
├── .gitignore                   # git ignore rules
└── README.md                    # This file
```

---
