import logging
import os
import asyncio
from datetime import datetime, timedelta, timezone
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove
)
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
    ConversationHandler,
    CallbackQueryHandler,
    JobQueue
)
from aiohttp import web
import psycopg2
from urllib.parse import urlparse

# Configurazione
TOKEN = os.getenv("TELEGRAM_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_CHAT_ID"))
COSTO_MENSILE = 15  # €15 al mese
DATABASE_URL = os.getenv("DATABASE_URL")

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Stati conversazione
LIST_NAME, ACTION_EXISTING, ACTION_NEW, DURATION, REPORT_LIST, REPORT_DETAILS = range(6)

# Funzione per ottenere la connessione al database
def get_db_connection():
    if DATABASE_URL:
        # Configurazione per PostgreSQL (produzione)
        parsed = urlparse(DATABASE_URL)
        conn = psycopg2.connect(
            database=parsed.path[1:],
            user=parsed.username,
            password=parsed.password,
            host=parsed.hostname,
            port=parsed.port,
            sslmode='require'
        )
        return conn
    else:
        # Configurazione per SQLite (sviluppo locale)
        import sqlite3
        return sqlite3.connect("local_db.db")

# Inizializza DB
def init_db():
    conn = get_db_connection()
    cur = conn.cursor()
    
    if DATABASE_URL:  # PostgreSQL
        cur.execute("""
        CREATE TABLE IF NOT EXISTS lists (
            id SERIAL PRIMARY KEY,
            name TEXT UNIQUE,
            owner_id INTEGER,
            status TEXT DEFAULT 'active',
            created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
            expiration TIMESTAMPTZ,
            last_reminder TIMESTAMPTZ
        )
        """)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS requests (
            id SERIAL PRIMARY KEY,
            list_name TEXT,
            user_id INTEGER,
            action TEXT,
            months INTEGER,
            total_cost REAL,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
        )
        """)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS reports (
            id SERIAL PRIMARY KEY,
            list_name TEXT,
            user_id INTEGER,
            problem_details TEXT,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
        )
        """)
    else:  # SQLite
        cur.execute("""
        CREATE TABLE IF NOT EXISTS lists (
            id INTEGER PRIMARY KEY,
            name TEXT UNIQUE,
            owner_id INTEGER,
            status TEXT DEFAULT 'active',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expiration TIMESTAMP,
            last_reminder TIMESTAMP
        )
        """)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS requests (
            id INTEGER PRIMARY KEY,
            list_name TEXT,
            user_id INTEGER,
            action TEXT,
            months INTEGER,
            total_cost REAL,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS reports (
            id INTEGER PRIMARY KEY,
            list_name TEXT,
            user_id INTEGER,
            problem_details TEXT,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
    
    conn.commit()
    conn.close()

# Comando /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        ["📋 Gestisci Lista", "ℹ️ FAQ"],
        ["⚠️ Segnala Problema"]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    await update.message.reply_text(
        "Benvenuto nel gestionale abbonamenti! ✨\n\n"
        "📌 Ogni nuova lista o rinnovo ha un costo di "
        f"€{COSTO_MENSILE} al mese\n\n"
        "Scegli un'opzione dalla tastiera:",
        reply_markup=reply_markup
    )
    return ConversationHandler.END

# Comando /faq
async def faq(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("⚠️ Segnala Problema", callback_data="report_problem")]
    ]
    
    await update.message.reply_text(
        "❓ <b>FAQ - Domande Frequenti</b> ❓\n\n"
        "🔧 <b>Cosa fare se l'applicazione smette di funzionare?</b>\n"
        "1. Spegni la TV e il dispositivo collegato (es. decoder, Chromecast, ecc.)\n"
        "2. Attendi 5-10 minuti\n"
        "3. Riavvia tutti i dispositivi\n\n"
        "Se il problema persiste dopo questo riavvio:\n"
        "• Verifica la connessione internet\n"
        "• Assicurati di avere l'ultima versione dell'app\n"
        "• Contatta l'amministratore usando il pulsante qui sotto ⬇️\n\n"
        "📌 <b>Importante:</b> Prima di contattare l'amministratore, assicurati di avere a portata:\n"
        "- Il nome della lista che stavi usando\n"
        "- Una descrizione precisa del problema",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )

# Avvio segnalazione problema
async def start_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Resetta i dati precedenti
    context.user_data.clear()
    
    await update.message.reply_text(
        "⚠️ <b>SEGNALAZIONE PROBLEMA</b> ⚠️\n\n"
        "Per aiutarti meglio, ho bisogno di sapere:\n"
        "1. Qual è il nome della lista che stavi usando\n"
        "2. Una descrizione precisa del problema\n\n"
        "<b>Inserisci il nome della lista:</b>",
        parse_mode="HTML",
        reply_markup=ReplyKeyboardRemove()
    )
    return REPORT_LIST

# Gestione nome lista per segnalazione
async def handle_report_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    list_name = update.message.text.strip()
    context.user_data["report_list"] = list_name
    
    await update.message.reply_text(
        "📝 <b>Ora descrivi il problema:</b>\n\n"
        "Per favore includi:\n"
        "- Cosa stavi facendo quando è successo\n"
        "- Quale messaggio di errore hai visto (se c'era)\n"
        "- Quando è successo (ora approssimativa)\n"
        "- Ogni altra informazione utile",
        parse_mode="HTML"
    )
    return REPORT_DETAILS

# Gestione dettagli problema
async def handle_report_details(update: Update, context: ContextTypes.DEFAULT_TYPE):
    problem_details = update.message.text.strip()
    list_name = context.user_data["report_list"]
    user_id = update.message.from_user.id
    
    # Salva segnalazione nel DB
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        if DATABASE_URL:  # PostgreSQL
            cur.execute(
                "INSERT INTO reports (list_name, user_id, problem_details) "
                "VALUES (%s, %s, %s) RETURNING id",
                (list_name, user_id, problem_details)
            )
            report_id = cur.fetchone()[0]
        else:  # SQLite
            cur.execute(
                "INSERT INTO reports (list_name, user_id, problem_details) "
                "VALUES (?, ?, ?)",
                (list_name, user_id, problem_details)
            )
            report_id = cur.lastrowid
            
        conn.commit()
        
        # Notifica admin
        admin_text = (
            f"🚨 NUOVA SEGNALAZIONE PROBLEMA 🚨\n\n"
            f"• Lista: {list_name}\n"
            f"• Utente: {user_id}\n"
            f"• Dettagli:\n{problem_details}"
        )
        
        keyboard = [
            [
                InlineKeyboardButton("✅ Gestita", callback_data=f"resolve_{report_id}"),
                InlineKeyboardButton("📝 Contatta", callback_data=f"contact_{user_id}")
            ]
        ]
        
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=admin_text,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        # Conferma all'utente
        keyboard = [
            ["📋 Gestisci Lista", "ℹ️ FAQ"]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        
        await update.message.reply_text(
            "📬 Segnalazione inviata all'amministratore!\n\n"
            "Riceverai una risposta al più presto.\n\n"
            "Grazie per la tua pazienza!",
            reply_markup=reply_markup
        )
    except Exception as e:
        logger.error(f"Errore salvataggio segnalazione: {e}")
        await update.message.reply_text("❌ Si è verificato un errore. Riprova più tardi.")
    finally:
        conn.close()
    
    return ConversationHandler.END

# Gestione admin per segnalazioni
async def handle_report_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data, report_id = query.data.split("_")
    report_id = int(report_id)
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        if data == "resolve":
            # Contrassegna come risolta
            if DATABASE_URL:
                cur.execute(
                    "UPDATE reports SET status = 'resolved' WHERE id = %s",
                    (report_id,)
                )
            else:
                cur.execute(
                    "UPDATE reports SET status = 'resolved' WHERE id = ?",
                    (report_id,)
                )
            await query.edit_message_text(f"✅ Segnalazione #{report_id} contrassegnata come risolta")
        
        elif data == "contact":
            # Ottieni l'ID dell'utente
            if DATABASE_URL:
                cur.execute("SELECT user_id FROM reports WHERE id = %s", (report_id,))
            else:
                cur.execute("SELECT user_id FROM reports WHERE id = ?", (report_id,))
                
            result = cur.fetchone()
            if result:
                user_id = result[0]
                
                # Salva l'ID per rispondere
                context.user_data["contact_user"] = user_id
                context.user_data["report_id"] = report_id
                
                await query.message.reply_text(
                    f"✉️ Invia il messaggio per l'utente {user_id}:\n"
                    "(Scrivi /cancel per annullare)"
                )
            else:
                await query.message.reply_text("❌ Segnalazione non trovata")
    except Exception as e:
        logger.error(f"Errore gestione segnalazione: {e}")
        await query.message.reply_text("❌ Si è verificato un errore")
    finally:
        conn.commit()
        conn.close()

# Gestione risposta admin a segnalazione
async def handle_admin_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    
    if "contact_user" not in context.user_data:
        return
    
    user_id = context.user_data["contact_user"]
    report_id = context.user_data["report_id"]
    message_text = update.message.text
    
    # Invia il messaggio all'utente
    try:
        await context.bot.send_message(
            chat_id=user_id,
            text=f"✉️ Messaggio dall'amministratore:\n\n{message_text}"
        )
        
        # Contrassegna come in elaborazione
        conn = get_db_connection()
        cur = conn.cursor()
        try:
            if DATABASE_URL:
                cur.execute(
                    "UPDATE reports SET status = 'in_progress' WHERE id = %s",
                    (report_id,)
                )
            else:
                cur.execute(
                    "UPDATE reports SET status = 'in_progress' WHERE id = ?",
                    (report_id,)
                )
            conn.commit()
            await update.message.reply_text(f"✅ Messaggio inviato all'utente {user_id}")
        except Exception as e:
            logger.error(f"Errore aggiornamento stato segnalazione: {e}")
            await update.message.reply_text(f"✅ Messaggio inviato, ma errore aggiornamento stato: {e}")
        finally:
            conn.close()
        
        # Pulisci i dati temporanei
        del context.user_data["contact_user"]
        del context.user_data["report_id"]
    
    except Exception as e:
        await update.message.reply_text(f"❌ Errore nell'invio del messaggio: {e}")

# Gestione liste
async def manage_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📋 Inserisci il nome della lista:",
        reply_markup=ReplyKeyboardRemove()
    )
    return LIST_NAME

async def handle_list_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    list_name = update.message.text.strip()
    context.user_data["list_name"] = list_name
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        if DATABASE_URL:
            cur.execute("SELECT * FROM lists WHERE name = %s", (list_name,))
        else:
            cur.execute("SELECT * FROM lists WHERE name = ?", (list_name,))
            
        lista = cur.fetchone()
        
        if lista:
            # Indici delle colonne
            id_idx, name_idx, owner_idx, status_idx, created_idx, exp_idx, reminder_idx = range(7)
            
            keyboard = [
                [InlineKeyboardButton("🔄 Rinnova", callback_data="renew")],
                [InlineKeyboardButton("🗑 Cancella", callback_data="cancel")]
            ]
            
            # Controlla se la lista è scaduta
            now = datetime.now(timezone.utc)
            exp_date = lista[exp_idx] if lista[exp_idx] else now
            if isinstance(exp_date, str):
                exp_date = datetime.fromisoformat(exp_date)
                
            days_left = (exp_date - now).days if exp_date > now else 0
            
            status = "✅ Attiva" if lista[status_idx] == 'active' else "❌ Scaduta"
            
            await update.message.reply_text(
                f"✅ Lista trovata!\n"
                f"📌 Stato: {status}\n"
                f"📆 Scadenza: {exp_date.strftime('%d/%m/%Y') if lista[exp_idx] else 'Non impostata'}\n"
                f"⏳ Giorni rimasti: {days_left if days_left > 0 else 0}\n\n"
                f"💳 Costo rinnovo: €{COSTO_MENSILE}/mese\n"
                "Scegli un'azione:",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return ACTION_EXISTING
        else:
            keyboard = [
                [InlineKeyboardButton("✅ Crea nuova", callback_data="create_new")]
            ]
            await update.message.reply_text(
                f"❌ Lista non trovata\n\n"
                f"💳 Costo creazione: €{COSTO_MENSILE}/mese\n"
                "Vuoi creare una nuova lista?",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return ACTION_NEW
    except Exception as e:
        logger.error(f"Errore ricerca lista: {e}")
        await update.message.reply_text("❌ Si è verificato un errore. Riprova.")
        return ConversationHandler.END
    finally:
        conn.close()

async def ask_duration(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    action = query.data
    context.user_data["action"] = action
    
    # Messaggio informativo sui costi
    esempi = "\n".join([
        f"- {mesi} mesi = €{mesi * COSTO_MENSILE}"
        for mesi in [1, 3, 6, 12]
    ])
    
    await query.edit_message_text(
        f"💳 Costo servizio: €{COSTO_MENSILE} al mese\n\n"
        "📆 Per quanti mesi vuoi procedere?\n"
        f"{esempi}\n\n"
        "Inserisci il numero di mesi:"
    )
    return DURATION

async def handle_duration(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        mesi = int(update.message.text.strip())
        if mesi < 1:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ Inserisci un numero valido (minimo 1 mese). Riprova:")
        return DURATION

    list_name = context.user_data["list_name"]
    action = context.user_data["action"]
    user_id = update.message.from_user.id
    costo_totale = mesi * COSTO_MENSILE

    # Salva richiesta nel DB
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        if DATABASE_URL:
            cur.execute(
                "INSERT INTO requests (list_name, user_id, action, months, total_cost) "
                "VALUES (%s, %s, %s, %s, %s) RETURNING id",
                (list_name, user_id, action, mesi, costo_totale)
            )
            request_id = cur.fetchone()[0]
        else:
            cur.execute(
                "INSERT INTO requests (list_name, user_id, action, months, total_cost) "
                "VALUES (?, ?, ?, ?, ?)",
                (list_name, user_id, action, mesi, costo_totale)
            )
            request_id = cur.lastrowid
            
        conn.commit()
        
        # Notifica admin
        admin_text = (
            f"⚠️ NUOVA RICHIESTA ⚠️\n"
            f"• Lista: {list_name}\n"
            f"• Azione: {action.upper()}\n"
            f"• Utente: {user_id}\n"
            f"• Mesi: {mesi}\n"
            f"• Totale: €{costo_totale}"
        )
        
        keyboard = [
            [
                InlineKeyboardButton("✅ Approva", callback_data=f"approve_{request_id}"),
                InlineKeyboardButton("❌ Rifiuta", callback_data=f"reject_{request_id}")
            ]
        ]
        
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=admin_text,
            reply_markup=InlineKeyboardMarkup(keyboard)
            
        await update.message.reply_text(
            "📬 Richiesta inviata all'amministratore!\n\n"
            f"🔍 Dettagli:\n"
            f"- Azione: {action}\n"
            f"- Durata: {mesi} mesi\n"
            f"- Importo: €{costo_totale}\n\n"
            "Riceverai una notifica quando la richiesta verrà elaborata."
        )
    except Exception as e:
        logger.error(f"Errore salvataggio richiesta: {e}")
        await update.message.reply_text("❌ Si è verificato un errore. Riprova.")
    finally:
        conn.close()
    
    return ConversationHandler.END

async def handle_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    list_name = context.user_data["list_name"]
    user_id = query.from_user.id

    # Salva richiesta di cancellazione
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        if DATABASE_URL:
            cur.execute(
                "INSERT INTO requests (list_name, user_id, action) "
                "VALUES (%s, %s, 'cancel') RETURNING id",
                (list_name, user_id)
            request_id = cur.fetchone()[0]
        else:
            cur.execute(
                "INSERT INTO requests (list_name, user_id, action) "
                "VALUES (?, ?, 'cancel')",
                (list_name, user_id))
            request_id = cur.lastrowid
            
        conn.commit()
        
        # Notifica admin
        admin_text = (
            f"⚠️ RICHIESTA CANCELLAZIONE ⚠️\n"
            f"• Lista: {list_name}\n"
            f"• Utente: {user_id}"
        )
        
        keyboard = [
            [
                InlineKeyboardButton("✅ Approva", callback_data=f"approve_{request_id}"),
                InlineKeyboardButton("❌ Rifiuta", callback_data=f"reject_{request_id}")
            ]
        ]
        
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=admin_text,
            reply_markup=InlineKeyboardMarkup(keyboard))
            
        await query.edit_message_text(
            "📬 Richiesta di cancellazione inviata all'amministratore!\n"
            "Riceverai una notifica quando verrà elaborata."
        )
    except Exception as e:
        logger.error(f"Errore richiesta cancellazione: {e}")
        await query.edit_message_text("❌ Si è verificato un errore. Riprova.")
    finally:
        conn.close()
    
    return ConversationHandler.END

# Gestione admin
async def handle_admin_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data, req_id = query.data.split("_")
    req_id = int(req_id)

    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        # Ottieni dati richiesta
        if DATABASE_URL:
            cur.execute("SELECT * FROM requests WHERE id = %s", (req_id,))
        else:
            cur.execute("SELECT * FROM requests WHERE id = ?", (req_id,))
            
        req = cur.fetchone()
        
        if not req:
            await query.edit_message_text("❌ Richiesta non trovata")
            return

        # Indici colonne
        id_idx, list_name_idx, user_id_idx, action_idx, months_idx, total_cost_idx, status_idx, created_at_idx = range(8)
        
        list_name = req[list_name_idx]
        user_id = req[user_id_idx]
        action = req[action_idx]
        mesi = req[months_idx] if req[months_idx] else 0
        costo_totale = req[total_cost_idx] if req[total_cost_idx] else 0

        # Gestisci azione
        if data == "approve":
            if action == "create":
                # Calcola la data di scadenza
                exp_date = datetime.now(timezone.utc) + timedelta(days=mesi*30)
                exp_str = exp_date.isoformat()
                
                if DATABASE_URL:
                    cur.execute(
                        "INSERT INTO lists (name, owner_id, expiration) VALUES (%s, %s, %s)",
                        (list_name, user_id, exp_str)
                    )
                else:
                    cur.execute(
                        "INSERT INTO lists (name, owner_id, expiration) VALUES (?, ?, ?)",
                        (list_name, user_id, exp_str)
                    )
                user_msg = f"✅ Nuova lista '{list_name}' creata con successo!"
                
            elif action == "renew":
                # Calcola la nuova data di scadenza
                if DATABASE_URL:
                    cur.execute("SELECT expiration FROM lists WHERE name = %s", (list_name,))
                else:
                    cur.execute("SELECT expiration FROM lists WHERE name = ?", (list_name,))
                    
                current_exp = cur.fetchone()
                
                if current_exp and current_exp[0]:
                    if isinstance(current_exp[0], str):
                        exp_date = datetime.fromisoformat(current_exp[0]) + timedelta(days=mesi*30)
                    else:
                        exp_date = current_exp[0] + timedelta(days=mesi*30)
                else:
                    exp_date = datetime.now(timezone.utc) + timedelta(days=mesi*30)
                    
                exp_str = exp_date.isoformat()
                
                if DATABASE_URL:
                    cur.execute(
                        "UPDATE lists SET status = 'active', expiration = %s WHERE name = %s",
                        (exp_str, list_name))
                else:
                    cur.execute(
                        "UPDATE lists SET status = 'active', expiration = ? WHERE name = ?",
                        (exp_str, list_name))
                user_msg = f"✅ Rinnovo lista '{list_name}' completato!"
                
            elif action == "cancel":
                if DATABASE_URL:
                    cur.execute(
                        "UPDATE lists SET status = 'cancelled' WHERE name = %s",
                        (list_name,))
                else:
                    cur.execute(
                        "UPDATE lists SET status = 'cancelled' WHERE name = ?",
                        (list_name,))
                user_msg = f"✅ Lista '{list_name}' cancellata con successo!"
            
            # Aggiorna stato richiesta
            if DATABASE_URL:
                cur.execute(
                    "UPDATE requests SET status = 'approved' WHERE id = %s",
                    (req_id,))
            else:
                cur.execute(
                    "UPDATE requests SET status = 'approved' WHERE id = ?",
                    (req_id,))
            
            # Aggiungi dettagli pagamento se applicabile
            if action in ["create", "renew"] and mesi and costo_totale:
                user_msg += (
                    f"\n\n💳 Dettagli pagamento:\n"
                    f"- Durata: {mesi} mesi\n"
                    f"- Totale: €{costo_totale}\n\n"
                    "L'amministratore ti contatterà per i dettagli di pagamento."
                )
            
            # Notifica utente
            await context.bot.send_message(chat_id=user_id, text=user_msg)
            await query.edit_message_text(f"✅ Richiesta #{req_id} approvata")
        
        elif data == "reject":
            if DATABASE_URL:
                cur.execute(
                    "UPDATE requests SET status = 'rejected' WHERE id = %s",
                    (req_id,))
            else:
                cur.execute(
                    "UPDATE requests SET status = 'rejected' WHERE id = ?",
                    (req_id,))
            
            user_msg = f"❌ La tua richiesta per '{list_name}' è stata rifiutata"
            if action in ["create", "renew"] and mesi and costo_totale:
                user_msg += f"\nAzione: {action.capitalize()} ({mesi} mesi)"
            
            await context.bot.send_message(chat_id=user_id, text=user_msg)
            await query.edit_message_text(f"❌ Richiesta #{req_id} rifiutata")
        
        conn.commit()
    except Exception as e:
        logger.error(f"Errore gestione richiesta admin: {e}")
        await query.edit_message_text(f"❌ Errore durante l'elaborazione: {e}")
    finally:
        conn.close()

# Sistema di reminder
async def check_expirations(context: ContextTypes.DEFAULT_TYPE):
    conn = get_db_connection()
    cur = conn.cursor()
    now = datetime.now(timezone.utc)
    now_str = now.isoformat()
    
    try:
        # Trova liste in scadenza (entro 7 giorni)
        if DATABASE_URL:
            cur.execute("""
                SELECT id, name, owner_id, expiration, last_reminder 
                FROM lists 
                WHERE status = 'active'
                AND expiration IS NOT NULL
                AND expiration > %s
            """, (now_str,))
        else:
            cur.execute("""
                SELECT id, name, owner_id, expiration, last_reminder 
                FROM lists 
                WHERE status = 'active'
                AND expiration IS NOT NULL
                AND expiration > ?
            """, (now_str,))
        
        active_lists = cur.fetchall()
        
        for lista in active_lists:
            # Indici colonne
            id_idx, name_idx, owner_id_idx, expiration_idx, last_reminder_idx = range(5)
            
            list_id = lista[id_idx]
            list_name = lista[name_idx]
            owner_id = lista[owner_id_idx]
            exp_value = lista[expiration_idx]
            last_reminder_value = lista[last_reminder_idx]
            
            # Converti i valori datetime se necessario
            if isinstance(exp_value, str):
                exp_date = datetime.fromisoformat(exp_value)
            else:
                exp_date = exp_value
                
            if last_reminder_value:
                if isinstance(last_reminder_value, str):
                    last_reminder = datetime.fromisoformat(last_reminder_value)
                else:
                    last_reminder = last_reminder_value
            else:
                last_reminder = None

            # Calcola giorni rimanenti
            days_left = (exp_date - now).days
            
            # Determina quando inviare i reminder
            reminder_days = [7, 3, 1, 0]
            
            if days_left in reminder_days:
                # Controlla se abbiamo già inviato un reminder oggi
                if last_reminder and (now - last_reminder).days < 1:
                    continue  # Salta se abbiamo già inviato un reminder oggi
                
                # Messaggio per l'utente
                if days_left > 0:
                    user_msg = (
                        f"⏰ PROMEMORIA RINNOVO LISTA\n\n"
                        f"La tua lista '{list_name}' scadrà tra {days_left} giorni!\n"
                        f"📆 Data scadenza: {exp_date.strftime('%d/%m/%Y')}\n\n"
                        f"💳 Costo rinnovo: €{COSTO_MENSILE} al mese\n"
                        f"Per rinnovare, usa il comando /manage"
                    )
                else:
                    user_msg = (
                        f"⚠️ URGENTE! LISTA SCADUTA\n\n"
                        f"La tua lista '{list_name}' è scaduta oggi!\n\n"
                        f"Per evitare la disattivazione, rinnovare subito con /manage"
                    )
                
                try:
                    await context.bot.send_message(chat_id=owner_id, text=user_msg)
                except Exception as e:
                    logger.error(f"Errore invio reminder a {owner_id}: {e}")
                
                # Messaggio per l'admin
                admin_msg = (
                    f"🔔 PROMEMORIA SCADENZA LISTA\n\n"
                    f"Lista: {list_name}\n"
                    f"Proprietario: {owner_id}\n"
                    f"Scadenza: {exp_date.strftime('%d/%m/%Y')}\n"
                    f"Giorni rimasti: {days_left}\n\n"
                    f"Stato: {'ATTIVA' if days_left > 0 else 'SCADUTA'}"
                )
                
                try:
                    await context.bot.send_message(chat_id=ADMIN_ID, text=admin_msg)
                except Exception as e:
                    logger.error(f"Errore invio reminder ad admin: {e}")
                
                # Aggiorna l'ultimo reminder
                if DATABASE_URL:
                    cur.execute(
                        "UPDATE lists SET last_reminder = %s WHERE id = %s",
                        (now_str, list_id))
                else:
                    cur.execute(
                        "UPDATE lists SET last_reminder = ? WHERE id = ?",
                        (now_str, list_id))
                
                conn.commit()
    except Exception as e:
        logger.error(f"Errore controllo scadenze: {e}")
    finally:
        conn.close()

# Comando admin per forzare il controllo
async def force_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Solo l'amministratore può usare questo comando!")
        return
    
    await update.message.reply_text("🔍 Avvio controllo manuale scadenze...")
    await check_expirations(context)
    await update.message.reply_text("✅ Controllo scadenze completato!")

# Gestione messaggi generici
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    
    if text == "📋 Gestisci Lista":
        return await manage_list(update, context)
    elif text == "ℹ️ FAQ":
        return await faq(update, context)
    elif text == "⚠️ Segnala Problema":
        return await start_report(update, context)
    else:
        await update.message.reply_text(
            "Non ho capito il comando. Usa la tastiera per selezionare un'opzione.",
            reply_markup=ReplyKeyboardMarkup([
                ["📋 Gestisci Lista", "ℹ️ FAQ"],
                ["⚠️ Segnala Problema"]
            ], resize_keyboard=True)
        )

# Health check per Render
async def health_check(request):
    return web.Response(text="Bot is running")

# Main
def main():
    init_db()
    application = Application.builder().token(TOKEN).build()

    # Aggiungi job per i reminder
    job_queue = application.job_queue
    job_queue.run_repeating(check_expirations, interval=86400, first=10)  # Ogni 24 ore

    # Handler conversazione gestione liste
    list_handler = ConversationHandler(
        entry_points=[CommandHandler("manage", manage_list)],
        states={
            LIST_NAME: [MessageHandler(filters.TEXT, handle_list_name)],
            ACTION_EXISTING: [
                CallbackQueryHandler(ask_duration, pattern="^renew$"),
                CallbackQueryHandler(handle_cancel, pattern="^cancel$")
            ],
            ACTION_NEW: [
                CallbackQueryHandler(ask_duration, pattern="^create_new$")
            ],
            DURATION: [MessageHandler(filters.TEXT, handle_duration)]
        },
        fallbacks=[CommandHandler("cancel", start)],
        map_to_parent={ConversationHandler.END: ConversationHandler.END}
    )

    # Handler conversazione segnalazione problemi
    report_handler = ConversationHandler(
        entry_points=[CommandHandler("report", start_report)],
        states={
            REPORT_LIST: [MessageHandler(filters.TEXT, handle_report_list)],
            REPORT_DETAILS: [MessageHandler(filters.TEXT, handle_report_details)]
        },
        fallbacks=[CommandHandler("cancel", start)],
        map_to_parent={ConversationHandler.END: ConversationHandler.END}
    )

    # Registra handler
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("faq", faq))
    application.add_handler(CommandHandler("check_expirations", force_check))
    application.add_handler(CallbackQueryHandler(handle_admin_action, pattern=r"^(approve|reject)_\d+"))
    application.add_handler(CallbackQueryHandler(handle_report_action, pattern=r"^(resolve|contact)_\d+"))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(list_handler)
    application.add_handler(report_handler)
    
    # Handler per risposte admin
    application.add_handler(MessageHandler(
        filters.TEXT & filters.Chat(chat_id=ADMIN_ID),
        handle_admin_reply
    ))

    # Avvia il bot in base all'ambiente
    if 'RENDER' in os.environ:
        # Configurazione per Render.com
        port = int(os.environ.get('PORT', 5000))
        app_name = os.environ.get('RENDER_EXTERNAL_HOSTNAME', 'your-app-name.onrender.com')
        webhook_url = f'https://{app_name}/{TOKEN}'

        # Crea un mini-server web per gli health check
        async def web_app():
            app = web.Application()
            app.router.add_get('/', health_check)
            return app
        
        # Configura il webhook
        async def set_webhook_and_start():
            await application.bot.set_webhook(
                url=webhook_url,
                drop_pending_updates=True
            )
            return await web_app()

        application.run_webhook(
            web_app=set_webhook_and_start(),
            port=port,
            listen='0.0.0.0',
            secret_token=os.getenv('WEBHOOK_SECRET', os.urandom(24).hex()),
            bootstrap=set_webhook_and_start
        )
    else:
        # Modalità locale con polling
        application.run_polling()

if __name__ == "__main__":
    main()
