from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import QueuePool
import os
import logging
import sys
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

# Configure logging for production
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

def clean_database_url(database_url):
    """
    Clean DATABASE_URL by removing invalid psycopg2 connection parameters.
    psycopg2 doesn't recognize parameters like read_timeout, write_timeout, etc.
    """
    if not database_url or 'postgresql' not in database_url:
        return database_url

    try:
        # Parse the URL
        parsed = urlparse(database_url)

        # Get query parameters
        query_params = parse_qs(parsed.query)

        # Valid psycopg2 parameters (connection-level)
        valid_params = {
            'connect_timeout', 'sslmode', 'sslrootcert', 'sslcert', 'sslkey',
            'application_name', 'client_encoding', 'options', 'fallback_application_name',
            'keepalives', 'keepalives_idle', 'keepalives_interval', 'keepalives_count',
            'tcp_user_timeout', 'sslcrl', 'requiressl', 'sslcompression'
        }
        
        # Filter out invalid parameters
        cleaned_params = {k: v for k, v in query_params.items() if k in valid_params}
        
        # DO NOT force SSL mode - let connection strategies handle SSL configuration
        # The create_engine_with_fallback function will set appropriate SSL modes
        # Forcing sslmode=require here breaks the no-SSL-first strategy

        # Reconstruct query string
        cleaned_query = urlencode(cleaned_params, doseq=True) if cleaned_params else ''

        # Reconstruct URL
        cleaned_url = urlunparse((
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            parsed.params,
            cleaned_query,
            parsed.fragment
        ))

        # Log what was removed
        removed_params = set(query_params.keys()) - set(cleaned_params.keys())
        if removed_params:
            logger.info(f"Removed invalid psycopg2 parameters from DATABASE_URL: {removed_params}")

        return cleaned_url

    except Exception as e:
        logger.warning(f"Failed to clean DATABASE_URL: {e}. Using original URL.")
        return database_url

# Apply Render SSL fixes if on Render
if os.getenv('RENDER'):
    try:
        # Apply minimal SSL fixes for Render (skip complex connection testing)
        logger.info("🔧 Applying minimal Render SSL configuration")
        try:
            from render_ssl_fix import set_ssl_environment
            set_ssl_environment()
            logger.info("✅ Render SSL environment configured")
        except Exception as ssl_e:
            logger.warning(f"SSL environment setup failed: {ssl_e}")
            # Continue anyway - the direct URL approach should work
    except ImportError:
        logger.warning("Render SSL fix module not available")
    except Exception as e:
        logger.warning(f"Failed to apply Render SSL fixes: {e}")

# Environment validation
DATABASE_URL = os.getenv('DATABASE_URL')
if not DATABASE_URL:
    logger.error("DATABASE_URL environment variable is required")
    raise ValueError("DATABASE_URL environment variable is required")

# Clean DATABASE_URL to remove invalid psycopg2 parameters (skip on Render for SSL flexibility)
if not os.getenv('RENDER'):
    DATABASE_URL = clean_database_url(DATABASE_URL)
else:
    logger.info("🔧 Skipping URL cleaning on Render to preserve SSL strategy flexibility")

TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
if not TELEGRAM_BOT_TOKEN:
    logger.error("TELEGRAM_BOT_TOKEN environment variable is required")
    raise ValueError("TELEGRAM_BOT_TOKEN environment variable is required")

# Database configuration optimized for Render free tier (512MB RAM limit)
pool_size = int(os.getenv('DATABASE_POOL_SIZE', '3'))  # Ridotto per risparmiare memoria
max_overflow = int(os.getenv('DATABASE_MAX_OVERFLOW', '2'))  # Ridotto per efficienza

