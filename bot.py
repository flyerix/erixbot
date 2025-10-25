import os
import logging
import json
from datetime import datetime, timedelta
import asyncio
from threading import Thread
import time
import traceback

# Configurazione logging (deve essere prima di tutto)
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Telegram Bot imports
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters

# Flask imports for webhook
from flask import Flask, request, jsonify

# Database imports (optional for testing)
try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
    DATABASE_AVAILABLE = True
except ImportError:
    logger.warning("psycopg2 non disponibile - database disabilitato per test locale")
    DATABASE_AVAILABLE = False

# Flask app for webhook
app = Flask(__name__)

# Telegram bot configuration
TELEGRAM_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
if not TELEGRAM_TOKEN:
    logger.error("TELEGRAM_BOT_TOKEN non configurato!")
    exit(1)

# Global application instance
application = None

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint per Render"""
    return jsonify({"status": "healthy", "timestamp": datetime.now().isoformat()}), 200

@app.route('/webhook', methods=['POST'])
def webhook_handler():
    """Webhook handler per Telegram"""
    if not application:
        logger.error("Bot non inizializzato")
        return jsonify({"error": "Bot not initialized"}), 500

    try:
        # Log per debugging
        logger.info(f"Ricevuta richiesta webhook: {request.method} {request.url}")
        logger.info(f"Headers: {dict(request.headers)}")

        # Process webhook data
        data = request.get_json(force=True)
        if data:
            logger.info(f"Dati webhook: {json.dumps(data, indent=2)}")

            # Crea update object
            update = Update.de_json(data, application.bot)
            if update:
                # Processa l'update in modo async
                try:
                    import asyncio
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    loop.run_until_complete(application.process_update(update))
                    loop.close()
                    logger.info("Update processato con successo")
                except Exception as e:
                    logger.error(f"Errore processamento update: {e}")
                    return jsonify({"error": f"Update processing failed: {str(e)}"}), 500
            else:
                logger.warning("Update è None")
                return jsonify({"error": "Invalid update data"}), 400
        else:
            logger.warning("Nessun dato JSON ricevuto")
            return jsonify({"error": "No JSON data received"}), 400

        return jsonify({"status": "ok"}), 200

    except Exception as e:
        logger.error(f"Errore webhook: {e}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500

# Aggiungi anche un endpoint per il token per compatibilità
@app.route('/<bot_token>', methods=['POST'])
def webhook_token_handler(bot_token):
    """Webhook handler per URL con token (compatibilità)"""
    try:
        logger.info(f"Ricevuta richiesta con token: {bot_token}")
        logger.info(f"Request data: {request.get_data(as_text=True)}")

        # Verifica se il token è corretto
        if bot_token != TELEGRAM_TOKEN:
            logger.error(f"Token non valido: {bot_token}")
            return jsonify({"error": "Invalid token"}), 401

        # Processa come webhook normale
        return webhook_handler()
    except Exception as e:
        logger.error(f"Errore webhook token: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/')
def root():
    """Root endpoint"""
    return jsonify({"message": "Erix Bot is running!", "version": "1.0"}), 200

def init_bot():
    """Inizializza il bot Telegram"""
    global application
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    # Registra i gestori di comandi
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CallbackQueryHandler(handle_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    return application

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestisce il comando /start"""
    user = update.effective_user
    telegram_id = user.id

    # Registra utente nel database solo se disponibile
    if DATABASE_AVAILABLE:
        try:
            conn = get_db_connection()
            cur = conn.cursor()

            # Controlla se utente esiste già
            cur.execute("SELECT id FROM users WHERE telegram_id = %s", (telegram_id,))
            existing_user = cur.fetchone()

            if not existing_user:
                cur.execute("""
                    INSERT INTO users (telegram_id, username, full_name)
                    VALUES (%s, %s, %s)
                """, (telegram_id, user.username, user.full_name))
                conn.commit()
                logger.info(f"Nuovo utente registrato: {telegram_id}")
            else:
                logger.info(f"Utente esistente: {telegram_id}")

            cur.close()
            conn.close()
        except Exception as e:
            logger.error(f"Errore registrazione utente: {e}")
    else:
        logger.info(f"Bot avviato da utente {telegram_id} (database non disponibile)")

    welcome_text = (
        "🤖 *Benvenuto in Erix Bot!*\n\n"
        "Sono il tuo assistente personale per:\n"
        "• 🎫 Gestione ticket di supporto\n"
        "• 📝 Promemoria intelligenti\n"
        "• 📋 Liste personali con scadenze\n"
        "• 🔥 Offerte Fire TV Stick\n\n"
        "Usa /help per vedere tutti i comandi disponibili!"
    )

    await update.message.reply_markdown(welcome_text)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestisce il comando /help"""
    help_text = (
        "📖 *Guida Comandi Erix Bot*\n\n"
        "*Comandi utente:*\n"
        "/start - Avvia il bot\n"
        "/help - Mostra questa guida\n"
        "/ticket <testo> - Apri un ticket\n"
        "/cerca <nome> - Cerca una lista\n"
        "/promemoria - Imposta preferenze notifiche\n"
        "/miei_ticket - Elenca i tuoi ticket\n"
        "/firestick - Menu offerte Fire TV Stick\n\n"
        "*Solo admin:*\n"
        "/admin - Pannello gestione admin\n\n"
        "💡 *Suggerimento:* Per le offerte Fire TV Stick, usa il pulsante qui sotto!"
    )

    keyboard = [[InlineKeyboardButton("🔥 Offerte Fire TV Stick", callback_data="firestick_menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_markdown(help_text, reply_markup=reply_markup)

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestisce i callback dei pulsanti inline"""
    query = update.callback_query
    await query.answer()

    if query.data == "firestick_menu":
        await query.edit_message_text(
            "🔥 *Menu Offerte Fire TV Stick*\n\n"
            "Scegli un'opzione:\n"
            "• Attiva notifiche per offerte\n"
            "• Disattiva notifiche\n"
            "• Visualizza offerte attuali\n\n"
            "Usa il comando /firestick per gestire le tue preferenze!",
            parse_mode="Markdown"
        )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestisce i messaggi di testo"""
    await update.message.reply_text("📝 Usa i comandi per interagire con me! Usa /help per vedere tutti i comandi disponibili.")

def get_db_connection():
    """Restituisce una connessione al database"""
    if not DATABASE_AVAILABLE:
        raise Exception("Database non disponibile - psycopg2 non installato")
    return psycopg2.connect(os.getenv('DATABASE_URL'), cursor_factory=RealDictCursor)

def init_database():
    """Inizializza il database e crea le tabelle se non esistono"""
    if not DATABASE_AVAILABLE:
        logger.warning("Database non disponibile - skip inizializzazione")
        return
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Tabella utenti
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                telegram_id BIGINT UNIQUE NOT NULL,
                username VARCHAR(255),
                full_name VARCHAR(255),
                is_admin BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT NOW()
            );
        """)
        
        # Tabella liste
        cur.execute("""
            CREATE TABLE IF NOT EXISTS lists (
                id SERIAL PRIMARY KEY,
                name VARCHAR(255) UNIQUE NOT NULL,
                cost DECIMAL(10,2),
                expiration_date DATE,
                notes TEXT,
                created_by INTEGER REFERENCES users(id),
                created_at TIMESTAMP DEFAULT NOW()
            );
        """)
        
        # Tabella ticket
        cur.execute("""
            CREATE TABLE IF NOT EXISTS tickets (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id),
                subject VARCHAR(255),
                status VARCHAR(50) DEFAULT 'open',
                is_ai_responded BOOLEAN DEFAULT FALSE,
                sentiment VARCHAR(10),
                urgency VARCHAR(10) DEFAULT 'medium',
                created_at TIMESTAMP DEFAULT NOW(),
                closed_at TIMESTAMP
            );
        """)
        
        # Tabella iscrizioni alle notifiche di scadenza liste
        cur.execute("""
            CREATE TABLE IF NOT EXISTS list_subscriptions (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                list_id INTEGER REFERENCES lists(id) ON DELETE CASCADE,
                notify_days_before INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT NOW(),
                UNIQUE (user_id, list_id)
            );
        """)

        # Preferenze utente per promemoria
        cur.execute("""
            CREATE TABLE IF NOT EXISTS user_prefs (
                user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
                default_notify_days_before INTEGER DEFAULT 1,
                quiet_hours_start INTEGER,
                quiet_hours_end INTEGER,
                timezone TEXT
            );
        """)

        # Deduplica notifiche inviate
        cur.execute("""
            CREATE TABLE IF NOT EXISTS list_notifications_sent (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                list_id INTEGER REFERENCES lists(id) ON DELETE CASCADE,
                notify_for_date DATE NOT NULL,
                created_at TIMESTAMP DEFAULT NOW(),
                UNIQUE (user_id, list_id, notify_for_date)
            );
        """)

        # Multi-promemoria per lista (giorni multipli per utente/lista)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS list_subscription_notifications (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                list_id INTEGER REFERENCES lists(id) ON DELETE CASCADE,
                days_before INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT NOW(),
                UNIQUE (user_id, list_id, days_before)
            );
        """)
        
        # Tabella messaggi ticket
        cur.execute("""
            CREATE TABLE IF NOT EXISTS ticket_messages (
                id SERIAL PRIMARY KEY,
                ticket_id INTEGER REFERENCES tickets(id),
                user_id INTEGER REFERENCES users(id),
                message TEXT,
                is_from_admin BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT NOW()
            );
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS firestick_subscriptions (
                user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
                created_at TIMESTAMP DEFAULT NOW()
            );
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS firestick_deals_sent (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                deal_hash TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT NOW(),
                UNIQUE (user_id, deal_hash)
            );
        """)
        
        # Tabella per tracciare i rinnovi degli abbonamenti
        cur.execute("""
            CREATE TABLE IF NOT EXISTS list_renewals (
                id SERIAL PRIMARY KEY,
                list_id INTEGER REFERENCES lists(id) ON DELETE CASCADE,
                user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                months INTEGER NOT NULL,
                old_expiration DATE,
                new_expiration DATE,
                created_at TIMESTAMP DEFAULT NOW()
            );
        """)
        
        # Tabella per richieste di rinnovo pendenti (in attesa di approvazione admin)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS renewal_requests (
                id SERIAL PRIMARY KEY,
                list_id INTEGER REFERENCES lists(id) ON DELETE CASCADE,
                user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                months INTEGER NOT NULL,
                requested_by INTEGER REFERENCES users(id),
                status VARCHAR(20) DEFAULT 'pending', -- pending, approved, rejected, contacted
                admin_notes TEXT,
                old_expiration DATE,
                new_expiration DATE,
                created_at TIMESTAMP DEFAULT NOW(),
                processed_at TIMESTAMP,
                processed_by INTEGER REFERENCES users(id)
            );
        """)
        
        # Tabella blacklist/whitelist utenti
        cur.execute("""
            CREATE TABLE IF NOT EXISTS user_restrictions (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                restriction_type VARCHAR(20) NOT NULL, -- 'blacklist', 'whitelist'
                reason TEXT,
                restricted_by INTEGER REFERENCES users(id),
                created_at TIMESTAMP DEFAULT NOW(),
                expires_at TIMESTAMP,
                is_active BOOLEAN DEFAULT TRUE,
                UNIQUE (user_id, restriction_type)
            );
        """)

        # Tabella per rate limiting anti-spam
        cur.execute("""
            CREATE TABLE IF NOT EXISTS rate_limit_log (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                command VARCHAR(100),
                timestamp TIMESTAMP DEFAULT NOW(),
                ip_address VARCHAR(45)
            );
        """)

        # Tabella per sistema undo/redo
        cur.execute("""
            CREATE TABLE IF NOT EXISTS operation_history (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                operation_type VARCHAR(50) NOT NULL, -- 'create', 'update', 'delete'
                table_name VARCHAR(50) NOT NULL,
                record_id INTEGER,
                old_data JSONB,
                new_data JSONB,
                created_at TIMESTAMP DEFAULT NOW()
            );
        """)

        # Tabella per auto-complete e suggerimenti
        cur.execute("""
            CREATE TABLE IF NOT EXISTS command_suggestions (
                id SERIAL PRIMARY KEY,
                command VARCHAR(100) UNIQUE NOT NULL,
                usage_count INTEGER DEFAULT 0,
                last_used TIMESTAMP DEFAULT NOW()
            );
        """)

        # Crea indici per migliorare le performance
        cur.execute("CREATE INDEX IF NOT EXISTS idx_users_telegram_id ON users(telegram_id);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_tickets_user_id ON tickets(user_id);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_tickets_status ON tickets(status);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_ticket_messages_ticket_id ON ticket_messages(ticket_id);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_lists_name ON lists(name);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_list_subscriptions_user_list ON list_subscriptions(user_id, list_id);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_lists_expiration_date ON lists(expiration_date);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_notifications_sent_user_list_date ON list_notifications_sent(user_id, list_id, notify_for_date);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_sub_notif_user_list_day ON list_subscription_notifications(user_id, list_id, days_before);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_firestick_deals_sent_user_hash ON firestick_deals_sent(user_id, deal_hash);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_list_renewals_list_user ON list_renewals(list_id, user_id);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_renewal_requests_status ON renewal_requests(status);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_renewal_requests_list_user ON renewal_requests(list_id, user_id);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_user_restrictions_user_type ON user_restrictions(user_id, restriction_type);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_user_restrictions_active ON user_restrictions(is_active, expires_at);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_rate_limit_user_time ON rate_limit_log(user_id, timestamp);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_operation_history_user ON operation_history(user_id);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_command_suggestions_usage ON command_suggestions(usage_count DESC, last_used DESC);")
        
        # Migrazione per aggiungere le colonne mancanti se esistono tabelle vecchie
        try:
            cur.execute("ALTER TABLE tickets ADD COLUMN IF NOT EXISTS sentiment VARCHAR(10);")
            cur.execute("ALTER TABLE tickets ADD COLUMN IF NOT EXISTS urgency VARCHAR(10) DEFAULT 'medium';")
            cur.execute("ALTER TABLE renewal_requests ADD COLUMN IF NOT EXISTS old_expiration DATE;")
            cur.execute("ALTER TABLE renewal_requests ADD COLUMN IF NOT EXISTS new_expiration DATE;")
            # Aggiungi colonna updated_at se non esiste
            cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT NOW();")
            logger.info("Migrazione database completata - colonne aggiunte con successo")
        except Exception as migration_error:
            logger.warning(f"Migrazione non necessaria o già eseguita: {migration_error}")
            conn.rollback()  # Rollback per continuare con il commit principale
        
        conn.commit()
        cur.close()
        conn.close()
        
        logger.info("Database inizializzato con successo")
        return True
        
    except Exception as e:
        logger.error(f"Errore nell'inizializzazione del database: {e}")
        return False

