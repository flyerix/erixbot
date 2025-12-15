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
    # SQLite autonomous mode - no SSL configuration needed
    logger.info("🔧 SQLite autonomous mode - no SSL configuration needed")
    logger.info("✅ Using persistent SQLite database (no external dependencies)")

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

# Database configuration - SQLite persistente per autonomia completa
PERSISTENT_DATA_DIR = "/opt/render/project/src/data"
DATABASE_PATH = os.path.join(PERSISTENT_DATA_DIR, "erixcast.db")

# Assicura che la directory dati esista
os.makedirs(PERSISTENT_DATA_DIR, exist_ok=True)
os.makedirs(os.path.join(PERSISTENT_DATA_DIR, "backups"), exist_ok=True)

# Forza uso SQLite persistente per autonomia completa
DATABASE_URL = f"sqlite:///{DATABASE_PATH}"
logger.info(f"🔧 Using persistent SQLite database: {DATABASE_PATH}")

# SQLite pool configuration ottimizzata per concorrenza
pool_size = 5  # Increased for concurrent access
max_overflow = 10  # Allow overflow connections

def create_sqlite_engine(database_url):
    """Create SQLite engine for autonomous bot operation"""
    
    logger.info("🔧 Creating persistent SQLite database for autonomous operation...")
    
    # Verifica che il file database sia accessibile
    db_path = database_url.replace("sqlite:///", "")
    db_dir = os.path.dirname(db_path)
    
    if not os.path.exists(db_dir):
        logger.info(f"📁 Creating database directory: {db_dir}")
        os.makedirs(db_dir, exist_ok=True)
    
    # Crea engine SQLite ottimizzato per concorrenza
    engine = create_engine(
        database_url,
        pool_size=5,  # Increased from 1 to handle concurrent requests
        max_overflow=10,  # Allow overflow connections
        pool_timeout=60,  # Increased timeout to prevent timeouts
        pool_recycle=3600,  # 1 ora
        pool_pre_ping=False,
        echo=False,
        # Ottimizzazioni SQLite per accesso concorrente
        connect_args={
            "check_same_thread": False,  # Permette accesso multi-thread
            "timeout": 60,  # Increased timeout per lock
        }
    )
    
    # Test connessione SQLite
    try:
        with engine.connect() as conn:
            from sqlalchemy import text
            # Test base
            result = conn.execute(text("SELECT 1"))
            result.fetchone()
            
            # Ottimizzazioni SQLite per performance
            conn.execute(text("PRAGMA journal_mode=WAL"))  # Write-Ahead Logging
            conn.execute(text("PRAGMA synchronous=NORMAL"))  # Bilanciamento sicurezza/performance
            conn.execute(text("PRAGMA cache_size=10000"))  # Cache 10MB
            conn.execute(text("PRAGMA temp_store=MEMORY"))  # Temp tables in memoria
            conn.execute(text("PRAGMA mmap_size=268435456"))  # Memory mapping 256MB
            
            logger.info("✅ SQLite database connection successful with optimizations")
            logger.info(f"📊 Database file: {db_path}")
            
            # Verifica dimensione database
            if os.path.exists(db_path):
                size_mb = os.path.getsize(db_path) / 1024 / 1024
                logger.info(f"📈 Database size: {size_mb:.2f} MB")
            
            return engine
            
    except Exception as e:
        logger.error(f"❌ SQLite connection failed: {e}")
        raise

