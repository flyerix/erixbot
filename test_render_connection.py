#!/usr/bin/env python3
"""
Aggressive Render PostgreSQL Connection Test
Tests all possible connection strategies to find what works
"""
import os
import sys
import logging
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_direct_psycopg2_connection():
    """Test direct psycopg2 connection with different SSL modes"""
    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        logger.error("DATABASE_URL not found")
        return False
    
    try:
        import psycopg2
        from urllib.parse import urlparse
        
        parsed = urlparse(database_url)
        base_params = {
            'host': parsed.hostname,
            'port': parsed.port or 5432,
            'database': parsed.path.lstrip('/'),
            'user': parsed.username,
            'password': parsed.password
        }
        
        # Test different SSL modes in order of stability
        ssl_modes = [
            ('disable', 'No SSL - Most stable'),
            ('allow', 'SSL allowed but not required'),
            ('prefer', 'SSL preferred with fallback'),
            ('require', 'SSL required - Least stable on Render')
        ]
        
        for sslmode, description in ssl_modes:
            try:
                logger.info(f"🧪 Testing {description} (sslmode={sslmode})")
                
                conn_params = {
                    **base_params,
                    'sslmode': sslmode,
                    'connect_timeout': 15,
                    'application_name': f'ErixCastBot-Test-{sslmode}'
                }
                
                # Attempt connection
                conn = psycopg2.connect(**conn_params)
                cursor = conn.cursor()
                
                # Test basic operations
                cursor.execute("SELECT version()")
                version = cursor.fetchone()[0]
                
                cursor.execute("SELECT current_database()")
                db_name = cursor.fetchone()[0]
                
                cursor.execute("SELECT current_user")
                user = cursor.fetchone()[0]
                
                cursor.close()
                conn.close()
                
                logger.info(f"✅ SUCCESS with {sslmode}!")
                logger.info(f"📊 Database: {db_name}, User: {user}")
                logger.info(f"🔧 PostgreSQL: {version[:60]}...")
                
                return sslmode, description
                
            except Exception as e:
                logger.warning(f"❌ Failed with {sslmode}: {str(e)[:100]}...")
                continue
        
        logger.error("💥 All SSL modes failed!")
        return None, None
        
    except ImportError:
        logger.error("psycopg2 not available for testing")
        return None, None
    except Exception as e:
        logger.error(f"Connection test failed: {e}")
        return None, None

def test_sqlalchemy_connection():
    """Test SQLAlchemy connection with the working SSL mode"""
    working_ssl_mode, description = test_direct_psycopg2_connection()
    
    if not working_ssl_mode:
        logger.error("No working SSL mode found, cannot test SQLAlchemy")
        return False
    
    try:
        from sqlalchemy import create_engine, text
        
        database_url = os.getenv('DATABASE_URL')
        parsed = urlparse(database_url)
        
        # Clean URL and add working SSL mode
        clean_url = urlunparse((
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            '',
            f'sslmode={working_ssl_mode}&connect_timeout=15&application_name=ErixCastBot-SQLAlchemy',
            ''
        ))
        
        logger.info(f"🔧 Testing SQLAlchemy with {working_ssl_mode} mode")
        
        # Create engine with minimal configuration
        engine = create_engine(
            clean_url,
            pool_size=1,
            max_overflow=0,
            pool_timeout=10,
            pool_recycle=300,
            pool_pre_ping=False,
            echo=False
        )
        
        # Test connection
        with engine.connect() as conn:
            result = conn.execute(text("SELECT version()"))
            version = result.fetchone()[0]
            
            result = conn.execute(text("SELECT current_database()"))
            db_name = result.fetchone()[0]
            
        logger.info(f"✅ SQLAlchemy SUCCESS with {working_ssl_mode}!")
        logger.info(f"📊 Database: {db_name}")
        logger.info(f"🔧 PostgreSQL: {version[:60]}...")
        
        return True
        
    except Exception as e:
        logger.error(f"SQLAlchemy test failed: {e}")
        return False

def generate_optimal_database_url():
    """Generate the optimal DATABASE_URL based on test results"""
    working_ssl_mode, description = test_direct_psycopg2_connection()
    
    if not working_ssl_mode:
        logger.error("Cannot generate optimal URL - no working connection found")
        return None
    
    database_url = os.getenv('DATABASE_URL')
    parsed = urlparse(database_url)
    
    # Create optimal URL with working SSL mode
    optimal_params = {
        'sslmode': working_ssl_mode,
        'connect_timeout': '15',
        'application_name': 'ErixCastBot'
    }
    
    query_string = urlencode(optimal_params)
    optimal_url = urlunparse((
        parsed.scheme,
        parsed.netloc,
        parsed.path,
        '',
        query_string,
        ''
    ))
    
    logger.info(f"🎯 OPTIMAL DATABASE_URL generated:")
    logger.info(f"   SSL Mode: {working_ssl_mode} ({description})")
    logger.info(f"   URL: {optimal_url}")
    
    return optimal_url

if __name__ == '__main__':
    logger.info("🚀 Starting Render PostgreSQL Connection Test")
    logger.info("=" * 60)
    
    # Test 1: Direct psycopg2 connection
    logger.info("📋 STEP 1: Testing direct psycopg2 connections")
    working_mode, desc = test_direct_psycopg2_connection()
    
    if working_mode:
        logger.info(f"✅ Found working connection: {working_mode} ({desc})")
        
        # Test 2: SQLAlchemy connection
        logger.info("\n📋 STEP 2: Testing SQLAlchemy with working mode")
        sqlalchemy_success = test_sqlalchemy_connection()
        
        if sqlalchemy_success:
            # Test 3: Generate optimal URL
            logger.info("\n📋 STEP 3: Generating optimal DATABASE_URL")
            optimal_url = generate_optimal_database_url()
            
            if optimal_url:
                logger.info("\n🎉 CONNECTION TEST COMPLETE!")
                logger.info("=" * 60)
                logger.info(f"✅ RECOMMENDED SSL MODE: {working_mode}")
                logger.info(f"✅ OPTIMAL DATABASE_URL: {optimal_url}")
                logger.info("=" * 60)
                
                # Set environment variable for immediate use
                os.environ['DATABASE_URL'] = optimal_url
                logger.info("🔧 DATABASE_URL updated in environment")
                
                sys.exit(0)
    
    logger.error("\n💥 CONNECTION TEST FAILED!")
    logger.error("=" * 60)
    logger.error("❌ No stable connection method found")
    logger.error("❌ Render PostgreSQL may be experiencing issues")
    logger.error("=" * 60)
    sys.exit(1)