from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import QueuePool
from datetime import datetime, timezone
import os
import logging
import sys

# Configure logging for production
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Environment validation
DATABASE_URL = os.getenv('DATABASE_URL')
if not DATABASE_URL:
    logger.error("DATABASE_URL environment variable is required")
    raise ValueError("DATABASE_URL environment variable is required")

TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
if not TELEGRAM_BOT_TOKEN:
    logger.error("TELEGRAM_BOT_TOKEN environment variable is required")
    raise ValueError("TELEGRAM_BOT_TOKEN environment variable is required")

# Database configuration optimized for Render free tier (512MB RAM limit)
pool_size = int(os.getenv('DATABASE_POOL_SIZE', '3'))  # Ridotto per risparmiare memoria
max_overflow = int(os.getenv('DATABASE_MAX_OVERFLOW', '2'))  # Ridotto per efficienza

engine = create_engine(
    DATABASE_URL,
    poolclass=QueuePool,
    pool_size=pool_size,
    max_overflow=max_overflow,
    pool_timeout=20,  # Ridotto per risposte più rapide
    pool_recycle=900,  # Recycle ogni 15 minuti (più frequente per stabilità)
    pool_pre_ping=True,  # Verifica connessioni prima dell'uso
    echo=False,  # Disabilita logging SQL in produzione
    # Ottimizzazioni per bassa memoria
    connect_args={
        'connect_timeout': 10,
        'read_timeout': 30,
        'write_timeout': 30,
    } if 'postgresql' in DATABASE_URL else {}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Import models directly (with --chdir, the root directory is in Python path)
from models import SessionLocal as ModelsSessionLocal, List, Ticket, TicketMessage, UserNotification, RenewalRequest, TicketFeedback, UserActivity, AuditLog, UserBehavior, Base, create_tables
models = ModelsSessionLocal
models.SessionLocal = SessionLocal

# Create all tables using the centralized function
create_tables(engine)

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
        """Aggressive health check to keep Render service alive"""
        try:
            # Test database connection
            session = SessionLocal()
            from sqlalchemy import text
            session.execute(text("SELECT 1"))
            session.commit()
            session.close()

            # Test bot connectivity (quick test)
            try:
                import asyncio
                # Quick async test without blocking
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

                # Test if bot application exists and is responsive
                from . import bot
                bot_status = "bot_ready" if hasattr(bot, 'application') else "bot_initializing"

                loop.close()
            except:
                bot_status = "bot_check_failed"

            # Get resource status from bot
            resource_status = {}
            try:
                import bot
                if hasattr(bot, 'resource_monitor'):
                    resource_status = bot.resource_monitor.get_resource_status()
            except:
                pass

            return jsonify({
                'status': 'healthy',
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'database': 'connected',
                'bot_status': bot_status,
                'uptime_seconds': int((datetime.now(timezone.utc) - datetime.fromisoformat('2025-01-01T00:00:00')).total_seconds()) % 86400,
                'resources': resource_status
            }), 200
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return jsonify({
                'status': 'unhealthy',
                'error': str(e),
                'timestamp': datetime.now(timezone.utc).isoformat()
            }), 500

    @app.route('/ping')
    def ping():
        """Lightweight ping endpoint to prevent Render sleep"""
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
                render_url = os.environ.get('RENDER_URL', f'http://localhost:{port}')
                endpoint = f"{render_url}/ping"  # Use lightweight ping endpoint
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
                                    endpoint='/ping',
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
                                except:
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
                                    endpoint='/ping',
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
                                except:
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
                                endpoint='/ping',
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
                            except:
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
                                endpoint='/ping',
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
                            except:
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
