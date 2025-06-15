import logging
import sqlite3
import os
import pathlib
import asyncio
import html
import traceback
import signal
import httpx
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
from telegram.request import HTTPXRequest
from flask import Flask, request, jsonify

# Configurazione avanzata
TOKEN = os.getenv("TELEGRAM_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_CHAT_ID", "0"))
DB_NAME = "database.db"
COSTO_MENSILE = 15  # €15 al mese
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "default-secret-token")
RENDER_EXTERNAL_URL = os.getenv("RENDER_EXTERNAL_URL", "https://your-render-app.onrender.com")

# Percorso assoluto per il database
DB_PATH = os.path.join(pathlib.Path(__file__).parent.resolve(), DB_NAME)

# Configurazione logging avanzata
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Abilita debug per le connessioni
logging.getLogger("httpx").setLevel(logging.DEBUG)

# Server web per Render
app = Flask(__name__)

@app.route('/')
def home():
    return "🤖 Bot Telegram is running and ready!", 200, {'Connection': 'keep-alive'}

@app.route('/webhook', methods=['POST'])
def webhook():
    if request.headers.get('X-Telegram-Bot-Api-Secret-Token') != WEBHOOK_SECRET:
        return jsonify({"status": "unauthorized"}), 403
        
    json_data = request.get_json()
    asyncio.run(process_update(json_data))
    return jsonify({"status": "ok"}), 200

# Stati conversazione
LIST_NAME, ACTION_EXISTING, ACTION_NEW, DURATION, REPORT_LIST, REPORT_DETAILS = range(6)

# Inizializza DB
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    # Tabelle
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
        status极 TEXT DEFAULT 'pending',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    conn.commit()
    conn.close()

