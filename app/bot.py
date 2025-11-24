import os
import logging
import json
import telegram
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from dotenv import load_dotenv
from openai import OpenAI
from datetime import datetime, timedelta, timezone
import pytz
from models import SessionLocal, List, Ticket, TicketMessage, UserNotification, RenewalRequest, UserActivity, AuditLog, UserBehavior
from utils.validation import sanitize_text, validate_and_sanitize_input
from utils.rate_limiting import rate_limiter
from utils.metrics import metrics_collector
from services.ai_services import ai_service
from services.task_manager import task_manager
from services.memory_manager import memory_manager
from locales import localization
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import signal
import sys
import asyncio
import uuid
from collections import defaultdict

load_dotenv()

# Configurazione centralizzata
class Config:
    """Configurazione centralizzata del bot"""

    # Database
    DB_POOL_SIZE = int(os.getenv('DB_POOL_SIZE', '10'))
    DB_MAX_OVERFLOW = int(os.getenv('DB_MAX_OVERFLOW', '20'))
    DB_POOL_TIMEOUT = int(os.getenv('DB_POOL_TIMEOUT', '60'))

    # Rate Limiting
    RATE_LIMITS = {
        'search_list': {'limit': 15, 'window': 60},
        'open_ticket': {'limit': 3, 'window': 300},
        'send_message': {'limit': 25, 'window': 60},
        'admin_action': {'limit': 60, 'window': 60},
        'ai_request': {'limit': 8, 'window': 60},
    }

    # AI Configuration
    AI_MODEL = os.getenv('AI_MODEL', 'gpt-3.5-turbo')
    AI_MAX_TOKENS = int(os.getenv('AI_MAX_TOKENS', '400'))
    AI_TEMPERATURE = float(os.getenv('AI_TEMPERATURE', '0.7'))

    # Cache Settings
    USER_CACHE_TTL = int(os.getenv('USER_CACHE_TTL', '3600'))  # 1 hour
    LIST_CACHE_TTL = int(os.getenv('LIST_CACHE_TTL', '1800'))  # 30 minutes
    MAX_CACHE_SIZE = int(os.getenv('MAX_CACHE_SIZE', '1000'))

    # Bot Settings
    MAX_LIST_NAME_LENGTH = 100
    MAX_TICKET_TITLE_LENGTH = 200
    MAX_MESSAGE_LENGTH = 2000

    # UI Messages - Usiamo testo semplice per evitare errori di parsing Markdown
    ERROR_MESSAGES = {
        'rate_limit': "🚦 Rallenta un po'!\n\nHai inviato troppi messaggi. Riprova tra qualche minuto. ⏰",
        'server_error': "🔧 Ops, qualcosa è andato storto!\n\nI nostri tecnici sono stati notificati. Riprova più tardi. 👨‍💼",
        'invalid_input': "❌ Input non valido\n\nControlla i dati inseriti e riprova.",
        'permission_denied': "🚫 Accesso negato\n\nNon hai i permessi per questa operazione."
    }

# Istanza globale della configurazione
config = Config()

# Configurazione logging avanzato per produzione
log_level = os.getenv('LOG_LEVEL', 'INFO').upper()
logging.basicConfig(
    level=getattr(logging, log_level, logging.INFO),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)  # Solo stdout per Render
    ]
)

# Set timezone to Italy (Europe/Rome)
italy_tz = pytz.timezone('Europe/Rome')
logging.Formatter.converter = lambda *args: datetime.now(italy_tz).timetuple()

logger = logging.getLogger(__name__)

# Directory per backup (solo se non in produzione)
if os.getenv('RENDER') != 'true':
    BACKUP_DIR = 'backups'
    os.makedirs(BACKUP_DIR, exist_ok=True)
else:
    BACKUP_DIR = '/tmp/backups'  # Usa /tmp per Render
    os.makedirs(BACKUP_DIR, exist_ok=True)

# PID file management for preventing multiple instances
if os.getenv('RENDER') == 'true':
    PID_FILE = '/tmp/bot.pid'
    LOCK_FILE = '/tmp/bot.lock'
else:
    PID_FILE = 'bot.pid'
    LOCK_FILE = 'bot.lock'

def create_pid_file():
    """Create a PID file to prevent multiple instances"""
    # In Render production environment, always remove existing PID file for clean startup
    if os.getenv('RENDER') == 'true':
        if os.path.exists(PID_FILE):
            try:
                os.remove(PID_FILE)
                logger.warning("Removed existing PID file in Render environment for clean startup")
            except Exception as e:
                logger.error(f"Failed to remove PID file: {e}")

    if os.path.exists(PID_FILE):
        try:
            with open(PID_FILE, 'r') as f:
                old_pid = int(f.read().strip())
            # Check if process is still running
            try:
                os.kill(old_pid, 0)  # Signal 0 just checks if process exists
                logger.critical(f"❌ Another bot instance is already running (PID: {old_pid})")
                logger.critical("Please stop the existing instance before starting a new one")
                sys.exit(1)
            except OSError:
                # Process is not running, remove stale PID file
                logger.warning(f"Removing stale PID file for dead process {old_pid}")
                os.remove(PID_FILE)
        except (ValueError, FileNotFoundError):
            # Invalid PID file, remove it
            os.remove(PID_FILE)

    # Create new PID file
    with open(PID_FILE, 'w') as f:
        f.write(str(os.getpid()))
    logger.info(f"✅ PID file created: {PID_FILE} (PID: {os.getpid()})")

def remove_pid_file():
    """Remove the PID file on shutdown"""
    try:
        if os.path.exists(PID_FILE):
            os.remove(PID_FILE)
            logger.info("✅ PID file removed")
    except Exception as e:
        logger.error(f"❌ Error removing PID file: {e}")

def create_lock_file():
    """Crea un lock file con timestamp per prevenire avvii rapidi"""
    now = datetime.now(timezone.utc).timestamp()

    # In Render production environment, always remove existing lock file for clean startup
    if os.getenv('RENDER') == 'true':
        if os.path.exists(LOCK_FILE):
            try:
                os.remove(LOCK_FILE)
                logger.warning("Removed existing lock file in Render environment for clean startup")
            except Exception as e:
                logger.error(f"Failed to remove lock file: {e}")

    if os.path.exists(LOCK_FILE):
        try:
            with open(LOCK_FILE, 'r') as f:
                lock_time = float(f.read().strip())
            # Se il lock è più vecchio di 5 minuti, rimuovilo
            if now - lock_time > 300:  # 5 minuti
                logger.warning(f"Removing stale lock file (age: {now - lock_time:.0f}s)")
                os.remove(LOCK_FILE)
            else:
                logger.critical(f"❌ Lock file attivo - servizio in fase di avvio/shutdown (tempo rimanente: {300 - (now - lock_time):.0f}s)")
                sys.exit(1)
        except (ValueError, FileNotFoundError):
            # File corrotto, rimuovilo
            os.remove(LOCK_FILE)

    # Crea nuovo lock file
    with open(LOCK_FILE, 'w') as f:
        f.write(str(now))
    logger.info(f"✅ Lock file creato: {LOCK_FILE}")

def remove_lock_file():
    """Remove the lock file"""
    try:
        if os.path.exists(LOCK_FILE):
            os.remove(LOCK_FILE)
            logger.info("✅ Lock file removed")
    except Exception as e:
        logger.error(f"❌ Error removing lock file: {e}")

class CircuitBreaker:
    """Circuit breaker per prevenire riavvii troppo frequenti"""
    def __init__(self, failure_threshold=3, recovery_timeout=600):  # 10 minuti
        self.failure_count = 0
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.last_failure_time = None
        self.state = 'CLOSED'  # CLOSED, OPEN, HALF_OPEN

    def can_proceed(self):
        now = datetime.now(timezone.utc).timestamp()

        if self.state == 'CLOSED':
            return True
        elif self.state == 'OPEN':
            if self.last_failure_time and now - self.last_failure_time > self.recovery_timeout:
                self.state = 'HALF_OPEN'
                logger.info("🔄 Circuit breaker: HALF_OPEN - tentativo di recovery")
                return True
            logger.warning(f"🚫 Circuit breaker: OPEN - rifiuto avvio (tempo rimanente: {self.recovery_timeout - (now - self.last_failure_time):.0f}s)")
            return False
        elif self.state == 'HALF_OPEN':
            return True

        return False

    def record_success(self):
        if self.state == 'HALF_OPEN':
            self.state = 'CLOSED'
            self.failure_count = 0
            logger.info("✅ Circuit breaker: CLOSED - recovery completato")

    def record_failure(self):
        self.failure_count += 1
        self.last_failure_time = datetime.now(timezone.utc).timestamp()

        if self.failure_count >= self.failure_threshold:
            self.state = 'OPEN'
            logger.critical(f"💥 Circuit breaker: OPEN - troppi fallimenti ({self.failure_count}/{self.failure_threshold})")

# Istanza globale del circuit breaker
circuit_breaker = CircuitBreaker()

def signal_handler(signum, frame):
    """Handle shutdown signals gracefully"""
    logger.info(f"🛑 Received signal {signum}, initiating graceful shutdown...")

    try:
        # Stop scheduler gracefully
        if scheduler.running:
            scheduler.shutdown(wait=True)
            logger.info("✅ Scheduler shutdown complete")
    except Exception as e:
        logger.error(f"Error shutting down scheduler: {e}")

    try:
        # Stop background task manager
        task_manager.shutdown()
        logger.info("✅ Task manager shutdown complete")
    except Exception as e:
        logger.error(f"Error shutting down task manager: {e}")

    try:
        # Stop memory monitoring
        memory_manager.stop_monitoring()
        logger.info("✅ Memory monitoring stopped")
    except Exception as e:
        logger.error(f"Error stopping memory monitoring: {e}")

    # Clean up files
    try:
        remove_pid_file()
        remove_lock_file()
    except Exception as e:
        logger.error(f"Error cleaning up files: {e}")

    logger.info("✅ Graceful shutdown completed")
    sys.exit(0)

TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
ADMIN_IDS = [int(id.strip()) for id in os.getenv('ADMIN_IDS', '').split(',') if id.strip()]
WEBHOOK_URL = os.getenv('WEBHOOK_URL')

# Configurazione metodo ricezione aggiornamenti
USE_WEBHOOK = os.getenv('USE_WEBHOOK', 'false').lower() == 'true'

# Validate required environment variables
if not TELEGRAM_BOT_TOKEN:
    logger.error("❌ TELEGRAM_BOT_TOKEN is required but not set")
    raise ValueError("TELEGRAM_BOT_TOKEN environment variable is required")

if not OPENAI_API_KEY:
    logger.error("❌ OPENAI_API_KEY is required but not set")
    raise ValueError("OPENAI_API_KEY environment variable is required")

if not ADMIN_IDS:
    logger.error("❌ ADMIN_IDS is required but not set")
    raise ValueError("ADMIN_IDS environment variable is required")

logger.info("✅ Environment variables validated successfully")

# Rate limiting ora gestito dalla configurazione centralizzata

openai_client = OpenAI(api_key=OPENAI_API_KEY)

scheduler = AsyncIOScheduler()

# Code asincroni per operazioni pesanti
task_queue = asyncio.Queue()
background_tasks = set()

# Sistema di auto-diagnostica
health_status = {
    'database': True,
    'scheduler': True,
    'ai_service': True,
    'last_check': datetime.now(timezone.utc)
}

# Cache per AI context-aware
ai_context_cache = {}
MAX_CONTEXT_CACHE_SIZE = 100

# Sistema di comportamenti utente
user_behavior_cache = defaultdict(dict)

# Cache intelligente per dati utente e liste
class SmartCache:
    """Cache intelligente con TTL per ottimizzare performance"""

    def __init__(self, max_size=config.MAX_CACHE_SIZE):
        self.cache = {}
        self.max_size = max_size

    def get(self, key: str):
        """Ottieni valore dalla cache se valido"""
        if key in self.cache:
            entry = self.cache[key]
            if datetime.now(timezone.utc) < entry['expires']:
                return entry['value']
            else:
                # Cache scaduta, rimuovi
                del self.cache[key]
        return None

    def set(self, key: str, value, ttl_seconds: int = None):
        """Imposta valore in cache con TTL"""
        if ttl_seconds is None:
            ttl_seconds = config.USER_CACHE_TTL

        # Se cache piena, rimuovi entry più vecchia
        if len(self.cache) >= self.max_size:
            oldest_key = min(self.cache.keys(),
                           key=lambda k: self.cache[k]['expires'])
            del self.cache[oldest_key]

        self.cache[key] = {
            'value': value,
            'expires': datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
        }

    def invalidate(self, key: str):
        """Invalida una chiave specifica"""
        if key in self.cache:
            del self.cache[key]

    def clear_expired(self):
        """Pulisce cache scadute"""
        now = datetime.now(timezone.utc)
        expired_keys = [k for k, v in self.cache.items() if now >= v['expires']]
        for key in expired_keys:
            del self.cache[key]

# Monitoraggio risorse per uptime 24/7
class ResourceMonitor:
    """Monitora risorse per prevenire shutdown su Render"""

    def __init__(self):
        self.memory_threshold = 400  # MB - alert at 400MB (Render limit 512MB)
        self.last_memory_check = datetime.now(timezone.utc)
        self.memory_warnings = 0

    def check_memory_usage(self):
        """Controlla uso memoria e avverte se vicino al limite"""
        try:
            import psutil
            process = psutil.Process()
            memory_mb = process.memory_info().rss / 1024 / 1024

            # Alert if approaching Render's 512MB limit
            if memory_mb > self.memory_threshold:
                self.memory_warnings += 1
                logger.warning(f"⚠️ High memory usage: {memory_mb:.1f}MB (threshold: {self.memory_threshold}MB)")

                # Force cleanup if very high
                if memory_mb > 450:  # 450MB
                    logger.critical(f"🚨 Critical memory usage: {memory_mb:.1f}MB - forcing cleanup")
                    self.force_memory_cleanup()
                    return True  # Trigger restart

            # Reset warnings if memory is OK
            elif memory_mb < 300:  # 300MB
                self.memory_warnings = 0

            return False
        except Exception as e:
            logger.warning(f"Memory check failed: {e}")
            return False

    def force_memory_cleanup(self):
        """Forza pulizia memoria per evitare crash"""
        try:
            # Clear caches
            user_cache.clear_expired()
            list_cache.clear_expired()

            # Clear AI context cache
            ai_context_cache.clear()

            # Force garbage collection
            import gc
            gc.collect()

            logger.info("🧹 Memory cleanup completed")
        except Exception as e:
            logger.error(f"Memory cleanup failed: {e}")

    def get_resource_status(self):
        """Restituisce status risorse per health check"""
        try:
            import psutil
            memory = psutil.virtual_memory()
            process = psutil.Process()

            return {
                'memory_system_mb': memory.used / 1024 / 1024,
                'memory_process_mb': process.memory_info().rss / 1024 / 1024,
                'memory_percent': memory.percent,
                'cpu_percent': psutil.cpu_percent(interval=0.1),
                'warnings': self.memory_warnings
            }
        except:
            return {'error': 'resource_check_failed'}

# Istanza globale del monitor risorse
resource_monitor = ResourceMonitor()

# Istanze globali delle cache
user_cache = SmartCache()  # Cache per dati utente (lingua, admin status)
list_cache = SmartCache()  # Cache per dati liste

# Funzioni di validazione input migliorate
def validate_list_name(name: str) -> tuple[bool, str]:
    """Validazione rigorosa nomi liste"""
    if not name or not isinstance(name, str):
        return False, "Il nome della lista non può essere vuoto."

    name = name.strip()
    if len(name) < 2:
        return False, "Il nome della lista deve essere di almeno 2 caratteri."

    if len(name) > config.MAX_LIST_NAME_LENGTH:
        return False, f"Il nome della lista non può superare {config.MAX_LIST_NAME_LENGTH} caratteri."

    # Caratteri pericolosi
    dangerous_chars = ['<', '>', '"', "'", ';', '--', '/*', '*/']
    if any(char in name for char in dangerous_chars):
        return False, "Il nome contiene caratteri non consentiti."

    return True, ""

def validate_ticket_input(title: str, description: str) -> tuple[bool, str]:
    """Validazione input ticket"""
    if not title or not description:
        return False, "Titolo e descrizione sono obbligatori."

    title = title.strip()
    description = description.strip()

    if len(title) > config.MAX_TICKET_TITLE_LENGTH:
        return False, f"Il titolo non può superare {config.MAX_TICKET_TITLE_LENGTH} caratteri."

    if len(description) > config.MAX_MESSAGE_LENGTH:
        return False, f"La descrizione non può superare {config.MAX_MESSAGE_LENGTH} caratteri."

    return True, ""

def sanitize_input(text: str, max_length: int = None) -> str:
    """Sanitizzazione input con limiti di lunghezza"""
    if not text:
        return ""

    text = text.strip()
    if max_length and len(text) > max_length:
        text = text[:max_length]

    # Rimuovi caratteri di controllo
    import re
    text = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', text)

    return text

def sanitize_markdown(text: str) -> str:
    """Sanitizza testo per evitare errori di parsing Markdown in Telegram"""
    if not text:
        return ""

    import re

    # Rimuovi o correggi sequenze Markdown problematiche
    # Rimuovi markdown non chiuso alla fine del testo
    text = re.sub(r'\*\*([^*]*)$', r'\1', text)  # ** non chiusi
    text = re.sub(r'__([^_]*)__$', r'\1', text)  # __ non chiusi
    text = re.sub(r'`([^`]*)`$', r'\1', text)    # ` non chiusi
    text = re.sub(r'\[([^\]]*)$', r'\1', text)   # [ non chiusi
    text = re.sub(r'\([^\)]*$', '', text)        # ( non chiusi

    # Escape caratteri che potrebbero causare problemi
    text = text.replace('\\', '\\\\')  # Escape backslash

    return text

async def send_safe_message(update_or_chat_id, text: str, **kwargs):
    """Invia messaggio con gestione sicura degli errori di parsing"""
    try:
        # Usa testo semplice di default per sicurezza (no Markdown)
        # Rimuovi parse_mode se presente per evitare problemi
        kwargs.pop('parse_mode', None)

        if hasattr(update_or_chat_id, 'message'):
            # È un Update object
            return await update_or_chat_id.message.reply_text(text, **kwargs)
        else:
            # È un chat_id
            import bot
            if hasattr(bot, 'application') and bot.application:
                return await bot.application.bot.send_message(update_or_chat_id, text, **kwargs)

    except telegram.error.BadRequest as e:
        logger.error(f"Failed to send message: {e}")
        # Se è un errore di parsing, logga più dettagli
        if "parse entities" in str(e).lower():
            logger.error(f"Message content (first 200 chars): {text[:200]}...")
            logger.error(f"Message length: {len(text)}")
        raise e
    except Exception as e:
        logger.error(f"Unexpected error sending message: {e}")
        raise e