def check_database_connection():
    """Verifica la connessione al database"""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT 1;")
        cur.close()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Errore di connessione al database: {e}")
        return False

def get_database_stats():
    """Restituisce statistiche del database"""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        stats = {}
        
        # Conteggio record per tabella
        tables = ['users', 'lists', 'tickets', 'ticket_messages']
        for table in tables:
            cur.execute(f"SELECT COUNT(*) FROM {table};")
            stats[table] = cur.fetchone()[0]
        
        # Dimensione database
        cur.execute("""
            SELECT pg_size_pretty(pg_database_size(current_database()));
        """)
        stats['db_size'] = cur.fetchone()[0]
        
        cur.close()
        conn.close()
        
        return stats
        
    except Exception as e:
        logger.error(f"Errore nel recupero statistiche database: {e}")
        return {}

def check_user_restriction(telegram_id: int, restriction_type: str) -> bool:
    """Verifica se un utente ha una restrizione attiva"""
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute("""
            SELECT ur.is_active, ur.expires_at
            FROM user_restrictions ur
            JOIN users u ON ur.user_id = u.id
            WHERE u.telegram_id = %s AND ur.restriction_type = %s
            AND ur.is_active = true
            AND (ur.expires_at IS NULL OR ur.expires_at > NOW())
        """, (telegram_id, restriction_type))

        result = cur.fetchone()
        return result is not None

    except Exception as e:
        logger.error(f"Error checking user restriction: {e}")
        return False
    finally:
        if 'cur' in locals():
            cur.close()
        if 'conn' in locals():
            conn.close()