# Gestore globale degli errori
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Gestore globale degli errori."""
    logger.error("⚠️⚠️⚠️ ECCEZIONE NON GESTITA ⚠️⚠️⚠️", exc_info=context.error)
    
    # Rileva timeout specifici
    if isinstance(context.error, httpx.ConnectTimeout):
        logger.warning("Timeout di connessione rilevato, verificare la rete")
    
    # Prepara il traceback
    tb_list = traceback.format_exception(None, context.error, context.error.__traceback__)
    tb_string = ''.join(tb_list)
    
    # Costruisci il messaggio di errore
    error_message = (
        f"🚨 ERRORE CRITICO NEL BOT 🚨\n\n"
        f"• Eccezione: {type(context.error).__name__}\n"
        f"• Messaggio: {context.error}\n\n"
        f"Traceback completo:\n<pre>{html.escape(tb_string)}</pre>"
    )
    
    # Invia la notifica all'amministratore
    try:
        if ADMIN_ID:
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=error_message,
                parse_mode="HTML"
            )
    except Exception as e:
        logger.error(f"Impossibile inviare notifica errore: {e}")
    
    # Log dell'errore su console
    logger.error(f"Update: {update}")
    logger.error(f"Context: {context}")

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
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO reports (list_name, user_id, problem_details) "
        "VALUES (?, ?, ?)",
        (list_name, user_id, problem_details)
    )
    report_id = cur.lastrowid
    conn.commit()
    conn.close()
    
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
    
    try:
        if ADMIN_ID:
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=admin_text,
                reply_markup=InlineKeyboardMarkup(keyboard)

            )
    except Exception as e:
        logger.error(f"Errore nell'invio della notifica admin: {e}")
    
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
    return ConversationHandler.END

# Gestione admin per segnalazioni
async def handle_report_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data, value = query.data.split("_")
    report_id = int(value)
    
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    
    if data == "resolve":
        # Contrassegna come risolta
        cur.execute(
            "UPDATE reports SET status = 'resolved' WHERE id = ?",
            (report_id,)
        )
        await query.edit_message_text(f"✅ Segnalazione #{report_id} contrassegnata come risolta")
    
    elif data == "contact":
        # Ottieni l'ID dell'utente
        cur.execute("SELECT user_id FROM reports WHERE id = ?", (report_id,))
        result = cur.fetchone()
        if result:
            user_id = result[0]
        else:
            await query.edit_message_text("❌ Segnalazione non trovata")
            return
        
        # Salva l'ID per rispondere
        context.user_data["contact_user"] = user_id
        context.user_data["report_id"] = report_id
        
        await query.message.reply_text(
            f"✉️ Invia il messaggio per l'utente {user_id}:\n"
            "(Scrivi /cancel per annullare)"
        )
    
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
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute(
            "UPDATE reports SET status = 'in_progress' WHERE id = ?",
            (report_id,)
        )
        conn.commit()
        conn.close()
        
        await update.message.reply_text(f"✅ Messaggio inviato all'utente {user_id}")
        
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
    
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT * FROM lists WHERE name = ?", (list_name,))
    lista = cur.fetchone()
    conn.close()

    if lista:
        keyboard = [
            [InlineKeyboardButton("🔄 Rinnova", callback_data="renew")],
            [InlineKeyboardButton("🗑 Cancella", callback_data="cancel")]
        ]
        
        # Controlla se la lista è scaduta
        now = datetime.now(timezone.utc)
        exp_date = datetime.fromisoformat(lista[5]) if lista[5] else now
        days_left = (exp_date - now).days if exp_date > now else 0
        
        status = "✅ Attiva" if lista[3] == 'active' else "❌ Scaduta"
        
        await update.message.reply_text(
            f"✅ Lista trovata!\n"
            f"📌 Stato: {status}\n"
            f"📆 Scadenza: {exp_date.strftime('%d/%m/%Y') if lista[5] else 'Non impostata'}\n"
            f"⏳ Giorni rimasti: {days_left if days_left > 0 else 0}\n\n"
            f"💳 Costo rinnovo: €{COSTO_MENSILE}/mese\n"
            "Scegli un'azione:",
            reply_markup=InlineKeyboardMarkup(keyboard))
        return ACTION_EXISTING
    else:
        # Se la lista non esiste, chiediamo direttamente la durata per la creazione
        context.user_data["action"] = "create"  # Imposta l'azione su 'create'
        
        # Messaggio informativo sui costi
        esempi = "\n".join([
            f"- {mesi} mesi = €{mesi * COSTO_MENSILE}"
            for mesi in [1, 3, 6, 12]
        ])
        
        await update.message.reply_text(
            f"❌ Lista non trovata\n\n"
            f"💳 Costo creazione: €{COSTO_MENSILE}/mese\n\n"
            "📆 Per quanti mesi vuoi creare la lista?\n"
            f"{esempi}\n\n"
            "Inserisci il numero di mesi:"
        )
        return DURATION

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
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO requests (list_name, user_id, action, months, total_cost) "
        "VALUES (?, ?, ?, ?, ?)",
        (list_name, user_id, action, mesi, costo_totale)
    )
    req_id = cur.lastrowid
    conn.commit()
    conn.close()

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
            InlineKeyboardButton("✅ Approva", callback_data=f"approve_{req_id}"),
            InlineKeyboardButton("❌ Rifiuta", callback_data=f"reject_{req_id}")
        ]
    ]
    
    try:
        if ADMIN_ID:
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=admin_text,
                reply_markup=InlineKeyboardMarkup(keyboard))
    except Exception as e:
        logger.error(f"Errore nell'invio della notifica admin: {e}")
    
    await update.message.reply_text(
        "📬 Richiesta inviata all'amministratore!\n\n"
        f"🔍 Dettagli:\n"
        f"- Azione: {action}\n"
        f"- Durata: {mesi} mesi\n"
        f"- Importo: €{costo_totale}\n\n"
        "Riceverai una notifica quando la richiesta verrà elaborata."
    )
    return ConversationHandler.END

async def handle_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback极
    await query.answer()
    
    list_name = context.user_data["list_name"]
    user_id = query.from_user.id

    # Salva richiesta di cancellazione
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO requests (list_name, user_id, action) "
        "VALUES (?, ?, 'cancel')",
        (list_name, user_id)
    )
    req_id = cur.lastrowid
    conn.commit()
    conn.close()

    # Notifica admin
    admin_text = (
        f"⚠️ RICHIESTA CANCELLAZIONE ⚠️\n"
        f"• Lista: {list_name}\n"
        f"• Utente: {user_id}"
    )
    
    keyboard = [
        [
            InlineKeyboardButton("✅ Approva", callback_data=f"approve_{req_id}"),
            InlineKeyboardButton("❌ Rifiuta", callback_data=f"reject_{req_id}")
        ]
    ]
    
    try:
        if ADMIN_ID:
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=admin_text,
                reply_markup=InlineKeyboardMarkup(keyboard))
    except Exception as e:
        logger.error(f"Errore nell'invio della notifica admin: {e}")
    
    await query.edit_message_text(
        "📬 Richiesta di cancellazione inviata all'amministratore!\n"
        "Riceverai una notifica quando verrà elaborata."
    )
    return ConversationHandler.END

# Gestione admin per approvare/rifiutare richieste
async def handle_admin_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data, req_id = query.data.split("_")
    req_id = int(req_id)

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    
    # Ottieni dati richiesta
    cur.execute("SELECT * FROM requests WHERE id = ?", (req_id,))
    req = cur.fetchone()
    
    if not req:
        await query.edit_message_text("❌ Richiesta non trovata")
        return

    req_id, list_name, user_id, action, mesi, costo_totale, status, created_at = req

    # Gestisci azione
    if data == "approve":
        # Verifica se la lista esiste già e se è di un altro proprietario
        cur.execute("SELECT owner_id FROM lists WHERE name = ?", (list_name,))
        existing_list = cur.fetchone()
        
        if existing_list and existing_list[0] != user_id:
            # Richiedi verifica proprietà
            keyboard = [
                [InlineKeyboardButton("🔒 Verifica Proprietà", callback_data=f"verify_{req_id}")]
            ]
            
            await query.edit_message_text(
                f"⚠️ ATTENZIONE: La lista '{list_name}' è già registrata a nome di un altro utente!\n\n"
                f"Proprietario attuale: {existing_list[0]}\n"
                f"Richiedente: {user_id}\n"
                "Premi il pulsante per avviare la verifica della proprietà:",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            conn.close()
            return
        
        # Se la lista non esiste o il proprietario è lo stesso, procedi
        if action == "create":
            # Calcola la data di scadenza
            exp_date = datetime.now(timezone.utc) + timedelta(days=mesi*30)
            exp_str = exp_date.strftime("%Y-%m-%d %H:%M:%S")
            
            cur.execute(
                "INSERT INTO lists (name, owner_id, expiration) VALUES (?, ?, ?)",
                (list_name, user_id, exp_str)
            )
            user_msg = f"✅ Nuova lista '{list_name}' creata con successo!"
            
        elif action == "renew":
            # Calcola la nuova data di scadenza
            cur.execute("SELECT expiration FROM lists WHERE name = ?", (list_name,))
            current_exp = cur.fetchone()
            
            if current_exp and current_exp[0]:
                exp_date = datetime.fromisoformat(current_exp[0]) + timedelta(days=mesi*30)
            else:
                exp_date = datetime.now(timezone.utc) + timedelta(days=mesi*30)
                
            exp_str = exp_date.strftime("%Y-%m-%d %H:%M:%S")
            
            cur.execute(
                "UPDATE lists SET status = 'active', expiration = ? WHERE name = ?",
                (exp_str, list_name)
            )
            user_msg = f"✅ Rinnovo lista '{list_name}' completato!"
            
        elif action == "cancel":
            cur.execute(
                "UPDATE lists SET status = 'cancelled' WHERE name = ?",
                (list_name,)
            )
            user_msg = f"✅ Lista '{list_name}' cancellata con successo!"
        
        # Aggiorna stato richiesta
        cur.execute(
            "UPDATE requests SET status = 'approved' WHERE id = ?",
            (req_id,)
        )
        
        # Aggiungi dettagli pagamento se applicabile
        if action in ["create", "renew"] and mesi and costo_totale:
            user_msg += (
                f"\n\n💳 Dettagli pagamento:\n"
                f"- Durata: {mesi} mesi\n"
                f"- Totale: €{costo_totale}\n\n"
                "L'amministratore ti contatterà per i dettagli di pagamento."
            )
        
        # Notifica utente
        try:
            await context.bot.send_message(chat_id=user_id, text=user_msg)
        except Exception as e:
            logger.error(f"Errore nell'invio del messaggio all'utente: {e}")
        
        await query.edit_message_text(f"✅ Richiesta #{req_id} approvata")
    
    elif data == "reject":
        cur.execute(
            "UPDATE requests SET status = 'rejected' WHERE id = ?",
            (req_id,)
        )
        
        user_msg = f"❌ La tua richiesta per '{list_name}' è stata rifiutata"
        if action in ["create", "renew"] and mesi and costo_totale:
            user_msg += f"\nAzione: {action.capitalize()} ({mesi} mesi)"
        
        try:
            await context.bot.send_message(chat_id=user_id, text=user_msg)
        except Exception as e:
            logger.error(f"Errore nell'invio del messaggio all'utente: {e}")
        
        await query.edit_message_text(f"❌ Richiesta #{req_id} rifiutata")
    
    conn.commit()
    conn.close()

# Verifica proprietà lista
async def verify_ownership(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    # Estrai dati dalla callback
    data = query.data.split("_")
    req_id = int(data[1])
    
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    
    # Ottieni dati richiesta
    cur.execute("SELECT * FROM requests WHERE id = ?", (req_id,))
    req = cur.fetchone()
    
    if not req:
        await query.edit_message_text("❌ Richiesta non trovata")
        return
    
    req_id, list_name, user_id, action, mesi, costo_totale, status, created_at = req
    
    # Messaggio all'utente
    try:
        await context.bot.send_message(
            chat_id=user_id,
            text=f"🔒 Verifica proprietà lista '{list_name}'\n\n"
                 "Per favore conferma di essere il proprietario di questa lista "
                 "rispondendo SI oppure NO:"
        )
    except Exception as e:
        logger.error(f"Errore nell'invio del messaggio di verifica: {e}")
        await query.edit_message_text(f"❌ Impossibile inviare messaggio a {user_id}")
        return
    
    # Salva stato per gestire la risposta
    context.user_data["verify_req"] = req_id
    context.user_data["verify_user"] = user_id
    context.user_data["verify_list"] = list_name
    
    await query.edit_message_text(f"✅ Richiesta di verifica inviata all'utente {user_id}")

# Gestione risposta utente alla verifica
async def handle_verification(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    text = update.message.text.lower()
    
    # Controlla se c'è una verifica in corso
    if "verify_req" not in context.user_data or context.user_data["verify_user"] != user_id:
        return
    
    req_id = context.user_data["verify_req"]
    list_name = context.user_data["verify_list"]
    
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    
    if text == "si":
        # Aggiorna stato richiesta
        cur.execute(
            "UPDATE requests SET status = 'verified' WHERE id = ?",
            (req_id,)
        )
        
        # Notifica admin
        try:
            if ADMIN_ID:
                await context.bot.send_message(
                    chat_id=ADMIN_ID,
                    text=f"✅ Utente {user_id} ha confermato la proprietà della lista '{list_name}'"
                )
        except Exception as e:
            logger.error(f"Errore nell'invio della notifica admin: {e}")
        
        await update.message.reply_text("✅ Verifica completata! La tua richiesta è in fase di approvazione.")
    else:
        # Annulla richiesta
        cur.execute(
            "UPDATE requests SET status = 'rejected' WHERE id = ?",
            (req_id,)
        )
        
        await update.message.reply_text("❌ Richiesta annullata")
        try:
            if ADMIN_ID:
                await context.bot.send_message(
                    chat_id=ADMIN_ID,
                    text=f"❌ Utente {user_id} ha NEGATO la proprietà della lista '{list_name}'"
                )
        except Exception as e:
            logger.error(f"Errore nell'invio della notifica admin: {e}")
    
    # Pulisci dati temporanei
    del context.user_data["verify_req"]
    del context.user_data["verify_user"]
    del context.user_data["verify_list"]
    
    conn.commit()
    conn.close()

# Sistema di reminder
async def check_expirations(context: ContextTypes.DEFAULT_TYPE):
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        now = datetime.now(timezone.utc)
        
        # Trova liste in scadenza (entro 7 giorni)
        cur.execute("""
            SELECT id, name, owner_id, expiration, last_reminder 
            FROM lists 
            WHERE status = 'active'
            AND expiration IS NOT NULL
            AND expiration > ?
        """, (now.strftime("%Y-%m-%d %H:%M:%S"),))
        
        active_lists = cur.fetchall()
        
        for lista in active_lists:
            list_id, list_name, owner_id, exp_str, last_reminder_str = lista
            exp_date = datetime.fromisoformat(exp_str)
            
            # Calcola giorni rimanenti
            days_left = (exp_date - now).days
            
            # Determina quando inviare i reminder
            reminder_days = [7, 3, 1, 0]
            
            if days_left in reminder_days:
                # Controlla se abbiamo già inviato un reminder oggi
                last_reminder = datetime.fromisoformat(last_reminder_str) if last_reminder_str else None
                
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
                        f"Per evitare la disattivazione, rinnova subito con /manage"
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
                    if ADMIN_ID:
                        await context.bot.send_message(chat_id=ADMIN_ID, text=admin_msg)
                except Exception as e:
                    logger.error(f"Errore invio reminder ad admin: {e}")
                
                # Aggiorna l'ultimo reminder
                cur.execute(
                    "UPDATE lists SET last_reminder = ? WHERE id = ?",
                    (now.strftime("%Y-%m-%d %H:%M:%S"), list_id)
                )
        
        conn.commit()
    except Exception as e:
        logger.error(f"Errore nel controllo delle scadenze: {e}")
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

# Processa aggiornamenti da webhook
async def process_update(update_data):
    application = Application.builder() \
        .token(TOKEN) \
        .request(HTTPXRequest(
            connect_timeout=30.0,
            read_timeout=30.0,
            write_timeout=30.0,
            pool_timeout=30.0
        )) \
        .build()
    
    # Setup degli handler
    setup_handlers(application)
    
    # Inizializza l'applicazione
    await application.initialize()
    
    # Processa l'aggiornamento
    update = Update.de_json(update_data, application.bot)
    await application.process_update(update)
    
    # Chiudi l'applicazione
    await application.shutdown()

# Setup degli handler
def setup_handlers(application):
    # Registra il gestore di errori
    application.add_error_handler(error_handler)
    
    # Aggiungi job per i reminder se disponibile
    if application.job_queue:
        job_queue = application.job_queue
        job_queue.run_repeating(check_expirations, interval=86400, first=10)  # Ogni 24 ore
        logger.info("JobQueue abilitata per i promemoria")
    else:
        logger.warning("JobQueue non disponibile. I promemoria automatici saranno disabilitati.")
    
    # Handler conversazione gestione liste
    list_handler = ConversationHandler(
        entry_points=[CommandHandler("manage", manage_list)],
        states={
            LIST_NAME: [MessageHandler(filters.TEXT, handle_list_name)],
            ACTION_EXISTING: [
                CallbackQueryHandler(ask_duration, pattern="^renew$"),
                CallbackQueryHandler(handle_cancel, pattern="^cancel$")
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
    application.add_handler(CallbackQueryHandler(handle_admin_action, pattern="^(approve|reject)_"))
    application.add_handler(CallbackQueryHandler(handle_report_action, pattern="^(resolve|contact)_"))
    # Aggiungi handler per la verifica
    application.add_handler(CallbackQueryHandler(verify_ownership, pattern="^verify_"))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(list_handler)
    application.add_handler(report_handler)
    
    # Handler per risposte admin
    application.add_handler(MessageHandler(
        filters.TEXT & filters.Chat(chat_id=ADMIN_ID),
        handle_admin_reply
    ))
    
    # Handler per gestione verifica utente
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        handle_verification
    ))

# Main
def main():
    # Inizializza il database
    init_db()
    
    # Verifica configurazione
    if not TOKEN:
        logger.error("❌ TOKEN non configurato!")
        return
    if ADMIN_ID == 0:
        logger.warning("⚠️ ADMIN_CHAT_ID non configurato, funzionalità admin limitate")
    
    # Configurazione webhook
    webhook_url = f"{RENDER_EXTERNAL_URL}/webhook"
    
    # Configura l'applicazione con timeout estesi
    application = Application.builder() \
        .token(TOKEN) \
        .request(HTTPXRequest(
            connect_timeout=30.0,
            read_timeout=30.0,
            write_timeout=30.0,
            pool_timeout=30.0
        )) \
        .build()
    
    # Setup degli handler
    setup_handlers(application)
    
    # Avvia il bot in modalità webhook
    logger.info(f"🤖 Configurazione webhook su: {webhook_url}")
    
    # Configura il webhook all'avvio
    async def on_startup():
        await application.bot.set_webhook(
            webhook_url,
            secret_token=WEBHOOK_SECRET,
            drop_pending_updates=True
        )
        logger.info("✅ Webhook configurato con successo")
    
    # Configura shutdown graceful
    loop = asyncio.get_event_loop()
    
    for signame in ('SIGINT', 'SIGTERM'):
        loop.add_signal_handler(
            getattr(signal, signame),
            lambda: asyncio.create_task(application.stop())
        )
    
    # Avvia il bot
    logger.info("🤖 Bot in avvio...")
    
    # Avvia l'applicazione in modo asincrono
    loop = asyncio.get_event_loop()
    loop.create_task(on_startup())
    
    # Avvia il server Flask solo se non siamo su Render
    if not os.getenv("RENDER"):
        port = int(os.environ.get("PORT", 8080))
        app.run(host='0.0.0.0', port=port)
    else:
        # Su Render, usa Gunicorn per avviare l'app
        logger.info("🚀 Applicazione pronta per essere avviata da Gunicorn")
        application.run_webhook(
            listen="0.0.0.0",
            port=int(os.environ.get("PORT", 8080)),
            webhook_url=webhook_url,
            secret_token=WEBHOOK_SECRET
        )

if __name__ == "__main__":
    main()
