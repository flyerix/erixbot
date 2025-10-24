#!/usr/bin/env python3
"""
Erix Bot - Bot Telegram avanzato per supporto, promemoria e gestione liste
Con funzionalità enterprise: blacklist/whitelist, anti-spam, undo/redo, preview modifiche, auto-complete, inline mode
"""

import os
import sys
import time
import json
import logging
import asyncio
import threading
import functools
import traceback
from datetime import datetime, timedelta
from collections import defaultdict
import re
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputTextMessageContent, InlineQueryResultArticle
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    InlineQueryHandler, ContextTypes, filters
)
from telegram.error import BadRequest

# Third party imports
import psycopg2
import psycopg2.extras
from flask import Flask
import requests
from bs4 import BeautifulSoup
import openai

# ==================== CONFIGURAZIONE LOGGING SICURA ====================

def setup_logger():
    """Configura il logger in modo sicuro per Render"""
    try:
        logger = logging.getLogger(__name__)
        logger.setLevel(logging.INFO)

        # Rimuovi handler esistenti per evitare duplicati
        for handler in logger.handlers[:]:
            logger.removeHandler(handler)

        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

        logger.propagate = False
        return logger
    except Exception as e:
        # Fallback - usa solo print
        print(f"ERROR: Impossibile configurare il logger: {e}")
        return None

# Inizializza logger
logger = setup_logger()

def safe_log(level, message):
    """Logging sicuro che non causa errori"""
    try:
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        log_message = f"{timestamp} - {level.upper()} - {message}"
        
        if logger:
            if level == 'info':
                logger.info(message)
            elif level == 'warning':
                logger.warning(message)
            elif level == 'error':
                logger.error(message)
            elif level == 'debug':
                logger.debug(message)
            else:
                logger.info(message)
        else:
            # Fallback a print se logger non è disponibile
            print(log_message)
    except Exception as e:
        # Ultima risorsa - usa sempre print
        print(f"LOG ERROR: {message} - {e}")

# ==================== CONFIGURAZIONE ====================

# Caricamento configurazione
TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
ADMIN_IDS = [int(id.strip()) for id in os.getenv('ADMIN_IDS', '').split(',') if id.strip()]
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
DATABASE_URL = os.getenv('DATABASE_URL')
RENDER = os.getenv('RENDER', 'false').lower() == 'true'

# Cache per performance
cache = {}

# AI Templates per risposte automatiche
AI_TEMPLATES = {
    'connection_issue': {
        'keywords': ['connessione', 'non funziona', 'errore', 'problema'],
        'emoji': '🔌',
        'title': 'Problema di Connessione',
        'steps': [
            'Verifica che la tua connessione internet sia stabile',
            'Controlla se altri dispositivi funzionano',
            'Riavvia il router/modem',
            'Prova a cambiare rete WiFi',
            'Contatta il supporto se il problema persiste'
        ]
    },
    'list_not_found': {
        'keywords': ['lista', 'non trovo', 'cerca', 'manca'],
        'emoji': '📋',
        'title': 'Lista Non Trovata',
        'steps': [
            'Verifica di aver scritto correttamente il nome',
            'Prova con una ricerca parziale',
            'Controlla se la lista è stata rimossa',
            'Chiedi a un admin di verificare'
        ]
    }
}

# Importa moduli di progetto DOPO la configurazione del logger
try:
    from database import (
        get_db_connection, init_database, check_database_connection,
        check_database_extensions, get_user_restrictions, add_user_restriction,
        remove_user_restriction, check_user_restriction, undo_last_operation,
        log_operation, get_command_suggestions, update_command_usage,
        get_list_suggestions
    )
    from backup_manager import BackupManager
except ImportError as e:
    safe_log('error', f"Errore nell'importazione dei moduli: {e}")
    # Definisci funzioni fallback per evitare errori
    def get_db_connection():
        raise Exception("Database non disponibile")
    
    def init_database():
        return False
    
    def check_database_connection():
        return False

# ==================== DECORATORI ====================

def admin_required(func):
    """Decorator per verificare che l'utente sia admin"""
    @functools.wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user_id = update.effective_user.id
        if user_id not in ADMIN_IDS:
            await update.message.reply_text("❌ Accesso negato. Solo per amministratori.")
            return
        return await func(update, context, *args, **kwargs)
    return wrapper

def track_metrics(func):
    """Decorator per tracciare metriche delle funzioni"""
    @functools.wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        start_time = time.time()
        try:
            result = await func(update, context, *args, **kwargs)
            execution_time = time.time() - start_time
            safe_log('info', f"{func.__name__} executed in {execution_time:.2f}s")
            return result
        except Exception as e:
            execution_time = time.time() - start_time
            safe_log('error', f"{func.__name__} failed after {execution_time:.2f}s: {e}")
            raise
    return wrapper

def rate_limit(func):
    """Decorator per rate limiting base"""
    @functools.wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        # Implementazione base rate limiting
        return await func(update, context, *args, **kwargs)
    return wrapper

async def notify_admins(bot, message: str):
    """Invia notifica a tutti gli admin"""
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(
                chat_id=admin_id,
                text=message,
                parse_mode='Markdown'
            )
        except Exception as e:
            # Usa print invece di safe_log per evitare ricorsione
            print(f"ERROR: Failed to notify admin {admin_id}: {e}")

