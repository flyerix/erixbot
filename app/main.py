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
        
        # Force SSL mode for PostgreSQL connections if not specified
        if 'postgresql' in database_url and 'sslmode' not in query_params:
            cleaned_params['sslmode'] = ['require']
            logger.info("Added sslmode=require to DATABASE_URL for PostgreSQL connection")

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
        from render_ssl_fix import fix_render_database_url, set_ssl_environment
        set_ssl_environment()
        fixed_url = fix_render_database_url()
        if fixed_url:
            os.environ['DATABASE_URL'] = fixed_url
            logger.info("Applied Render SSL fixes")
    except ImportError:
        logger.warning("Render SSL fix module not available")
    except Exception as e:
        logger.warning(f"Failed to apply Render SSL fixes: {e}")

# Environment validation
DATABASE_URL = os.getenv('DATABASE_URL')
if not DATABASE_URL:
    logger.error("DATABASE_URL environment variable is required")
    raise ValueError("DATABASE_URL environment variable is required")

# Clean DATABASE_URL to remove invalid psycopg2 parameters
DATABASE_URL = clean_database_url(DATABASE_URL)

TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
if not TELEGRAM_BOT_TOKEN:
    logger.error("TELEGRAM_BOT_TOKEN environment variable is required")
    raise ValueError("TELEGRAM_BOT_TOKEN environment variable is required")

# Database configuration optimized for Render free tier (512MB RAM limit)
pool_size = int(os.getenv('DATABASE_POOL_SIZE', '3'))  # Ridotto per risparmiare memoria
max_overflow = int(os.getenv('DATABASE_MAX_OVERFLOW', '2'))  # Ridotto per efficienza

def create_engine_with_fallback(database_url, pool_size, max_overflow):
    """Create engine with SSL fallback strategies optimized for Render"""
    
    # Enhanced SSL strategies specifically for Render PostgreSQL
    ssl_configs = [
        # Strategy 1: Render-optimized SSL with aggressive keepalives
        {
            'name': 'Render SSL optimized',
            'connect_args': {
                'connect_timeout': 45,  # Longer timeout for SSL handshake
                'sslmode': 'require',
                'keepalives': 1,
                'keepalives_idle': 300,    # 5 minutes (shorter for Render)
                'keepalives_interval': 15,  # 15 seconds (more frequent)
                'keepalives_count': 5,     # More attempts
                'tcp_user_timeout': 30000, # 30 seconds (shorter)
                'application_name': 'ErixCastBot-Render'
            },
            'pool_recycle': 1800,  # 30 minutes (shorter for SSL stability)
            'pool_pre_ping': True,
            'pool_timeout': 45
        },
        # Strategy 2: Minimal SSL with short timeouts
        {
            'name': 'Minimal SSL fast',
            'connect_args': {
                'connect_timeout': 20,
                'sslmode': 'require',
                'application_name': 'ErixCastBot-Fast'
            },
            'pool_recycle': 900,   # 15 minutes
            'pool_pre_ping': False, # Disable pre-ping to avoid SSL issues
            'pool_timeout': 20
        },
        # Strategy 3: SSL prefer with connection pooling disabled
        {
            'name': 'SSL prefer no-pool',
            'connect_args': {
                'connect_timeout': 15,
                'sslmode': 'prefer',
                'application_name': 'ErixCastBot-NoPool'
            },
            'pool_recycle': 300,   # 5 minutes
            'pool_pre_ping': False,
            'pool_timeout': 15,
            'pool_size': 1,        # Single connection
            'max_overflow': 0
        },
        # Strategy 4: SSL allow with minimal configuration
        {
            'name': 'SSL allow minimal',
            'connect_args': {
                'connect_timeout': 10,
                'sslmode': 'allow',
                'application_name': 'ErixCastBot-Minimal'
            },
            'pool_recycle': 180,   # 3 minutes
            'pool_pre_ping': False,
            'pool_timeout': 10,
            'pool_size': 1,
            'max_overflow': 0
        },
        # Strategy 5: Disable SSL as last resort
        {
            'name': 'No SSL (last resort)',
            'connect_args': {
                'connect_timeout': 10,
                'sslmode': 'disable',
                'application_name': 'ErixCastBot-NoSSL'
            },
            'pool_recycle': 120,   # 2 minutes
            'pool_pre_ping': False,
            'pool_timeout': 10,
            'pool_size': 1,
            'max_overflow': 0
        }
    ]
    
    for i, config in enumerate(ssl_configs):
        try:
            logger.info(f"🔄 Attempting database connection strategy {i+1}/5: {config['name']}")
            
            # Use config-specific pool settings if provided
            config_pool_size = config.get('pool_size', pool_size)
            config_max_overflow = config.get('max_overflow', max_overflow)
            config_pool_timeout = config.get('pool_timeout', 30)
            config_pool_pre_ping = config.get('pool_pre_ping', True)
            
            engine = create_engine(
                database_url,
                poolclass=QueuePool,
                pool_size=config_pool_size,
                max_overflow=config_max_overflow,
                pool_timeout=config_pool_timeout,
                pool_recycle=config['pool_recycle'],
                pool_pre_ping=config_pool_pre_ping,
                echo=False,
                connect_args=config['connect_args'] if 'postgresql' in database_url else {}
            )
            
            # Test the connection with multiple attempts
            test_attempts = 3
            for attempt in range(test_attempts):
                try:
                    with engine.connect() as conn:
                        result = conn.execute("SELECT version()")
                        version_info = result.fetchone()[0][:50]
                        logger.info(f"✅ Database connection successful with strategy: {config['name']}")
                        logger.info(f"📊 PostgreSQL version: {version_info}...")
                        logger.info(f"🔧 Pool config: size={config_pool_size}, overflow={config_max_overflow}, timeout={config_pool_timeout}s")
                        return engine
                except Exception as test_e:
                    if attempt < test_attempts - 1:
                        logger.warning(f"⚠️ Connection test attempt {attempt + 1}/{test_attempts} failed: {test_e}")
                        import time
                        time.sleep(2)  # Brief pause before retry
                    else:
                        raise test_e
                
        except Exception as e:
            logger.warning(f"❌ Strategy {i+1} '{config['name']}' failed: {str(e)[:100]}...")
            
            # If this is the last strategy, don't give up yet
            if i == len(ssl_configs) - 1:
                logger.error("🚨 All predefined SSL strategies failed - attempting emergency fallback")
                
                # Emergency fallback: Try to extract just the base connection without any SSL params
                try:
                    # Parse URL and remove all query parameters
                    from urllib.parse import urlparse, urlunparse
                    parsed = urlparse(database_url)
                    clean_url = urlunparse((
                        parsed.scheme,
                        parsed.netloc,
                        parsed.path,
                        '',  # No params
                        '',  # No query
                        ''   # No fragment
                    ))
                    
                    logger.info("🆘 Attempting emergency connection without any parameters")
                    emergency_engine = create_engine(
                        clean_url,
                        poolclass=QueuePool,
                        pool_size=1,
                        max_overflow=0,
                        pool_timeout=5,
                        pool_recycle=60,
                        pool_pre_ping=False,
                        echo=False
                    )
                    
                    with emergency_engine.connect() as conn:
                        conn.execute("SELECT 1")
                        logger.warning("⚠️ Emergency connection successful - using minimal configuration")
                        return emergency_engine
                        
                except Exception as emergency_e:
                    logger.error(f"💥 Emergency fallback also failed: {emergency_e}")
                    logger.error("💀 All connection strategies exhausted - database unavailable")
                    raise Exception(f"Database connection failed after all strategies. Last error: {e}")
    
    return None

