#!/usr/bin/env python3
"""
SSL Connection Fix for Render PostgreSQL
Fixes SSL connection issues with PostgreSQL on Render
"""
import os
import logging
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

logger = logging.getLogger(__name__)

def fix_render_database_url():
    """
    Fix DATABASE_URL for Render PostgreSQL SSL connections
    """
    database_url = os.getenv('DATABASE_URL')
    
    if not database_url or 'postgresql' not in database_url:
        return database_url
    
    try:
        # Parse the URL
        parsed = urlparse(database_url)
        query_params = parse_qs(parsed.query)
        
        # Add SSL parameters for Render
        ssl_params = {
            'sslmode': ['require'],
            'sslcert': [],  # Empty but valid
            'sslkey': [],   # Empty but valid
            'sslrootcert': []  # Empty but valid
        }
        
        # Merge with existing params
        for key, value in ssl_params.items():
            if key not in query_params:
                query_params[key] = value
        
        # Reconstruct URL
        new_query = urlencode(query_params, doseq=True)
        fixed_url = urlunparse((
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            parsed.params,
            new_query,
            parsed.fragment
        ))
        
        logger.info("Applied Render SSL fix to DATABASE_URL")
        return fixed_url
        
    except Exception as e:
        logger.error(f"Failed to fix DATABASE_URL: {e}")
        return database_url

def set_ssl_environment():
    """Set SSL environment variables for PostgreSQL"""
    ssl_env_vars = {
        'PGSSLMODE': 'require',
        'PGSSLCERT': '',
        'PGSSLKEY': '',
        'PGSSLROOTCERT': ''
    }
    
    for key, value in ssl_env_vars.items():
        if key not in os.environ:
            os.environ[key] = value
            logger.info(f"Set {key}={value}")

if __name__ == '__main__':
    # Apply fixes
    set_ssl_environment()
    fixed_url = fix_render_database_url()
    
    if fixed_url:
        os.environ['DATABASE_URL'] = fixed_url
        print("✅ Render SSL fixes applied successfully")
    else:
        print("❌ Failed to apply SSL fixes")