# ==================== GESTIONE ERRORI ====================

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestisce errori globali del bot"""
    error_msg = f"Exception while handling an update: {context.error}"

    # Logging sicuro - gestisci caso logger None
    safe_log('error', error_msg)

    error_message = "Si è verificato un errore imprevisto. Riprova più tardi o contatta un admin."
    try:
        if update.message:
            await update.message.reply_text(f"❌ *Errore interno del bot*\n\n{error_message}")
        elif update.callback_query:
            await update.callback_query.message.reply_text(f"❌ *Errore interno del bot*\n\n{error_message}")
    except:
        pass

# ==================== FLASK HEALTH CHECK ====================

app = Flask(__name__)

@app.route('/health')
def health_check():
    """Endpoint per health check su Render"""
    return {'status': 'healthy', 'timestamp': datetime.now().isoformat()}

def start_flask_app():
    """Avvia Flask in un thread separato"""
    app.run(host='0.0.0.0', port=5000, debug=False)

# ==================== UPTIME MONITOR ====================

def setup_uptime_monitor():
    """Setup ping continuo per mantenere attivo il servizio"""
    def ping_server():
        while True:
            try:
                requests.get('https://httpbin.org/get', timeout=10)
                time.sleep(300)  # Ping ogni 5 minuti
            except:
                time.sleep(60)  # Riprova dopo 1 minuto se fallisce

    monitor = threading.Thread(target=ping_server, daemon=True)
    monitor.start()
    return monitor

# ==================== FUNZIONI START ====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler comando /start"""
    try:
        user = update.effective_user
        user_id = user.id

        # Registra utente nel database
        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute("""
            INSERT INTO users (telegram_id, username, full_name, is_admin)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (telegram_id) DO UPDATE SET
                username = EXCLUDED.username,
                full_name = EXCLUDED.full_name
        """, (user_id, user.username, user.full_name, user_id in ADMIN_IDS))

        conn.commit()
        cur.close()
        conn.close()

        # Invalida cache
        cache.pop(f'user_{user_id}_admin', None)

        # Messaggio di benvenuto
        welcome_text = f"""
👋 Ciao {user.full_name}!

🎉 *Benvenuto nel bot di supporto!*

🔧 *Cosa posso fare per te:*
• 🎫 Apri un ticket di supporto
• 📋 Cerca e gestisci le tue liste
• 🔔 Imposta promemoria personalizzati
• 📱 Offerte Fire TV Stick in tempo reale

💡 *Comandi principali:*
• /help - Guida completa
• /ticket - Apri un nuovo ticket
• /cerca - Cerca una lista
• /promemoria - Gestisci notifiche
• /miei_ticket - I tuoi ticket
• /firestick - Offerte Fire TV

{"😊 Sei un amministratore del sistema!" if user_id in ADMIN_IDS else ""}

📱 *Iniziamo!*
        """

        keyboard = [[InlineKeyboardButton("📖 Guida Completa", callback_data='help')]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(welcome_text, parse_mode='MarkdownV2', reply_markup=reply_markup)

    except Exception as e:
        safe_log('error', f"Error in start: {e}")
        await update.message.reply_text("❌ *Errore temporaneo*\n\nIl database non è al momento disponibile.\n\n💡 *Riprova tra qualche minuto o contatta un admin se il problema persiste*")

async def show_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mostra guida completa con menu interattivo"""
    try:
        query = update.callback_query if hasattr(update, 'callback_query') else None
        if query:
            await query.answer()

        help_text = """
📚 *GUIDA COMPLETA*

🔧 *Comandi Disponibili:*

🎫 *Supporto*
• /ticket <descrizione> - Apri un nuovo ticket
• /miei_ticket - Visualizza i tuoi ticket aperti

📋 *Liste e Ricerche*
• /cerca <nome> - Cerca una lista specifica
• Scrivi solo il nome di una lista per cercarla

🔔 *Promemoria*
• /promemoria - Gestisci le tue preferenze notifiche

📱 *Offerte Fire TV*
• /firestick - Menu offerte (attiva/disattiva notifiche)

🔧 *Admin (solo amministratori)*
• /admin - Pannello gestione completo

💡 *Tips:*
• Inizia a digitare per suggerimenti automatici
• Usa @bot + query per ricerca inline
• Forward messaggi per auto-estrazione ID
        """

        keyboard = [
            [InlineKeyboardButton("🎫 Nuovo Ticket", callback_data='help_ticket')],
            [InlineKeyboardButton("🔍 Come Cercare", callback_data='help_cerca')],
            [InlineKeyboardButton("🔔 Promemoria", callback_data='help_promemoria')],
            [InlineKeyboardButton("📋 Miei Ticket", callback_data='help_miei_ticket')],
            [InlineKeyboardButton("🔧 Admin Panel", callback_data='help_admin')],
            [InlineKeyboardButton("📱 Offerte Fire TV", callback_data='help_firestick')]
        ]

        reply_markup = InlineKeyboardMarkup(keyboard)

        if query:
            await query.edit_message_text(help_text, parse_mode='MarkdownV2', reply_markup=reply_markup)
        else:
            await update.message.reply_text(help_text, parse_mode='MarkdownV2', reply_markup=reply_markup)

    except Exception as e:
        safe_log('error', f"Error in show_help: {e}")
        await (query.message if query else update.message).reply_text("❌ Errore nel caricamento della guida.")

# ==================== FIRESTICK OFFERS ====================

async def firestick_offers_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menu principale offerte Fire TV Stick"""
    try:
        query = update.callback_query if hasattr(update, 'callback_query') else None
        if query:
            await query.answer()

        user_id = update.effective_user.id

        # Verifica stato iscrizione
        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute("SELECT 1 FROM firestick_subscriptions fs JOIN users u ON fs.user_id = u.id WHERE u.telegram_id = %s", (user_id,))
        is_subscribed = cur.fetchone()

        conn.commit()
        cur.close()
        conn.close()

        status_emoji = "✅" if is_subscribed else "❌"
        status_text = "Attivo" if is_subscribed else "Non attivo"

        text = f"""
📺 *OFFERTE FIRE TV STICK*

🔴 *Stato Notifiche:* {status_emoji} {status_text}

📱 *Cosa monitoriamo:*
• Fire TV Stick HD
• Fire TV Stick 4K
• Fire TV Stick 4K Max
• Fire TV Stick Lite

⚡ *Offerte rilevate automaticamente*
🔔 *Notifiche solo quando in sconto*
📊 *Storico prezzi per verifica*

Seleziona un'azione:
        """

        keyboard = [
            [InlineKeyboardButton(f"{'🔔 Disattiva' if is_subscribed else '🔔 Attiva'} Notifiche", callback_data='firestick_sub' if not is_subscribed else 'firestick_unsub')],
            [InlineKeyboardButton("🔍 Cerca Offerte Attuali", callback_data='firestick_search')],
            [InlineKeyboardButton("📈 Storico Prezzi", callback_data='firestick_history')],
            [InlineKeyboardButton("🔙 Menu Principale", callback_data='help')]
        ]

        reply_markup = InlineKeyboardMarkup(keyboard)

        if query:
            await query.edit_message_text(text, parse_mode='MarkdownV2', reply_markup=reply_markup)
        else:
            await update.message.reply_text(text, parse_mode='MarkdownV2', reply_markup=reply_markup)

    except Exception as e:
        safe_log('error', f"Error in firestick_offers_cmd: {e}")

# ==================== TICKET SYSTEM ====================

async def new_ticket(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Crea nuovo ticket"""
    try:
        user_id = update.effective_user.id
        description = ' '.join(context.args) if context.args else ''

        if not description:
            await update.message.reply_text("📝 Usa: /ticket <descrizione del problema>")
            return

        # Verifica blacklist
        if check_user_restriction(user_id, 'blacklist'):
            await update.message.reply_text("🚫 Non puoi aprire ticket mentre sei in blacklist.")
            return

        # Crea ticket
        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute("""
            INSERT INTO tickets (user_id, subject, status, sentiment, urgency)
            SELECT u.id, %s, 'open', %s, %s
            FROM users u WHERE u.telegram_id = %s
        """, (description[:255], 'neutral', 'medium', user_id))

        conn.commit()
        ticket_id = cur.lastrowid
        cur.close()
        conn.close()

        # Log operazione per undo
        log_operation(user_id, 'create', 'tickets', ticket_id, None, {'subject': description[:255]})

        # Notifica admin
        await notify_admins(context.bot, f"🎫 Nuovo ticket #{ticket_id} da {update.effective_user.full_name}\n\n{description}")

        await update.message.reply_text(f"✅ Ticket #{ticket_id} creato!\n\n📝 Descrizione: {description}\n⏰ Un admin ti risponderà presto.")

    except Exception as e:
        safe_log('error', f"Error in new_ticket: {e}")
        await update.message.reply_text("❌ Errore nella creazione del ticket.")

async def my_tickets(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mostra ticket dell'utente"""
    try:
        user_id = update.effective_user.id

        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute("""
            SELECT t.id, t.subject, t.status, t.created_at
            FROM tickets t
            JOIN users u ON t.user_id = u.id
            WHERE u.telegram_id = %s
            ORDER BY t.created_at DESC
            LIMIT 10
        """, (user_id,))

        tickets = cur.fetchall()
        conn.commit()
        cur.close()
        conn.close()

        if not tickets:
            await update.message.reply_text("📋 Non hai ticket aperti.\n\n💡 Usa /ticket <descrizione> per aprirne uno nuovo.")
            return

        text = "📋 *I Tuoi Ticket:*\n\n"
        for ticket_id, subject, status, created_at in tickets:
            status_emoji = {"open": "🔴", "in_progress": "🟡", "closed": "🟢"}.get(status, "⚪")
            text += f"{status_emoji} *#{ticket_id}* - {subject}\n"
            text += f"   📅 {created_at.strftime('%d/%m/%Y %H:%M')}\n\n"

        await update.message.reply_text(text, parse_mode='Markdown')

    except Exception as e:
        safe_log('error', f"Error in my_tickets: {e}")
        await update.message.reply_text("❌ Errore nel caricamento dei ticket.")

# ==================== SEARCH SYSTEM ====================

def escape_markdown(text):
    """Escape dei caratteri speciali Markdown"""
    if not text:
        return ""
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    return ''.join(f'\\{char}' if char in escape_chars else char for char in str(text))

async def search_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cerca una lista per nome"""
    try:
        query = update.callback_query if hasattr(update, 'callback_query') else None
        if query:
            await query.answer()

        list_name = ' '.join(context.args) if context.args else None

        if not list_name:
            if query:
                await query.edit_message_text("📝 Inserisci il nome della lista da cercare:")
            else:
                await update.message.reply_text("📝 Usa: /cerca <nome della lista>")
            return

        # Cerca nel database
        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute("""
            SELECT l.id, l.name, l.cost, l.expiration_date, l.notes, l.created_at
            FROM lists l
            WHERE l.name ILIKE %s
        """, (f'%{list_name}%',))

        results = cur.fetchall()
        conn.commit()
        cur.close()
        conn.close()

        if not results:
            await (query.message if query else update.message).reply_text(f"❌ Nessuna lista trovata con '{list_name}'.\n\n💡 Prova con un nome parziale o controlla l'ortografia.")
            return

        # Mostra risultati
        if len(results) == 1:
            # Risultato singolo - mostra dettagli completi
            await show_list_details(update, context, results[0], query)
        else:
            # Risultati multipli - mostra lista con pulsanti
            await show_search_results(update, context, results, query)

    except Exception as e:
        safe_log('error', f"Error in search_list: {e}")
        await (query.message if query else update.message).reply_text("❌ Errore nella ricerca.")

async def show_list_details(update: Update, context: ContextTypes.DEFAULT_TYPE, list_data, query=None):
    """Mostra dettagli completi di una lista"""
    list_id, name, cost, expiration_date, notes, created_at = list_data

    # Verifica iscrizione notifiche
    user_id = update.effective_user.id

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT notification_days
        FROM list_subscriptions
        WHERE user_id = (SELECT id FROM users WHERE telegram_id = %s)
        AND list_id = %s
    """, (user_id, list_id))

    subscription = cur.fetchone()
    conn.commit()
    cur.close()
    conn.close()

    # Pulsanti gestione notifiche
    keyboard = []

    if subscription:
        current_days = subscription[0]
        days_options = [
            ("1 giorno prima", 1),
            ("3 giorni prima", 3),
            ("5 giorni prima", 5)
        ]

        for day_name, days in days_options:
            is_active = days in current_days if current_days else False
            emoji = "🔔" if is_active else "🔕"
            callback = f"{'sub' if is_active else 'unsub'}_{list_id}_{days}"
            keyboard.append([InlineKeyboardButton(f"{emoji} {day_name}", callback_data=callback)])
    else:
        # Non iscritto - mostra pulsante iscrizione
        keyboard.append([InlineKeyboardButton("🔔 Attiva Notifiche", callback_data=f'sub_{list_id}_3')])

    keyboard.append([InlineKeyboardButton("🔙 Torna alla Ricerca", callback_data='search_back')])

    # Formatta messaggio
    expiration_text = expiration_date.strftime('%d/%m/%Y') if expiration_date else 'Non specificata'
    notes_text = escape_markdown(notes) if notes else 'Nessuna nota'

    text = f"""
📋 *Lista Trovata:*

🏷️ *Nome:* {escape_markdown(name)}
💰 *Costo:* €{cost}
📅 *Scadenza:* {expiration_text}
📝 *Note:* {notes_text}
⏰ *Creata il:* {created_at.strftime('%d/%m/%Y')}

🔔 *Notifiche:* {'Attive' if subscription else 'Non attive'}
    """

    reply_markup = InlineKeyboardMarkup(keyboard)

    if query:
        await query.edit_message_text(text, parse_mode='MarkdownV2', reply_markup=reply_markup)
    else:
        await update.message.reply_text(text, parse_mode='MarkdownV2', reply_markup=reply_markup)

async def show_search_results(update: Update, context: ContextTypes.DEFAULT_TYPE, results, query=None):
    """Mostra risultati multipli della ricerca"""
    text = f"📋 *Risultati Ricerca ({len(results)} trovati):*\n\n"

    keyboard = []
    for list_id, name, cost, expiration_date, notes, created_at in results:
        expiration_text = expiration_date.strftime('%d/%m/%Y') if expiration_date else 'N/A'
        text += f"• *{escape_markdown(name)}* - €{cost} (scad: {expiration_text})\n"

        keyboard.append([InlineKeyboardButton(f"📋 {name}", callback_data=f'list_details_{list_id}')])

    keyboard.append([InlineKeyboardButton("🔍 Nuova Ricerca", callback_data='search_new')])
    keyboard.append([InlineKeyboardButton("🔙 Menu Principale", callback_data='help')])

    reply_markup = InlineKeyboardMarkup(keyboard)

    if query:
        await query.edit_message_text(text, parse_mode='MarkdownV2', reply_markup=reply_markup)
    else:
        await update.message.reply_text(text, parse_mode='MarkdownV2', reply_markup=reply_markup)

# ==================== PROMEMORIA SYSTEM ====================

async def reminder_prefs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestione preferenze promemoria"""
    try:
        user_id = update.effective_user.id

        # Recupera preferenze attuali
        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute("""
            SELECT quiet_hours_start, quiet_hours_end, timezone, notification_days
            FROM user_prefs
            WHERE user_id = (SELECT id FROM users WHERE telegram_id = %s)
        """, (user_id,))

        prefs = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()

        quiet_start = prefs[0] if prefs and prefs[0] is not None else 22
        quiet_end = prefs[1] if prefs and prefs[1] is not None else 8
        timezone = prefs[2] if prefs and prefs[2] else 'Europe/Rome'
        current_days = prefs[3] if prefs and prefs[3] else []

        text = f"""
🔔 *GESTIONE PROMEMORIA*

⚙️ *Preferenze Attuali:*

🕐 *Quiet Hours:* {quiet_start:02d}:00 - {quiet_end:02d}:00
🌍 *Timezone:* {timezone}
📅 *Giorni Notifica:* {', '.join(map(str, current_days)) if current_days else 'Nessuno'}

📝 *Configura le tue preferenze:*
        """

        keyboard = [
            [InlineKeyboardButton("🕐 Quiet Hours", callback_data='prefs_quiet_hours')],
            [InlineKeyboardButton("🌍 Timezone", callback_data='prefs_timezone')],
            [InlineKeyboardButton("📅 Giorni Notifica", callback_data='prefs_days')],
            [InlineKeyboardButton("🔙 Menu Principale", callback_data='help')]
        ]

        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(text, parse_mode='MarkdownV2', reply_markup=reply_markup)

    except Exception as e:
        safe_log('error', f"Error in reminder_prefs: {e}")
        await update.message.reply_text("❌ Errore nel caricamento delle preferenze.")

# ==================== ADMIN PANEL ====================

async def list_management(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menu principale admin"""
    try:
        query = update.callback_query if hasattr(update, 'callback_query') else None
        if query:
            await query.answer()

        text = """
👑 *Pannello Admin - Funzionalità Avanzate*

Seleziona l'area di gestione:
        """

        keyboard = [
            [InlineKeyboardButton("🎫 Gestione Ticket", callback_data='ticket_management')],
            [InlineKeyboardButton("📋 Gestione Liste", callback_data='list_management')],
            [InlineKeyboardButton("🔒 Gestione Utenti", callback_data='admin_user_management')],
            [InlineKeyboardButton("📊 Dashboard & Metriche", callback_data='admin_dashboard')],
            [InlineKeyboardButton("💾 Backup & Report", callback_data='backup_db')],
            [InlineKeyboardButton("🔄 Undo/Redo", callback_data='undo_operation')]
        ]

        reply_markup = InlineKeyboardMarkup(keyboard)

        if query:
            await query.edit_message_text(text, parse_mode='MarkdownV2', reply_markup=reply_markup)
        else:
            await update.message.reply_text(text, parse_mode='MarkdownV2', reply_markup=reply_markup)

    except Exception as e:
        safe_log('error', f"Error in handle_admin_menu: {e}")

# ==================== SISTEMA BLACKLIST/WHITELIST ====================
@admin_required
@track_metrics
async def handle_user_management(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Interfaccia admin per gestione utenti (blacklist/whitelist)"""
    try:
        query = update.callback_query if hasattr(update, 'callback_query') else None
        if query:
            await query.answer()

        text = """
🔒 *Gestione Utenti - Admin Panel*

Seleziona l'azione da eseguire:
        """

        keyboard = [
            [InlineKeyboardButton("🚫 Blacklist Utente", callback_data='admin_blacklist')],
            [InlineKeyboardButton("✅ Whitelist Utente", callback_data='admin_whitelist')],
            [InlineKeyboardButton("📋 Lista Restrizioni", callback_data='admin_restrictions_list')],
            [InlineKeyboardButton("🔍 Cerca Utente", callback_data='admin_search_user')],
            [InlineKeyboardButton("🔙 Menu Admin", callback_data='admin_menu')]
        ]

        reply_markup = InlineKeyboardMarkup(keyboard)

        if query:
            await query.edit_message_text(text, parse_mode='MarkdownV2', reply_markup=reply_markup)
        else:
            await update.message.reply_text(text, parse_mode='MarkdownV2', reply_markup=reply_markup)

    except Exception as e:
        safe_log('error', f"Error in handle_user_management: {e}")

@admin_required
@track_metrics
async def handle_admin_blacklist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Avvia processo blacklist utente"""
    try:
        query = update.callback_query
        await query.answer()

        text = """
🚫 *Blacklist Utente*

Invia l'ID Telegram dell'utente da bloccare:
`123456789`

Oppure inoltra un messaggio dell'utente per estrarre automaticamente l'ID.
        """

        context.user_data['admin_action'] = 'blacklist'
        await query.edit_message_text(text, parse_mode='MarkdownV2')

    except Exception as e:
        safe_log('error', f"Error in handle_admin_blacklist: {e}")

@admin_required
@track_metrics
async def handle_admin_whitelist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Avvia processo whitelist utente"""
    try:
        query = update.callback_query
        await query.answer()

        text = """
✅ *Whitelist Utente*

Invia l'ID Telegram dell'utente da sbloccare:
`123456789`

Oppure inoltra un messaggio dell'utente per estrarre automaticamente l'ID.
        """

        context.user_data['admin_action'] = 'whitelist'
        await query.edit_message_text(text, parse_mode='MarkdownV2')

    except Exception as e:
        safe_log('error', f"Error in handle_admin_whitelist: {e}")

async def handle_admin_user_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestisce input admin per blacklist/whitelist"""
    try:
        if 'admin_action' not in context.user_data:
            return

        action = context.user_data['admin_action']
        user_id = update.effective_user.id

        # Controlla se è un messaggio inoltrato
        if update.message.forward_origin:
            target_user_id = update.message.forward_origin.sender_user.id
            target_username = update.message.forward_origin.sender_user.username or "N/A"
        else:
            # Prova a estrarre ID dal testo
            text = update.message.text.strip()
            if text.isdigit():
                target_user_id = int(text)
                target_username = "ID Manuale"
            else:
                await update.message.reply_text("❌ Formato non valido. Invia un ID numerico o inoltra un messaggio dell'utente.")
                return

        # Richiedi motivo
        context.user_data['target_user_id'] = target_user_id
        context.user_data['target_username'] = target_username
        context.user_data['admin_input_step'] = 'reason'

        action_text = "blacklist" if action == 'blacklist' else "whitelist"
        await update.message.reply_text(f"📝 Inserisci il motivo per {action_text} l'utente (opzionale):")

    except Exception as e:
        safe_log('error', f"Error in handle_admin_user_input: {e}")
        await update.message.reply_text("❌ Errore nell'elaborazione della richiesta.")

async def handle_admin_reason_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestisce input motivo per blacklist/whitelist"""
    try:
        if 'admin_input_step' not in context.user_data or context.user_data['admin_input_step'] != 'reason':
            return

        action = context.user_data['admin_action']
        target_user_id = context.user_data['target_user_id']
        target_username = context.user_data['target_username']
        reason = update.message.text.strip() or None

        # Richiedi durata (solo per blacklist)
        if action == 'blacklist':
            context.user_data['reason'] = reason
            context.user_data['admin_input_step'] = 'duration'

            await update.message.reply_text("""
⏰ Seleziona durata blacklist:

• Invia un numero per i giorni (es. 7)
• Invia "0" per permanente
• Invia "skip" per chiedere conferma senza durata
            """)
        else:
            # Esegui whitelist direttamente
            remove_user_restriction(target_user_id, 'blacklist')
            await update.message.reply_text(f"✅ Utente {target_username} (ID: {target_user_id}) rimosso dalla blacklist.")
            await notify_admins(context.bot, f"🔓 {update.effective_user.full_name} ha rimosso il whitelist per l'utente {target_username} (ID: {target_user_id})")

            # Pulisci dati temporanei
            del context.user_data['admin_action']
            del context.user_data['target_user_id']
            del context.user_data['target_username']

    except Exception as e:
        safe_log('error', f"Error in handle_admin_reason_input: {e}")
        await update.message.reply_text("❌ Errore nell'elaborazione del motivo.")

async def handle_admin_duration_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestisce input durata per blacklist"""
    try:
        if 'admin_input_step' not in context.user_data or context.user_data['admin_input_step'] != 'duration':
            return

        duration_text = update.message.text.strip().lower()

        if duration_text == 'skip':
            duration_days = None
        elif duration_text.isdigit():
            duration_days = int(duration_text)
        else:
            await update.message.reply_text("❌ Formato non valido. Inserisci un numero di giorni o 'skip'.")
            return

        target_user_id = context.user_data['target_user_id']
        target_username = context.user_data['target_username']
        reason = context.user_data['reason']

        # Calcola data scadenza
        expires_at = None
        if duration_days and duration_days > 0:
            expires_at = datetime.now() + timedelta(days=duration_days)

        # Applica blacklist
        add_user_restriction(target_user_id, 'blacklist', reason, update.effective_user.id, expires_at)

        duration_text = "permanente" if not duration_days else f"per {duration_days} giorni"
        await update.message.reply_text(f"🚫 Utente {target_username} (ID: {target_user_id}) aggiunto alla blacklist {duration_text}.")
        await notify_admins(context.bot, f"🚫 {update.effective_user.full_name} ha messo in blacklist l'utente {target_username} (ID: {target_user_id}) per {duration_text}. Motivo: {reason or 'Non specificato'}")

        # Pulisci dati temporanei
        del context.user_data['admin_action']
        del context.user_data['target_user_id']
        del context.user_data['target_username']
        del context.user_data['reason']
        del context.user_data['admin_input_step']

    except Exception as e:
        safe_log('error', f"Error in handle_admin_duration_input: {e}")

# ==================== SISTEMA ANTI-SPAM AVANZATO ====================
class AdvancedRateLimiter:
    """Sistema anti-spam avanzato con più livelli di controllo"""

    def __init__(self):
        self.user_requests = defaultdict(list)  # timestamp per utente
        self.user_commands = defaultdict(list)  # comandi per utente
        self.spam_patterns = defaultdict(list)  # pattern spam per utente
        self.warning_levels = defaultdict(int)  # livelli warning per utente

        # Configurazione soglie
        self.MAX_REQUESTS_PER_MINUTE = 15
        self.MAX_REQUESTS_PER_HOUR = 100
        self.MAX_IDENTICAL_COMMANDS = 5  # comandi identici consecutivi
        self.SPAM_THRESHOLD = 3  # numero warning prima del ban temporaneo

    def is_spam(self, user_id: int, command: str, message_text: str = None) -> tuple:
        """
        Verifica se l'utente sta spamando
        Returns: (is_spam: bool, reason: str, action: str)
        """
        now = time.time()

        # Pulisci richieste vecchie
        self._cleanup_old_requests(user_id, now)

        # Controllo 1: Rate limiting per minuto
        minute_requests = len([t for t in self.user_requests[user_id] if now - t < 60])
        if minute_requests >= self.MAX_REQUESTS_PER_MINUTE:
            return True, "Troppe richieste al minuto", "rate_limit_minute"

        # Controllo 2: Rate limiting per ora
        hour_requests = len([t for t in self.user_requests[user_id] if now - t < 3600])
        if hour_requests >= self.MAX_REQUESTS_PER_HOUR:
            return True, "Troppe richieste all'ora", "rate_limit_hour"

        # Controllo 3: Comandi identici consecutivos
        recent_commands = [cmd for cmd_time, cmd in self.user_commands[user_id] if now - cmd_time < 300]  # 5 minuti
        if len(recent_commands) >= 3:
            identical_count = 1
            last_command = recent_commands[-1]
            for i in range(len(recent_commands) - 2, -1, -1):
                if recent_commands[i] == last_command:
                    identical_count += 1
                else:
                    break

            if identical_count >= self.MAX_IDENTICAL_COMMANDS:
                return True, "Comandi identici consecutivi", "identical_commands"

        # Controllo 4: Pattern spam nel testo
        if message_text:
            spam_score = self._analyze_spam_patterns(message_text, user_id)
            if spam_score > 0.7:  # 70% probabilità spam
                return True, "Pattern spam rilevato", "spam_patterns"

        # Registra la richiesta
        self.user_requests[user_id].append(now)
        self.user_commands[user_id].append((now, command))

        return False, "", ""

    def _cleanup_old_requests(self, user_id: int, now: float):
        """Rimuove richieste vecchie dalle cache"""
        # Richieste vecchie di 1 ora
        self.user_requests[user_id] = [t for t in self.user_requests[user_id] if now - t < 3600]

        # Comandi vecchi di 5 minuti
        self.user_commands[user_id] = [(t, cmd) for t, cmd in self.user_commands[user_id] if now - t < 300]

    def _analyze_spam_patterns(self, text: str, user_id: int) -> float:
        """Analizza pattern spam nel testo"""
        spam_indicators = [
            r'\b(?:viagra|cialis|casino|poker|lottery|winner|free|urgent|click|here|now)\b',
            r'[A-Z]{5,}',  # MAIUSCOLE consecutive
            r'(.)\1{4,}',  # Caratteri ripetuti
            r'https?://[^\s]{10,}',  # URL lunghi
            r'[0-9]{4,}',  # Numeri lunghi
        ]

        spam_score = 0.0
        text_lower = text.lower()

        for pattern in spam_indicators:
            matches = re.findall(pattern, text_lower, re.IGNORECASE)
            if matches:
                spam_score += 0.3

        # Controlla pattern ricorrenti per utente
        recent_messages = self.spam_patterns[user_id][-5:]  # Ultimi 5 messaggi
        similarity_count = 0
        for msg in recent_messages:
            similarity = self._calculate_similarity(text_lower, msg)
            if similarity > 0.8:  # 80% similarità
                similarity_count += 1

        if similarity_count >= 3:
            spam_score += 0.5

        # Salva messaggio per controlli futuri
        self.spam_patterns[user_id].append(text_lower)
        if len(self.spam_patterns[user_id]) > 10:  # Mantieni solo ultimi 10
            self.spam_patterns[user_id] = self.spam_patterns[user_id][-10:]

        return min(spam_score, 1.0)

    def _calculate_similarity(self, text1: str, text2: str) -> float:
        """Calcola similarità tra due testi (semplificata)"""
        words1 = set(text1.split())
        words2 = set(text2.split())

        if not words1 or not words2:
            return 0.0

        intersection = words1.intersection(words2)
        union = words1.union(words2)

        return len(intersection) / len(union) if union else 0.0

    def add_warning(self, user_id: int):
        """Aggiunge warning per comportamento sospetto"""
        self.warning_levels[user_id] += 1

        if self.warning_levels[user_id] >= self.SPAM_THRESHOLD:
            # Auto-blacklist temporanea
            add_user_restriction(user_id, 'blacklist', 'Spam automatico', None, datetime.now() + timedelta(hours=1))
            return True  # Blacklist applicata

        return False

    def reset_warnings(self, user_id: int):
        """Resetta warning per buon comportamento"""
        self.warning_levels[user_id] = max(0, self.warning_levels[user_id] - 1)

# Inizializza anti-spam
advanced_rate_limiter = AdvancedRateLimiter()

def enhanced_spam_check(func):
    """Decorator per controllo spam avanzato"""
    @functools.wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user_id = update.effective_user.id
        command = getattr(func, '__name__', 'unknown')
        message_text = update.message.text if update.message else None

        # Verifica blacklist
        if check_user_restriction(user_id, 'blacklist'):
            if update.callback_query:
                await update.callback_query.answer("🚫 Sei temporaneamente bloccato per spam.", show_alert=True)
            else:
                await update.message.reply_text("🚫 Sei temporaneamente bloccato per comportamento inappropriato.")
            return

        # Controllo anti-spam
        is_spam, reason, action = advanced_rate_limiter.is_spam(user_id, command, message_text)

        if is_spam:
            safe_log('warning', f"Spam detected for user {user_id}: {reason}")

            # Aggiungi warning
            was_blacklisted = advanced_rate_limiter.add_warning(user_id)

            if was_blacklisted:
                await update.message.reply_text("🚫 Blacklist automatico per spam. Contatta un admin per lo sblocco.")
                return

            # Messaggio warning
            warning_msg = f"⚠️ Warning: {reason}. Rallenta il ritmo o rischi la blacklist automatica."
            if update.callback_query:
                await update.callback_query.answer(warning_msg, show_alert=True)
            else:
                await update.message.reply_text(warning_msg)
            return

        # Esegui funzione normale
        return await func(update, context, *args, **kwargs)
    return wrapper

# ==================== SISTEMA AUTO-COMPLETE ====================
class AutoCompleteManager:
    """Gestisce auto-complete per comandi e nomi liste"""

    def __init__(self):
        self.command_cache = {}
        self.list_cache = {}
        self.cache_ttl = 300  # 5 minuti

    def get_command_suggestions(self, partial: str, limit: int = 5):
        """Suggerimenti comandi basati su input parziale"""
        suggestions = get_command_suggestions(partial, limit)

        if not suggestions:
            # Fallback su comandi built-in
            all_commands = [
                '/start', '/help', '/ticket', '/cerca', '/admin',
                '/promemoria', '/miei_ticket', '/firestick'
            ]
            suggestions = [cmd for cmd in all_commands if cmd.startswith(partial)]

        return suggestions[:limit]

    def get_list_suggestions(self, partial: str, limit: int = 5):
        """Suggerimenti nomi liste basate su input parziale"""
        return get_list_suggestions(partial, limit)

    def update_command_usage(self, command: str):
        """Aggiorna contatore uso comando"""
        update_command_usage(command)

# Inizializza auto-complete
autocomplete_manager = AutoCompleteManager()

async def handle_inline_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestisce ricerca inline senza context switching"""
    try:
        query = update.inline_query.query.strip()

        if not query:
            # Mostra comandi recenti e popolari
            recent_commands = autocomplete_manager.get_command_suggestions('', 5)
            results = []

            for cmd in recent_commands:
                results.append(
                    InlineQueryResultArticle(
                        id=f"cmd_{cmd}",
                        title=f"Comando: {cmd}",
                        description=f"Esegui {cmd}",
                        input_message_content=InputTextMessageContent(cmd)
                    )
                )

            await update.inline_query.answer(results, cache_time=60)
            return

        results = []

        # Cerca comandi
        command_suggestions = autocomplete_manager.get_command_suggestions(query, 3)
        for cmd in command_suggestions:
            results.append(
                InlineQueryResultArticle(
                    id=f"cmd_{cmd}",
                    title=f"Comando: {cmd}",
                    description=f"Esegui {cmd}",
                    input_message_content=InputTextMessageContent(cmd)
                )
            )

        # Cerca liste
        list_suggestions = autocomplete_manager.get_list_suggestions(query, 3)
        for list_name in list_suggestions:
            results.append(
                InlineQueryResultArticle(
                    id=f"list_{list_name}",
                    title=f"Lista: {list_name}",
                    description=f"Cerca informazioni su {list_name}",
                    input_message_content=InputTextMessageContent(f"/cerca {list_name}")
                )
            )

        # Se non ci sono risultati, mostra un messaggio di help
        if not results:
            results.append(
                InlineQueryResultArticle(
                    id="help",
                    title="💡 Suggerimenti",
                    description="Scrivi per cercare comandi e liste",
                    input_message_content=InputTextMessageContent("/help")
                )
            )

        await update.inline_query.answer(results, cache_time=60)

    except Exception as e:
        safe_log('error', f"Error in handle_inline_search: {e}")

# ==================== SISTEMA UNDO/REDO ====================
@admin_required
@track_metrics
async def handle_undo_operation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestisce operazioni undo per admin"""
    try:
        query = update.callback_query
        await query.answer()

        user_id = query.from_user.id

        # Trova ultima operazione dell'utente
        undone = undo_last_operation(user_id)

        if undone:
            table_name, record_id = undone
            await query.edit_message_text(f"✅ Operazione annullata!\n\n📋 Tabella: {table_name}\n🆔 Record ID: {record_id}")
        else:
            await query.edit_message_text("❌ Nessuna operazione da annullare.")

    except Exception as e:
        safe_log('error', f"Error in handle_undo_operation: {e}")

async def handle_preview_changes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mostra preview delle modifiche prima di applicarle"""
    try:
        query = update.callback_query
        await query.answer()

        # Estrai parametri dal callback data
        parts = query.data.split('_')
        action = parts[1]  # create, update, delete
        table = parts[2]   # lists, tickets, etc.

        preview_text = f"""
🔍 *Preview Modifiche*

📋 **Azione:** {action.title()}
📊 **Tabella:** {table.title()}
⚠️ **Conferma richiesta**

        """

        # Pulsanti conferma
        confirm_callback = f"confirm_{action}_{table}"
        cancel_callback = f"cancel_{action}_{table}"

        keyboard = [
            [InlineKeyboardButton("✅ Conferma", callback_data=confirm_callback)],
            [InlineKeyboardButton("❌ Annulla", callback_data=cancel_callback)],
            [InlineKeyboardButton("🔄 Undo", callback_data='undo_operation')]
        ]

        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(preview_text, parse_mode='MarkdownV2', reply_markup=reply_markup)

    except Exception as e:
        safe_log('error', f"Error in handle_preview_changes: {e}")

# ==================== GESTIONE MESSAGGI MIGLIORATA ====================
async def handle_message_improved(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestione messaggi migliorata con auto-complete e anti-spam"""
    try:
        message_text = update.message.text.strip()
        user_id = update.effective_user.id

        # Verifica blacklist
        if check_user_restriction(user_id, 'blacklist'):
            await update.message.reply_text("🚫 Sei temporaneamente bloccato per comportamento inappropriato.")
            return

        # Controllo anti-spam avanzato
        is_spam, reason, action = advanced_rate_limiter.is_spam(user_id, 'message', message_text)

        if is_spam:
            safe_log('warning', f"Spam detected for user {user_id}: {reason}")

            # Aggiungi warning
            was_blacklisted = advanced_rate_limiter.add_warning(user_id)

            if was_blacklisted:
                await update.message.reply_text("🚫 Blacklist automatico per spam. Contatta un admin per lo sblocco.")
                return

            await update.message.reply_text(f"⚠️ Warning: {reason}. Rallenta il ritmo o rischi la blacklist automatica.")
            return

        # Auto-complete per comandi
        if message_text.startswith('/'):
            command = message_text.split()[0]
            autocomplete_manager.update_command_usage(command)

            # Mostra suggerimenti se comando parziale
            if len(command) > 1 and not command.endswith(' '):
                suggestions = autocomplete_manager.get_command_suggestions(command, 3)
                if suggestions:
                    suggestion_text = f"💡 Suggerimenti: {', '.join(suggestions)}"
                    await update.message.reply_text(suggestion_text)

        # Gestione conversazione guidata per admin
        if 'admin_action' in context.user_data:
            await handle_admin_user_input(update, context)
            return

        if 'admin_input_step' in context.user_data:
            step = context.user_data['admin_input_step']
            if step == 'reason':
                await handle_admin_reason_input(update, context)
            elif step == 'duration':
                await handle_admin_duration_input(update, context)
            return

        # Messaggio normale - risposta AI o template
        await process_message_with_ai(update, context)

    except Exception as e:
        safe_log('error', f"Error in handle_message_improved: {e}")
        await update.message.reply_text("❌ Errore nell'elaborazione del messaggio.")

async def process_message_with_ai(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Elabora messaggio con AI o template responses"""
    try:
        message_text = update.message.text.strip()

        # Cerca template match
        best_template = find_best_template(message_text)

        if best_template and best_template['confidence'] > 0.7:
            # Usa template response
            template_response = format_template_response(best_template)
            await update.message.reply_markdown_v2(template_response)
        elif OPENAI_API_KEY:
            # Fallback su AI
            ai_response = await generate_ai_response(message_text, update.effective_user.id)
            if ai_response:
                await update.message.reply_text(ai_response)
        else:
            # Nessuna risposta automatica disponibile
            await update.message.reply_text("📨 Messaggio ricevuto! Un admin ti risponderà al più presto.")

    except Exception as e:
        safe_log('error', f"Error in process_message_with_ai: {e}")

def find_best_template(message_text: str):
    """Trova template più appropriato per il messaggio"""
    message_lower = message_text.lower()

    best_match = None
    best_score = 0

    for template_name, template_data in AI_TEMPLATES.items():
        score = 0
        for keyword in template_data['keywords']:
            if keyword in message_lower:
                score += 1

        # Bonus per match esatti
        if any(word in message_lower for word in template_data['keywords']):
            score += 0.5

        if score > best_score:
            best_score = score
            best_match = {
                'name': template_name,
                'data': template_data,
                'confidence': min(score / len(template_data['keywords']) if template_data['keywords'] else 0, 1.0)
            }

    return best_match

def format_template_response(template_info):
    """Formatta risposta template"""
    template_data = template_info['data']

    response = f"""
{template_data['emoji']} *{template_data['title']}*

📋 *Passi da seguire:*
"""

    for i, step in enumerate(template_data['steps'], 1):
        response += f"{i}. {step}\n"

    response += f"\n💡 *Se il problema persiste, apri un ticket con /ticket*"

    return response

async def generate_ai_response(message_text: str, user_id: int):
    """Genera risposta AI usando OpenAI"""
    try:
        # Costruisci prompt
        prompt = f"""
Sei un assistente per un servizio di supporto IPTV. Rispondi in italiano in modo chiaro e conciso.

Messaggio utente: "{message_text}"

Rispondi in modo utile e professionale. Se non puoi risolvere il problema, suggerisci di aprire un ticket.
"""

        client = openai.OpenAI(api_key=OPENAI_API_KEY)
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=150,
            temperature=0.7
        )

        return response.choices[0].message.content.strip()

    except Exception as e:
        safe_log('error', f"Error generating AI response: {e}")
        return None

# ==================== DECORATORI MIGLIORATI ====================
def with_undo_redo(operation_type: str, table_name: str):
    """Decorator per aggiungere undo/redo alle operazioni CRUD"""
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
            user_id = update.effective_user.id

            # Salva stato prima dell'operazione per undo
            if operation_type in ['update', 'delete']:
                # Qui dovresti salvare lo stato attuale prima della modifica
                # Per ora è un placeholder
                pass

            try:
                # Esegui l'operazione
                result = await func(update, context, *args, **kwargs)

                # Log operazione per undo/redo
                if operation_type == 'create':
                    # Estrai ID del record creato
                    record_id = getattr(result, 'id', None) if result else None
                    log_operation(user_id, operation_type, table_name, record_id, None, {'created': True})
                elif operation_type in ['update', 'delete']:
                    # Log operazione con dati precedenti
                    log_operation(user_id, operation_type, table_name, None, {'modified': True}, None)

                return result

            except Exception as e:
                safe_log('error', f"Error in {func.__name__}: {e}")
                raise

        return wrapper
    return decorator

# ==================== FUNZIONE PRINCIPALE ====================

def main():
    """Funzione principale del bot"""
    try:
        safe_log('info', "🚀 Avvio bot Telegram...")

        # Verifica configurazione base
        if not TOKEN:
            safe_log('error', "❌ Token del bot non configurato")
            return

        safe_log('info', "✅ Configurazione base verificata")

        # Prova a connettere al database
        try:
            db_connected = check_database_connection()
            if not db_connected:
                safe_log('error', "❌ Impossibile connettersi al database all'avvio")
                return
        except Exception as e:
            safe_log('error', f"❌ Errore nella connessione al database: {e}")
            return

        safe_log('info', "✅ Connessione database verificata")

        if not init_database():
            safe_log('error', "❌ Errore nell'inizializzazione del database")
            return

        safe_log('info', "✅ Database inizializzato")

        # Verifica estensioni database necessarie
        try:
            if not check_database_extensions():
                safe_log('warning', "⚠️ Alcune estensioni database mancanti. La ricerca intelligente potrebbe non funzionare correttamente.")
        except Exception as e:
            safe_log('warning', f"⚠️ Impossibile verificare estensioni database: {e}")

        # Avvia Flask in un thread separato per health checks
        if RENDER:
            try:
                flask_thread = threading.Thread(target=start_flask_app, daemon=True)
                flask_thread.start()
                safe_log('info', "🌐 Server Health Check avviato sulla porta 5000")

                # Avvia il servizio di ping continuo
                uptime_monitor = setup_uptime_monitor()
                safe_log('info', "🔄 Uptime monitor avviato")
            except Exception as e:
                safe_log('error', f"❌ Errore nell'avvio dei servizi di supporto: {e}")

        # Crea applicazione bot
        application = Application.builder().token(TOKEN).build()

        # Aggiungi error handler
        application.add_error_handler(error_handler)

        # Registra command handler
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("help", show_help))
        application.add_handler(CommandHandler("ticket", new_ticket))
        application.add_handler(CommandHandler("cerca", search_list))
        application.add_handler(CommandHandler("admin", list_management))
        application.add_handler(CommandHandler("promemoria", reminder_prefs))
        application.add_handler(CommandHandler("miei_ticket", my_tickets))
        application.add_handler(CommandHandler("firestick", firestick_offers_cmd))

        # Handler per callback queries
        application.add_handler(CallbackQueryHandler(show_help, pattern='^help$'))
        application.add_handler(CallbackQueryHandler(list_management, pattern='^admin_menu$'))

        # Handler per le nuove funzionalità
        application.add_handler(CallbackQueryHandler(handle_user_management, pattern='^admin_user_management$'))
        application.add_handler(CallbackQueryHandler(handle_admin_blacklist, pattern='^admin_blacklist$'))
        application.add_handler(CallbackQueryHandler(handle_admin_whitelist, pattern='^admin_whitelist$'))
        application.add_handler(CallbackQueryHandler(handle_undo_operation, pattern='^undo_operation$'))
        application.add_handler(CallbackQueryHandler(handle_preview_changes, pattern='^preview_'))

        # Handler per inline search
        application.add_handler(InlineQueryHandler(handle_inline_search))

        # Handler per messaggi generici (con anti-spam e auto-complete)
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message_improved))

        safe_log('info', "✅ Bot avviato con successo!")
        safe_log('info', f"🔑 OpenAI Configurata: {bool(OPENAI_API_KEY)}")
        safe_log('info', "📊 Sistema di metriche attivo")
        safe_log('info', "🛡️ Anti-spam e moderazione attivi")
        safe_log('info', "🔄 Undo/Redo system attivo")
        safe_log('info', "💡 Auto-complete e inline mode attivi")

        if RENDER:
            safe_log('info', "🌐 Modalità webhook per Render")
            application.run_webhook(
                listen="0.0.0.0",
                port=int(os.getenv('PORT', 10000)),
                url_path=TOKEN,
                webhook_url=f"https://{os.getenv('RENDER_SERVICE_NAME', 'telegram-bot-docker')}.onrender.com/{TOKEN}",
                drop_pending_updates=True,
                allowed_updates=Update.ALL_TYPES
            )
        else:
            safe_log('info', "🔍 Modalità polling attiva")
            application.run_polling()

    except Exception as e:
        # Fallback logging - usa solo print per sicurezza
        error_msg = f"ERRORE CRITICO nell'avvio del bot: {e}\n{traceback.format_exc()}"
        print(error_msg)
        print("ATTENZIONE: Impossibile scrivere nel log di errore - usa solo console output")

if __name__ == '__main__':
    main()