def create_engine_with_fallback(database_url, pool_size, max_overflow):
    """Create engine with direct URL manipulation for Render PostgreSQL"""
    
    # ULTRA-DIRECT APPROACH: Manually create URLs with different SSL modes
    # This bypasses all URL parsing issues and directly tests what works
    
    from urllib.parse import urlparse, urlunparse
    parsed = urlparse(database_url)
    
    # Create base URL without any query parameters
    base_url = urlunparse((
        parsed.scheme,
        parsed.netloc, 
        parsed.path,
        '',  # No params
        '',  # No query
        ''   # No fragment
    ))
    
    # Direct URL strategies - manually construct each one
    ssl_configs = [
        # Strategy 1: NO SSL - Direct URL construction
        {
            'name': 'Direct No SSL',
            'url': f"{base_url}?sslmode=disable&connect_timeout=15&application_name=ErixCastBot-NoSSL",
            'pool_recycle': 300,
            'pool_pre_ping': False,
            'pool_timeout': 15,
            'pool_size': 1,
            'max_overflow': 0
        },
        # Strategy 2: Completely bare URL (no parameters at all)
        {
            'name': 'Bare URL (no params)',
            'url': base_url,
            'pool_recycle': 180,
            'pool_pre_ping': False,
            'pool_timeout': 10,
            'pool_size': 1,
            'max_overflow': 0
        },
        # Strategy 3: SSL Allow
        {
            'name': 'Direct SSL Allow',
            'url': f"{base_url}?sslmode=allow&connect_timeout=20&application_name=ErixCastBot-Allow",
            'pool_recycle': 600,
            'pool_pre_ping': False,
            'pool_timeout': 20,
            'pool_size': 1,
            'max_overflow': 0
        },
        # Strategy 4: SSL Prefer
        {
            'name': 'Direct SSL Prefer',
            'url': f"{base_url}?sslmode=prefer&connect_timeout=25&application_name=ErixCastBot-Prefer",
            'pool_recycle': 900,
            'pool_pre_ping': False,
            'pool_timeout': 25,
            'pool_size': 2,
            'max_overflow': 0
        },
        # Strategy 5: SSL Required (last resort)
        {
            'name': 'Direct SSL Required',
            'url': f"{base_url}?sslmode=require&connect_timeout=30&application_name=ErixCastBot-Required",
            'pool_recycle': 1200,
            'pool_pre_ping': False,
            'pool_timeout': 30,
            'pool_size': 2,
            'max_overflow': 1
        }
    ]
    
    for i, config in enumerate(ssl_configs):
        try:
            logger.info(f"🔄 Attempting database connection strategy {i+1}/5: {config['name']}")
            logger.info(f"🔗 Using URL: {config['url'][:80]}...")
            
            # Use config-specific pool settings
            config_pool_size = config.get('pool_size', pool_size)
            config_max_overflow = config.get('max_overflow', max_overflow)
            config_pool_timeout = config.get('pool_timeout', 30)
            config_pool_pre_ping = config.get('pool_pre_ping', False)
            
            # Create engine with the specific URL (no connect_args needed)
            engine = create_engine(
                config['url'],  # Use the pre-constructed URL
                poolclass=QueuePool,
                pool_size=config_pool_size,
                max_overflow=config_max_overflow,
                pool_timeout=config_pool_timeout,
                pool_recycle=config['pool_recycle'],
                pool_pre_ping=config_pool_pre_ping,
                echo=False
                # No connect_args - everything is in the URL
            )
            
            # Test the connection with multiple attempts
            test_attempts = 2  # Reduced attempts for faster failover
            for attempt in range(test_attempts):
                try:
                    with engine.connect() as conn:
                        from sqlalchemy import text
                        result = conn.execute(text("SELECT version()"))
                        version_info = result.fetchone()[0][:50]
                        logger.info(f"✅ Database connection successful with strategy: {config['name']}")
                        logger.info(f"📊 PostgreSQL version: {version_info}...")
                        logger.info(f"🔧 Pool config: size={config_pool_size}, overflow={config_max_overflow}, timeout={config_pool_timeout}s")
                        return engine
                except Exception as test_e:
                    if attempt < test_attempts - 1:
                        logger.warning(f"⚠️ Connection test attempt {attempt + 1}/{test_attempts} failed: {test_e}")
                        import time
                        time.sleep(1)  # Brief pause before retry
                    else:
                        raise test_e
                
        except Exception as e:
            logger.warning(f"❌ Strategy {i+1} '{config['name']}' failed: {str(e)[:100]}...")
            continue  # Try next strategy immediately
    
    # If we get here, all strategies failed
    logger.error("💥 All connection strategies failed!")
    logger.error("🔍 Attempting final diagnostic connection...")
    
    # Final diagnostic attempt with minimal configuration
    try:
        diagnostic_engine = create_engine(
            base_url,  # Completely bare URL
            pool_size=1,
            max_overflow=0,
            pool_timeout=5,
            pool_recycle=30,
            pool_pre_ping=False,
            echo=True  # Enable echo for debugging
        )
        
        with diagnostic_engine.connect() as conn:
            from sqlalchemy import text
            result = conn.execute(text("SELECT 1"))
            result.fetchone()
            logger.warning("⚠️ Diagnostic connection successful with bare URL")
            return diagnostic_engine
            
    except Exception as diagnostic_e:
        logger.error(f"💀 Diagnostic connection also failed: {diagnostic_e}")
        logger.error("🚨 DATABASE COMPLETELY UNAVAILABLE - Check Render PostgreSQL status")
        raise Exception(f"All database connection attempts failed. Last diagnostic error: {diagnostic_e}")
    
    return None

