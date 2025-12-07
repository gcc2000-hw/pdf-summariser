# pdf text and table extraction service using PyMuPDF and pdfplumber

import fitz 
import pdfplumber
from typing import Dict, List, Optional, Any
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


class PDFExtractionError(Exception):
    # custom exception for pdf extraction errors
    pass


class PDFExtractor:
    # handles pdf text and table extraction using PyMuPDF (for extraction and metadata) and pdfplumber (for table extraction)

    def __init__(self, max_pages: int = 3):
        self.max_pages = max_pages
    
    def extract_from_file(
        self, 
        pdf_path: Path, 
        extract_tables: bool = True
    ) -> Dict[str, Any]:
        # extract text from pdf file

        if not pdf_path.exists():
            raise PDFExtractionError(f"pdf file not found: {pdf_path}")
        try:
            # extract text and metadata using PyMuPDF
            text_data = self._extract_text_pymupdf(pdf_path)
            
            # optionally extract tables using pdfplumber
            tables = []
            if extract_tables:
                tables = self._extract_tables_pdfplumber(pdf_path)
            
            return {
                "text": text_data["text"],
                "metadata": text_data["metadata"],
                "tables": tables,
                "page_count": text_data["page_count"],
                "extraction_method": "pymupdf + pdfplumber" if extract_tables else "pymupdf"
            }
            
        except Exception as e:
            logger.error(f"pdf extraction failed: {str(e)}")
            raise PDFExtractionError(f"Failed to extract pdf: {str(e)}")
    
    def _extract_text_pymupdf(self, pdf_path: Path) -> Dict[str, Any]:
        #Extract text using PyMuPDF
        try:
            doc = fitz.open(pdf_path)
            
            # Get total page count before processing
            total_pages = len(doc)
            
            # Keep to the max pages limit
            pages_to_process = min(total_pages, self.max_pages)
            
            # Extract text from each page
            full_text = []
            for page_num in range(pages_to_process):
                page = doc[page_num]
                text = page.get_text()
                full_text.append(f"=== Page {page_num + 1} ===\n{text}")
            
            # Get metadata
            metadata = {
                "title": doc.metadata.get("title", ""),
                "author": doc.metadata.get("author", ""),
                "subject": doc.metadata.get("subject", ""),
                "creator": doc.metadata.get("creator", ""),
                "producer": doc.metadata.get("producer", ""),
                "creation_date": doc.metadata.get("creationDate", ""),
            }
            
            # Close document after getting all data
            doc.close()
            
            return {
                "text": "\n\n".join(full_text),
                "metadata": metadata,
                "page_count": total_pages  # Use the variable we captured earlier
            }
            
        except Exception as e:
            raise PDFExtractionError(f"PyMuPDF extraction failed: {str(e)}")
    
    def _extract_tables_pdfplumber(self, pdf_path: Path) -> List[Dict[str, Any]]:
        # extract tables using pdfplumber
        tables_data = []
        try:
            with pdfplumber.open(pdf_path) as pdf:
                pages_to_process = min(len(pdf.pages), self.max_pages)
                
                for page_num in range(pages_to_process):
                    page = pdf.pages[page_num]
                    tables = page.extract_tables()
                    
                    for table_idx, table in enumerate(tables):
                        if table:  # Only add nonempty tables
                            tables_data.append({
                                "page": page_num + 1,
                                "table_index": table_idx,
                                "data": table,
                                "row_count": len(table),
                                "column_count": len(table[0]) if table else 0
                            })
            
            logger.info(f"Extracted {len(tables_data)} tables from pdf")
            return tables_data
            
        except Exception as e:
            logger.warning(f"Table extraction failed: {str(e)}")
            return []  # Dont fail entire extraction if tables fail