def add_user_restriction(telegram_id: int, restriction_type: str, reason: str = None,
                        restricted_by: int = None, expires_at: datetime = None):
    """Aggiunge una restrizione utente"""
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute("""
            INSERT INTO user_restrictions (user_id, restriction_type, reason, restricted_by, expires_at)
            SELECT u.id, %s, %s, %s, %s
            FROM users u WHERE u.telegram_id = %s
            ON CONFLICT (user_id, restriction_type) DO UPDATE SET
                reason = EXCLUDED.reason,
                restricted_by = EXCLUDED.restricted_by,
                expires_at = EXCLUDED.expires_at,
                is_active = true
        """, (restriction_type, reason, restricted_by, expires_at, telegram_id))

        conn.commit()
        logger.info(f"User {telegram_id} {'blacklisted' if restriction_type == 'blacklist' else 'whitelisted'}")

    except Exception as e:
        logger.error(f"Error adding user restriction: {e}")
    finally:
        if 'cur' in locals():
            cur.close()
        if 'conn' in locals():
            conn.close()

def remove_user_restriction(telegram_id: int, restriction_type: str):
    """Rimuove una restrizione utente"""
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute("""
            UPDATE user_restrictions SET is_active = false
            WHERE user_id = (SELECT id FROM users WHERE telegram_id = %s)
            AND restriction_type = %s
        """, (telegram_id, restriction_type))

        conn.commit()
        logger.info(f"Removed {restriction_type} for user {telegram_id}")

    except Exception as e:
        logger.error(f"Error removing user restriction: {e}")
    finally:
        if 'cur' in locals():
            cur.close()
        if 'conn' in locals():
            conn.close()