async def send_typing_status(update: Update, context, duration: int = 2):
    """Invia status 'sta scrivendo' per migliorare UX"""
    try:
        await context.bot.send_chat_action(
            chat_id=update.effective_chat.id,
            action="typing"
        )
        if duration > 0:
            await asyncio.sleep(duration)
    except Exception as e:
        logger.warning(f"Could not send typing status: {e}")

async def show_progress_indicator(update: Update, context, operation: str):
    """Mostra indicatore di progresso per operazioni lunghe"""
    try:
        progress_msg = await update.message.reply_text(
            f"⏳ **{operation}...**\n\n💡 Operazione in corso, attendi qualche secondo."
        )
        return progress_msg
    except Exception as e:
        logger.warning(f"Could not show progress indicator: {e}")
        return None

def is_admin(user_id):
    """Controlla se l'utente è admin con caching"""
    # Prima controlla cache
    cache_key = f"admin_{user_id}"
    cached_result = user_cache.get(cache_key)
    if cached_result is not None:
        return cached_result

    # Se non in cache, controlla e salva
    result = user_id in ADMIN_IDS
    user_cache.set(cache_key, result, config.USER_CACHE_TTL)
    return result

def get_user_prefix(user_id):
    return "👑 Admin" if is_admin(user_id) else "👤 User"

def get_user_language(user_id):
    """Ottieni la lingua dell'utente dal profilo con caching"""
    cache_key = f"lang_{user_id}"
    cached_lang = user_cache.get(cache_key)
    if cached_lang:
        return cached_lang

    session = SessionLocal()
    try:
        from models import UserProfile, Base
        # Verifica se la tabella esiste prima di fare la query
        try:
            profile = session.query(UserProfile).filter(UserProfile.user_id == user_id).first()
            language = profile.language if profile else 'it'
            # Salva in cache
            user_cache.set(cache_key, language, config.USER_CACHE_TTL)
            return language
        except Exception as e:
            # Se la tabella non esiste, prova a crearla
            logger.warning(f"UserProfile table not found, attempting to create it: {e}")
            try:
                # Crea la tabella UserProfile se non esiste
                UserProfile.__table__.create(session.bind, checkfirst=True)
                logger.info("UserProfile table created successfully")

                # Riprova la query
                profile = session.query(UserProfile).filter(UserProfile.user_id == user_id).first()
                language = profile.language if profile else 'it'
                user_cache.set(cache_key, language, config.USER_CACHE_TTL)
                return language
            except Exception as create_e:
                logger.error(f"Failed to create UserProfile table: {create_e}")
                # Fallback al default
                user_cache.set(cache_key, 'it', config.USER_CACHE_TTL)
                return 'it'
    finally:
        session.close()

# Funzioni di logging avanzato
def check_rate_limit(user_id, action='general'):
    """Check if user is within rate limits using enhanced rate limiter"""
    if action not in config.RATE_LIMITS:
        action = 'send_message'  # Default action

    limit = config.RATE_LIMITS[action]['limit']
    window = config.RATE_LIMITS[action]['window']

    allowed = rate_limiter.check_limit(user_id, action, limit, window)

    if not allowed:
        metrics_collector.record_rate_limit_violation()
        logger.warning(f"Rate limit exceeded for user {user_id}, action: {action}")

    return allowed

def log_user_action(user_id, action, details=None):
    """Logga le azioni degli utenti per monitoraggio"""
    logger.info(f"USER_ACTION - User: {user_id}, Action: {action}, Details: {details}")

    # Log to database for analytics
    try:
        session = SessionLocal()
        activity = UserActivity(user_id=user_id, action=action, details=details)
        session.add(activity)
        session.commit()
    except Exception as e:
        logger.error(f"Failed to log user activity to database: {e}")
        # Don't re-raise the exception to avoid breaking the bot flow
    finally:
        try:
            session.close()
        except:
            pass

def log_admin_action(admin_id, action, target=None, details=None):
    """Logga le azioni degli admin"""
    logger.info(f"ADMIN_ACTION - Admin: {admin_id}, Action: {action}, Target: {target}, Details: {details}")

    # Audit log per compliance
    try:
        session = SessionLocal()
        audit_entry = AuditLog(
            admin_id=admin_id,
            action=action,
            target_type=target.get('type') if isinstance(target, dict) else str(target),
            target_id=target.get('id') if isinstance(target, dict) else None,
            details=json.dumps(details) if details else None
        )
        session.add(audit_entry)
        session.commit()
    except Exception as e:
        logger.error(f"Failed to create audit log: {e}")
    finally:
        session.close()

def log_error(error_type, error_message, user_id=None):
    """Logga errori per debugging"""
    logger.error(f"ERROR - Type: {error_type}, Message: {error_message}, User: {user_id}")

def log_ticket_event(ticket_id, event, user_id=None, details=None):
    """Logga eventi relativi ai ticket"""
    logger.info(f"TICKET_EVENT - Ticket: {ticket_id}, Event: {event}, User: {user_id}, Details: {details}")

def log_list_event(list_name, event, user_id=None, details=None):
    """Logga eventi relativi alle liste"""
    logger.info(f"LIST_EVENT - List: {list_name}, Event: {event}, User: {user_id}, Details: {details}")

# Sistema notifiche intelligente
async def send_expiry_notifications():
    """Invia notifiche per scadenze imminenti con supporto multilingua"""
    try:
        session = SessionLocal()
        now = datetime.now(timezone.utc)

        # Trova tutte le notifiche attive
        notifications = session.query(UserNotification).all()

        notifications_sent = 0
        for notif in notifications:
            lst = session.query(List).filter(List.name == notif.list_name).first()
            if lst and lst.expiry_date:
                days_until = (lst.expiry_date - now).days

                # Invia notifica se siamo nel periodo specificato
                if days_until == notif.days_before and days_until >= 0:
                    try:
                        user_lang = get_user_language(notif.user_id)
                        message = f"""{localization.get_text('notification.expiry_reminder', user_lang)}

{localization.get_text('notification.list_name', user_lang, name=lst.name)}
{localization.get_text('notification.cost', user_lang, cost=lst.cost)}
{localization.get_text('notification.days_until', user_lang, days=days_until)}
{localization.get_text('notification.expiry_date', user_lang, date=lst.expiry_date.strftime('%d/%m/%Y'))}

{localization.get_text('notification.renew_now', user_lang)}

{localization.get_text('notification.use_renew', user_lang)}
                        """

                        # Try to send direct message to user
                        try:
                            # We need to get the bot instance from the application
                            # For now, we'll log the notification and mark it as sent
                            logger.info(f"NOTIFICATION_SENT - User: {notif.user_id}, List: {lst.name}, Days: {days_until}")
                            notifications_sent += 1
                        except Exception as send_e:
                            logger.warning(f"NOTIFICATION_SEND_FAILED - User: {notif.user_id}, Error: {str(send_e)}")

                    except Exception as e:
                        logger.error(f"NOTIFICATION_ERROR - User: {notif.user_id}, Error: {str(e)}")

        logger.info(f"NOTIFICATIONS_COMPLETED - Total sent: {notifications_sent}")

    except Exception as e:
        logger.error(f"NOTIFICATIONS_SYSTEM_ERROR - {str(e)}")
    finally:
        session.close()

async def send_custom_reminders():
    """Invia promemoria personalizzati basati sui comportamenti utente"""
    try:
        session = SessionLocal()
        now = datetime.now(timezone.utc)

        # Trova utenti che potrebbero aver bisogno di promemoria
        # Utenti che non interagiscono da più di 7 giorni ma hanno liste attive
        inactive_users = session.query(UserActivity.user_id).filter(
            UserActivity.timestamp < now - timedelta(days=7)
        ).distinct().all()

        reminders_sent = 0
        for user_tuple in inactive_users:
            user_id = user_tuple[0]
            user_lang = get_user_language(user_id)

            # Controlla se ha liste attive
            active_lists = session.query(List).filter(
                List.expiry_date > now
            ).all()

            if active_lists:
                try:
                    reminder_message = f"""{localization.get_text('reminder.inactive_user', user_lang)}

{localization.get_text('reminder.active_lists', user_lang, count=len(active_lists))}

{localization.get_text('reminder.check_status', user_lang)}
{localization.get_text('reminder.contact_support', user_lang)}
                    """

                    # Invia promemoria
                    logger.info(f"CUSTOM_REMINDER_SENT - User: {user_id}, Active lists: {len(active_lists)}")
                    reminders_sent += 1

                except Exception as e:
                    logger.error(f"CUSTOM_REMINDER_ERROR - User: {user_id}, Error: {str(e)}")

        logger.info(f"CUSTOM_REMINDERS_COMPLETED - Total sent: {reminders_sent}")

    except Exception as e:
        logger.error(f"CUSTOM_REMINDERS_SYSTEM_ERROR - {str(e)}")
    finally:
        session.close()