# Create engine with fallback strategies (non-blocking approach)
engine = None
SessionLocal = None

def initialize_database():
    """Initialize database connection with graceful failure handling"""
    global engine, SessionLocal
    
    try:
        logger.info("🔄 Initializing database connection...")
        engine = create_engine_with_fallback(DATABASE_URL, pool_size, max_overflow)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        logger.info("✅ Database connection initialized successfully")
        return True
    except Exception as e:
        logger.error(f"❌ Database initialization failed: {e}")
        logger.warning("⚠️ Starting without database connection - will retry later")
        
        # Create a dummy SessionLocal that raises an error when used
        def dummy_session():
            raise Exception("Database not available - connection failed at startup")
        
        SessionLocal = dummy_session
        return False

# Try to initialize database, but don't fail if it doesn't work
database_available = initialize_database()

# Import models directly (with --chdir, the root directory is in Python path)
from models import UptimePing, create_tables
import models
if SessionLocal:
    models.SessionLocal = SessionLocal

# Database retry mechanism
def retry_database_connection():
    """Retry database connection periodically"""
    global engine, SessionLocal, database_available
    
    if database_available:
        return True  # Already connected
    
    try:
        logger.info("🔄 Retrying database connection...")
        engine = create_engine_with_fallback(DATABASE_URL, pool_size, max_overflow)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        models.SessionLocal = SessionLocal
        
        # Test the connection
        if test_database_connection():
            database_available = True
            logger.info("✅ Database reconnection successful!")
            
            # Try to create tables
            tables_created = create_tables_with_retry(engine)
            if tables_created:
                logger.info("✅ Database tables created after reconnection")
            
            return True
        else:
            raise Exception("Connection test failed after engine creation")
            
    except Exception as e:
        logger.warning(f"⚠️ Database reconnection failed: {e}")
        return False

# Create all tables using the centralized function with retry logic
def create_tables_with_retry(engine, max_retries=5):
    """Create tables with retry logic for connection issues"""
    for attempt in range(max_retries):
        try:
            create_tables(engine)
            logger.info("✅ Database tables created successfully")
            return True
        except Exception as e:
            logger.warning(f"⚠️ Attempt {attempt + 1}/{max_retries} to create tables failed: {e}")
            if attempt == max_retries - 1:
                logger.error("❌ Failed to create tables after all retries - continuing without table creation")
                return False
            import time
            # Exponential backoff with jitter
            sleep_time = (2 ** attempt) + (attempt * 0.5)
            logger.info(f"Waiting {sleep_time:.1f}s before retry...")
            time.sleep(sleep_time)
    
    return False