def check_rate_limit(user_id: int, command: str, max_requests: int = 5, window_seconds: int = 60):
    """Verifica rate limit per utente"""
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        # Conta richieste nell'ultima finestra temporale
        cur.execute("""
            SELECT COUNT(*) FROM rate_limit_log
            WHERE user_id = %s AND command = %s
            AND timestamp >= NOW() - INTERVAL '%s seconds'
        """, (user_id, command, window_seconds))

        request_count = cur.fetchone()[0]

        # Log della richiesta
        cur.execute("""
            INSERT INTO rate_limit_log (user_id, command, timestamp)
            VALUES (%s, %s, NOW())
        """, (user_id, command))

        conn.commit()

        return request_count >= max_requests

    except Exception as e:
        logger.error(f"Error checking rate limit: {e}")
        return False
    finally:
        if 'cur' in locals():
            cur.close()
        if 'conn' in locals():
            conn.close()

def log_operation(user_id: int, operation_type: str, table_name: str, record_id: int,
                 old_data: dict = None, new_data: dict = None):
    """Log operazione per sistema undo/redo"""
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute("""
            INSERT INTO operation_history (user_id, operation_type, table_name, record_id, old_data, new_data)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (user_id, operation_type, table_name, record_id,
              json.dumps(old_data) if old_data else None,
              json.dumps(new_data) if new_data else None))

        conn.commit()

    except Exception as e:
        logger.error(f"Error logging operation: {e}")
    finally:
        if 'cur' in locals():
            cur.close()
        if 'conn' in locals():
            conn.close()

def check_database_extensions():
    """Verifica che le estensioni PostgreSQL necessarie siano installate"""
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        # Verifica estensioni necessarie per ricerca intelligente
        required_extensions = ['pg_trgm']  # Per ricerca full-text con similarità

        for ext in required_extensions:
            cur.execute("SELECT 1 FROM pg_extension WHERE extname = %s", (ext,))
            if not cur.fetchone():
                logger.warning(f"Estensione PostgreSQL '{ext}' non installata. Installala per funzionalità complete.")
                return False

        cur.close()
        conn.close()
        logger.info("✅ Tutte le estensioni database necessarie sono installate")
        return True

    except Exception as e:
        logger.error(f"Error checking database extensions: {e}")
        return False

def undo_last_operation(user_id: int):
    """Annulla l'ultima operazione dell'utente"""
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        # Trova l'ultima operazione
        cur.execute("""
            SELECT id, operation_type, table_name, record_id, old_data, new_data
            FROM operation_history
            WHERE user_id = %s
            ORDER BY created_at DESC
            LIMIT 1
        """, (user_id,))

        result = cur.fetchone()
        if not result:
            return None

        op_id, op_type, table_name, record_id, old_data_json, new_data_json = result

        # Se era una DELETE, ricrea il record
        if op_type == 'delete' and old_data_json:
            old_data = json.loads(old_data_json)
            columns = ', '.join(old_data.keys())
            values = ', '.join(['%s'] * len(old_data))
            cur.execute(f"INSERT INTO {table_name} ({columns}) VALUES ({values})", list(old_data.values()))

        # Se era una CREATE, elimina il record
        elif op_type == 'create' and record_id:
            cur.execute(f"DELETE FROM {table_name} WHERE id = %s", (record_id,))

        # Se era un UPDATE, ripristina i vecchi dati
        elif op_type == 'update' and old_data_json:
            old_data = json.loads(old_data_json)
            set_clause = ', '.join([f"{k} = %s" for k in old_data.keys()])
            cur.execute(f"UPDATE {table_name} SET {set_clause} WHERE id = %s", list(old_data.values()) + [record_id])

        # Rimuovi l'operazione dal log
        cur.execute("DELETE FROM operation_history WHERE id = %s", (op_id,))

        conn.commit()
        return table_name, record_id

    except Exception as e:
        logger.error(f"Error undoing operation: {e}")
        return None
    finally:
        if 'cur' in locals():
            cur.close()
        if 'conn' in locals():
            conn.close()

def get_command_suggestions(partial: str, limit: int = 5):
    """Ottieni suggerimenti comandi per auto-complete"""
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute("""
            SELECT command FROM command_suggestions
            WHERE command ILIKE %s
            ORDER BY usage_count DESC, last_used DESC
            LIMIT %s
        """, (f'{partial}%', limit))

        results = cur.fetchall()
        return [row[0] for row in results]

    except Exception as e:
        logger.error(f"Error getting command suggestions: {e}")
        return []
    finally:
        if 'cur' in locals():
            cur.close()
        if 'conn' in locals():
            conn.close()

def update_command_usage(command: str):
    """Aggiorna contatore uso comando"""
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute("""
            INSERT INTO command_suggestions (command, usage_count, last_used)
            VALUES (%s, 1, NOW())
            ON CONFLICT (command) DO UPDATE SET
                usage_count = command_suggestions.usage_count + 1,
                last_used = NOW()
        """, (command,))

        conn.commit()

    except Exception as e:
        logger.error(f"Error updating command usage: {e}")
    finally:
        if 'cur' in locals():
            cur.close()
        if 'conn' in locals():
            conn.close()

def get_list_suggestions(partial: str, limit: int = 5):
    """Ottieni suggerimenti nomi liste per auto-complete"""
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute("""
            SELECT name FROM lists
            WHERE name ILIKE %s
            ORDER BY name
            LIMIT %s
        """, (f'{partial}%', limit))

        results = cur.fetchall()
        return [row[0] for row in results]

    except Exception as e:
        logger.error(f"Error getting list suggestions: {e}")
        return []
    finally:
        if 'cur' in locals():
            cur.close()
        if 'conn' in locals():
            conn.close()

def get_user_restrictions(limit: int = 50):
    """Ottieni lista restrizioni utenti per admin dashboard"""
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute("""
            SELECT
                u.telegram_id,
                u.full_name,
                ur.restriction_type,
                ur.reason,
                ur.created_at,
                ur.expires_at,
                ur.is_active,
                admin.full_name as restricted_by_name
            FROM user_restrictions ur
            JOIN users u ON ur.user_id = u.id
            LEFT JOIN users admin ON ur.restricted_by = admin.id
            ORDER BY ur.created_at DESC
            LIMIT %s
        """, (limit,))

        return cur.fetchall()

    except Exception as e:
        logger.error(f"Error getting user restrictions: {e}")
        return []
    finally:
        if 'cur' in locals():
            cur.close()
        if 'conn' in locals():
            conn.close()

# ==================== NUOVE FUNZIONI PER BOT COMPLETO ====================

def create_or_update_user(telegram_id, username, full_name):
    """Crea o aggiorna utente nel database"""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO users (telegram_id, username, full_name, created_at)
            VALUES (%s, %s, %s, NOW())
            ON CONFLICT (telegram_id) DO UPDATE SET
                username = EXCLUDED.username,
                full_name = EXCLUDED.full_name
        """, (telegram_id, username, full_name))
        conn.commit()
        cur.close()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Errore create_or_update_user: {e}")
        return False

