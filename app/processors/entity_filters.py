
import re
from app.models.schemas import EntityType


class EntityFilter:
    # minimal filters for cleaning up obvious extraction noise

    def should_keep_entity(self, text: str, entity_type: EntityType) -> bool:
        # Remove leading/trailing whitespace for checks
        cleaned = text.strip()
        
        # filter 1 too short (single character)
        if len(cleaned) <= 1:
            return False
        
        # filter 2 contains newlines (formatting artifacts from tables)
        if '\n' in text or '\r' in text:
            return False
        
        # filter 3 Pure numbers (not entities)
        if cleaned.isdigit():
            return False
        
        # filter 4 Product/SKU codes
        # These seem to be consistently misclassified as organizations
        if re.match(r'^[A-Z]{3}-[A-Z]{2}-\d{4}$', text.upper()):
            return False
        
        return True
    
    def reclassify_entity(self, text: str, current_type: EntityType) -> EntityType:
        text_lower = text.lower()
        if current_type == EntityType.PERSON and 'governorate' in text_lower:
            return EntityType.LOCATION
        return current_type