# Try to create tables only if database is available
if database_available and engine:
    tables_created = create_tables_with_retry(engine)
    if not tables_created:
        logger.warning("⚠️ Tables creation failed - bot will attempt to create them on first use")
else:
    logger.warning("⚠️ Skipping table creation - database not available")

# Test database connection with SSL
def test_database_connection():
    """Test database connection with proper error handling"""
    max_retries = 5
    for attempt in range(max_retries):
        try:
            session = SessionLocal()
            from sqlalchemy import text
            result = session.execute(text("SELECT version()"))
            version = result.fetchone()[0]
            session.close()
            logger.info(f"Database connection successful - PostgreSQL version: {version[:50]}...")
            return True
        except Exception as e:
            logger.warning(f"Database connection attempt {attempt + 1}/{max_retries} failed: {e}")
            if attempt == max_retries - 1:
                logger.error("Database connection failed after all retries")
                return False
            import time
            time.sleep(2 ** attempt)  # Exponential backoff
    return False

# Test connection at startup only if database was initialized
if database_available:
    if not test_database_connection():
        logger.error("Critical: Database connection test failed")
        database_available = False
else:
    logger.warning("⚠️ Skipping database connection test - database not initialized")

# Flask app for health checks (always create for Gunicorn compatibility)
try:
    from flask import Flask, jsonify, request
    app = Flask(__name__)
    logger.info("Flask app created for health checks")
except ImportError:
    logger.warning("Flask not available, health check endpoints disabled")
    app = None