# Create engine with fallback strategies
engine = create_engine_with_fallback(DATABASE_URL, pool_size, max_overflow)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Import models directly (with --chdir, the root directory is in Python path)
from models import UptimePing, create_tables
import models
models.SessionLocal = SessionLocal

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

# Try to create tables, but don't fail if it doesn't work
tables_created = create_tables_with_retry(engine)
if not tables_created:
    logger.warning("⚠️ Tables creation failed - bot will attempt to create them on first use")

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

# Test connection at startup
if not test_database_connection():
    logger.error("Critical: Database connection failed at startup")
    # Don't exit, let the app try to recover

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
            
            # Try primary connection first
            try:
                session = SessionLocal()
                from sqlalchemy import text
                result = session.execute(text("SELECT 1"))
                result.fetchone()
                session.commit()
                db_status = "connected"
                connection_strategy = "primary"
            except Exception as db_e:
                logger.warning(f"Primary health check failed: {db_e}")
                
                # If primary fails, try to reconnect with fallback engine
                try:
                    if session:
                        session.close()
                    
                    # Create a new engine with fallback strategies
                    logger.info("🔄 Attempting health check with fallback connection")
                    fallback_engine = create_engine_with_fallback(DATABASE_URL, 1, 0)
                    
                    if fallback_engine:
                        from sqlalchemy.orm import sessionmaker
                        FallbackSession = sessionmaker(bind=fallback_engine)
                        session = FallbackSession()
                        result = session.execute(text("SELECT 1"))
                        result.fetchone()
                        session.commit()
                        db_status = "connected_fallback"
                        connection_strategy = "fallback"
                        logger.info("✅ Health check successful with fallback connection")
                    else:
                        db_status = f"fallback_failed: {str(db_e)[:50]}"
                        connection_strategy = "failed"
                        
                except Exception as fallback_e:
                    logger.error(f"Fallback health check also failed: {fallback_e}")
                    db_status = f"all_failed: {str(fallback_e)[:30]}"
                    connection_strategy = "all_failed"
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
            is_healthy = db_status in ['connected', 'connected_fallback']
            status_code = 200 if is_healthy else 503
            
            from datetime import datetime, timezone
            return jsonify({
                'status': 'healthy' if is_healthy else 'degraded',
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'database': db_status,
                'connection_strategy': connection_strategy,
                'bot_status': bot_status,
                'uptime_seconds': int((datetime.now(timezone.utc) - datetime.fromisoformat('2025-01-01T00:00:00')).total_seconds()) % 86400,
                'resources': resource_status,
                'ssl_info': 'SSL connection with fallback strategies'
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

                            # Record success in database
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

                            # Record failure in database
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

                        # Record timeout in database
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

                        # Record error in database
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
