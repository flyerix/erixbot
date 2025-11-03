import re
from typing import Optional

def sanitize_text(text: str, max_length: int = 1000) -> Optional[str]:
    """Sanitize user input text"""
    if not text or len(text.strip()) == 0:
        return None

    # Remove potentially dangerous characters
    sanitized = re.sub(r'[<>]', '', text.strip())
    return sanitized[:max_length] if len(sanitized) > max_length else sanitized

def validate_list_name(name: str) -> bool:
    """Validate list name format"""
    return bool(re.match(r'^[a-zA-Z0-9_\-\s]{1,100}$', name))

def validate_ticket_title(title: str) -> bool:
    """Validate ticket title"""
    if not title or len(title.strip()) == 0:
        return False
    return len(title.strip()) <= 200

def validate_ticket_description(description: str) -> bool:
    """Validate ticket description"""
    if not description or len(description.strip()) == 0:
        return False
    return len(description.strip()) <= 2000

def validate_cost_format(cost: str) -> bool:
    """Validate cost format (€15, 15€, etc.)"""
    return bool(re.match(r'^€?\d+(\.\d{1,2})?€?$', cost.strip()))

def validate_date_format(date_str: str) -> bool:
    """Validate date format DD/MM/YYYY"""
    return bool(re.match(r'^\d{2}/\d{2}/\d{4}$', date_str.strip()))