def get_user_by_telegram_id(telegram_id):
    """Ottiene utente dal database"""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE telegram_id = %s", (telegram_id,))
        user = cur.fetchone()
        cur.close()
        conn.close()
        return user
    except Exception as e:
        logger.error(f"Errore get_user_by_telegram_id: {e}")
        return None

def create_ticket(user_id, description):
    """Crea un nuovo ticket"""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO tickets (user_id, subject, status, created_at)
            VALUES (%s, %s, 'open', NOW())
            RETURNING id
        """, (user_id, description))
        ticket_id = cur.fetchone()['id']
        conn.commit()
        cur.close()
        conn.close()
        return ticket_id
    except Exception as e:
        logger.error(f"Errore create_ticket: {e}")
        return None

def get_user_tickets(user_id):
    """Ottiene i ticket di un utente"""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT id, subject, status, created_at 
            FROM tickets 
            WHERE user_id = %s 
            ORDER BY created_at DESC 
            LIMIT 10
        """, (user_id,))
        tickets = cur.fetchall()
        cur.close()
        conn.close()
        return tickets
    except Exception as e:
        logger.error(f"Errore get_user_tickets: {e}")
        return []

def search_lists(query):
    """Cerca liste nel database"""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT id, name, cost, expiration_date, notes, created_at
            FROM lists 
            WHERE name ILIKE %s
            ORDER BY name
            LIMIT 10
        """, (f'%{query}%',))
        results = cur.fetchall()
        cur.close()
        conn.close()
        return results
    except Exception as e:
        logger.error(f"Errore search_lists: {e}")
        return []

def get_all_tickets(status=None, limit=10):
    """Ottiene tutti i ticket (per admin)"""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        if status:
            cur.execute("""
                SELECT t.*, u.full_name as user_name
                FROM tickets t
                JOIN users u ON t.user_id = u.id
                WHERE t.status = %s
                ORDER BY t.created_at DESC
                LIMIT %s
            """, (status, limit))
        else:
            cur.execute("""
                SELECT t.*, u.full_name as user_name
                FROM tickets t
                JOIN users u ON t.user_id = u.id
                ORDER BY t.created_at DESC
                LIMIT %s
            """, (limit,))
            
        tickets = cur.fetchall()
        cur.close()
        conn.close()
        return tickets
    except Exception as e:
        logger.error(f"Errore get_all_tickets: {e}")
        return []

def close_ticket(ticket_id, admin_id):
    """Chiude un ticket"""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            UPDATE tickets 
            SET status = 'closed', closed_at = NOW()
            WHERE id = %s
        """, (ticket_id,))
        conn.commit()
        cur.close()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Errore close_ticket: {e}")
        return False