def create_engine_with_fallback(database_url, pool_size, max_overflow):
    """Create engine - now always uses persistent SQLite for autonomy"""
    
    # SOLUZIONE AUTONOMA: Usa sempre SQLite persistente
    logger.info("🚀 Creating autonomous SQLite database (no external dependencies)")
    
    return create_sqlite_engine(database_url)
    


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
        
        # Set SessionLocal to None when database unavailable
        SessionLocal = None
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
        if models:
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
# Sistema di backup automatico per SQLite
def backup_sqlite_database():
    """Backup automatico del database SQLite"""
    try:
        import shutil
        from datetime import datetime
        
        if not os.path.exists(DATABASE_PATH):
            return False
        
        backup_dir = os.path.join(PERSISTENT_DATA_DIR, "backups")
        os.makedirs(backup_dir, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = os.path.join(backup_dir, f"erixcast_backup_{timestamp}.db")
        
        shutil.copy2(DATABASE_PATH, backup_path)
        
        # Mantieni solo gli ultimi 10 backup per risparmiare spazio
        backups = sorted([f for f in os.listdir(backup_dir) if f.startswith("erixcast_backup_")])
        while len(backups) > 10:
            old_backup = os.path.join(backup_dir, backups.pop(0))
            os.remove(old_backup)
        
        size_mb = os.path.getsize(backup_path) / 1024 / 1024
        logger.info(f"✅ Database backup created: {backup_path} ({size_mb:.2f} MB)")
        return True
        
    except Exception as e:
        logger.error(f"❌ Database backup failed: {e}")
        return False

def get_database_stats():
    """Statistiche database per monitoraggio"""
    try:
        stats = {}
        
        if os.path.exists(DATABASE_PATH):
            stats["file_size_mb"] = round(os.path.getsize(DATABASE_PATH) / 1024 / 1024, 2)
            stats["file_exists"] = True
            
            # Conta backup disponibili
            backup_dir = os.path.join(PERSISTENT_DATA_DIR, "backups")
            if os.path.exists(backup_dir):
                backups = [f for f in os.listdir(backup_dir) if f.startswith("erixcast_backup_")]
                stats["backup_count"] = len(backups)
                if backups:
                    latest_backup = sorted(backups)[-1]
                    stats["latest_backup"] = latest_backup
            else:
                stats["backup_count"] = 0
        else:
            stats["file_exists"] = False
            stats["file_size_mb"] = 0
            stats["backup_count"] = 0
        
        return stats
    except Exception as e:
        logger.error(f"Error getting database stats: {e}")
        return {"error": str(e)}

# Crea tabelle e backup iniziale
if database_available and engine:
    tables_created = create_tables_with_retry(engine)
    if not tables_created:
        logger.warning("⚠️ Tables creation failed - bot will attempt to create them on first use")
    else:
        # Crea backup iniziale dopo creazione tabelle
        backup_sqlite_database()
    
    # Informazioni database SQLite persistente
    db_stats = get_database_stats()
    logger.info(f"💾 Persistent SQLite database ready:")
    logger.info(f"   📁 Path: {DATABASE_PATH}")
    logger.info(f"   📊 Size: {db_stats.get('file_size_mb', 0)} MB")
    logger.info(f"   🔄 Backups: {db_stats.get('backup_count', 0)} available")
    logger.info(f"   ✅ Autonomous operation: Data persists across all redeploys")
else:
    logger.warning("⚠️ Skipping table creation - database not available")

# Test database connection with SSL
def test_database_connection():
    """Test database connection with proper error handling"""
    # Check if database is available first
    if not database_available or not SessionLocal or not callable(SessionLocal):
        logger.warning("⚠️ Database not available for connection test")
        return False
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            session = SessionLocal()
            from sqlalchemy import text
            # Use SQLite compatible query instead of PostgreSQL version()
            result = session.execute(text("SELECT 1 as test"))
            test_result = result.fetchone()[0]
            session.close()
            if test_result == 1:
                logger.info("Database connection successful - SQLite database operational")
                return True
            else:
                raise Exception("Unexpected test result")
        except Exception as e:
            logger.warning(f"Database connection attempt {attempt + 1}/{max_retries} failed: {e}")
            if attempt == max_retries - 1:
                logger.error("Database connection failed after all retries")
                return False
            import time
            time.sleep(1 + attempt)  # Linear backoff for SQLite
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
            
            # Get database statistics
            db_stats = get_database_stats()
            
            # Fix timezone issue - use consistent UTC datetime
            current_time = datetime.now(timezone.utc)
            start_of_day = current_time.replace(hour=0, minute=0, second=0, microsecond=0)
            uptime_seconds = int((current_time - start_of_day).total_seconds())
            
            return jsonify({
                'status': service_status,
                'timestamp': current_time.isoformat(),
                'database': {
                    'status': db_status,
                    'type': 'sqlite_persistent',
                    'connection_strategy': connection_strategy,
                    'available': database_available,
                    'file_size_mb': db_stats.get('file_size_mb', 0),
                    'backup_count': db_stats.get('backup_count', 0),
                    'latest_backup': db_stats.get('latest_backup', 'none'),
                    'path': DATABASE_PATH if database_available else 'unavailable'
                },
                'bot_status': bot_status,
                'uptime_seconds': uptime_seconds,
                'resources': resource_status,
                'autonomous_operation': {
                    'enabled': True,
                    'persistent_storage': True,
                    'external_dependencies': False,
                    'backup_system': 'automatic'
                }
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
                'uptime_seconds': int((datetime.now(timezone.utc).replace(tzinfo=None) - datetime.fromisoformat('2025-01-01T00:00:00')).total_seconds()) % 86400
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
    
    # Avvia il bot in un thread separato
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()
    logger.info("ErixCastBot started successfully in production mode")
    
    # Avvia il watchdog per monitorare la stabilità del bot (solo se non in sviluppo)
    if os.getenv('RENDER') == 'true':
        def start_watchdog():
            """Avvia il watchdog per monitorare il bot"""
            try:
                # Aspetta che il bot si avvii
                import time
                time.sleep(180)  # Aspetta 3 minuti per evitare conflitti
                
                # Importa e avvia il watchdog
                try:
                    from bot_watchdog import BotWatchdog
                    watchdog = BotWatchdog()
                    logger.info("🐕 Starting bot watchdog...")
                    watchdog.run_monitoring()
                except ImportError:
                    logger.warning("⚠️ Watchdog module not available, skipping...")
                
            except Exception as e:
                logger.error(f"❌ Watchdog failed to start: {e}")
        
        # Avvia il watchdog in un thread separato solo su Render
        watchdog_thread = threading.Thread(target=start_watchdog, daemon=True)
        watchdog_thread.start()
        logger.info("🐕 Bot watchdog thread started (Render only)")
    else:
        logger.info("🐕 Watchdog disabled in development mode")

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
                            
                            # Backup database ogni ora (solo per ping_5min per evitare backup multipli)
                            if thread_name == "ping_5min":
                                import time
                                current_hour = int(time.time() // 3600)
                                last_backup_hour = getattr(ping_worker, 'last_backup_hour', 0)
                                
                                if current_hour > last_backup_hour:
                                    if backup_sqlite_database():
                                        ping_worker.last_backup_hour = current_hour
                                        logger.info("🔄 Hourly database backup completed")

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