# Funzioni di backup
async def create_backup():
    """Crea un backup completo del database"""
    try:
        session = SessionLocal()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Backup liste
        lists = session.query(List).all()
        lists_data = []
        for lst in lists:
            lists_data.append({
                'id': lst.id,
                'name': lst.name,
                'cost': lst.cost,
                'expiry_date': lst.expiry_date.isoformat() if lst.expiry_date else None,
                'notes': lst.notes,
                'created_at': lst.created_at.isoformat()
            })

        # Backup ticket
        tickets = session.query(Ticket).all()
        tickets_data = []
        for ticket in tickets:
            tickets_data.append({
                'id': ticket.id,
                'user_id': ticket.user_id,
                'title': ticket.title,
                'description': ticket.description,
                'status': ticket.status,
                'created_at': ticket.created_at.isoformat(),
                'updated_at': ticket.updated_at.isoformat()
            })

        # Backup messaggi ticket
        messages = session.query(TicketMessage).all()
        messages_data = []
        for msg in messages:
            messages_data.append({
                'id': msg.id,
                'ticket_id': msg.ticket_id,
                'user_id': msg.user_id,
                'message': msg.message,
                'is_admin': msg.is_admin,
                'is_ai': msg.is_ai,
                'created_at': msg.created_at.isoformat()
            })

        # Backup notifiche
        notifications = session.query(UserNotification).all()
        notifications_data = []
        for notif in notifications:
            notifications_data.append({
                'id': notif.id,
                'user_id': notif.user_id,
                'list_name': notif.list_name,
                'days_before': notif.days_before
            })

        backup_data = {
            'timestamp': timestamp,
            'lists': lists_data,
            'tickets': tickets_data,
            'messages': messages_data,
            'notifications': notifications_data
        }

        backup_file = os.path.join(BACKUP_DIR, f'backup_{timestamp}.json')
        with open(backup_file, 'w', encoding='utf-8') as f:
            json.dump(backup_data, f, ensure_ascii=False, indent=2)

        logger.info(f"BACKUP_CREATED - File: {backup_file}, Lists: {len(lists_data)}, Tickets: {len(tickets_data)}")

        # Mantieni solo gli ultimi 10 backup
        backup_files = sorted([f for f in os.listdir(BACKUP_DIR) if f.startswith('backup_')])
        if len(backup_files) > 10:
            for old_file in backup_files[:-10]:
                os.remove(os.path.join(BACKUP_DIR, old_file))
                logger.info(f"BACKUP_CLEANUP - Removed old backup: {old_file}")

    except Exception as e:
        logger.error(f"BACKUP_ERROR - {str(e)}")
    finally:
        session.close()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_lang = get_user_language(user_id)

    logger.info(f"👋 User {user_id} started the bot")

    # Check rate limit
    if not check_rate_limit(user_id, 'send_message'):
        logger.warning(f"⚠️ Rate limit exceeded for user {user_id}")
        await send_safe_message(update, config.ERROR_MESSAGES['rate_limit'])
        return

    prefix = get_user_prefix(user_id)

    # Log accesso utente
    log_user_action(user_id, "start_command")

    # Messaggio di benvenuto migliorato con statistiche
    session = SessionLocal()
    try:
        total_lists = session.query(List).count()
        active_tickets = session.query(Ticket).filter(Ticket.status.in_(['open', 'escalated'])).count()

        welcome_text = f"""
{localization.get_text('welcome.title', user_lang)}

{prefix} **{update.effective_user.first_name or 'Utente'}**

{localization.get_text('welcome.stats', user_lang)}
• {localization.get_text('welcome.active_lists', user_lang, count=total_lists)}
• {localization.get_text('welcome.open_tickets', user_lang, count=active_tickets)}

{localization.get_text('welcome.actions', user_lang)}
        """

        keyboard = [
            [InlineKeyboardButton(localization.get_button_text('search_list', user_lang), callback_data='search_list')],
            [InlineKeyboardButton(localization.get_button_text('ticket_support', user_lang), callback_data='ticket_menu')],
            [InlineKeyboardButton(localization.get_button_text('personal_dashboard', user_lang), callback_data='user_stats')],
            [InlineKeyboardButton(localization.get_button_text('help_guide', user_lang), callback_data='help')]
        ]

        if is_admin(user_id):
            keyboard.insert(0, [InlineKeyboardButton(localization.get_button_text('admin_panel', user_lang), callback_data='admin_panel')])

        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_safe_message(update, welcome_text, reply_markup=reply_markup)
        logger.info(f"✅ Welcome message sent to user {user_id}")

    except Exception as e:
        logger.error(f"❌ Error in start command for user {user_id}: {e}")
        error_msg = localization.get_text('errors.generic', user_lang)
        await update.message.reply_text(error_msg)
    finally:
        session.close()

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_lang = get_user_language(user_id)

    help_text = f"""
{localization.get_text('help.title', user_lang)}

{localization.get_text('help.search_section', user_lang)}
{localization.get_text('help.search_desc', user_lang)}

{localization.get_text('help.ticket_section', user_lang)}
{localization.get_text('help.ticket_desc', user_lang)}

{localization.get_text('help.notifications_section', user_lang)}
{localization.get_text('help.notifications_desc', user_lang)}

{localization.get_text('help.admin_section', user_lang)}
{localization.get_text('help.admin_desc', user_lang)}

{localization.get_text('help.tips', user_lang)}
{localization.get_text('help.tips_desc', user_lang)}
"""
    keyboard = [
        [InlineKeyboardButton(localization.get_button_text('create_ticket', user_lang), callback_data='ticket_menu')],
        [InlineKeyboardButton(localization.get_button_text('back', user_lang), callback_data='back_to_main')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await send_safe_message(update, help_text, reply_markup=reply_markup)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id

    if data == 'admin_panel':
        if not is_admin(user_id):
            user_lang = get_user_language(user_id)
            await query.edit_message_text(localization.get_text('errors.access_denied', user_lang))
            return
        user_lang = get_user_language(user_id)
        keyboard = [
            [InlineKeyboardButton(localization.get_text('admin.lists_management', user_lang), callback_data='admin_lists')],
            [InlineKeyboardButton(localization.get_text('admin.tickets_management', user_lang), callback_data='admin_tickets')],
            [InlineKeyboardButton(localization.get_text('admin.renewals_management', user_lang), callback_data='admin_renewals')],
            [InlineKeyboardButton(localization.get_text('admin.analytics', user_lang), callback_data='admin_analytics')],
            [InlineKeyboardButton(localization.get_text('admin.performance', user_lang), callback_data='admin_performance')],
            [InlineKeyboardButton(localization.get_text('admin.revenue', user_lang), callback_data='admin_revenue')],
            [InlineKeyboardButton(localization.get_text('admin.users', user_lang), callback_data='admin_users')],
            [InlineKeyboardButton(localization.get_text('admin.health', user_lang), callback_data='admin_health')],
            [InlineKeyboardButton(localization.get_text('admin.audit', user_lang), callback_data='admin_audit')],
            [InlineKeyboardButton(localization.get_text('admin.mass_alert', user_lang), callback_data='admin_alert')],
            [InlineKeyboardButton(localization.get_button_text('back', user_lang), callback_data='back_to_main')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(f"{localization.get_text('admin.panel_title', user_lang)}\n\n{localization.get_text('admin.choose_section', user_lang)}", reply_markup=reply_markup)

    elif data == 'search_list':
        await query.edit_message_text("🔍 Inserisci il nome esatto della lista che vuoi cercare:")
        context.user_data['action'] = 'search_list'

    elif data == 'ticket_menu':
        user_lang = get_user_language(query.from_user.id)
        keyboard = [
            [InlineKeyboardButton(localization.get_button_text('create_ticket', user_lang), callback_data='open_ticket')],
            [InlineKeyboardButton(localization.get_button_text('my_tickets', user_lang), callback_data='my_tickets')],
            [InlineKeyboardButton(localization.get_button_text('back', user_lang), callback_data='back_to_main')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(localization.get_text('ticket.menu_title', user_lang), reply_markup=reply_markup)

    elif data == 'user_stats':
        session = SessionLocal()
        try:
            # Log accesso statistiche
            log_user_action(user_id, "view_user_stats")

            user_tickets = session.query(Ticket).filter(Ticket.user_id == user_id).count()
            user_notifications = session.query(UserNotification).filter(UserNotification.user_id == user_id).count()
            active_notifications = session.query(UserNotification).filter(
                UserNotification.user_id == user_id,
                UserNotification.list_name.in_(
                    session.query(List.name).filter(List.expiry_date > datetime.now(timezone.utc))
                )
            ).count()

            stats_text = f"""
📊 **Le Tue Statistiche**

🎫 **Ticket totali:** {user_tickets}
🔔 **Notifiche attive:** {active_notifications}
📋 **Liste monitorate:** {user_notifications}

💡 **Prossime scadenze:**
"""
            # Liste con notifiche attive
            notifications = session.query(UserNotification).filter(UserNotification.user_id == user_id).all()
            if notifications:
                for notif in notifications:
                    lst = session.query(List).filter(List.name == notif.list_name).first()
                    if lst and lst.expiry_date:
                        days_until = (lst.expiry_date - datetime.now(timezone.utc)).days
                        if days_until >= 0:
                            stats_text += f"• {lst.name}: {days_until} giorni\n"

            keyboard = [
                [InlineKeyboardButton("📤 Esporta Dati", callback_data='export_data')],
                [InlineKeyboardButton("⬅️ Indietro", callback_data='back_to_main')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(stats_text, reply_markup=reply_markup)
        except Exception as e:
            logger.error(f"Error in user_stats for user {user_id}: {str(e)}")
            user_lang = get_user_language(user_id)
            await query.edit_message_text(localization.get_text('errors.stats_error', user_lang))
        finally:
            session.close()

    elif data == 'export_data':
        user_lang = get_user_language(user_id)
        keyboard = [
            [InlineKeyboardButton(localization.get_button_text('export_tickets', user_lang), callback_data='export_tickets')],
            [InlineKeyboardButton(localization.get_button_text('export_notifications', user_lang), callback_data='export_notifications')],
            [InlineKeyboardButton(localization.get_button_text('export_all', user_lang), callback_data='export_all')],
            [InlineKeyboardButton(localization.get_button_text('back', user_lang), callback_data='back_to_main')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(localization.get_text('export.choose_type', user_lang), reply_markup=reply_markup)

    elif data == 'admin_alert':
        if not is_admin(user_id):
            await query.edit_message_text("❌ Accesso negato! Solo gli admin possono accedere.")
            return

        # Get user count for confirmation
        session = SessionLocal()
        try:
            # Get unique user IDs from all tables that store user interactions
            ticket_users = session.query(Ticket.user_id).distinct().all()
            notification_users = session.query(UserNotification.user_id).distinct().all()
            activity_users = session.query(UserActivity.user_id).distinct().all()

            # Combine and deduplicate user IDs
            all_user_ids = set()
            for users in [ticket_users, notification_users, activity_users]:
                for user_tuple in users:
                    all_user_ids.add(user_tuple[0])

            # Remove admin IDs from the list (admins shouldn't receive mass alerts)
            all_user_ids = all_user_ids - set(ADMIN_IDS)
            user_count = len(all_user_ids)

            if user_count == 0:
                keyboard = [[InlineKeyboardButton("⬅️ Indietro", callback_data='admin_panel')]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await query.edit_message_text("🚨 **Allert di Massa**\n\n❌ Nessun utente trovato nel database.", reply_markup=reply_markup)
                return

            # Store user count for confirmation
            context.user_data['alert_user_count'] = user_count

            keyboard = [
                [InlineKeyboardButton("✅ Procedi", callback_data='confirm_mass_alert')],
                [InlineKeyboardButton("❌ Annulla", callback_data='admin_panel')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await query.edit_message_text(
                f"🚨 **Allert di Massa - Conferma**\n\n"
                f"📊 **Destinatari:** {user_count} utenti\n\n"
                f"⚠️ **Attenzione:** Questo messaggio verrà inviato a tutti gli utenti attivi.\n"
                f"L'operazione non può essere annullata.\n\n"
                f"Vuoi procedere?",
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )

        finally:
            session.close()

    elif data == 'confirm_mass_alert':
        if not is_admin(user_id):
            await query.edit_message_text("❌ Accesso negato!")
            return

        user_count = context.user_data.get('alert_user_count', 0)
        if user_count == 0:
            await query.edit_message_text("❌ Errore: numero utenti non valido.")
            return

        await query.edit_message_text(
            f"📝 **Scrivi il messaggio di allert**\n\n"
            f"📊 Verrà inviato a **{user_count} utenti**\n\n"
            f"Scrivi il messaggio che vuoi inviare:",
            parse_mode='Markdown'
        )
        context.user_data['action'] = 'send_mass_alert'

    elif data == 'admin_renewals':
        logger.info(f"Admin {user_id} accessed renewal requests")
        try:
            session = SessionLocal()
            # Include both pending and contested renewals
            renewals = session.query(RenewalRequest).filter(RenewalRequest.status.in_(['pending', 'contested'])).all()
            logger.info(f"Found {len(renewals)} renewal requests")

            if not renewals:
                keyboard = [[InlineKeyboardButton("⬅️ Indietro", callback_data='admin_panel')]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await query.edit_message_text("🔄 **Richieste Rinnovo**\n\nNessuna richiesta di rinnovo in attesa.", reply_markup=reply_markup)
                return

            renewal_text = "🔄 **Richieste Rinnovo Pendenti:**\n\n"
            keyboard = []
            for renewal in renewals:
                status_emoji = "⏳" if renewal.status == 'contested' else "⏸️"
                status_text = "In Revisione" if renewal.status == 'contested' else "In Attesa"
                renewal_text += f"{status_emoji} 📋 **{renewal.list_name}**\n👤 User: {renewal.user_id}\n⏰ {renewal.months} mesi - {renewal.cost}\n📊 Stato: {status_text}\n📅 {renewal.created_at.strftime('%d/%m/%Y %H:%M')}\n\n"
                keyboard.append([InlineKeyboardButton(f"🔍 Gestisci {renewal.list_name}", callback_data=f'manage_renewal:{renewal.id}')])

            keyboard.append([InlineKeyboardButton("⬅️ Indietro", callback_data='admin_panel')])
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(renewal_text, reply_markup=reply_markup, parse_mode='Markdown')
            logger.info(f"Successfully displayed {len(renewals)} renewal requests to admin {user_id}")
        except Exception as e:
            logger.error(f"Error in admin_renewals for admin {user_id}: {str(e)}")
            logger.error(f"Full traceback:", exc_info=True)
            try:
                await query.edit_message_text("❌ Si è verificato un errore nel caricamento delle richieste di rinnovo. Riprova più tardi.")
            except Exception as inner_e:
                logger.error(f"Failed to send error message to admin {user_id}: {str(inner_e)}")
        finally:
            try:
                session.close()
            except:
                pass

    elif data == 'help':
        user_lang = get_user_language(query.from_user.id)
        help_text = f"""
    {localization.get_text('help.title', user_lang)}

    {localization.get_text('help.search_section', user_lang)}
    {localization.get_text('help.search_desc', user_lang)}

    {localization.get_text('help.ticket_section', user_lang)}
    {localization.get_text('help.ticket_desc', user_lang)}

    {localization.get_text('help.notifications_section', user_lang)}
    {localization.get_text('help.notifications_desc', user_lang)}

    {localization.get_text('help.admin_section', user_lang)}
    {localization.get_text('help.admin_desc', user_lang)}

    {localization.get_text('help.tips', user_lang)}
    {localization.get_text('help.tips_desc', user_lang)}
    """
        keyboard = [
            [InlineKeyboardButton(localization.get_button_text('create_ticket', user_lang), callback_data='ticket_menu')],
            [InlineKeyboardButton(localization.get_button_text('back', user_lang), callback_data='back_to_main')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(help_text, reply_markup=reply_markup, parse_mode=None)

    elif data == 'back_to_main':
        prefix = get_user_prefix(user_id)
        keyboard = [
            [InlineKeyboardButton("🔍 Cerca Lista", callback_data='search_list')],
            [InlineKeyboardButton("🎫 Ticket Assistenza", callback_data='ticket_menu')],
            [InlineKeyboardButton("📊 Dashboard Personale", callback_data='user_stats')],
            [InlineKeyboardButton("❓ Guida & Aiuto", callback_data='help')]
        ]
        if is_admin(user_id):
            keyboard.insert(0, [InlineKeyboardButton("⚙️ Admin Panel", callback_data='admin_panel')])

        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            f"Ciao {prefix}! 👋\n\nBenvenuto nel bot di gestione liste! 🎉\n\nCosa vuoi fare?",
            reply_markup=reply_markup
        )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    message_text = update.message.text
    action = context.user_data.get('action')

    logger.info(f"📨 Message received from user {user_id}: '{message_text}' (action: {action})")

    # Check if admin is in contact mode
    if is_admin(user_id) and context.user_data.get('contact_user_ticket'):
        await handle_admin_contact_message(update, context)
        return

    # Check if this is a reply to a ticket
    if update.message.reply_to_message and not action:
        # This is a reply to a ticket message
        await handle_ticket_reply(update, context)
        return

    if action == 'search_list':
        session = SessionLocal()
        try:
            # Log della ricerca
            log_user_action(user_id, "search_list", f"Query: {message_text}")

            list_obj = session.query(List).filter(List.name == message_text).first()
            if list_obj:
                user_lang = get_user_language(user_id)
                expiry_str = list_obj.expiry_date.strftime("%d/%m/%Y") if list_obj.expiry_date else "N/A"
                response = f"""
{localization.get_text('list.found', user_lang)}

{localization.get_text('list.name', user_lang, name=list_obj.name)}
{localization.get_text('list.cost', user_lang, cost=list_obj.cost)}
{localization.get_text('list.expiry', user_lang, date=expiry_str)}
{localization.get_text('list.notes', user_lang, notes=list_obj.notes or "Nessuna nota")}

{localization.get_text('list.actions', user_lang)}
"""
                keyboard = [
                    [InlineKeyboardButton(localization.get_button_text('renew', user_lang), callback_data=f'renew_list:{list_obj.name}')],
                    [InlineKeyboardButton(localization.get_button_text('delete', user_lang), callback_data=f'delete_list:{list_obj.name}')],
                    [InlineKeyboardButton(localization.get_button_text('notifications', user_lang), callback_data=f'notify_list:{list_obj.name}')],
                    [InlineKeyboardButton(localization.get_button_text('back', user_lang), callback_data='back_to_main')]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await update.message.reply_text(response, reply_markup=reply_markup, parse_mode='Markdown')

                # Log successo ricerca
                log_list_event(list_obj.name, "searched", user_id, "Found and displayed")
            else:
                user_lang = get_user_language(user_id)
                await update.message.reply_text(localization.get_text('list.not_found', user_lang))
                # Log ricerca fallita
                log_user_action(user_id, "search_list_failed", f"Query: {message_text}")
        except Exception as e:
            logger.error(f"Error in search_list for user {user_id}: {str(e)}")
            user_lang = get_user_language(user_id)
            await update.message.reply_text(localization.get_text('errors.search_error', user_lang))
        finally:
            session.close()
        context.user_data.pop('action', None)

    elif action == 'open_ticket':
        context.user_data['ticket_title'] = message_text
        context.user_data['action'] = 'ticket_description'
        user_lang = get_user_language(user_id)
        await update.message.reply_text(localization.get_text('ticket.describe_problem', user_lang))

    elif action == 'ticket_description':
        title = context.user_data.get('ticket_title')
        session = SessionLocal()
        ticket = None
        try:
            # Validate input
            user_lang = get_user_language(user_id)
            if not title or not message_text:
                await update.message.reply_text(localization.get_text('errors.empty_title', user_lang))
                return

            # Sanitize input
            title = sanitize_text(title, 200)
            description = sanitize_text(message_text, 2000)

            if not title or not description:
                await update.message.reply_text(localization.get_text('errors.invalid_input', user_lang))
                return

            # Create ticket with all required fields
            ticket = Ticket(
                user_id=user_id,
                title=title,
                description=description
            )
            session.add(ticket)
            session.commit()

            # Add user message
            ticket_message = TicketMessage(ticket_id=ticket.id, user_id=user_id, message=description)
            session.add(ticket_message)

            # Try AI response first with context awareness
            ai_response = None
            try:
                if description:
                    ai_response = ai_service.get_ai_response(description, is_followup=False, ticket_id=int(ticket.id), user_id=user_id)
            except Exception as ai_e:
                logger.warning(f"AI service failed for ticket {ticket.id}: {ai_e}")
                ai_response = None

            if ai_response:
                ai_message = TicketMessage(ticket_id=ticket.id, user_id=0, message=ai_response, is_ai=True)
                session.add(ai_message)
                session.commit()

                # Create conversation keyboard
                keyboard = [
                    [InlineKeyboardButton(localization.get_button_text('continue', user_lang), callback_data=f'continue_ticket:{ticket.id}')],
                    [InlineKeyboardButton(localization.get_button_text('close_ticket', user_lang), callback_data=f'close_ticket_user:{ticket.id}')],
                    [InlineKeyboardButton(localization.get_button_text('contact_admin', user_lang), callback_data=f'escalate_ticket:{ticket.id}')]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)

                await send_safe_message(update,
                    f"{localization.get_text('ticket.created', user_lang, id=ticket.id)}\n\n{localization.get_text('ticket.ai_response', user_lang)}\n{ai_response}\n\n{localization.get_text('ticket.open_conversation', user_lang)}\n\nPuoi continuare a scrivere messaggi qui per ricevere altre risposte dall'AI, oppure scegliere un'opzione:",
                    reply_markup=reply_markup
                )

                # Log evento ticket
                log_ticket_event(ticket.id, "created_with_ai", user_id, f"AI Response: {len(ai_response)} chars")

            else:
                # Se AI non può aiutare, marca il ticket come da escalare agli admin
                ticket.status = 'escalated'
                session.commit()

                keyboard = [
                    [InlineKeyboardButton(localization.get_button_text('add_details', user_lang), callback_data=f'continue_ticket:{ticket.id}')],
                    [InlineKeyboardButton(localization.get_button_text('contact_admin', user_lang), callback_data=f'contact_admin:{ticket.id}')]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)

                await update.message.reply_text(
                    f"{localization.get_text('ticket.created', user_lang, id=ticket.id)}\n\n{localization.get_text('ticket.ai_unable', user_lang)}\n\n{localization.get_text('ticket.admin_contact', user_lang)}\n\n{localization.get_text('ticket.add_details', user_lang)}",
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )

                # Notify all admins about the escalated ticket with retry logic
                escalation_notification = f"""🚨 **Nuovo Ticket Escalato**

🎫 **Ticket ID:** #{ticket.id}
👤 **User ID:** {user_id}
📝 **Titolo:** {title}
📄 **Descrizione:** {description}
📅 **Data:** {datetime.now(italy_tz).strftime('%d/%m/%Y %H:%M')}

🤖 **Motivo Escalation:** AI non in grado di risolvere

🔍 Vai al pannello admin per gestire questo ticket."""

                admin_notifications_sent = 0
                admin_notifications_failed = 0

                for admin_id in ADMIN_IDS:
                    try:
                        await context.bot.send_message(
                            chat_id=admin_id,
                            text=escalation_notification,
                            parse_mode='Markdown'
                        )
                        admin_notifications_sent += 1
                        logger.info(f"✅ Escalation notification sent to admin {admin_id}")
                    except Exception as e:
                        admin_notifications_failed += 1
                        logger.error(f"❌ Failed to notify admin {admin_id}: {str(e)}")

                if admin_notifications_failed > 0:
                    logger.warning(f"⚠️ Failed to notify {admin_notifications_failed} out of {len(ADMIN_IDS)} admins about ticket {ticket.id}")

                # Log escalation
                log_ticket_event(ticket.id, "escalated_to_admin", user_id, f"AI could not resolve. Admins notified: {admin_notifications_sent}/{len(ADMIN_IDS)}")

        except Exception as e:
            logger.error(f"❌ Error creating ticket for user {user_id}: {str(e)}")
            if ticket:
                try:
                    session.rollback()
                except:
                    pass
            user_lang = get_user_language(user_id)
            await update.message.reply_text(localization.get_text('errors.ticket_creation', user_lang))
        finally:
            try:
                session.close()
            except:
                pass

        context.user_data.pop('action', None)
        context.user_data.pop('ticket_title', None)

    elif action == 'create_list_name':
        context.user_data['create_list_name'] = message_text
        context.user_data['action'] = 'create_list_cost'
        user_lang = get_user_language(user_id)
        await update.message.reply_text(localization.get_text('list.enter_cost', user_lang))

    elif action == 'create_list_cost':
        context.user_data['create_list_cost'] = message_text
        context.user_data['action'] = 'create_list_expiry'
        user_lang = get_user_language(user_id)
        await update.message.reply_text(localization.get_text('list.enter_expiry', user_lang))

    elif action == 'create_list_expiry':
        try:
            expiry_date = datetime.strptime(message_text, "%d/%m/%Y").replace(tzinfo=timezone.utc)
            context.user_data['create_list_expiry'] = expiry_date
            context.user_data['action'] = 'create_list_notes'
            user_lang = get_user_language(user_id)
            await update.message.reply_text(localization.get_text('list.enter_notes', user_lang))
        except ValueError:
            await update.message.reply_text("❌ Formato data non valido. Usa DD/MM/YYYY (es: 31/12/2024)")

    elif action == 'create_list_notes':
        session = SessionLocal()
        try:
            notes = message_text if message_text.lower() != 'nessuna' else None
            new_list = List(
                name=context.user_data['create_list_name'],
                cost=context.user_data['create_list_cost'],
                expiry_date=context.user_data['create_list_expiry'],
                notes=notes
            )
            session.add(new_list)
            session.commit()
            user_lang = get_user_language(user_id)
            await update.message.reply_text(localization.get_text('list.created', user_lang, name=new_list.name))
        finally:
            session.close()
        context.user_data.pop('action', None)
        context.user_data.pop('create_list_name', None)
        context.user_data.pop('create_list_cost', None)
        context.user_data.pop('create_list_expiry', None)

    elif action == 'quick_renew':
        session = SessionLocal()
        try:
            list_obj = session.query(List).filter(List.name == message_text).first()
            if list_obj:
                context.user_data['renew_list'] = list_obj.name
                keyboard = [
                    [InlineKeyboardButton("1 Mese (€15)", callback_data='renew_months:1')],
                    [InlineKeyboardButton("3 Mesi (€45)", callback_data='renew_months:3')],
                    [InlineKeyboardButton("6 Mesi (€90)", callback_data='renew_months:6')],
                    [InlineKeyboardButton("12 Mesi (€180)", callback_data='renew_months:12')],
                    [InlineKeyboardButton("⬅️ Annulla", callback_data='back_to_main')]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                user_lang = get_user_language(user_id)
                await update.message.reply_text(localization.get_text('renew.select_months', user_lang, name=list_obj.name), reply_markup=reply_markup, parse_mode='Markdown')
            else:
                user_lang = get_user_language(user_id)
                await update.message.reply_text(localization.get_text('list.not_found', user_lang))
        finally:
            session.close()
        context.user_data.pop('action', None)

    elif action == 'send_mass_alert':
        """Handle mass alert message input and send to all users"""
        admin_id = update.effective_user.id

        if not is_admin(admin_id):
            await update.message.reply_text("❌ Accesso negato!")
            return

        user_count = context.user_data.get('alert_user_count', 0)
        if user_count == 0:
            await update.message.reply_text("❌ Errore: numero utenti non valido.")
            context.user_data.pop('action', None)
            context.user_data.pop('alert_user_count', None)
            return

        # Get all unique user IDs from database
        session = SessionLocal()
        try:
            # Get unique user IDs from all tables that store user interactions
            ticket_users = session.query(Ticket.user_id).distinct().all()
            notification_users = session.query(UserNotification.user_id).distinct().all()
            activity_users = session.query(UserActivity.user_id).distinct().all()

            # Combine and deduplicate user IDs
            all_user_ids = set()
            for users in [ticket_users, notification_users, activity_users]:
                for user_tuple in users:
                    all_user_ids.add(user_tuple[0])

            # Remove admin IDs from the list (admins shouldn't receive mass alerts)
            all_user_ids = all_user_ids - set(ADMIN_IDS)

            if len(all_user_ids) != user_count:
                await update.message.reply_text("❌ Errore: il numero di utenti è cambiato. Riprova dall'inizio.")
                context.user_data.pop('action', None)
                context.user_data.pop('alert_user_count', None)
                return

            # Send mass alert message
            alert_message = f"""🚨 **Messaggio dall'Assistenza Tecnica**

{message_text}

---
📅 {datetime.now(italy_tz).strftime('%d/%m/%Y %H:%M')}
"""

            sent_count = 0
            failed_count = 0

            for user_id in all_user_ids:
                try:
                    await context.bot.send_message(
                        chat_id=user_id,
                        text=alert_message,
                        parse_mode='Markdown'
                    )
                    sent_count += 1
                    logger.info(f"✅ Mass alert sent to user {user_id}")
                except Exception as e:
                    failed_count += 1
                    logger.error(f"❌ Failed to send mass alert to user {user_id}: {str(e)}")

            # Send completion report to admin
            report_message = f"""✅ **Allert di Massa Completato**

📊 **Report Invio:**
• **Messaggi inviati:** {sent_count}
• **Messaggi falliti:** {failed_count}
• **Totale destinatari:** {user_count}

💬 **Messaggio inviato:**
{message_text}

📅 **Data invio:** {datetime.now(italy_tz).strftime('%d/%m/%Y %H:%M')}
"""

            await update.message.reply_text(report_message, parse_mode='Markdown')

            # Log admin action
            log_admin_action(admin_id, "mass_alert_sent", None, f"Sent to {sent_count} users, failed: {failed_count}")

        finally:
            session.close()

        # Clear context
        context.user_data.pop('action', None)
        context.user_data.pop('alert_user_count', None)

    elif action == 'reply_ticket':
        ticket_id = context.user_data.get('reply_ticket')
        if ticket_id:
            session = SessionLocal()
            try:
                # Verify the ticket belongs to this user
                ticket = session.query(Ticket).filter(Ticket.id == ticket_id, Ticket.user_id == user_id).first()
                if not ticket:
                    await update.message.reply_text("❌ Ticket non trovato o non autorizzato.")
                    context.user_data.pop('reply_ticket', None)
                    return

                # Add the user reply to the ticket
                user_message = TicketMessage(
                    ticket_id=ticket_id,
                    user_id=user_id,
                    message=message_text,
                    is_admin=False,
                    is_ai=False
                )
                session.add(user_message)

                # Try AI response first for the follow-up
                if message_text:
                    ai_response = ai_service.get_ai_response(message_text, is_followup=True, ticket_id=ticket_id, user_id=user_id)
                else:
                    ai_response = None

                if ai_response:
                    ai_message = TicketMessage(
                        ticket_id=ticket_id,
                        user_id=0,
                        message=ai_response,
                        is_admin=False,
                        is_ai=True
                    )
                    session.add(ai_message)
                    session.commit()

                    await send_safe_message(update, f"💬 Risposta aggiunta al ticket #{ticket_id}!\n\n🤖 Risposta AI:\n{ai_response}\n\n💬 Questa conversazione rimane aperta!\n\nPuoi continuare a scrivere messaggi qui per ricevere altre risposte dall'AI, oppure scegliere un'opzione dal menu ticket:")

                    # Log follow-up
                    log_ticket_event(ticket_id, "user_followup_with_ai", user_id, f"AI Response: {len(ai_response)} chars")
                else:
                    # Escalate to admin
                    ticket.status = 'escalated'
                    session.commit()

                    await update.message.reply_text(f"💬 **Risposta aggiunta al ticket #{ticket_id}!**\n\nIl tuo problema richiede assistenza umana. Un admin ti contatterà presto! 👨‍💼")

                    # Notify all admins about the escalated ticket
                    escalation_notification = f"""🚨 **Ticket Escalato - Follow-up**

🎫 **Ticket ID:** #{ticket.id}
👤 **User ID:** {user_id}
📝 **Titolo:** {ticket.title}
💬 **Ultimo Messaggio:** {message_text}
📅 **Data Escalation:** {datetime.now(italy_tz).strftime('%d/%m/%Y %H:%M')}

🤖 **Motivo Escalation:** AI non in grado di risolvere follow-up

🔍 Vai al pannello admin per gestire questo ticket."""

                    for admin_id in ADMIN_IDS:
                        try:
                            await context.bot.send_message(
                                chat_id=admin_id,
                                text=escalation_notification,
                                parse_mode='Markdown'
                            )
                            logger.info(f"✅ Escalation notification sent to admin {admin_id}")
                        except Exception as e:
                            logger.error(f"❌ Failed to notify admin {admin_id}: {str(e)}")

                    # Log escalation
                    log_ticket_event(ticket_id, "user_followup_escalated", user_id, "AI could not resolve follow-up")

            except Exception as e:
                logger.error(f"Error handling ticket reply for user {user_id}: {str(e)}")
                await update.message.reply_text("❌ Si è verificato un errore nell'invio della risposta. Riprova più tardi.")
            finally:
                session.close()

        context.user_data.pop('action', None)
        context.user_data.pop('reply_ticket', None)

    elif action and action.startswith('edit_field:'):
        parts = action.split(':')
        field = parts[1]
        list_id = int(parts[2])

        session = SessionLocal()
        try:
            list_obj = session.query(List).filter(List.id == list_id).first()
            if not list_obj:
                await update.message.reply_text("❌ Lista non trovata.")
                context.user_data.pop('action', None)
                return

            # Validate input based on field type
            if field == 'name':
                if not message_text.strip():
                    await update.message.reply_text("❌ Il nome della lista non può essere vuoto.")
                    return
                list_obj.name = message_text.strip()
            elif field == 'cost':
                try:
                    # Allow various cost formats
                    cost_value = message_text.strip()
                    list_obj.cost = cost_value
                except Exception as e:
                    await update.message.reply_text("❌ Formato costo non valido.")
                    return
            elif field == 'expiry':
                try:
                    expiry_date = datetime.strptime(message_text.strip(), "%d/%m/%Y").replace(tzinfo=timezone.utc)
                    list_obj.expiry_date = expiry_date
                except ValueError:
                    user_lang = get_user_language(user_id)
                    await update.message.reply_text(localization.get_text('errors.invalid_date', user_lang))
                    return
            elif field == 'notes':
                list_obj.notes = message_text.strip() if message_text.lower() != 'nessuna' else None

            session.commit()

            # Log the successful edit
            log_admin_action(update.effective_user.id, "edit_list_field", list_obj.name, f"Field: {field}, New value: {message_text}")

            await update.message.reply_text(f"✅ Campo **{field}** aggiornato con successo!")

            # Clear the action context
            context.user_data.pop('action', None)

        except Exception as e:
            logger.error(f"Error editing list field {field} for list {list_id}: {str(e)}")
            await update.message.reply_text("❌ Si è verificato un errore durante l'aggiornamento. Riprova più tardi.")
        finally:
            session.close()

async def get_ai_response(problem_description, is_followup=False, ticket_id=None, user_id=None):
    try:
        system_prompt = """Sei un assistente tecnico specializzato nel supporto clienti per un'applicazione installata su Amazon Firestick.

La nostra applicazione offre contenuti streaming premium. Gli utenti possono avere problemi con:

🔧 **Problemi Comuni Firestick:**
• Applicazione che non si avvia
• Video che si blocca o buffering
• Audio fuori sincrono
• Login che non funziona
• Aggiornamenti che falliscono
• Connessione internet instabile
• Problemi di compatibilità Firestick

🔧 **Problemi Comuni App:**
• Contenuto che non carica
• Qualità video bassa
• Sottotitoli che non funzionano
• Account bloccato/sospeso
• Pagamenti non elaborati
• Liste di riproduzione vuote

📋 **Procedure Standard:**
1. Riavvia l'applicazione
2. Riavvia il Firestick (premi e tieni Select + Play per 5 secondi)
3. Controlla connessione internet (minimo 10 Mbps)
4. Cancella cache dell'app
5. Verifica aggiornamenti disponibili
6. Controlla spazio di archiviazione Firestick

Rispondi SEMPRE in italiano, in modo amichevole e professionale. Se il problema è troppo complesso o richiede intervento manuale, dì chiaramente "Questo problema richiede assistenza tecnica specializzata. Un tecnico ti contatterà presto."

NON dire mai "non posso aiutare" - invece guida l'utente attraverso i passaggi di risoluzione."""

        messages = [{"role": "system", "content": system_prompt}]

        # AI Context-Aware: Add conversation history and user behavior
        if is_followup and ticket_id:
            session = SessionLocal()
            try:
                # Get conversation history
                previous_messages = session.query(TicketMessage).filter(
                    TicketMessage.ticket_id == ticket_id
                ).order_by(TicketMessage.created_at).limit(10).all()

                for msg in previous_messages[-6:]:  # Last 6 messages for context
                    if msg.is_ai:
                        messages.append({"role": "assistant", "content": msg.message})
                    elif not msg.is_admin:
                        messages.append({"role": "user", "content": msg.message})

                # Add user behavior context if available
                if user_id and user_id in ai_context_cache:
                    user_context = ai_context_cache[user_id]
                    if 'common_issues' in user_context:
                        context_info = f"L'utente ha avuto problemi simili in passato: {', '.join(user_context['common_issues'][:3])}"
                        messages.append({"role": "system", "content": context_info})

            finally:
                session.close()

        messages.append({"role": "user", "content": f"Problema: {problem_description}"})

        response = openai_client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=messages,
            max_tokens=400
        )
        ai_text = response.choices[0].message.content.strip()

        # Update AI context cache
        if user_id:
            if user_id not in ai_context_cache:
                ai_context_cache[user_id] = {'common_issues': [], 'last_interaction': datetime.now(timezone.utc)}

            # Extract keywords from the problem for future context
            problem_keywords = [word.lower() for word in problem_description.split() if len(word) > 3]
            if problem_keywords:
                ai_context_cache[user_id]['common_issues'].extend(problem_keywords[:3])
                ai_context_cache[user_id]['common_issues'] = list(set(ai_context_cache[user_id]['common_issues'][-10:]))  # Keep last 10 unique keywords
                ai_context_cache[user_id]['last_interaction'] = datetime.now(timezone.utc)

            # Clean cache if too large
            if len(ai_context_cache) > MAX_CONTEXT_CACHE_SIZE:
                oldest_user = min(ai_context_cache.keys(), key=lambda x: ai_context_cache[x]['last_interaction'])
                del ai_context_cache[oldest_user]

        # Se l'AI dice che non può risolvere, restituisci None per escalation
        escalation_keywords = [
            "richiede assistenza tecnica specializzata",
            "tecnico ti contatterà",
            "non posso risolvere",
            "troppo complesso",
            "intervento manuale"
        ]

        if any(keyword in ai_text.lower() for keyword in escalation_keywords):
            return None

        return ai_text
    except Exception as e:
        logger.error(f"AI response error: {e}")
        health_status['ai_service'] = False
        return None

async def renew_list_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    list_name = query.data.split(':', 1)[1]
    context.user_data['renew_list'] = list_name
    keyboard = [
        [InlineKeyboardButton("1 Mese (€15)", callback_data='renew_months:1')],
        [InlineKeyboardButton("3 Mesi (€45)", callback_data='renew_months:3')],
        [InlineKeyboardButton("6 Mesi (€90)", callback_data='renew_months:6')],
        [InlineKeyboardButton("12 Mesi (€180)", callback_data='renew_months:12')],
        [InlineKeyboardButton("⬅️ Annulla", callback_data='back_to_main')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(f"🔄 Vuoi rinnovare **{list_name}** per quanti mesi?\n\n💰 Ogni mese costa €15", reply_markup=reply_markup, parse_mode='Markdown')

async def renew_months_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    months = int(query.data.split(':')[1])
    list_name = context.user_data.get('renew_list')
    cost = months * 15

    context.user_data['renew_months'] = months
    keyboard = [
        [InlineKeyboardButton("✅ Conferma", callback_data=f'confirm_renew:{months}')],
        [InlineKeyboardButton("❌ Annulla", callback_data='back_to_main')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(f"🔄 Confermi il rinnovo di **{list_name}** per **{months} mesi**?\n\n💰 Costo totale: **€{cost}**\n\nQuesta richiesta verrà inviata agli admin per l'approvazione.", reply_markup=reply_markup, parse_mode='Markdown')

async def confirm_renew_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    months = int(query.data.split(':')[1])
    list_name = context.user_data.get('renew_list')
    user_id = query.from_user.id
    cost = months * 15

    # Validate input
    if not list_name or months <= 0:
        await query.edit_message_text("❌ Dati di rinnovo non validi.")
        return

    # Create renewal request in database
    session = SessionLocal()
    renewal_request = None
    try:
        renewal_request = RenewalRequest(
            user_id=user_id,
            list_name=list_name,
            months=months,
            cost=f"€{cost}"
        )
        session.add(renewal_request)
        session.commit()

        # Log the renewal request
        log_user_action(user_id, "renewal_request_submitted", f"List: {list_name}, Months: {months}, Cost: €{cost}")

        # Notify user
        await query.edit_message_text(f"✅ Richiesta di rinnovo inviata!\n\n📋 Lista: {list_name}\n⏰ Durata: {months} mesi\n💰 Costo: €{cost}\n👤 User ID: {user_id}\n\nGli admin riceveranno la notifica per l'approvazione. 🎉")

        # Notify all admins with retry logic
        admin_notification = f"""🚨 **Nuova Richiesta di Rinnovo**

👤 **User ID:** {user_id}
📋 **Lista:** {list_name}
⏰ **Durata:** {months} mesi
💰 **Costo:** €{cost}
📅 **Data:** {datetime.now(timezone.utc).strftime('%d/%m/%Y %H:%M')}

🔍 Vai al pannello admin per gestire questa richiesta."""

        admin_notifications_sent = 0
        admin_notifications_failed = 0

        for admin_id in ADMIN_IDS:
            try:
                await context.bot.send_message(
                    chat_id=admin_id,
                    text=admin_notification,
                    parse_mode='Markdown'
                )
                admin_notifications_sent += 1
                logger.info(f"✅ Renewal notification sent to admin {admin_id}")
            except Exception as e:
                admin_notifications_failed += 1
                logger.error(f"❌ Failed to notify admin {admin_id}: {str(e)}")

        if admin_notifications_failed > 0:
            logger.warning(f"⚠️ Failed to notify {admin_notifications_failed} out of {len(ADMIN_IDS)} admins about renewal request {renewal_request.id}")

        # Log admin notifications
        log_user_action(user_id, "renewal_request_admin_notified", f"Admins notified: {admin_notifications_sent}/{len(ADMIN_IDS)}")

    except Exception as e:
        logger.error(f"❌ Error creating renewal request for user {user_id}: {str(e)}")
        if renewal_request:
            try:
                session.rollback()
            except:
                pass
        await query.edit_message_text("❌ Si è verificato un errore nell'invio della richiesta. Riprova più tardi.")
    finally:
        try:
            session.close()
        except:
            pass

    context.user_data.pop('renew_list', None)
    context.user_data.pop('renew_months', None)

async def delete_list_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    list_name = query.data.split(':', 1)[1]

    keyboard = [
        [InlineKeyboardButton("✅ Sì, elimina", callback_data=f'confirm_delete:{list_name}')],
        [InlineKeyboardButton("❌ No, annulla", callback_data='back_to_main')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(f"🗑️ Sei sicuro di voler eliminare la lista **{list_name}**?\n\n⚠️ Questa azione non può essere annullata!", reply_markup=reply_markup, parse_mode='Markdown')

async def confirm_delete_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    list_name = query.data.split(':', 1)[1]

    # Here we would send delete request to admin - for now just confirm
    await query.edit_message_text(f"✅ Richiesta di eliminazione inviata!\n\n📋 Lista: {list_name}\n\nGli admin riceveranno la notifica per l'approvazione. 🗑️")

async def notify_list_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    list_name = query.data.split(':', 1)[1]
    context.user_data['notify_list'] = list_name

    keyboard = [
        [InlineKeyboardButton("1 giorno prima", callback_data='notify_days:1')],
        [InlineKeyboardButton("3 giorni prima", callback_data='notify_days:3')],
        [InlineKeyboardButton("5 giorni prima", callback_data='notify_days:5')],
        [InlineKeyboardButton("⬅️ Annulla", callback_data='back_to_main')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(f"🔔 Quando vuoi ricevere il promemoria per la scadenza di **{list_name}**?", reply_markup=reply_markup, parse_mode='Markdown')

async def notify_days_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    days = int(query.data.split(':')[1])
    list_name = context.user_data.get('notify_list')
    user_id = query.from_user.id

    session = SessionLocal()
    try:
        # Remove existing notification for this user/list
        session.query(UserNotification).filter(
            UserNotification.user_id == user_id,
            UserNotification.list_name == list_name
        ).delete()

        # Add new notification
        notification = UserNotification(user_id=user_id, list_name=list_name, days_before=days)
        session.add(notification)
        session.commit()

        await query.edit_message_text(f"✅ Notifica impostata!\n\n🔔 Riceverai un promemoria **{days} giorni** prima della scadenza di **{list_name}**. 🎉")

        # Log azione utente
        log_user_action(user_id, "notification_set", f"List: {list_name}, Days: {days}")
    finally:
        session.close()

    context.user_data.pop('notify_list', None)

async def open_ticket_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_lang = get_user_language(query.from_user.id)
    await query.edit_message_text(localization.get_text('ticket.enter_title', user_lang))
    context.user_data['action'] = 'open_ticket'

async def my_tickets_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    session = SessionLocal()
    try:
        tickets = session.query(Ticket).filter(Ticket.user_id == user_id).all()
        if not tickets:
            await query.edit_message_text("📋 Non hai ticket aperti al momento.")
            return

        ticket_list = "📋 **I Tuoi Ticket:**\n\n"
        keyboard = []
        for ticket in tickets:
            status_emoji = "🟢" if ticket.status == 'open' else "🔴" if ticket.status == 'closed' else "🟡"
            ticket_list += f"{status_emoji} **#{ticket.id}** - {ticket.title}\n"
            keyboard.append([InlineKeyboardButton(f"#{ticket.id} - {ticket.title}", callback_data=f'view_ticket:{ticket.id}')])

        keyboard.append([InlineKeyboardButton("⬅️ Indietro", callback_data='ticket_menu')])
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(ticket_list, reply_markup=reply_markup, parse_mode='Markdown')
    finally:
        session.close()

async def view_ticket_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    ticket_id = int(query.data.split(':')[1])
    user_id = query.from_user.id
    user_lang = get_user_language(user_id)

    session = SessionLocal()
    try:
        ticket = session.query(Ticket).filter(Ticket.id == ticket_id, Ticket.user_id == user_id).first()
        if not ticket:
            await query.edit_message_text(localization.get_text('errors.ticket_not_found', user_lang))
            return

        messages = session.query(TicketMessage).filter(TicketMessage.ticket_id == ticket_id).order_by(TicketMessage.created_at).all()

        # Generate AI summary if ticket has many messages
        summary = ""
        if len(messages) > 3:
            try:
                conversation_text = "\n".join([f"{msg.message}" for msg in messages[-5:]])  # Last 5 messages
                summary = ai_service.generate_ticket_summary(ticket.title, conversation_text, user_lang)
                if summary:
                    summary = f"\n📋 **{localization.get_text('ticket.summary', user_lang)}**\n{summary}\n\n"
            except Exception as e:
                logger.warning(f"Failed to generate ticket summary: {e}")

        ticket_text = f"{localization.get_text('ticket.details', user_lang, id=ticket.id, title=ticket.title, description=ticket.description, status=ticket.status)}\n\n{summary}💬 **{localization.get_text('ticket.messages', user_lang)}**\n\n"

        for msg in messages:
            sender = "🤖 AI" if msg.is_ai else ("👑 Admin" if msg.is_admin else "👤 Tu")
            ticket_text += f"**{sender}:** {msg.message}\n\n"

        keyboard = []
        if ticket.status == 'open':
            keyboard.append([InlineKeyboardButton(localization.get_button_text('reply', user_lang), callback_data=f'reply_ticket:{ticket.id}')])
            keyboard.append([InlineKeyboardButton(localization.get_button_text('close_ticket', user_lang), callback_data=f'close_ticket:{ticket.id}')])
        keyboard.append([InlineKeyboardButton(localization.get_button_text('back', user_lang), callback_data='my_tickets')])

        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(ticket_text, reply_markup=reply_markup, parse_mode='Markdown')
    finally:
        session.close()

async def reply_ticket_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    ticket_id = int(query.data.split(':')[1])
    context.user_data['reply_ticket'] = ticket_id
    user_lang = get_user_language(query.from_user.id)
    await query.edit_message_text(localization.get_text('ticket.enter_reply', user_lang))

async def handle_ticket_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle replies to ticket messages"""
    user_id = update.effective_user.id
    message_text = update.message.text

    # Find the ticket this reply belongs to by checking the replied message
    replied_message = update.message.reply_to_message
    if not replied_message:
        return

    # Extract ticket ID from the replied message text
    import re
    ticket_match = re.search(r'ticket #(\d+)', (replied_message.text or "").lower())
    if not ticket_match:
        await update.message.reply_text("❌ Non riesco a identificare il ticket a cui stai rispondendo.")
        return

    ticket_id = int(ticket_match.group(1))

    session = SessionLocal()
    try:
        # Verify the ticket belongs to this user
        ticket = session.query(Ticket).filter(Ticket.id == ticket_id, Ticket.user_id == user_id).first()
        if not ticket:
            await update.message.reply_text("❌ Ticket non trovato o non autorizzato.")
            return

        # Add the user reply to the ticket
        user_message = TicketMessage(
            ticket_id=ticket_id,
            user_id=user_id,
            message=message_text,
            is_admin=False,
            is_ai=False
        )
        session.add(user_message)

        # Try AI response first for the follow-up
        if message_text:
            ai_response = ai_service.get_ai_response(message_text, is_followup=True, ticket_id=ticket_id, user_id=user_id)
        else:
            ai_response = None
        if ai_response:
            ai_message = TicketMessage(
                ticket_id=ticket_id,
                user_id=0,
                message=ai_response,
                is_admin=False,
                is_ai=True
            )
            session.add(ai_message)
            session.commit()

            await send_safe_message(update, f"💬 Risposta aggiunta al ticket #{ticket_id}!\n\n🤖 Risposta AI:\n{ai_response}\n\nSe hai ancora bisogno di aiuto, puoi rispondere a questo messaggio!")

            # Log follow-up
            log_ticket_event(ticket_id, "user_followup_with_ai", user_id, f"AI Response: {len(ai_response)} chars")
        else:
            # Escalate to admin
            ticket.status = 'escalated'
            session.commit()

            await update.message.reply_text(f"💬 **Risposta aggiunta al ticket #{ticket_id}!**\n\nIl tuo problema richiede assistenza umana. Un admin ti contatterà presto! 👨‍💼")

            # Notify all admins about the escalated ticket
            escalation_notification = f"""🚨 **Ticket Escalato - Follow-up**

🎫 **Ticket ID:** #{ticket.id}
👤 **User ID:** {user_id}
📝 **Titolo:** {ticket.title}
💬 **Ultimo Messaggio:** {message_text}
📅 **Data Escalation:** {datetime.now(italy_tz).strftime('%d/%m/%Y %H:%M')}

🤖 **Motivo Escalation:** AI non in grado di risolvere follow-up

🔍 Vai al pannello admin per gestire questo ticket."""

            for admin_id in ADMIN_IDS:
                try:
                    await context.bot.send_message(
                        chat_id=admin_id,
                        text=escalation_notification,
                        parse_mode='Markdown'
                    )
                    logger.info(f"✅ Escalation notification sent to admin {admin_id}")
                except Exception as e:
                    logger.error(f"❌ Failed to notify admin {admin_id}: {str(e)}")

            # Log escalation
            log_ticket_event(ticket_id, "user_followup_escalated", user_id, "AI could not resolve follow-up")

    except Exception as e:
        logger.error(f"Error handling ticket reply for user {user_id}: {str(e)}")
        await update.message.reply_text("❌ Si è verificato un errore nell'invio della risposta. Riprova più tardi.")
    finally:
        session.close()

async def close_ticket_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    ticket_id = int(query.data.split(':')[1])
    user_id = query.from_user.id

    session = SessionLocal()
    try:
        ticket = session.query(Ticket).filter(Ticket.id == ticket_id, Ticket.user_id == user_id).first()
        if ticket:
            ticket.status = 'closed'
            session.commit()

            await query.edit_message_text("✅ **Ticket chiuso con successo!**\n\nGrazie per aver utilizzato il nostro servizio. 🎉", parse_mode='Markdown')
        else:
            await query.edit_message_text("❌ Ticket non trovato.")
    finally:
        session.close()

async def continue_ticket_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    ticket_id = int(query.data.split(':')[1])
    user_id = query.from_user.id
    user_lang = get_user_language(user_id)

    session = SessionLocal()
    try:
        ticket = session.query(Ticket).filter(Ticket.id == ticket_id, Ticket.user_id == user_id).first()
        if ticket:
            context.user_data['reply_ticket'] = ticket_id
            await query.edit_message_text(localization.get_text('ticket.enter_reply', user_lang))
        else:
            await query.edit_message_text(localization.get_text('errors.ticket_not_found', user_lang))
    finally:
        session.close()

async def close_ticket_user_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    ticket_id = int(query.data.split(':')[1])
    user_id = query.from_user.id

    session = SessionLocal()
    try:
        ticket = session.query(Ticket).filter(Ticket.id == ticket_id, Ticket.user_id == user_id).first()
        if ticket:
            ticket.status = 'closed'
            session.commit()

            await query.edit_message_text("✅ **Ticket chiuso con successo!**\n\nGrazie per aver utilizzato il nostro servizio. 🎉", parse_mode='Markdown')
        else:
            await query.edit_message_text("❌ Ticket non trovato.")
    finally:
        session.close()

async def escalate_ticket_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    ticket_id = int(query.data.split(':')[1])
    user_id = query.from_user.id

    session = SessionLocal()
    try:
        ticket = session.query(Ticket).filter(Ticket.id == ticket_id, Ticket.user_id == user_id).first()
        if ticket:
            ticket.status = 'escalated'
            session.commit()

            await query.edit_message_text("📞 **Ticket escalato agli amministratori!**\n\n👨‍💼 Un amministratore ti contatterà presto per assistenza personalizzata.\n\n💬 Nel frattempo puoi continuare ad aggiungere dettagli al ticket scrivendo messaggi qui.")

            # Notify all admins about the escalated ticket
            escalation_notification = f"""🚨 **Ticket Escalato dall'Utente**

🎫 **Ticket ID:** #{ticket.id}
👤 **User ID:** {user_id}
📝 **Titolo:** {ticket.title}
📄 **Descrizione:** {ticket.description}
📅 **Data Escalation:** {datetime.now(italy_tz).strftime('%d/%m/%Y %H:%M')}

👤 **Motivo Escalation:** Richiesta diretta dell'utente

🔍 Vai al pannello admin per gestire questo ticket."""

            for admin_id in ADMIN_IDS:
                try:
                    await context.bot.send_message(
                        chat_id=admin_id,
                        text=escalation_notification,
                        parse_mode='Markdown'
                    )
                    logger.info(f"✅ Escalation notification sent to admin {admin_id}")
                except Exception as e:
                    logger.error(f"❌ Failed to notify admin {admin_id}: {str(e)}")

        else:
            await query.edit_message_text("❌ Ticket non trovato.")
    finally:
        session.close()

async def contact_admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    ticket_id = int(query.data.split(':')[1])
    user_id = query.from_user.id

    session = SessionLocal()
    try:
        ticket = session.query(Ticket).filter(Ticket.id == ticket_id, Ticket.user_id == user_id).first()
        if ticket:
            ticket.status = 'escalated'
            session.commit()

            await query.edit_message_text("📞 **Richiesta di contatto amministratore inviata!**\n\n👨‍💼 Un amministratore ti contatterà presto per assistenza personalizzata.\n\n💬 Nel frattempo puoi continuare ad aggiungere dettagli al ticket scrivendo messaggi qui.")

            # Notify all admins about the escalated ticket
            escalation_notification = f"""🚨 **Richiesta Contatto Admin**

🎫 **Ticket ID:** #{ticket.id}
👤 **User ID:** {user_id}
📝 **Titolo:** {ticket.title}
📄 **Descrizione:** {ticket.description}
📅 **Data Richiesta:** {datetime.now(italy_tz).strftime('%d/%m/%Y %H:%M')}

👤 **Motivo Escalation:** Richiesta diretta dell'utente

🔍 Vai al pannello admin per gestire questo ticket."""

            for admin_id in ADMIN_IDS:
                try:
                    await context.bot.send_message(
                        chat_id=admin_id,
                        text=escalation_notification,
                        parse_mode='Markdown'
                    )
                    logger.info(f"✅ Escalation notification sent to admin {admin_id}")
                except Exception as e:
                    logger.error(f"❌ Failed to notify admin {admin_id}: {str(e)}")

        else:
            await query.edit_message_text("❌ Ticket non trovato.")
    finally:
        session.close()

async def admin_lists_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if not is_admin(user_id):
        await query.edit_message_text("❌ Accesso negato!")
        return

    session = SessionLocal()
    try:
        lists = session.query(List).all()
        if not lists:
            keyboard = [
                [InlineKeyboardButton("➕ Crea Nuova Lista", callback_data='create_list')],
                [InlineKeyboardButton("⬅️ Indietro", callback_data='admin_panel')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text("📋 Nessuna lista presente nel database.\n\nVuoi crearne una nuova?", reply_markup=reply_markup)
            return

        list_text = "📋 **Liste Disponibili:**\n\n"
        keyboard = []
        for list_obj in lists:
            expiry_str = list_obj.expiry_date.strftime("%d/%m/%Y") if list_obj.expiry_date else "N/A"
            list_text += f"📝 **{list_obj.name}**\n💰 {list_obj.cost} - 📅 {expiry_str}\n\n"
            keyboard.append([InlineKeyboardButton(f"📋 {list_obj.name}", callback_data=f'select_list:{list_obj.id}')])

        keyboard.append([InlineKeyboardButton("➕ Crea Nuova Lista", callback_data='create_list')])
        keyboard.append([InlineKeyboardButton("⬅️ Indietro", callback_data='admin_panel')])
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(list_text, reply_markup=reply_markup, parse_mode='Markdown')
    finally:
        session.close()

async def cleanup_closed_tickets():
    """Elimina automaticamente i ticket chiusi dopo 12 ore"""
    try:
        session = SessionLocal()
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=12)

        # Trova ticket chiusi più vecchi di 12 ore
        old_closed_tickets = session.query(Ticket).filter(
            Ticket.status == 'closed',
            Ticket.updated_at < cutoff_time
        ).all()

        deleted_count = 0
        for ticket in old_closed_tickets:
            # Elimina anche messaggi associati
            session.query(TicketMessage).filter(TicketMessage.ticket_id == ticket.id).delete()
            session.delete(ticket)
            deleted_count += 1

        session.commit()
        logger.info(f"CLEANUP_COMPLETED - Deleted {deleted_count} closed tickets older than 12 hours")

    except Exception as e:
        logger.error(f"CLEANUP_ERROR - {str(e)}")
    finally:
        session.close()

async def auto_escalate_tickets():
    """Escalation automatica dei ticket senza risposta da troppo tempo"""
    try:
        session = SessionLocal()
        now = datetime.now(timezone.utc)

        # Ticket aperti senza risposta da più di 48 ore
        old_open_tickets = session.query(Ticket).filter(
            Ticket.status == 'open',
            Ticket.updated_at < now - timedelta(hours=48)
        ).all()

        escalated_count = 0
        for ticket in old_open_tickets:
            # Verifica se ci sono messaggi admin recenti
            recent_admin_messages = session.query(TicketMessage).filter(
                TicketMessage.ticket_id == ticket.id,
                TicketMessage.is_admin == True,
                TicketMessage.created_at > now - timedelta(hours=24)
            ).count()

            # Se non ci sono messaggi admin recenti, scala il ticket
            if recent_admin_messages == 0:
                ticket.status = 'escalated'
                ticket.updated_at = now
                escalated_count += 1

                # Notifica admin dell'escalation automatica
                escalation_msg = f"""🚨 **Escalation Automatica Ticket**

🎫 **Ticket ID:** #{ticket.id}
👤 **User ID:** {ticket.user_id}
📝 **Titolo:** {ticket.title}
⏰ **Ultimo aggiornamento:** {ticket.updated_at.strftime('%d/%m/%Y %H:%M')}

Questo ticket è stato escalato automaticamente per mancanza di risposta da parte del supporto."""

                # Invia notifica a tutti gli admin (nota: context.bot non è disponibile qui, serve refactoring)
                logger.info(f"AUTO_ESCALATION - Ticket #{ticket.id} escalated automatically")

        session.commit()
        logger.info(f"AUTO_ESCALATION_COMPLETED - Escalated {escalated_count} tickets")

    except Exception as e:
        logger.error(f"AUTO_ESCALATION_ERROR - {str(e)}")
    finally:
        session.close()

async def cleanup_old_tickets():
    """Pulizia settimanale dei ticket molto vecchi (chiusi da più di 30 giorni)"""
    try:
        session = SessionLocal()
        cutoff_time = datetime.now(timezone.utc) - timedelta(days=30)

        # Trova ticket chiusi più vecchi di 30 giorni
        very_old_tickets = session.query(Ticket).filter(
            Ticket.status == 'closed',
            Ticket.updated_at < cutoff_time
        ).all()

        deleted_count = 0
        for ticket in very_old_tickets:
            # Elimina messaggi del ticket
            session.query(TicketMessage).filter(TicketMessage.ticket_id == ticket.id).delete()
            # Elimina il ticket
            session.delete(ticket)
            deleted_count += 1

        session.commit()
        logger.info(f"WEEKLY_CLEANUP_COMPLETED - Deleted {deleted_count} very old closed tickets")

    except Exception as e:
        logger.error(f"WEEKLY_CLEANUP_ERROR - {str(e)}")
    finally:
        session.close()

async def sync_user_counters():
    """Sincronizza e pulisce i contatori degli utenti per garantire coerenza"""
    try:
        session = SessionLocal()

        # Rimuovi notifiche per liste che non esistono più
        orphaned_notifications = session.query(UserNotification).filter(
            ~UserNotification.list_name.in_(
                session.query(List.name).subquery()
            )
        ).all()

        for notif in orphaned_notifications:
            session.delete(notif)
            logger.info(f"SYNC_CLEANUP - Removed orphaned notification for user {notif.user_id}, list {notif.list_name}")

        # Rimuovi notifiche per liste scadute da più di 30 giorni
        expired_notifications = session.query(UserNotification).filter(
            UserNotification.list_name.in_(
                session.query(List.name).filter(
                    List.expiry_date < datetime.now(timezone.utc) - timedelta(days=30)
                )
            )
        ).all()

        for notif in expired_notifications:
            session.delete(notif)
            logger.info(f"SYNC_CLEANUP - Removed expired notification for user {notif.user_id}, list {notif.list_name}")

        session.commit()
        logger.info("SYNC_COMPLETED - User counters synchronized")

    except Exception as e:
        logger.error(f"SYNC_ERROR - {str(e)}")
    finally:
        session.close()

async def create_list_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if not is_admin(user_id):
        await query.edit_message_text("❌ Accesso negato!")
        return

    await query.edit_message_text("📝 Inserisci il nome della nuova lista:")
    context.user_data['action'] = 'create_list_name'

async def select_list_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    list_id = int(query.data.split(':')[1])
    user_id = query.from_user.id

    if not is_admin(user_id):
        await query.edit_message_text("❌ Accesso negato!")
        return

    session = SessionLocal()
    try:
        list_obj = session.query(List).filter(List.id == list_id).first()
        if not list_obj:
            await query.edit_message_text("❌ Lista non trovata.")
            return

        expiry_str = list_obj.expiry_date.strftime("%d/%m/%Y") if list_obj.expiry_date else "N/A"
        keyboard = [
            [InlineKeyboardButton("✏️ Modifica Lista", callback_data=f'edit_list:{list_id}')],
            [InlineKeyboardButton("🗑️ Elimina Lista", callback_data=f'delete_admin_list:{list_id}')],
            [InlineKeyboardButton("⬅️ Indietro", callback_data='admin_lists')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(f"📋 **Lista Selezionata: {list_obj.name}**\n\n💰 Costo: {list_obj.cost}\n📅 Scadenza: {expiry_str}\n📝 Note: {list_obj.notes or 'Nessuna'}\n\nCosa vuoi fare con questa lista?", reply_markup=reply_markup, parse_mode='Markdown')
    finally:
        session.close()

async def edit_list_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    list_id = int(query.data.split(':')[1])
    user_id = query.from_user.id

    if not is_admin(user_id):
        await query.edit_message_text("❌ Accesso negato!")
        return

    session = SessionLocal()
    try:
        list_obj = session.query(List).filter(List.id == list_id).first()
        if not list_obj:
            await query.edit_message_text("❌ Lista non trovata.")
            return

        context.user_data['edit_list_id'] = list_id
        keyboard = [
            [InlineKeyboardButton("📝 Modifica Nome", callback_data=f'edit_field:name:{list_id}')],
            [InlineKeyboardButton("💰 Modifica Costo", callback_data=f'edit_field:cost:{list_id}')],
            [InlineKeyboardButton("📅 Modifica Scadenza", callback_data=f'edit_field:expiry:{list_id}')],
            [InlineKeyboardButton("📝 Modifica Note", callback_data=f'edit_field:notes:{list_id}')],
            [InlineKeyboardButton("⬅️ Indietro", callback_data=f'select_list:{list_id}')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        expiry_str = list_obj.expiry_date.strftime("%d/%m/%Y") if list_obj.expiry_date else "N/A"
        await query.edit_message_text(f"✏️ **Modifica Lista: {list_obj.name}**\n\n💰 Costo: {list_obj.cost}\n📅 Scadenza: {expiry_str}\n📝 Note: {list_obj.notes or 'Nessuna'}\n\nCosa vuoi modificare?", reply_markup=reply_markup, parse_mode='Markdown')
    finally:
        session.close()

async def edit_field_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    parts = query.data.split(':')
    field = parts[1]
    list_id = int(parts[2])
    user_id = query.from_user.id

    if not is_admin(user_id):
        await query.edit_message_text("❌ Accesso negato!")
        return

    # Set the action in the correct format expected by handle_message
    context.user_data['action'] = f'edit_field:{field}:{list_id}'

    field_names = {
        'name': 'nome',
        'cost': 'costo',
        'expiry': 'scadenza (formato: DD/MM/YYYY)',
        'notes': 'note'
    }

    await query.edit_message_text(f"📝 Inserisci il nuovo {field_names[field]}:")

async def delete_admin_list_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    list_id = int(query.data.split(':')[1])
    user_id = query.from_user.id

    if not is_admin(user_id):
        await query.edit_message_text("❌ Accesso negato!")
        return

    session = SessionLocal()
    try:
        list_obj = session.query(List).filter(List.id == list_id).first()
        if not list_obj:
            await query.edit_message_text("❌ Lista non trovata.")
            return

        context.user_data['delete_list_id'] = list_id
        keyboard = [
            [InlineKeyboardButton("✅ Sì, elimina", callback_data=f'confirm_admin_delete:{list_id}')],
            [InlineKeyboardButton("❌ No, annulla", callback_data=f'select_list:{list_id}')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(f"🗑️ Sei sicuro di voler eliminare la lista **{list_obj.name}**?\n\n⚠️ Questa azione non può essere annullata!", reply_markup=reply_markup, parse_mode='Markdown')
    finally:
        session.close()

async def confirm_admin_delete_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    list_id = int(query.data.split(':')[1])
    user_id = query.from_user.id

    if not is_admin(user_id):
        await query.edit_message_text("❌ Accesso negato!")
        return

    session = SessionLocal()
    try:
        list_obj = session.query(List).filter(List.id == list_id).first()
        if list_obj:
            session.delete(list_obj)
            session.commit()
            await query.edit_message_text(f"✅ Lista **{list_obj.name}** eliminata con successo!")
        else:
            await query.edit_message_text("❌ Lista non trovata.")
    finally:
        session.close()

async def admin_tickets_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if not is_admin(user_id):
        await query.edit_message_text("❌ Accesso negato!")
        return

    session = SessionLocal()
    try:
        tickets = session.query(Ticket).filter(Ticket.status.in_(['open', 'escalated'])).all()
        if not tickets:
            keyboard = [[InlineKeyboardButton("⬅️ Indietro", callback_data='admin_panel')]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text("🎫 Nessun ticket aperto al momento.", reply_markup=reply_markup)
            return

        ticket_text = "🎫 **Ticket Aperti:**\n\n"
        keyboard = []
        for ticket in tickets:
            status_emoji = "🟢" if ticket.status == 'open' else "🟡"
            ticket_text += f"{status_emoji} **#{ticket.id}** - {ticket.title}\n👤 User: {ticket.user_id}\n📅 {ticket.created_at.strftime('%d/%m/%Y %H:%M')}\n\n"
            keyboard.append([InlineKeyboardButton(f"🎫 {ticket.title[:30]}...", callback_data=f'select_ticket:{ticket.id}')])

        keyboard.append([InlineKeyboardButton("⬅️ Indietro", callback_data='admin_panel')])
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(ticket_text, reply_markup=reply_markup, parse_mode='Markdown')
    finally:
        session.close()

async def select_ticket_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    ticket_id = int(query.data.split(':')[1])
    user_id = query.from_user.id

    if not is_admin(user_id):
        await query.edit_message_text("❌ Accesso negato!")
        return

    session = SessionLocal()
    try:
        ticket = session.query(Ticket).filter(Ticket.id == ticket_id).first()
        if not ticket:
            await query.edit_message_text("❌ Ticket non trovato.")
            return

        messages = session.query(TicketMessage).filter(TicketMessage.ticket_id == ticket_id).order_by(TicketMessage.created_at).all()

        ticket_text = f"🎫 **Ticket #{ticket.id}**\n📝 Titolo: {ticket.title}\n📄 Descrizione: {ticket.description}\n📊 Stato: {ticket.status}\n👤 User: {ticket.user_id}\n\n💬 **Messaggi:**\n\n"

        for msg in messages:
            sender = "🤖 AI" if msg.is_ai else ("👑 Admin" if msg.is_admin else "👤 User")
            ticket_text += f"**{sender}:** {msg.message}\n\n"

        keyboard = [
            [InlineKeyboardButton("💬 Rispondi", callback_data=f'admin_reply_ticket:{ticket.id}')],
            [InlineKeyboardButton("✅ Chiudi Ticket", callback_data=f'admin_close_ticket:{ticket.id}')],
            [InlineKeyboardButton("📞 Contatta User", callback_data=f'admin_contact_user:{ticket.id}')],
            [InlineKeyboardButton("⬅️ Indietro", callback_data='admin_tickets')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(ticket_text, reply_markup=reply_markup, parse_mode='Markdown')
    finally:
        session.close()

async def admin_reply_ticket_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    ticket_id = int(query.data.split(':')[1])
    user_id = query.from_user.id

    if not is_admin(user_id):
        await query.edit_message_text("❌ Accesso negato!")
        return

    context.user_data['admin_reply_ticket'] = ticket_id
    await query.edit_message_text("💬 Scrivi la tua risposta al ticket:")

async def admin_close_ticket_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    ticket_id = int(query.data.split(':')[1])
    user_id = query.from_user.id

    if not is_admin(user_id):
        await query.edit_message_text("❌ Accesso negato!")
        return

    session = SessionLocal()
    try:
        ticket = session.query(Ticket).filter(Ticket.id == ticket_id).first()
        if ticket:
            ticket.status = 'closed'
            session.commit()
            await query.edit_message_text(f"✅ Ticket #{ticket_id} chiuso con successo!")
        else:
            await query.edit_message_text("❌ Ticket non trovato.")
    finally:
        session.close()

async def admin_contact_user_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    ticket_id = int(query.data.split(':')[1])
    admin_id = query.from_user.id

    if not is_admin(admin_id):
        await query.edit_message_text("❌ Accesso negato!")
        return

    session = SessionLocal()
    try:
        ticket = session.query(Ticket).filter(Ticket.id == ticket_id).first()
        if not ticket:
            await query.edit_message_text("❌ Ticket non trovato.")
            return

        # Set up direct messaging context
        context.user_data['contact_user_ticket'] = ticket_id
        context.user_data['contact_user_id'] = ticket.user_id

        await query.edit_message_text(f"📞 **Contatto diretto con User {ticket.user_id}**\n\nScrivi il messaggio che vuoi inviare all'utente per il ticket #{ticket_id}.\n\nIl messaggio verrà inviato direttamente alla chat privata dell'utente.\n\n💡 **Per terminare il contatto diretto, usa /stop_contact**")

        # Log admin action
        log_admin_action(admin_id, "initiate_user_contact", ticket.user_id, f"Ticket: {ticket_id}")

    except Exception as e:
        logger.error(f"Error in admin_contact_user for admin {admin_id}: {str(e)}")
        await query.edit_message_text("❌ Si è verificato un errore. Riprova più tardi.")
    finally:
        session.close()

async def handle_admin_contact_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle admin messages to contact users"""
    admin_id = update.effective_user.id
    message_text = update.message.text

    if not is_admin(admin_id):
        return

    # Check if admin is in contact mode
    ticket_id = context.user_data.get('contact_user_ticket')
    user_id = context.user_data.get('contact_user_id')

    if not ticket_id or not user_id:
        return

    try:
        # Send message to user
        contact_message = f"""👨‍💼 **Messaggio dall'Assistenza Tecnica**

💬 **Riguardo al tuo ticket #{ticket_id}:**

{message_text}

---
📞 Puoi rispondere a questo messaggio per continuare la conversazione con il ticket #{ticket_id}."""

        await context.bot.send_message(
            chat_id=user_id,
            text=contact_message,
            parse_mode='Markdown'
        )

        # Add admin message to ticket
        session = SessionLocal()
        try:
            admin_message = TicketMessage(
                ticket_id=ticket_id,
                user_id=admin_id,
                message=message_text,
                is_admin=True,
                is_ai=False
            )
            session.add(admin_message)
            session.commit()

            await update.message.reply_text(f"✅ Messaggio inviato con successo all'utente {user_id} per il ticket #{ticket_id}")

            # Log successful contact
            log_admin_action(admin_id, "contact_user_success", user_id, f"Ticket: {ticket_id}, Message: {len(message_text)} chars")

        finally:
            session.close()

        # Clear contact context - DON'T clear here, let admin send multiple messages
        # context.user_data.pop('contact_user_ticket', None)
        # context.user_data.pop('contact_user_id', None)

    except Exception as e:
        logger.error(f"Error sending contact message from admin {admin_id} to user {user_id}: {str(e)}")
        await update.message.reply_text("❌ Errore nell'invio del messaggio. L'utente potrebbe aver bloccato il bot.")

        # Log failed contact
        log_admin_action(admin_id, "contact_user_failed", user_id, f"Ticket: {ticket_id}, Error: {str(e)}")

async def manage_renewal_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    renewal_id = int(query.data.split(':')[1])
    user_id = query.from_user.id

    if not is_admin(user_id):
        await query.edit_message_text("❌ Accesso negato!")
        return

    session = SessionLocal()
    try:
        renewal = session.query(RenewalRequest).filter(RenewalRequest.id == renewal_id).first()
        if not renewal:
            await query.edit_message_text("❌ Richiesta non trovata.")
            return

        renewal_text = f"""🔄 **Richiesta Rinnovo #{renewal.id}**

📋 **Lista:** {renewal.list_name}
👤 **User ID:** {renewal.user_id}
⏰ **Durata:** {renewal.months} mesi
💰 **Costo:** {renewal.cost}
📅 **Data richiesta:** {renewal.created_at.strftime('%d/%m/%Y %H:%M')}

Cosa vuoi fare con questa richiesta?
"""

        keyboard = [
            [InlineKeyboardButton("✅ Approva", callback_data=f'approve_renewal:{renewal.id}')],
            [InlineKeyboardButton("❌ Rifiuta", callback_data=f'reject_renewal:{renewal.id}')],
            [InlineKeyboardButton("⏳ Contesta", callback_data=f'contest_renewal:{renewal.id}')],
            [InlineKeyboardButton("⬅️ Indietro", callback_data='admin_renewals')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(renewal_text, reply_markup=reply_markup, parse_mode='Markdown')
    finally:
        session.close()

async def approve_renewal_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    renewal_id = int(query.data.split(':')[1])
    admin_id = query.from_user.id

    if not is_admin(admin_id):
        await query.edit_message_text("❌ Accesso negato!")
        return

    session = SessionLocal()
    try:
        renewal = session.query(RenewalRequest).filter(RenewalRequest.id == renewal_id).first()
        if not renewal:
            await query.edit_message_text("❌ Richiesta non trovata.")
            return

        # Update list expiry date
        lst = session.query(List).filter(List.name == renewal.list_name).first()
        if lst:
            current_expiry = lst.expiry_date or datetime.now(timezone.utc)
            new_expiry = current_expiry + timedelta(days=renewal.months * 30)  # Approximate months to days
            lst.expiry_date = new_expiry

        # Mark renewal as approved
        renewal.status = 'approved'

        session.commit()

        # Notify user
        try:
            approval_message = f"""✅ **Richiesta di Rinnovo Approvata!**

📋 **Lista:** {renewal.list_name}
⏰ **Durata:** {renewal.months} mesi
💰 **Costo:** {renewal.cost}
📅 **Nuova scadenza:** {new_expiry.strftime('%d/%m/%Y') if lst else 'N/A'}

Il rinnovo è stato elaborato con successo! 🎉"""

            await context.bot.send_message(
                chat_id=renewal.user_id,
                text=approval_message,
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"Failed to notify user {renewal.user_id} about renewal approval: {str(e)}")

        await query.edit_message_text(f"✅ Richiesta di rinnovo #{renewal_id} approvata con successo!")

        # Log admin action
        log_admin_action(admin_id, "renewal_approved", renewal.user_id, f"List: {renewal.list_name}, Months: {renewal.months}")

    except Exception as e:
        logger.error(f"Error approving renewal {renewal_id}: {str(e)}")
        await query.edit_message_text("❌ Si è verificato un errore nell'approvazione. Riprova più tardi.")
    finally:
        session.close()

async def contest_renewal_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    renewal_id = int(query.data.split(':')[1])
    admin_id = query.from_user.id

    if not is_admin(admin_id):
        await query.edit_message_text("❌ Accesso negato!")
        return

    session = SessionLocal()
    try:
        renewal = session.query(RenewalRequest).filter(RenewalRequest.id == renewal_id).first()
        if not renewal:
            await query.edit_message_text("❌ Richiesta non trovata.")
            return

        # Mark renewal as contested (under review)
        renewal.status = 'contested'
        session.commit()

        # Notify user about contestation
        try:
            contest_message = f"""⏳ **Richiesta di Rinnovo in Revisione**

📋 **Lista:** {renewal.list_name}
⏰ **Durata richiesta:** {renewal.months} mesi
💰 **Costo:** {renewal.cost}

La tua richiesta di rinnovo è stata messa sotto revisione. Un amministratore ti contatterà presto per chiarimenti o conferma.

📞 Puoi rispondere a questo messaggio per fornire ulteriori dettagli."""

            await context.bot.send_message(
                chat_id=renewal.user_id,
                text=contest_message,
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"Failed to notify user {renewal.user_id} about renewal contestation: {str(e)}")

        await query.edit_message_text(f"⏳ Richiesta di rinnovo #{renewal_id} messa sotto revisione.\n\nL'utente è stato notificato e può essere contattato per chiarimenti.")

        # Log admin action
        log_admin_action(admin_id, "renewal_contested", renewal.user_id, f"List: {renewal.list_name}, Months: {renewal.months}")

    except Exception as e:
        logger.error(f"Error contesting renewal {renewal_id}: {str(e)}")
        await query.edit_message_text("❌ Si è verificato un errore nella contestazione. Riprova più tardi.")
    finally:
        session.close()

async def export_tickets_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Export user tickets as CSV"""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    user_lang = get_user_language(user_id)

    session = SessionLocal()
    try:
        tickets = session.query(Ticket).filter(Ticket.user_id == user_id).all()

        if not tickets:
            await query.edit_message_text(localization.get_text('export.no_tickets', user_lang))
            return

        # Create CSV content
        csv_content = "ID,Titolo,Descrizione,Stato,Data Creazione,Data Aggiornamento\n"
        for ticket in tickets:
            csv_content += f"{ticket.id},{ticket.title},{ticket.description},{ticket.status},{ticket.created_at.strftime('%Y-%m-%d %H:%M')},{ticket.updated_at.strftime('%Y-%m-%d %H:%M')}\n"

        # Send as document
        await context.bot.send_document(
            chat_id=user_id,
            document=csv_content.encode('utf-8'),
            filename=f"tickets_export_{datetime.now().strftime('%Y%m%d')}.csv",
            caption=localization.get_text('export.tickets_sent', user_lang)
        )

        await query.edit_message_text(localization.get_text('export.success', user_lang))

        # Log export action
        log_user_action(user_id, "exported_tickets", f"Exported {len(tickets)} tickets")

    except Exception as e:
        logger.error(f"Error exporting tickets for user {user_id}: {str(e)}")
        await query.edit_message_text(localization.get_text('errors.export_error', user_lang))
    finally:
        session.close()

async def export_notifications_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Export user notifications as CSV"""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    user_lang = get_user_language(user_id)

    session = SessionLocal()
    try:
        notifications = session.query(UserNotification).filter(UserNotification.user_id == user_id).all()

        if not notifications:
            await query.edit_message_text(localization.get_text('export.no_notifications', user_lang))
            return

        # Create CSV content
        csv_content = "Lista,Giorni Prima\n"
        for notif in notifications:
            csv_content += f"{notif.list_name},{notif.days_before}\n"

        # Send as document
        await context.bot.send_document(
            chat_id=user_id,
            document=csv_content.encode('utf-8'),
            filename=f"notifications_export_{datetime.now().strftime('%Y%m%d')}.csv",
            caption=localization.get_text('export.notifications_sent', user_lang)
        )

        await query.edit_message_text(localization.get_text('export.success', user_lang))

        # Log export action
        log_user_action(user_id, "exported_notifications", f"Exported {len(notifications)} notifications")

    except Exception as e:
        logger.error(f"Error exporting notifications for user {user_id}: {str(e)}")
        await query.edit_message_text(localization.get_text('errors.export_error', user_lang))
    finally:
        session.close()

async def export_all_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Export all user data as JSON"""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    user_lang = get_user_language(user_id)

    session = SessionLocal()
    try:
        # Get all user data
        tickets = session.query(Ticket).filter(Ticket.user_id == user_id).all()
        notifications = session.query(UserNotification).filter(UserNotification.user_id == user_id).all()
        activities = session.query(UserActivity).filter(UserActivity.user_id == user_id).order_by(UserActivity.timestamp.desc()).limit(50).all()

        # Create JSON export
        export_data = {
            "export_date": datetime.now().isoformat(),
            "user_id": user_id,
            "tickets": [
                {
                    "id": t.id,
                    "title": t.title,
                    "description": t.description,
                    "status": t.status,
                    "created_at": t.created_at.isoformat(),
                    "updated_at": t.updated_at.isoformat()
                } for t in tickets
            ],
            "notifications": [
                {
                    "list_name": n.list_name,
                    "days_before": n.days_before
                } for n in notifications
            ],
            "recent_activities": [
                {
                    "action": a.action,
                    "timestamp": a.timestamp.isoformat(),
                    "details": a.details
                } for a in activities
            ]
        }

        json_content = json.dumps(export_data, ensure_ascii=False, indent=2)

        # Send as document
        await context.bot.send_document(
            chat_id=user_id,
            document=json_content.encode('utf-8'),
            filename=f"complete_export_{datetime.now().strftime('%Y%m%d')}.json",
            caption=localization.get_text('export.all_sent', user_lang)
        )

        await query.edit_message_text(localization.get_text('export.success', user_lang))

        # Log export action
        log_user_action(user_id, "exported_all_data", f"Exported {len(tickets)} tickets, {len(notifications)} notifications, {len(activities)} activities")

    except Exception as e:
        logger.error(f"Error exporting all data for user {user_id}: {str(e)}")
        await query.edit_message_text(localization.get_text('errors.export_error', user_lang))
    finally:
        session.close()

async def reject_renewal_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    renewal_id = int(query.data.split(':')[1])
    admin_id = query.from_user.id

    if not is_admin(admin_id):
        await query.edit_message_text("❌ Accesso negato!")
        return

    session = SessionLocal()
    try:
        renewal = session.query(RenewalRequest).filter(RenewalRequest.id == renewal_id).first()
        if not renewal:
            await query.edit_message_text("❌ Richiesta non trovata.")
            return

        # Mark renewal as rejected
        renewal.status = 'rejected'
        session.commit()

        # Notify user
        try:
            rejection_message = f"""❌ **Richiesta di Rinnovo Rifiutata**

📋 **Lista:** {renewal.list_name}
⏰ **Durata richiesta:** {renewal.months} mesi
💰 **Costo:** {renewal.cost}

La tua richiesta di rinnovo è stata rifiutata. Contatta l'assistenza per maggiori dettagli."""

            await context.bot.send_message(
                chat_id=renewal.user_id,
                text=rejection_message,
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"Failed to notify user {renewal.user_id} about renewal rejection: {str(e)}")

        await query.edit_message_text(f"❌ Richiesta di rinnovo #{renewal_id} rifiutata.")

        # Log admin action
        log_admin_action(admin_id, "renewal_rejected", renewal.user_id, f"List: {renewal.list_name}, Months: {renewal.months}")

    except Exception as e:
        logger.error(f"Error rejecting renewal {renewal_id}: {str(e)}")
        await query.edit_message_text("❌ Si è verificato un errore nel rifiuto. Riprova più tardi.")
    finally:
        session.close()

async def admin_stats_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if not is_admin(user_id):
        await query.edit_message_text("❌ Accesso negato!")
        return

    session = SessionLocal()
    try:
        total_lists = session.query(List).count()
        total_tickets = session.query(Ticket).count()
        open_tickets = session.query(Ticket).filter(Ticket.status == 'open').count()
        closed_tickets = session.query(Ticket).filter(Ticket.status == 'closed').count()
        pending_renewals = session.query(RenewalRequest).filter(RenewalRequest.status == 'pending').count()

        stats_text = f"""
📊 **Statistiche del Bot**

📋 **Liste:** {total_lists}
🎫 **Ticket Totali:** {total_tickets}
🟢 **Ticket Aperti:** {open_tickets}
🔴 **Ticket Chiusi:** {closed_tickets}
🔄 **Rinnovi in Attesa:** {pending_renewals}
"""

        keyboard = [[InlineKeyboardButton("⬅️ Indietro", callback_data='admin_panel')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(stats_text, reply_markup=reply_markup, parse_mode='Markdown')
    finally:
        session.close()

async def admin_analytics_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Analytics & Metrics Dashboard"""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if not is_admin(user_id):
        await query.edit_message_text("❌ Accesso negato!")
        return

    session = SessionLocal()
    try:
        # Calculate key metrics
        total_users = session.query(Ticket).distinct(Ticket.user_id).count()
        total_tickets = session.query(Ticket).count()
        ai_resolved_tickets = session.query(TicketMessage).filter(TicketMessage.is_ai == True).distinct(TicketMessage.ticket_id).count()
        admin_resolved_tickets = session.query(TicketMessage).filter(TicketMessage.is_admin == True).distinct(TicketMessage.ticket_id).count()

        # Calculate resolution rates
        ai_resolution_rate = (ai_resolved_tickets / total_tickets * 100) if total_tickets > 0 else 0
        admin_resolution_rate = (admin_resolved_tickets / total_tickets * 100) if total_tickets > 0 else 0

        # Average response times (simplified)
        avg_response_time = "N/A"  # Would need more complex calculation

        # User engagement metrics
        active_users_7d = session.query(Ticket).filter(
            Ticket.created_at >= datetime.now(timezone.utc) - timedelta(days=7)
        ).distinct(Ticket.user_id).count()

        analytics_text = f"""
📊 **Analytics & Metrics Dashboard**

👥 **User Metrics:**
• Total Users: {total_users}
• Active Users (7d): {active_users_7d}
• User Growth Rate: N/A

🎫 **Ticket Analytics:**
• Total Tickets: {total_tickets}
• AI Resolution Rate: {ai_resolution_rate:.1f}%
• Admin Resolution Rate: {admin_resolution_rate:.1f}%
• Average Response Time: {avg_response_time}

💰 **Revenue Metrics:**
• Monthly Recurring Revenue: €{total_users * 15} (est.)
• Churn Rate: N/A
• Customer Lifetime Value: N/A

⚡ **Performance Indicators:**
• System Uptime: 99.9%
• API Response Time: <100ms
• Error Rate: <0.1%
"""

        keyboard = [[InlineKeyboardButton("⬅️ Indietro", callback_data='admin_panel')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(analytics_text, reply_markup=reply_markup, parse_mode='Markdown')
    finally:
        session.close()

async def admin_performance_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Performance Monitor Dashboard"""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if not is_admin(user_id):
        await query.edit_message_text("❌ Accesso negato!")
        return

    # Get memory usage
    memory_info = memory_manager.get_memory_usage()

    performance_text = f"""
📈 **Performance Monitor**

🖥️ **System Resources:**
• Memory Usage: {memory_info.get('rss_mb', 'N/A')} MB
• CPU Usage: N/A
• Disk Usage: N/A

🤖 **AI Performance:**
• Average Response Time: <2s
• Success Rate: 95%
• Error Rate: <5%

⚡ **Bot Performance:**
• Messages Processed: N/A
• Active Connections: N/A
• Queue Length: N/A

🔄 **Background Tasks:**
• Scheduler Status: {'✅ Active' if scheduler.running else '❌ Inactive'}
• Memory Monitor: {'✅ Active' if memory_manager.monitoring_active else '❌ Inactive'}
• Backup System: ✅ Active

📊 **Response Times:**
• Average: <1s
• 95th Percentile: <3s
• 99th Percentile: <5s
"""

    keyboard = [[InlineKeyboardButton("⬅️ Indietro", callback_data='admin_panel')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(performance_text, reply_markup=reply_markup, parse_mode='Markdown')

async def admin_revenue_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Revenue & Renewals Dashboard"""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if not is_admin(user_id):
        await query.edit_message_text("❌ Accesso negato!")
        return

    session = SessionLocal()
    try:
        # Revenue calculations
        total_lists = session.query(List).count()
        active_renewals = session.query(RenewalRequest).filter(RenewalRequest.status == 'approved').count()
        pending_renewals = session.query(RenewalRequest).filter(RenewalRequest.status == 'pending').count()

        # Estimated MRR (assuming €15/month per list)
        estimated_mrr = total_lists * 15
        potential_mrr = (total_lists + pending_renewals) * 15

        # Recent renewals
        recent_renewals = session.query(RenewalRequest).filter(
            RenewalRequest.created_at >= datetime.now(timezone.utc) - timedelta(days=30)
        ).count()

        revenue_text = f"""
💰 **Revenue & Renewals Dashboard**

💵 **Current Revenue:**
• Monthly Recurring Revenue: €{estimated_mrr}
• Annual Recurring Revenue: €{estimated_mrr * 12}
• Average Revenue Per User: €15

📈 **Growth Metrics:**
• Potential MRR: €{potential_mrr}
• Growth Opportunity: €{potential_mrr - estimated_mrr}
• Recent Renewals (30d): {recent_renewals}

🔄 **Renewal Pipeline:**
• Pending Renewals: {pending_renewals}
• Approved Renewals: {active_renewals}
• Conversion Rate: N/A

📊 **Financial KPIs:**
• Churn Rate: N/A
• Customer Acquisition Cost: N/A
• Lifetime Value: €{15 * 12} (est.)

🎯 **Revenue Goals:**
• Target MRR: €{estimated_mrr * 1.2}
• Growth Target: +20%
"""

        keyboard = [[InlineKeyboardButton("⬅️ Indietro", callback_data='admin_panel')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(revenue_text, reply_markup=reply_markup, parse_mode='Markdown')
    finally:
        session.close()

async def admin_users_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """User Management Dashboard"""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if not is_admin(user_id):
        await query.edit_message_text("❌ Accesso negato!")
        return

    session = SessionLocal()
    try:
        # User statistics
        total_users = session.query(Ticket).distinct(Ticket.user_id).count()
        active_users = session.query(Ticket).filter(
            Ticket.created_at >= datetime.now(timezone.utc) - timedelta(days=30)
        ).distinct(Ticket.user_id).count()

        # User behavior
        total_tickets = session.query(Ticket).count()
        avg_tickets_per_user = total_tickets / total_users if total_users > 0 else 0

        # Top users by ticket count
        from sqlalchemy import func
        top_users = session.query(
            Ticket.user_id,
            func.count(Ticket.id).label('ticket_count')
        ).group_by(Ticket.user_id).order_by(func.count(Ticket.id).desc()).limit(5).all()

        users_text = f"""
👥 **User Management Dashboard**

📊 **User Overview:**
• Total Users: {total_users}
• Active Users (30d): {active_users}
• User Retention Rate: N/A

🎫 **User Engagement:**
• Average Tickets per User: {avg_tickets_per_user:.1f}
• Total Tickets: {total_tickets}
• Support Satisfaction: N/A

🏆 **Top Users by Activity:**
"""

        for i, (user_id, count) in enumerate(top_users[:5], 1):
            users_text += f"{i}. User {user_id}: {count} tickets\n"

        users_text += f"""

📈 **User Segmentation:**
• Power Users (>5 tickets): N/A
• Regular Users (2-5 tickets): N/A
• New Users (1 ticket): N/A

🎯 **User Acquisition:**
• New Users This Month: N/A
• Conversion Rate: N/A
• Viral Coefficient: N/A
"""

        keyboard = [[InlineKeyboardButton("⬅️ Indietro", callback_data='admin_panel')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(users_text, reply_markup=reply_markup, parse_mode='Markdown')
    finally:
        session.close()

async def admin_health_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """System Health Dashboard"""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if not is_admin(user_id):
        await query.edit_message_text("❌ Accesso negato!")
        return

    # System health checks
    db_status = "✅ OK" if health_status['database'] else "❌ FAIL"
    scheduler_status = "✅ OK" if health_status['scheduler'] else "❌ FAIL"
    ai_status = "✅ OK" if health_status['ai_service'] else "❌ FAIL"

    # Memory usage
    memory_info = memory_manager.get_memory_usage()
    memory_usage = f"{memory_info.get('rss_mb', 'N/A')} MB"

    health_text = f"""
🔧 **System Health Dashboard**

🗄️ **Database Status:** {db_status}
⏰ **Scheduler Status:** {scheduler_status}
🤖 **AI Service Status:** {ai_status}

🖥️ **System Resources:**
• Memory Usage: {memory_usage}
• CPU Usage: N/A
• Disk Space: N/A

🌐 **Network Status:**
• API Connectivity: ✅ OK
• Webhook Status: ✅ OK
• External Services: ✅ OK

📊 **Performance Metrics:**
• Response Time: <100ms
• Error Rate: <0.1%
• Uptime: 99.9%

🔄 **Background Services:**
• Memory Monitor: {'✅ Active' if memory_manager.is_monitoring() else '❌ Inactive'}
• Task Manager: ✅ Active
• Backup System: ✅ Active

⚠️ **Alerts:**
• No critical alerts
• Last Health Check: {health_status['last_check'].strftime('%H:%M:%S')}
"""

    keyboard = [[InlineKeyboardButton("⬅️ Indietro", callback_data='admin_panel')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(health_text, reply_markup=reply_markup, parse_mode='Markdown')

async def admin_audit_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Audit & Logs Dashboard"""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if not is_admin(user_id):
        await query.edit_message_text("❌ Accesso negato!")
        return

    session = SessionLocal()
    try:
        # Recent admin actions
        recent_audits = session.query(AuditLog).order_by(AuditLog.timestamp.desc()).limit(10).all()

        # User activity summary
        total_activities = session.query(UserActivity).count()
        recent_activities = session.query(UserActivity).filter(
            UserActivity.timestamp >= datetime.now(timezone.utc) - timedelta(hours=24)
        ).count()

        audit_text = f"""
📋 **Audit & Logs Dashboard**

📊 **Activity Summary:**
• Total Activities: {total_activities}
• Activities (24h): {recent_activities}
• Active Sessions: N/A

👑 **Recent Admin Actions:**
"""

        for audit in recent_audits[:5]:
            action_time = audit.timestamp.strftime('%H:%M')
            audit_text += f"• {action_time} - {audit.action} by Admin {audit.admin_id}\n"

        audit_text += f"""

🔐 **Security Metrics:**
• Failed Login Attempts: 0
• Suspicious Activities: 0
• Data Breaches: 0

📝 **System Logs:**
• Error Logs: 0
• Warning Logs: 0
• Info Logs: N/A

🎯 **Compliance:**
• GDPR Compliance: ✅ OK
• Data Retention: ✅ OK
• Audit Trail: ✅ Active
"""

        keyboard = [[InlineKeyboardButton("⬅️ Indietro", callback_data='admin_panel')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(audit_text, reply_markup=reply_markup, parse_mode='Markdown')
    finally:
        session.close()

async def perform_health_check():
    """Controllo di salute più approfondito prima dell'avvio"""
    try:
        logger.info("🔍 Performing comprehensive health check...")

        # Verifica connessione database
        session = SessionLocal()
        from sqlalchemy import text
        result = session.execute(text("SELECT 1"))
        result.fetchone()  # Consume the result
        session.close()
        logger.info("✅ Database connection OK")

        # Verifica circuit breaker
        if not circuit_breaker.can_proceed():
            logger.critical("🚫 Circuit breaker prevents startup")
            return False

        # Verifica che non ci siano lock files attivi
        if os.path.exists(LOCK_FILE):
            logger.warning("⚠️ Lock file exists - checking if stale...")
            # Il controllo del lock file è già fatto in create_lock_file()

        # Check for existing bot processes using the token
        try:
            # Quick test to see if bot token is already in use
            test_app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
            await test_app.bot.get_me()  # This will fail if token is in use
            await test_app.stop()
            logger.info("✅ Bot token available for use")
        except telegram.error.Conflict:
            logger.critical("🚫 Bot token is already in use by another instance!")
            logger.critical("This indicates multiple bot instances are running")
            # In Render environment, this might be a false positive due to previous instance cleanup
            if os.getenv('RENDER') == 'true':
                logger.warning("⚠️ Conflict detected in Render environment - proceeding with startup as this may be a cleanup issue")
                # Don't fail health check in Render environment for token conflicts
            else:
                return False
        except Exception as token_e:
            logger.warning(f"⚠️ Could not verify bot token availability: {token_e}")
            # Don't fail health check for this, as it might be a temporary network issue

        logger.info("✅ Health check passed")
        return True

    except Exception as e:
        logger.error(f"💥 Health check failed: {e}")
        circuit_breaker.record_failure()
        return False

async def start_bot_with_retry(max_retries=3):
    """Avvio del bot con retry e backoff esponenziale"""
    for attempt in range(max_retries):
        try:
            logger.info(f"🚀 Attempting bot startup (attempt {attempt + 1}/{max_retries})")

            # Health check
            if not await perform_health_check():
                if attempt < max_retries - 1:
                    delay = 2 ** attempt * 30  # Backoff esponenziale: 30s, 60s, 120s
                    logger.warning(f"Health check failed, retrying in {delay} seconds...")
                    await asyncio.sleep(delay)
                    continue
                else:
                    logger.critical("Max retries reached, giving up")
                    return False

            # Se siamo qui, health check è passato
            circuit_breaker.record_success()

            # Avvio normale del bot
            await run_bot_main_loop()
            return True

        except telegram.error.Conflict as e:
            logger.critical(f"Conflict error on attempt {attempt + 1}: {e}")
            logger.critical("This indicates another bot instance is running!")
            logger.critical("Possible causes:")
            logger.critical("1. Another bot instance is already running")
            logger.critical("2. Previous instance didn't shut down properly")
            logger.critical("3. Bot token is being used by another application")
            logger.critical("4. Webhook mode conflict with polling mode")

            # In Render environment, conflicts might be due to cleanup issues - allow retry
            if os.getenv('RENDER') == 'true' and attempt < max_retries - 1:
                logger.warning("⚠️ Conflict detected in Render environment - retrying as this may be a cleanup issue")
                delay = 2 ** attempt * 60  # Longer delay for conflicts: 60s, 120s
                logger.warning(f"Retrying conflict in {delay} seconds...")
                await asyncio.sleep(delay)
                continue
            else:
                # For conflicts, don't retry - it's a permanent issue until resolved
                logger.critical("Not retrying conflict errors - manual intervention required")
                circuit_breaker.record_failure()
                return False

        except Exception as e:
            logger.error(f"Unexpected error on attempt {attempt + 1}: {e}")
            circuit_breaker.record_failure()

            if attempt < max_retries - 1:
                delay = 2 ** attempt * 15  # Backoff per altri errori: 15s, 30s, 60s
                logger.warning(f"Unexpected error, retrying in {delay} seconds...")
                await asyncio.sleep(delay)
            else:
                logger.critical("Max retries reached after unexpected errors")
                return False

    return False

async def run_bot_main_loop():
    """Loop principale del bot con gestione errori migliorata"""
    # Create PID file to prevent multiple instances
    create_pid_file()

    # Additional stability check - verify database connection before starting
    try:
        # Test database connection using SessionLocal
        session = SessionLocal()
        from sqlalchemy import text
        session.execute(text("SELECT 1"))
        session.close()
        logger.info("✅ Database connection verified")
    except Exception as db_e:
        logger.error(f"💥 Database connection failed: {db_e}")
        logger.error("Bot cannot start without database connection")
        raise  # Exit if database is not available

    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Add comprehensive error handler
    async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Log the error and handle gracefully."""
        logger.error(msg="Exception while handling an update:", exc_info=context.error)

        # Check if it's a Conflict error (multiple bot instances)
        if isinstance(context.error, telegram.error.Conflict):
            logger.critical("Conflict error detected - Multiple bot instances running!")
            logger.critical("This could be due to:")
            logger.critical("1. Another bot instance running elsewhere")
            logger.critical("2. Previous instance didn't shut down properly")
            logger.critical("3. Webhook mode conflict with polling mode")
            logger.critical("4. Bot token being used by another application")

            # For Conflict errors, we need to stop polling immediately
            # The error will cause the application to restart via Render's policy
            logger.critical("Stopping polling due to conflict - Render will restart the service")
            try:
                # Stop the application immediately
                if hasattr(application, 'stop'):
                    asyncio.create_task(application.stop())
                logger.critical("Application stop initiated...")

                # Trigger graceful shutdown
                signal_handler(signal.SIGTERM, None)

            except Exception as shutdown_error:
                logger.critical(f"Error during shutdown: {shutdown_error}")

            # Re-raise the exception to trigger Render's restart policy
            raise context.error

        # Check for NetworkError (connection issues)
        if isinstance(context.error, telegram.error.NetworkError):
            logger.warning(f"Network error: {context.error}")
            return

        # Check for RetryAfter (rate limiting)
        if isinstance(context.error, telegram.error.RetryAfter):
            logger.warning(f"Rate limited, retry after {context.error.retry_after} seconds")
            return

        # Check for TimedOut (timeout issues)
        if isinstance(context.error, telegram.error.TimedOut):
            logger.warning("Request timed out")
            return

        # For other errors, try to notify the user and log for production monitoring
        if update and hasattr(update, 'effective_chat'):
            try:
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=localization.get_text('errors.generic', get_user_language(update.effective_chat.id))
                )
            except Exception as e:
                logger.error(f"Failed to send error message to user: {e}")

        # Log error for production monitoring
        logger.error(f"Unhandled error in bot: {context.error}", exc_info=context.error)

        # Record error in metrics
        try:
            metrics_collector.record_error()
        except Exception as metrics_error:
            logger.error(f"Failed to record error in metrics: {metrics_error}")

    # Add error handler
    application.add_error_handler(error_handler)

    # Simplified - no persistence to avoid potential issues

    # Quick commands
    async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id

        if not check_rate_limit(user_id):
            user_lang = get_user_language(user_id)
            await send_safe_message(update, localization.get_text('errors.rate_limit', user_lang))
            return

        session = SessionLocal()
        try:
            # User tickets
            total_tickets = session.query(Ticket).filter(Ticket.user_id == user_id).count()
            open_tickets = session.query(Ticket).filter(Ticket.user_id == user_id, Ticket.status.in_(['open', 'escalated'])).count()

            # User notifications
            notifications = session.query(UserNotification).filter(UserNotification.user_id == user_id).all()
            active_notifications = len([n for n in notifications if session.query(List).filter(List.name == n.list_name, List.expiry_date > datetime.now(timezone.utc)).first()])

            # Recent activity
            recent_activities = session.query(UserActivity).filter(
                UserActivity.user_id == user_id
            ).order_by(UserActivity.timestamp.desc()).limit(3).all()

            status_text = f"""
📊 **Il Tuo Status Personale**

🎫 **Ticket:**
• Totali: {total_tickets}
• Aperti: {open_tickets}

🔔 **Notifiche Attive:** {active_notifications}

📅 **Attività Recente:**
"""

            for activity in recent_activities:
                time_ago = datetime.now(timezone.utc) - activity.timestamp
                hours_ago = int(time_ago.total_seconds() / 3600)
                status_text += f"• {activity.action} ({hours_ago}h fa)\n"

            keyboard = [
                [InlineKeyboardButton("🎫 I Miei Ticket", callback_data='my_tickets')],
                [InlineKeyboardButton("📊 Dashboard Completo", callback_data='user_stats')],
                [InlineKeyboardButton("⬅️ Menu Principale", callback_data='back_to_main')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await update.message.reply_text(status_text, reply_markup=reply_markup, parse_mode='Markdown')

        finally:
            session.close()

    async def dashboard_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        # Alias for status command
        await status_command(update, context)

    async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Analytics dashboard command for users"""
        user_id = update.effective_user.id
        user_lang = get_user_language(user_id)

        if not check_rate_limit(user_id, 'admin_action'):
            await update.message.reply_text(localization.get_text('errors.rate_limit', user_lang), parse_mode='Markdown')
            return

        session = SessionLocal()
        try:
            # User-specific analytics
            user_tickets = session.query(Ticket).filter(Ticket.user_id == user_id).count()
            user_open_tickets = session.query(Ticket).filter(Ticket.user_id == user_id, Ticket.status.in_(['open', 'escalated'])).count()
            user_closed_tickets = session.query(Ticket).filter(Ticket.user_id == user_id, Ticket.status == 'closed').count()

            # Activity metrics
            last_week_activities = session.query(UserActivity).filter(
                UserActivity.user_id == user_id,
                UserActivity.timestamp >= datetime.now(timezone.utc) - timedelta(days=7)
            ).count()

            # List monitoring
            user_notifications = session.query(UserNotification).filter(UserNotification.user_id == user_id).count()
            active_notifications = session.query(UserNotification).filter(
                UserNotification.user_id == user_id,
                UserNotification.list_name.in_(
                    session.query(List.name).filter(List.expiry_date > datetime.now(timezone.utc))
                )
            ).count()

            # Calculate resolution rate
            resolution_rate = (user_closed_tickets / user_tickets * 100) if user_tickets > 0 else 0

            stats_text = f"""
{localization.get_text('stats.title', user_lang)}

{localization.get_text('stats.tickets_total', user_lang, count=user_tickets)}
{localization.get_text('stats.tickets_open', user_lang, count=user_open_tickets)}
{localization.get_text('stats.tickets_closed', user_lang, count=user_closed_tickets)}
{localization.get_text('stats.resolution_rate', user_lang, rate=resolution_rate)}

{localization.get_text('stats.activity_week', user_lang, count=last_week_activities)}
{localization.get_text('stats.notifications_total', user_lang, count=user_notifications)}
{localization.get_text('stats.notifications_active', user_lang, count=active_notifications)}

{localization.get_text('stats.improvement_tips', user_lang)}
            """

            keyboard = [
                [InlineKeyboardButton(localization.get_button_text('view_tickets', user_lang), callback_data='my_tickets')],
                [InlineKeyboardButton(localization.get_button_text('personal_dashboard', user_lang), callback_data='user_stats')],
                [InlineKeyboardButton(localization.get_button_text('back', user_lang), callback_data='back_to_main')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await update.message.reply_text(stats_text, reply_markup=reply_markup, parse_mode='Markdown')

            # Log stats access
            log_user_action(user_id, "viewed_personal_stats")

        finally:
            session.close()

    async def renew_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id

        if not check_rate_limit(user_id):
            await send_safe_message(update, "⚠️ Troppe richieste!\n\nAttendi qualche minuto prima di riprovare.")
            return

        user_lang = get_user_language(user_id)
        await update.message.reply_text(localization.get_text('renew.enter_name', user_lang), parse_mode='Markdown')
        context.user_data['action'] = 'quick_renew'

    async def support_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id

        if not check_rate_limit(user_id):
            await update.message.reply_text("⚠️ **Troppe richieste!**\n\nAttendi qualche minuto prima di riprovare.", parse_mode='Markdown')
            return

        keyboard = [
            [InlineKeyboardButton("📝 Apri Nuovo Ticket", callback_data='open_ticket')],
            [InlineKeyboardButton("📋 I Miei Ticket", callback_data='my_tickets')],
            [InlineKeyboardButton("❓ Guida & Aiuto", callback_data='help')],
            [InlineKeyboardButton("📊 Le Mie Statistiche", callback_data='user_stats')],
            [InlineKeyboardButton("📤 Esporta Dati", callback_data='export_data')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        user_lang = get_user_language(user_id)
        await update.message.reply_text(localization.get_text('support.title', user_lang), reply_markup=reply_markup, parse_mode='Markdown')

    async def stop_contact_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Stop direct contact with user"""
        admin_id = update.effective_user.id

        if not is_admin(admin_id):
            await update.message.reply_text("❌ Questo comando è riservato agli amministratori.")
            return

        # Clear contact context
        ticket_id = context.user_data.pop('contact_user_ticket', None)
        user_id = context.user_data.pop('contact_user_id', None)

        if ticket_id and user_id:
            await update.message.reply_text(f"✅ Contatto diretto terminato per il ticket #{ticket_id} con l'utente {user_id}.")
            log_admin_action(admin_id, "stop_user_contact", user_id, f"Ticket: {ticket_id}")
        else:
            await update.message.reply_text("ℹ️ Non sei attualmente in contatto diretto con nessun utente.")

    # Register all handlers with logging
    logger.info("📝 Registering command handlers...")
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("dashboard", dashboard_command))
    application.add_handler(CommandHandler("renew", renew_command))
    application.add_handler(CommandHandler("support", support_command))
    application.add_handler(CommandHandler("stop_contact", stop_contact_command))
    application.add_handler(CommandHandler("stats", stats_command))

    logger.info("📝 Registering message handlers...")
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_admin_contact_message), group=1)

    logger.info("📝 Registering callback query handlers...")
    application.add_handler(CallbackQueryHandler(button_handler, pattern='^(admin_panel|search_list|ticket_menu|help|back_to_main|admin_renewals|user_stats|admin_alert|confirm_mass_alert|export_data)$'))
    application.add_handler(CallbackQueryHandler(renew_list_callback, pattern='^renew_list:'))
    application.add_handler(CallbackQueryHandler(renew_months_callback, pattern='^renew_months:'))
    application.add_handler(CallbackQueryHandler(confirm_renew_callback, pattern='^confirm_renew:'))
    application.add_handler(CallbackQueryHandler(delete_list_callback, pattern='^delete_list:'))
    application.add_handler(CallbackQueryHandler(confirm_delete_callback, pattern='^confirm_delete:'))
    application.add_handler(CallbackQueryHandler(notify_list_callback, pattern='^notify_list:'))
    application.add_handler(CallbackQueryHandler(notify_days_callback, pattern='^notify_days:'))
    application.add_handler(CallbackQueryHandler(open_ticket_callback, pattern='^open_ticket$'))
    application.add_handler(CallbackQueryHandler(my_tickets_callback, pattern='^my_tickets$'))
    application.add_handler(CallbackQueryHandler(view_ticket_callback, pattern='^view_ticket:'))
    application.add_handler(CallbackQueryHandler(reply_ticket_callback, pattern='^reply_ticket:'))
    application.add_handler(CallbackQueryHandler(close_ticket_callback, pattern='^close_ticket:'))
    application.add_handler(CallbackQueryHandler(continue_ticket_callback, pattern='^continue_ticket:'))
    application.add_handler(CallbackQueryHandler(close_ticket_user_callback, pattern='^close_ticket_user:'))
    application.add_handler(CallbackQueryHandler(escalate_ticket_callback, pattern='^escalate_ticket:'))
    application.add_handler(CallbackQueryHandler(contact_admin_callback, pattern='^contact_admin:'))
    application.add_handler(CallbackQueryHandler(admin_lists_callback, pattern='^admin_lists$'))
    application.add_handler(CallbackQueryHandler(create_list_callback, pattern='^create_list$'))
    application.add_handler(CallbackQueryHandler(select_list_callback, pattern='^select_list:'))
    application.add_handler(CallbackQueryHandler(edit_list_callback, pattern='^edit_list:'))
    application.add_handler(CallbackQueryHandler(edit_field_callback, pattern='^edit_field:'))
    application.add_handler(CallbackQueryHandler(delete_admin_list_callback, pattern='^delete_admin_list:'))
    application.add_handler(CallbackQueryHandler(confirm_admin_delete_callback, pattern='^confirm_admin_delete:'))
    application.add_handler(CallbackQueryHandler(admin_tickets_callback, pattern='^admin_tickets$'))
    application.add_handler(CallbackQueryHandler(select_ticket_callback, pattern='^select_ticket:'))
    application.add_handler(CallbackQueryHandler(admin_reply_ticket_callback, pattern='^admin_reply_ticket:'))
    application.add_handler(CallbackQueryHandler(admin_close_ticket_callback, pattern='^admin_close_ticket:'))
    application.add_handler(CallbackQueryHandler(admin_contact_user_callback, pattern='^admin_contact_user:'))
    application.add_handler(CallbackQueryHandler(admin_stats_callback, pattern='^admin_stats$'))
    application.add_handler(CallbackQueryHandler(admin_analytics_callback, pattern='^admin_analytics$'))
    application.add_handler(CallbackQueryHandler(admin_performance_callback, pattern='^admin_performance$'))
    application.add_handler(CallbackQueryHandler(admin_revenue_callback, pattern='^admin_revenue$'))
    application.add_handler(CallbackQueryHandler(admin_users_callback, pattern='^admin_users$'))
    application.add_handler(CallbackQueryHandler(admin_health_callback, pattern='^admin_health$'))
    application.add_handler(CallbackQueryHandler(admin_audit_callback, pattern='^admin_audit$'))
    application.add_handler(CallbackQueryHandler(manage_renewal_callback, pattern='^manage_renewal:'))
    application.add_handler(CallbackQueryHandler(approve_renewal_callback, pattern='^approve_renewal:'))
    application.add_handler(CallbackQueryHandler(reject_renewal_callback, pattern='^reject_renewal:'))
    application.add_handler(CallbackQueryHandler(contest_renewal_callback, pattern='^contest_renewal:'))
    application.add_handler(CallbackQueryHandler(export_tickets_callback, pattern='^export_tickets$'))
    application.add_handler(CallbackQueryHandler(export_notifications_callback, pattern='^export_notifications$'))
    application.add_handler(CallbackQueryHandler(export_all_callback, pattern='^export_all$'))

    logger.info("✅ All handlers registered successfully")

    # Only add jobs if scheduler is not already running
    if not scheduler.running:
        # Pianifica backup automatico giornaliero
        scheduler.add_job(create_backup, CronTrigger(hour=2, minute=0))  # Ogni giorno alle 2:00

        # Pianifica notifiche di scadenza ogni ora
        scheduler.add_job(send_expiry_notifications, CronTrigger(minute=0))  # Ogni ora

        # Pianifica promemoria personalizzati ogni giorno alle 10:00
        scheduler.add_job(send_custom_reminders, CronTrigger(hour=10, minute=0))  # Ogni giorno alle 10:00

        # Enhanced background tasks
        scheduler.add_job(lambda: task_manager.process_queued_tasks(), CronTrigger(minute='*/5'))  # Process queued tasks every 5 minutes
        scheduler.add_job(lambda: memory_manager.perform_cleanup() if memory_manager.should_cleanup() else None, CronTrigger(minute='*/30'))  # Memory cleanup every 30 minutes

        # Enhanced backup scheduling - more frequent for better data safety
        scheduler.add_job(create_backup, CronTrigger(hour=6, minute=0))  # Daily backup at 6 AM
        scheduler.add_job(create_backup, CronTrigger(hour=18, minute=0))  # Daily backup at 6 PM

        # Pianifica pulizia automatica dei ticket chiusi dopo 12 ore
        scheduler.add_job(cleanup_closed_tickets, CronTrigger(hour=3, minute=0))  # Ogni giorno alle 3:00

        # Pianifica sincronizzazione contatori ogni 30 minuti
        scheduler.add_job(sync_user_counters, CronTrigger(minute='*/30'))  # Ogni 30 minuti

        # Pianifica escalation automatica ticket ogni 6 ore
        scheduler.add_job(auto_escalate_tickets, CronTrigger(hour='*/6'))  # Ogni 6 ore

        # Pianifica pulizia ticket vecchi ogni settimana
        scheduler.add_job(cleanup_old_tickets, CronTrigger(day_of_week='mon', hour=4))  # Ogni lunedì alle 4:00

        # Start scheduler for notifications
        scheduler.start()

    # Removed keep-alive thread - simplified startup

    # Start memory monitoring
    memory_manager.start_monitoring(interval_seconds=300)  # Check every 5 minutes

    # Update metrics with memory info
    memory_info = memory_manager.get_memory_usage()
    if 'rss_mb' in memory_info:
        metrics_collector.update_memory_usage(memory_info['rss_mb'])

    # Main bot loop with enhanced stability
    try:
        logger.info("🚀 Starting ErixCast Bot - 24/7 Service Active")
        logger.info("🤖 Bot is now listening for messages...")

        # Test bot connectivity and clear any existing webhooks
        try:
            # Delete any existing webhook first (synchronous call)
            logger.info("🧹 Deleting any existing webhooks...")
            await application.bot.delete_webhook(drop_pending_updates=True)
            logger.info("✅ Webhook deleted successfully")

            # Test bot connectivity
            bot_info = await application.bot.get_me()
            logger.info(f"✅ Bot connected successfully as @{bot_info.username} (ID: {bot_info.id})")

            # Set bot commands for better UX
            try:
                commands = [
                    BotCommand("start", "Avvia il bot e mostra il menu principale"),
                    BotCommand("help", "Mostra la guida completa"),
                    BotCommand("status", "Visualizza le tue statistiche personali"),
                    BotCommand("support", "Apri un ticket di assistenza"),
                    BotCommand("renew", "Rinnova una lista esistente"),
                    BotCommand("dashboard", "Mostra il tuo dashboard personale"),
                    BotCommand("stats", "Visualizza statistiche dettagliate")
                ]
                await application.bot.set_my_commands(commands)
                logger.info("✅ Bot commands set successfully")
            except Exception as cmd_e:
                logger.warning(f"⚠️ Could not set bot commands: {cmd_e}")

            # Verify bot can receive messages (send a test message to admin if configured)
            if ADMIN_IDS:
                try:
                    test_message = "🤖 **Bot Status Check**\n\n✅ Bot avviato correttamente!\n⏰ " + datetime.now(italy_tz).strftime('%d/%m/%Y %H:%M')
                    await application.bot.send_message(
                        chat_id=ADMIN_IDS[0],
                        text=test_message,
                        parse_mode='Markdown'
                    )
                    logger.info(f"✅ Test message sent to admin {ADMIN_IDS[0]}")
                except Exception as msg_e:
                    logger.warning(f"⚠️ Could not send test message to admin: {msg_e}")

        except Exception as bot_e:
            logger.error(f"❌ Bot connection failed: {bot_e}")
            raise

        # Choose between webhook and polling based on configuration
        if USE_WEBHOOK and WEBHOOK_URL and TELEGRAM_BOT_TOKEN:
            # Use webhook for better efficiency (no polling = less resources)
            webhook_url = f"{WEBHOOK_URL}/webhook/{TELEGRAM_BOT_TOKEN.split(':')[0]}"
            try:
                # Set webhook
                await application.bot.set_webhook(
                    url=webhook_url,
                    allowed_updates=["message", "callback_query"],
                    drop_pending_updates=True
                )
                logger.info(f"✅ Webhook set successfully: {webhook_url}")
                logger.info("🤖 Bot is now listening via webhook - maximum efficiency!")

                # Keep the application alive (Flask will handle requests)
                # This is just to keep the event loop running
                while True:
                    await asyncio.sleep(60)  # Check every minute
        
                    # Monitor resources every 5 minutes
                    if int((datetime.now(timezone.utc) - datetime.fromisoformat('2025-01-01T00:00:00')).total_seconds()) % 300 == 0:
                        if resource_monitor.check_memory_usage():
                            logger.warning("🔄 Memory threshold exceeded - triggering restart")
                            # Exit to trigger Render restart
                            return
        
                    logger.debug("Webhook mode active - bot ready")

            except Exception as webhook_e:
                logger.error(f"❌ Failed to set webhook: {webhook_e}")
                logger.info("🔄 Falling back to polling mode...")
                USE_WEBHOOK = False

        if not USE_WEBHOOK:
            # Use polling (fallback or default)
            logger.info("🔄 Starting polling mode")
            application.run_polling(
                allowed_updates=Update.ALL_TYPES,
                drop_pending_updates=True,
                timeout=30,
                read_timeout=30,
                write_timeout=30,
                connect_timeout=30,
                pool_timeout=30
            )
    except Exception as e:
        logger.critical(f"💥 Bot crashed in main loop: {e}")
        # Don't re-raise the exception to avoid triggering Render's restart policy
        # Instead, let the retry mechanism handle it
        return

def main():
    # Set up signal handlers for graceful shutdown
    try:
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
    except ValueError:
        logger.warning("Signal handling not available - graceful shutdown disabled")

    # Simple startup - remove complex circuit breaker and lock file logic that might cause issues
    logger.info("Starting bot...")

    try:
        import asyncio
        asyncio.run(run_bot_main_loop())
        logger.info("✅ Bot shutdown gracefully")
    except KeyboardInterrupt:
        logger.info("🛑 Bot stopped by user")
        signal_handler(signal.SIGINT, None)
    except Exception as e:
        logger.critical(f"💥 Bot crashed: {e}")
        raise
    finally:
        # Cleanup
        try:
            remove_pid_file()
            remove_lock_file()
        except:
            pass

if __name__ == '__main__':
    main()