def add_new_list(name, cost, expiration_date, notes, created_by):
    """Aggiunge una nuova lista"""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO lists (name, cost, expiration_date, notes, created_by, created_at)
            VALUES (%s, %s, %s, %s, %s, NOW())
        """, (name, cost, expiration_date, notes, created_by))
        conn.commit()
        cur.close()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Errore add_new_list: {e}")
        return False

def update_list(list_id, name=None, cost=None, expiration_date=None, notes=None):
    """Aggiorna una lista esistente"""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        updates = []
        params = []
        
        if name is not None:
            updates.append("name = %s")
            params.append(name)
        if cost is not None:
            updates.append("cost = %s")
            params.append(cost)
        if expiration_date is not None:
            updates.append("expiration_date = %s")
            params.append(expiration_date)
        if notes is not None:
            updates.append("notes = %s")
            params.append(notes)
            
        if updates:
            params.append(list_id)
            cur.execute(f"UPDATE lists SET {', '.join(updates)} WHERE id = %s", params)
            conn.commit()
            
        cur.close()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Errore update_list: {e}")
        return False

def get_all_lists(limit=10):
    """Ottiene tutte le liste"""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT l.*, u.full_name as creator_name
            FROM lists l
            LEFT JOIN users u ON l.created_by = u.id
            ORDER BY l.created_at DESC
            LIMIT %s
        """, (limit,))
        lists = cur.fetchall()
        cur.close()
        conn.close()
        return lists
    except Exception as e:
        logger.error(f"Errore get_all_lists: {e}")
        return []

