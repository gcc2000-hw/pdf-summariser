#we use spacy amd regex for NER 

import re
import spacy
from typing import List, Dict, Any, Optional
from datetime import datetime
import logging

from app.models.schemas import Entity, EntityType
from app.processors.entity_filters import EntityFilter


logger = logging.getLogger(__name__)


class EntityExtractionError(Exception):
    pass


class EntityExtractor:
    # extracts entities from text using spaCy and regex patterns
    # the entity types supported are date, money, person, organization, location
    def __init__(self, spacy_model: str = "en_core_web_sm"):
        try:
            self.nlp = spacy.load(spacy_model)
            logger.info(f"Loaded spacy model: {spacy_model}")
        except OSError:
            raise EntityExtractionError(
                f"spacy model not found."
            )
        # filtering logic
        self.filter = EntityFilter()
        # regex patterns for dates and money
        self._compile_patterns()
    
    def _compile_patterns(self):
        # compile regex patterns for dates and money
        
        # date patterns, try multiple format exps
        self.date_patterns = [
            # Jan 22 2013
            r'\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|'
            r'Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)'
            r'\s+\d{1,2}(?:st|nd|rd|th)?,?\s+\d{4}\b',
            
            # 01/22/2013
            r'\b\d{1,2}[-/]\d{1,2}[-/]\d{2,4}\b',
            
            # 2013-01-22 
            r'\b\d{4}-\d{2}-\d{2}\b',
        ]
        
        # Money patterns
        self.money_patterns = [
            # $1,234.56 or $1234.56
            r'\$\s*\d{1,3}(?:,\d{3})*(?:\.\d{2})?',
            
            # Percentages: 1.5%, 0.6%
            r'\b\d+(?:\.\d+)?%',
        ]
        
        # Compile patterns
        self.compiled_date_patterns = [re.compile(p, re.IGNORECASE) for p in self.date_patterns]
        self.compiled_money_patterns = [re.compile(p) for p in self.money_patterns]
    
    def extract_entities(
        self, 
        text: str,
        entity_types: Optional[List[EntityType]] = None
    ) -> List[Entity]:
        if not text or not text.strip():
            return []
        
        entities = []
        
        # Determine which entity types to extract
        types_to_extract = entity_types if entity_types else list(EntityType)
        
        # Extract dates using regex
        if EntityType.DATE in types_to_extract:
            entities.extend(self._extract_dates(text))
        
        # Extract money using regex
        if EntityType.MONEY in types_to_extract:
            entities.extend(self._extract_money(text))
        
        # Extract named entities using spacy
        spacy_types = [
            t for t in types_to_extract 
            if t in [EntityType.PERSON, EntityType.ORGANIZATION, EntityType.LOCATION]
        ]
        
        if spacy_types:
            entities.extend(self._extract_spacy_entities(text, spacy_types))
        
        # Remove duplicate text and type
        entities = self._deduplicate_entities(entities)
        
        logger.info(f"Extracted {len(entities)} entities from text")
        return entities
    
    def _extract_dates(self, text: str) -> List[Entity]:
        dates = []
        seen = set()  # Track already found dates
        
        for pattern in self.compiled_date_patterns:
            for match in pattern.finditer(text):
                date_text = match.group(0)
                
                # skip duplicates
                if date_text in seen:
                    continue
                seen.add(date_text)
                
                # Try to parse the date
                parsed_date = self._parse_date(date_text)
                
                dates.append(Entity(
                    type=EntityType.DATE,
                    text=date_text,
                    value=parsed_date,
                    confidence=0.9  # High confidence for regex matches
                ))
        
        return dates
    
    def _parse_date(self, date_str: str) -> Optional[str]:
        # Common date formats to try
        formats = [
            "%b %d %Y",      # Jan 22 2013
            "%B %d, %Y",     # January 22, 2013
            "%m/%d/%Y",      # 01/22/2013
            "%d-%m-%Y",      # 22-01-2013
            "%Y-%m-%d",      # 2013-01-22 (ISO)
        ]
        
        for fmt in formats:
            try:
                dt = datetime.strptime(date_str.replace(',', ''), fmt)
                return dt.strftime("%Y-%m-%d")
            except ValueError:
                continue
        
        return None  # couldnt parse
    
    def _extract_money(self, text: str) -> List[Entity]:
        money_entities = []
        seen = set()
        
        for pattern in self.compiled_money_patterns:
            for match in pattern.finditer(text):
                money_text = match.group(0)
                
                # skip duplicates
                if money_text in seen:
                    continue
                seen.add(money_text)
                
                # Parse the numeric value
                value = self._parse_money(money_text)
                
                money_entities.append(Entity(
                    type=EntityType.MONEY,
                    text=money_text,
                    value=value,
                    confidence=0.95  # Very high confidence for money patterns
                ))
        
        return money_entities
    
    def _parse_money(self, money_str: str) -> Optional[float]:
        try:
            # Remove currency symbols and commas
            cleaned = money_str.replace('$', '').replace(',', '').replace('%', '').strip()
            return float(cleaned)
        except ValueError:
            return None
    
    def _extract_spacy_entities(
        self, 
        text: str, 
        entity_types: List[EntityType]
    ) -> List[Entity]:
        entities = []
        
        # Process text with spacy
        doc = self.nlp(text)
        
        # Map spacy entity labels to our EntityType enum
        label_mapping = {
            "PERSON": EntityType.PERSON,
            "ORG": EntityType.ORGANIZATION,
            "GPE": EntityType.LOCATION,      # Geopolitical entity
            "LOC": EntityType.LOCATION,      # Location
        }
        
        for ent in doc.ents:
            # Check if this entity type is requested
            entity_type = label_mapping.get(ent.label_)
            
            if entity_type and entity_type in entity_types:
                # apply minimal filters to reduce obvious noise
                if self.filter.should_keep_entity(ent.text, entity_type):
                    final_type = self.filter.reclassify_entity(ent.text, entity_type)
                    entities.append(Entity(
                            type=final_type,
                            text=ent.text,
                            value=ent.text,
                            confidence=0.85
                        ))
        
        return entities
    
    def _deduplicate_entities(self, entities: List[Entity]) -> List[Entity]:
        seen = {}
        
        for entity in entities:
            key = (entity.type, entity.text)
            
            if key not in seen or entity.confidence > seen[key].confidence:
                seen[key] = entity
        
        return list(seen.values())
    
    def extract_by_type(
        self, 
        text: str, 
        entity_type: EntityType
    ) -> List[Entity]:
        return self.extract_entities(text, entity_types=[entity_type])
    
    def get_statistics(self, entities: List[Entity]) -> Dict[str, Any]:
        if not entities:
            return {"total": 0, "by_type": {}, "avg_confidence": 0.0}
        
        by_type = {}
        for entity in entities:
            type_str = entity.type.value
            by_type[type_str] = by_type.get(type_str, 0) + 1
        
        avg_confidence = sum(e.confidence for e in entities) / len(entities)
        
        return {
            "total": len(entities),
            "by_type": by_type,
            "avg_confidence": round(avg_confidence, 3)
        }