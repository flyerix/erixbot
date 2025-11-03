import re
import html
from typing import Optional
import bleach

def sanitize_text(text: str, max_length: int = 1000) -> Optional[str]:
    """Sanitize user input text with enhanced security"""
    if not text or len(text.strip()) == 0:
        return None

    # HTML escape to prevent XSS
    sanitized = html.escape(text.strip())

    # Remove potentially dangerous characters and patterns
    sanitized = re.sub(r'[<>]', '', sanitized)

    # Remove SQL injection patterns
    sanitized = re.sub(r'(\b(union|select|insert|delete|update|drop|create|alter)\b)', '', sanitized, flags=re.IGNORECASE)

    # Remove script tags and javascript: protocols
    sanitized = re.sub(r'<script[^>]*>.*?</script>', '', sanitized, flags=re.IGNORECASE | re.DOTALL)
    sanitized = re.sub(r'javascript:', '', sanitized, flags=re.IGNORECASE)

    # Use bleach for additional HTML sanitization
    sanitized = bleach.clean(sanitized, tags=[], strip=True)

    return sanitized[:max_length] if len(sanitized) > max_length else sanitized

def sanitize_input(input_data: str, input_type: str = 'text') -> Optional[str]:
    """Advanced input sanitization based on input type"""
    if not input_data:
        return None

    # Basic sanitization for all inputs
    sanitized = sanitize_text(input_data)

    if input_type == 'name':
        # For names, allow only alphanumeric, spaces, hyphens, underscores
        sanitized = re.sub(r'[^a-zA-Z0-9\s\-_]', '', sanitized or '')
    elif input_type == 'email':
        # Basic email pattern validation
        if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', sanitized or ''):
            return None
    elif input_type == 'url':
        # Remove dangerous URL schemes
        sanitized = re.sub(r'(javascript|data|vbscript):', '', sanitized or '', flags=re.IGNORECASE)
    elif input_type == 'number':
        # Allow only numbers and decimal points
        sanitized = re.sub(r'[^0-9.]', '', sanitized or '')

    return sanitized

def validate_and_sanitize_input(input_data: str, input_type: str = 'text', max_length: int = 1000) -> tuple[bool, Optional[str]]:
    """Validate and sanitize input, returning validation result and sanitized data"""
    sanitized = sanitize_input(input_data, input_type)

    if not sanitized:
        return False, None

    if len(sanitized) > max_length:
        return False, None

    # Additional type-specific validation
    if input_type == 'name' and not re.match(r'^[a-zA-Z0-9\s\-_]{1,100}$', sanitized):
        return False, None
    elif input_type == 'email' and not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', sanitized):
        return False, None

    return True, sanitized

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