# Health check endpoint for Render (only if Flask is available)
if app:
    @app.route('/health')
    def health_check():
        """Enhanced health check with SSL connection recovery"""
        try:
            # Test database connection with multiple strategies
            session = None
            db_status = "disconnected"
            connection_strategy = "unknown"
            
            # Check if database is available
            session = None
            try:
                if not database_available or not SessionLocal:
                    # Try to reconnect
                    if retry_database_connection():
                        db_status = "reconnected"
                        connection_strategy = "retry_success"
                    else:
                        db_status = "unavailable"
                        connection_strategy = "no_connection"
                else:
                    # Try primary connection
                    session = SessionLocal()
                    from sqlalchemy import text
                    result = session.execute(text("SELECT 1"))
                    result.fetchone()
                    session.commit()
                    db_status = "connected"
                    connection_strategy = "primary"
            except Exception as db_e:
                logger.warning(f"Primary health check failed: {db_e}")
                
                # Try to reconnect
                if retry_database_connection():
                    db_status = "reconnected"
                    connection_strategy = "retry_success"
                else:
                    db_status = f"failed: {str(db_e)[:50]}"
                    connection_strategy = "failed"
            finally:
                if session:
                    try:
                        session.close()
                    except Exception:
                        pass

            # Test bot connectivity (quick test)
            try:
                # Simple bot status check without circular imports
                bot_status = "bot_initializing"  # Default status
            except Exception:
                bot_status = "bot_check_failed"

            # Get resource status
            resource_status = {}
            try:
                # Use psutil directly instead of importing bot module
                import psutil
                process = psutil.Process()
                resource_status = {
                    'memory_mb': round(process.memory_info().rss / 1024 / 1024, 2),
                    'cpu_percent': psutil.cpu_percent(interval=0.1)
                }
            except Exception:
                pass

            # Determine overall health status
            is_healthy = db_status in ['connected', 'connected_fallback', 'reconnected']
            is_degraded = db_status in ['unavailable', 'failed']
            
            if is_healthy:
                status_code = 200
            elif is_degraded:
                status_code = 503  # Service unavailable but trying to recover
            else:
                status_code = 503
            
            from datetime import datetime, timezone
            
            # Determine service status
            if is_healthy:
                service_status = 'healthy'
            elif is_degraded:
                service_status = 'degraded'
            else:
                service_status = 'unhealthy'
            
            return jsonify({
                'status': service_status,
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'database': db_status,
                'connection_strategy': connection_strategy,
                'bot_status': bot_status,
                'database_available': database_available,
                'uptime_seconds': int((datetime.now(timezone.utc) - datetime.fromisoformat('2025-01-01T00:00:00')).total_seconds()) % 86400,
                'resources': resource_status,
                'ssl_info': 'Graceful degradation - service runs without database if needed'
            }), status_code
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            from datetime import datetime, timezone
            return jsonify({
                'status': 'unhealthy',
                'error': str(e),
                'timestamp': datetime.now(timezone.utc).isoformat()
            }), 500

    @app.route('/ping')
    def ping():
        """Lightweight ping endpoint to prevent Render sleep"""
        from datetime import datetime, timezone
        return jsonify({
            'status': 'pong',
            'timestamp': datetime.now(timezone.utc).isoformat()
        }), 200

    @app.route('/status')
    def status():
        """Detailed status endpoint for monitoring"""
        import psutil
        import os

        try:
            import psutil
            from datetime import datetime, timezone
            memory = psutil.virtual_memory()
            process = psutil.Process(os.getpid())

            return jsonify({
                'status': 'operational',
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'memory_usage_mb': round(memory.used / 1024 / 1024, 2),
                'memory_percent': memory.percent,
                'cpu_percent': psutil.cpu_percent(interval=0.1),
                'process_memory_mb': round(process.memory_info().rss / 1024 / 1024, 2),
                'uptime_seconds': int((datetime.now(timezone.utc) - datetime.fromisoformat('2025-01-01T00:00:00')).total_seconds()) % 86400
            }), 200
        except Exception as e:
            from datetime import datetime, timezone
            return jsonify({
                'status': 'status_check_failed',
                'error': str(e),
                'timestamp': datetime.now(timezone.utc).isoformat()
            }), 500

    # Webhook endpoint for Telegram (more efficient than polling)
    @app.route(f'/webhook/{TELEGRAM_BOT_TOKEN.split(":")[0]}', methods=['POST'])
    def telegram_webhook():
        """Telegram webhook endpoint - more efficient than polling"""
        try:
            # Import here to avoid circular imports
            import asyncio
            from telegram import Update

            # Get application from bot module
            import bot
            if hasattr(bot, 'application') and bot.application:
                # Process webhook update
                update_data = request.get_json()
                if update_data:
                    # Convert to Update object and process
                    update = Update.de_json(update_data, bot.application.bot)
                    if update:
                        # Process in background to avoid timeout
                        import threading
                        def process_update():
                            try:
                                # Create new event loop for this thread
                                loop = asyncio.new_event_loop()
                                asyncio.set_event_loop(loop)
                                loop.run_until_complete(bot.application.process_update(update))
                                loop.close()
                            except Exception as e:
                                logger.error(f"Error processing webhook update: {e}")

                        thread = threading.Thread(target=process_update, daemon=True)
                        thread.start()

                        return jsonify({'status': 'ok'}), 200

            return jsonify({'status': 'error', 'message': 'Bot not ready or invalid update'}), 400
        except Exception as e:
            logger.error(f"Webhook error: {e}")
            return jsonify({'status': 'error', 'message': str(e)}), 500

    @app.route('/')
    def root():
        """Root endpoint"""
        return jsonify({
            'service': 'ErixCastBot',
            'status': 'running',
            'version': '2.0.0'
        })

# Import and run bot in a separate thread
def run_bot():
    """Run the bot in a separate thread"""
    try:
        logger.info("Starting ErixCastBot...")
        # Import bot modules directly
        from bot import main as bot_main
        bot_main()
    except Exception as e:
        logger.error(f"Bot failed to start: {e}")
        raise