def start_flask():
    """Avvia il server Flask in un thread separato"""
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 8080)), debug=False)

async def setup_webhook_async():
    """Configura webhook in modo async"""
    try:
        webhook_url = f"https://{os.getenv('RENDER_EXTERNAL_URL')}/webhook"
        logger.info(f"🔄 Configurazione webhook async: {webhook_url}")

        # Prima rimuovi webhook esistente se necessario
        try:
            current_webhook = await application.bot.get_webhook_info()
            logger.info(f"📋 Webhook attuale: {current_webhook}")

            if current_webhook.url and current_webhook.url != webhook_url:
                logger.info(f"🗑️ Rimozione webhook esistente: {current_webhook.url}")
                delete_result = await application.bot.delete_webhook()
                logger.info(f"🗑️ Risultato rimozione: {delete_result}")

                # Attesa per permettere a Telegram di processare la rimozione
                import asyncio
                await asyncio.sleep(1)
        except Exception as e:
            logger.warning(f"⚠️ Errore rimozione webhook esistente: {e}")

        # Configura nuovo webhook con parametri ottimali
        logger.info(f"🔧 Configurazione webhook: {webhook_url}")
        webhook_info = await application.bot.set_webhook(
            url=webhook_url,
            max_connections=100,
            drop_pending_updates=True,
            allowed_updates=["message", "callback_query"]
        )

        logger.info(f"✅ Webhook configurato: {webhook_info}")

        # Verifica webhook dopo un breve delay
        await asyncio.sleep(1)
        webhook_status = await application.bot.get_webhook_info()
        logger.info(f"✅ Webhook status finale: {webhook_status}")

        # Verifica che l'URL sia corretto
        if webhook_status.url == webhook_url:
            logger.info(f"🎉 Webhook configurato correttamente: {webhook_url}")
        else:
            logger.error(f"❌ Webhook URL non corrisponde! Atteso: {webhook_url}, Attuale: {webhook_status.url}")

    except Exception as e:
        logger.error(f"❌ Errore configurazione webhook: {e}")
        logger.error(f"❌ Traceback: {traceback.format_exc()}")

def setup_webhook_after_start():
    """Wrapper per chiamare la funzione async"""
    try:
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(setup_webhook_async())
        loop.close()
    except Exception as e:
        logger.error(f"❌ Errore setup webhook: {e}")

