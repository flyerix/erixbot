import os
import logging
import psycopg2
import json
from datetime import datetime
from psycopg2.extras import RealDictCursor

# Configurazione logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

def get_db_connection():
    """Restituisce una connessione al database"""
    return psycopg2.connect(os.getenv('DATABASE_URL'), cursor_factory=RealDictCursor)

def init_database():
    """Inizializza il database e crea le tabelle se non esistono"""
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

# ==================== NUOVE FUNZIONI PER BOT SEMPLIFICATO ====================

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
