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
    Implements multiple strategies to handle SSL connection drops
    """
    database_url = os.getenv('DATABASE_URL')
    
    if not database_url or 'postgresql' not in database_url:
        return database_url
    
    try:
        # Parse the URL
        parsed = urlparse(database_url)
        query_params = parse_qs(parsed.query)
        
        # Strategy 1: Minimal SSL parameters (most compatible)
        # Remove problematic SSL parameters that might cause drops
        problematic_params = ['sslcert', 'sslkey', 'sslrootcert', 'sslcrl']
        for param in problematic_params:
            if param in query_params:
                del query_params[param]
        
        # Add flexible SSL parameters (allow non-SSL for stability)
        essential_ssl_params = {
            'sslmode': ['allow'],  # Changed from 'require' to 'allow' for stability
            'connect_timeout': ['30'],  # Reasonable timeout
            'application_name': ['ErixCastBot']
        }
        
        # Merge with existing params (essential params take priority)
        for key, value in essential_ssl_params.items():
            query_params[key] = value
        
        # Reconstruct URL with clean parameters
        new_query = urlencode(query_params, doseq=True)
        fixed_url = urlunparse((
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            parsed.params,
            new_query,
            parsed.fragment
        ))
        
        logger.info("✅ Applied Render SSL fix with flexible parameters")
        logger.info("🔧 SSL mode: allow (flexible), timeout: 30s")
        return fixed_url
        
    except Exception as e:
        logger.error(f"❌ Failed to fix DATABASE_URL: {e}")
        return database_url

def get_fallback_database_urls():
    """
    Generate multiple fallback DATABASE_URLs with different SSL configurations
    """
    base_url = os.getenv('DATABASE_URL')
    if not base_url or 'postgresql' not in base_url:
        return [base_url]
    
    try:
        parsed = urlparse(base_url)
        base_params = parse_qs(parsed.query)
        
        # Remove all existing SSL and connection params
        clean_params = {k: v for k, v in base_params.items() 
                       if k not in ['sslmode', 'sslcert', 'sslkey', 'sslrootcert', 
                                   'connect_timeout', 'application_name']}
        
        # Different SSL strategies
        strategies = [
            # Strategy 1: SSL required with timeout
            {
                'name': 'ssl_required',
                'params': {**clean_params, 'sslmode': ['require'], 'connect_timeout': ['30']}
            },
            # Strategy 2: SSL preferred (fallback allowed)
            {
                'name': 'ssl_preferred', 
                'params': {**clean_params, 'sslmode': ['prefer'], 'connect_timeout': ['20']}
            },
            # Strategy 3: SSL allowed (minimal)
            {
                'name': 'ssl_allowed',
                'params': {**clean_params, 'sslmode': ['allow'], 'connect_timeout': ['15']}
            },
            # Strategy 4: No SSL (last resort)
            {
                'name': 'no_ssl',
                'params': {**clean_params, 'sslmode': ['disable'], 'connect_timeout': ['10']}
            }
        ]
        
        fallback_urls = []
        for strategy in strategies:
            try:
                query_string = urlencode(strategy['params'], doseq=True)
                url = urlunparse((
                    parsed.scheme, parsed.netloc, parsed.path,
                    parsed.params, query_string, parsed.fragment
                ))
                fallback_urls.append((strategy['name'], url))
            except Exception as e:
                logger.warning(f"Failed to create {strategy['name']} URL: {e}")
        
        return fallback_urls
        
    except Exception as e:
        logger.error(f"Failed to generate fallback URLs: {e}")
        return [('original', base_url)]

def set_ssl_environment():
    """Set SSL environment variables for PostgreSQL with Render optimizations"""
    # Only set essential SSL environment variables
    # Avoid setting empty cert paths that might cause issues
    ssl_env_vars = {
        'PGSSLMODE': 'allow',  # Changed from 'require' to 'allow' for stability
        'PGCONNECT_TIMEOUT': '30',  # Reasonable timeout
        'PGAPPNAME': 'ErixCastBot'
    }
    
    # Only set variables that aren't already configured
    for key, value in ssl_env_vars.items():
        if key not in os.environ:
            os.environ[key] = value
            logger.info(f"✅ Set {key}={value}")
        else:
            logger.info(f"ℹ️ {key} already set to: {os.environ[key]}")

def test_database_connection_strategies():
    """
    Test different database connection strategies to find the most stable one
    """
    fallback_urls = get_fallback_database_urls()
    
    for strategy_name, url in fallback_urls:
        try:
            logger.info(f"🧪 Testing connection strategy: {strategy_name}")
            
            # Try to connect with psycopg2 directly
            import psycopg2
            from urllib.parse import urlparse
            
            parsed = urlparse(url)
            conn_params = {
                'host': parsed.hostname,
                'port': parsed.port or 5432,
                'database': parsed.path.lstrip('/'),
                'user': parsed.username,
                'password': parsed.password
            }
            
            # Add query parameters
            if parsed.query:
                from urllib.parse import parse_qs
                query_params = parse_qs(parsed.query)
                for key, values in query_params.items():
                    if values:
                        conn_params[key] = values[0]
            
            # Test connection
            conn = psycopg2.connect(**conn_params)
            cursor = conn.cursor()
            cursor.execute("SELECT version()")
            version = cursor.fetchone()[0]
            cursor.close()
            conn.close()
            
            logger.info(f"✅ Strategy '{strategy_name}' successful!")
            logger.info(f"📊 PostgreSQL: {version[:50]}...")
            return strategy_name, url
            
        except Exception as e:
            logger.warning(f"❌ Strategy '{strategy_name}' failed: {e}")
            continue
    
    logger.error("💥 All connection strategies failed in testing")
    return None, None

if __name__ == '__main__':
    # Apply fixes
    set_ssl_environment()
    fixed_url = fix_render_database_url()
    
    if fixed_url:
        os.environ['DATABASE_URL'] = fixed_url
        print("✅ Render SSL fixes applied successfully")
    else:
        print("❌ Failed to apply SSL fixes")