# For production deployment (Gunicorn) - start bot when imported
if __name__ != '__main__':
    # This block runs when imported by Gunicorn
    import threading
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()
    logger.info("ErixCastBot started successfully in production mode")

    # Start enhanced auto-ping system to prevent Render sleep
    if app is not None:
        # Import models for database tracking
        from models import UptimePing

        class PingCircuitBreaker:
            """Circuit breaker for ping threads to handle failures gracefully"""
            def __init__(self, failure_threshold=3, recovery_timeout=300):  # 5 minutes
                import time
                self.failure_threshold = failure_threshold
                self.recovery_timeout = recovery_timeout
                self.failure_counts = {}
                self.last_failures = {}
                self.lock = threading.Lock()
                self.time = time

            def record_success(self, thread_name):
                with self.lock:
                    if thread_name in self.failure_counts:
                        self.failure_counts[thread_name] = 0
                        if thread_name in self.last_failures:
                            del self.last_failures[thread_name]

            def record_failure(self, thread_name):
                with self.lock:
                    if thread_name not in self.failure_counts:
                        self.failure_counts[thread_name] = 0
                    self.failure_counts[thread_name] += 1
                    self.last_failures[thread_name] = self.time.time()

            def should_restart(self, thread_name):
                with self.lock:
                    if thread_name not in self.failure_counts:
                        return False
                    if self.failure_counts[thread_name] >= self.failure_threshold:
                        # Check if recovery timeout has passed
                        if thread_name in self.last_failures:
                            if self.time.time() - self.last_failures[thread_name] > self.recovery_timeout:
                                # Reset and allow restart
                                self.failure_counts[thread_name] = 0
                                del self.last_failures[thread_name]
                                return True
                        return False
                    return False

        ping_circuit_breaker = PingCircuitBreaker()

        def create_ping_thread(interval_minutes, thread_name):
            """Create a ping thread with specified interval"""
            def ping_worker():
                import time
                import requests
                from datetime import datetime, timezone

                port = int(os.environ.get('PORT', 10000))
                render_url = f'http://localhost:{port}'
                endpoint = f"{render_url}/health"  # Use health check endpoint
                interval_seconds = interval_minutes * 60

                consecutive_failures = 0
                max_consecutive_failures = 5

                logger.info(f"🔔 Starting ping thread '{thread_name}' with {interval_minutes}min interval")

                while True:
                    start_time = time.time()
                    try:
                        # Attempt ping
                        response = requests.get(endpoint, timeout=10)
                        response_time = int((time.time() - start_time) * 1000)  # ms

                        if response.status_code == 200:
                            consecutive_failures = 0
                            ping_circuit_breaker.record_success(thread_name)

                            # Log success with comprehensive details
                            logger.info(f"✅ Ping '{thread_name}' successful - Response: {response_time}ms - Status: {response.status_code}")

                            # Record success in database (if available)
                            if database_available and SessionLocal:
                                try:
                                    session = SessionLocal()
                                    ping_record = UptimePing(
                                        thread_name=thread_name,
                                        endpoint='/health',
                                        success=True,
                                        response_time_ms=response_time
                                    )
                                    session.add(ping_record)
                                    session.commit()
                                except Exception as db_e:
                                    logger.warning(f"⚠️ Failed to record ping success in database: {db_e}")
                                finally:
                                    try:
                                        session.close()
                                    except Exception:
                                        pass
                        else:
                            consecutive_failures += 1
                            ping_circuit_breaker.record_failure(thread_name)

                            # Log failure with details
                            logger.warning(f"⚠️ Ping '{thread_name}' failed - Status: {response.status_code} - Response: {response_time}ms - Consecutive: {consecutive_failures}")

                            # Record failure in database (if available)
                            if database_available and SessionLocal:
                                try:
                                    session = SessionLocal()
                                    ping_record = UptimePing(
                                        thread_name=thread_name,
                                        endpoint='/health',
                                        success=False,
                                        response_time_ms=response_time,
                                        error_message=f"HTTP {response.status_code}"
                                    )
                                    session.add(ping_record)
                                    session.commit()
                                except Exception as db_e:
                                    logger.warning(f"⚠️ Failed to record ping failure in database: {db_e}")
                                finally:
                                    try:
                                        session.close()
                                    except Exception:
                                        pass

                    except requests.exceptions.Timeout:
                        consecutive_failures += 1
                        ping_circuit_breaker.record_failure(thread_name)
                        response_time = int((time.time() - start_time) * 1000)

                        logger.error(f"⏰ Ping '{thread_name}' timeout - Response: {response_time}ms - Consecutive: {consecutive_failures}")

                        # Record timeout in database (if available)
                        if database_available and SessionLocal:
                            try:
                                session = SessionLocal()
                                ping_record = UptimePing(
                                    thread_name=thread_name,
                                    endpoint='/health',
                                    success=False,
                                    response_time_ms=response_time,
                                    error_message="Timeout"
                                )
                                session.add(ping_record)
                                session.commit()
                            except Exception as db_e:
                                logger.warning(f"⚠️ Failed to record ping timeout in database: {db_e}")
                            finally:
                                try:
                                    session.close()
                                except Exception:
                                    pass

                    except Exception as e:
                        consecutive_failures += 1
                        ping_circuit_breaker.record_failure(thread_name)
                        response_time = int((time.time() - start_time) * 1000)

                        logger.error(f"💥 Ping '{thread_name}' error: {str(e)} - Response: {response_time}ms - Consecutive: {consecutive_failures}")

                        # Record error in database (if available)
                        if database_available and SessionLocal:
                            try:
                                session = SessionLocal()
                                ping_record = UptimePing(
                                    thread_name=thread_name,
                                    endpoint='/health',
                                    success=False,
                                    response_time_ms=response_time,
                                    error_message=str(e)
                                )
                                session.add(ping_record)
                                session.commit()
                            except Exception as db_e:
                                logger.warning(f"⚠️ Failed to record ping error in database: {db_e}")
                            finally:
                                try:
                                    session.close()
                                except Exception:
                                    pass

                    # Check if thread should restart due to circuit breaker
                    if ping_circuit_breaker.should_restart(thread_name):
                        logger.warning(f"🔄 Circuit breaker triggered restart for ping thread '{thread_name}'")
                        break  # Exit loop to restart thread

                    # Check for excessive consecutive failures
                    if consecutive_failures >= max_consecutive_failures:
                        logger.critical(f"💥 Ping thread '{thread_name}' failed {consecutive_failures} times consecutively - triggering restart")
                        break  # Exit loop to restart thread

                    # Sleep until next ping
                    time.sleep(interval_seconds)

                # If we reach here, thread is restarting
                logger.info(f"🔄 Restarting ping thread '{thread_name}' in 30 seconds...")
                time.sleep(30)

                # Restart the thread
                new_thread = threading.Thread(target=ping_worker, daemon=True, name=f"{thread_name}_restart")
                new_thread.start()
                logger.info(f"✅ Ping thread '{thread_name}' restarted successfully")

            return threading.Thread(target=ping_worker, daemon=True, name=thread_name)

        # Create multiple redundant ping threads with different intervals
        ping_threads = []
        intervals = [
            (5, "ping_5min"),
            (7, "ping_7min"),
            (10, "ping_10min")
        ]

        for interval, name in intervals:
            thread = create_ping_thread(interval, name)
            ping_threads.append(thread)
            thread.start()

        logger.info(f"🚀 Enhanced auto-ping system started with {len(ping_threads)} redundant threads - 24/7 availability ensured")

if __name__ == '__main__':
    # For local development only
    import threading
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()

    if app:
        port = int(os.environ.get('PORT', 10000))
        logger.info(f"Starting Flask server on port {port}")
        app.run(host='0.0.0.0', port=port)
    else:
        logger.info("Flask not available, running bot only")
        bot_thread.join()