@app.route('/webhook/setup', methods=['POST'])
def manual_webhook_setup():
    """Endpoint per configurare manualmente il webhook"""
    try:
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        webhook_url = f"https://{os.getenv('RENDER_EXTERNAL_URL')}/webhook"
        logger.info(f"🔧 Configurazione webhook manuale: {webhook_url}")

        # Prima verifica status attuale
        try:
            current_webhook = loop.run_until_complete(application.bot.get_webhook_info())
            logger.info(f"📋 Webhook attuale prima del setup: {current_webhook}")
        except Exception as e:
            logger.warning(f"⚠️ Errore verifica webhook esistente: {e}")

        # Rimuovi webhook esistente
        logger.info("🗑️ Rimozione webhook esistente...")
        delete_result = loop.run_until_complete(application.bot.delete_webhook())
        logger.info(f"🗑️ Risultato rimozione: {delete_result}")

        # Attesa per permettere a Telegram di processare
        loop.run_until_complete(asyncio.sleep(1))

        # Configura nuovo webhook
        logger.info(f"🔧 Configurazione webhook: {webhook_url}")
        webhook_info = loop.run_until_complete(application.bot.set_webhook(
            url=webhook_url,
            max_connections=100,
            drop_pending_updates=True,
            allowed_updates=["message", "callback_query"]
        ))

        # Verifica dopo setup
        loop.run_until_complete(asyncio.sleep(1))
        webhook_status = loop.run_until_complete(application.bot.get_webhook_info())

        logger.info(f"✅ Setup completato: {webhook_info}")
        logger.info(f"✅ Status finale: {webhook_status}")

        loop.close()

        return jsonify({
            "status": "success",
            "webhook_url": webhook_url,
            "webhook_info": str(webhook_info),
            "webhook_status": str(webhook_status),
            "render_external_url": os.getenv('RENDER_EXTERNAL_URL'),
            "bot_token_configured": bool(TELEGRAM_TOKEN)
        }), 200

    except Exception as e:
        logger.error(f"❌ Errore setup webhook manuale: {e}")
        logger.error(f"❌ Traceback: {traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500

@app.route('/webhook/delete', methods=['POST'])
def delete_webhook():
    """Endpoint per rimuovere il webhook"""
    try:
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        logger.info("🗑️ Rimozione webhook...")
        result = loop.run_until_complete(application.bot.delete_webhook())
        loop.run_until_complete(asyncio.sleep(1))
        status = loop.run_until_complete(application.bot.get_webhook_info())
        logger.info(f"✅ Webhook rimosso: {result}")
        logger.info(f"✅ Status dopo rimozione: {status}")

        loop.close()

        return jsonify({
            "status": "success",
            "delete_result": str(result),
            "webhook_status": str(status)
        }), 200

    except Exception as e:
        logger.error(f"❌ Errore rimozione webhook: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/webhook/status', methods=['GET'])
def webhook_status():
    """Endpoint per verificare lo status del webhook"""
    try:
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        webhook_info = loop.run_until_complete(application.bot.get_webhook_info())

        loop.close()

        return jsonify({
            "webhook_info": str(webhook_info),
            "render_external_url": os.getenv('RENDER_EXTERNAL_URL'),
            "bot_token_configured": bool(TELEGRAM_TOKEN)
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

def main():
    """Punto di ingresso principale dell'applicazione"""
    logger.info("🚀 Avvio Erix Bot...")

    # Log environment variables per debug
    logger.info(f"🌍 Environment variables:")
    logger.info(f"   RENDER_EXTERNAL_URL: {os.getenv('RENDER_EXTERNAL_URL')}")
    logger.info(f"   TELEGRAM_BOT_TOKEN: {'*' * len(os.getenv('TELEGRAM_BOT_TOKEN', ''))}")
    logger.info(f"   RENDER: {os.getenv('RENDER')}")
    logger.info(f"   DATABASE_URL: {'*' * 20}...")

    # Verifica RENDER_EXTERNAL_URL
    render_external_url = os.getenv('RENDER_EXTERNAL_URL')
    if not render_external_url:
        logger.error("❌ RENDER_EXTERNAL_URL non configurato!")
        logger.error("   Verifica che 'RENDER_EXTERNAL_URL' sia impostato su 'Auto' in Render Dashboard")
        return

    # Inizializza database solo se disponibile
    if DATABASE_AVAILABLE:
        logger.info("📊 Inizializzazione database...")
        init_database()
        logger.info("✅ Database inizializzato")
    else:
        logger.warning("📊 Database non disponibile - bot funzionerà in modalità limitata")

    # Inizializza bot
    logger.info("🤖 Inizializzazione bot Telegram...")
    global application
    application = init_bot()
    logger.info("✅ Bot Telegram inizializzato")

    # Avvia Flask server
    logger.info("🌐 Avvio server Flask...")
    port = int(os.getenv('PORT', 8080))

    # Configura webhook dopo un breve delay per permettere al server di avviarsi
    if render_external_url:
        import threading
        threading.Timer(2.0, setup_webhook_after_start).start()
        logger.info("⏰ Webhook sarà configurato tra 2 secondi...")

    logger.info(f"🌐 Server Flask in avvio su porta {port}...")
    app.run(host='0.0.0.0', port=port, debug=False)

if __name__ == "__main__":
    main()
