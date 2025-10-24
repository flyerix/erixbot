#!/usr/bin/env python3
"""
Erix Bot - Bot Telegram semplificato con database PostgreSQL
"""

import os
import logging
import asyncio
import threading
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, filters
)
from database import (
    get_db_connection, init_database, check_database_connection,
    check_user_restriction, add_user_restriction, remove_user_restriction,
    create_or_update_user, get_user_by_telegram_id, create_ticket,
    get_user_tickets, search_lists, get_command_suggestions,
    update_command_usage, get_list_suggestions, get_user_restrictions,
    get_database_stats
)

# ==================== CONFIGURAZIONE ====================

# Configurazione logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Variabili d'ambiente
TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
ADMIN_IDS = [int(id.strip()) for id in os.getenv('ADMIN_IDS', '').split(',') if id.strip()]
DATABASE_URL = os.getenv('DATABASE_URL')
RENDER = os.getenv('RENDER', 'false').lower() == 'true'

# ==================== FUNZIONI DI UTILITÀ ====================

async def notify_admins(bot, message: str):
    """Invia notifica a tutti gli admin"""
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(chat_id=admin_id, text=message)
        except Exception as e:
            logger.error(f"Failed to notify admin {admin_id}: {e}")

def escape_html(text):
    """Escape dei caratteri speciali HTML"""
    if not text:
        return ""
    return (str(text)
        .replace('&', '&amp;')
        .replace('<', '&lt;')
        .replace('>', '&gt;')
    )

def safe_edit_message(query, text, reply_markup=None, parse_mode='HTML'):
    """Modifica sicura di un messaggio che gestisce l'errore 'Message is not modified'"""
    try:
        return query.edit_message_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
    except Exception as e:
        if "Message is not modified" in str(e):
            # Ignora l'errore se il messaggio non è cambiato
            return None
        else:
            raise e

def safe_reply(update, text, reply_markup=None, parse_mode='HTML'):
    """Risposta sicura che gestisce sia messaggi che callback query"""
    try:
        if update.callback_query:
            return update.callback_query.message.reply_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
        else:
            return update.message.reply_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
    except Exception as e:
        logger.error(f"Error in safe_reply: {e}")
        return None

# ==================== HANDLER COMANDI ====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler comando /start"""
    try:
        user = update.effective_user
        
        # Registra/aggiorna utente nel database
        create_or_update_user(user.id, user.username, user.full_name)
        
        welcome_text = f"""
👋 Ciao <b>{escape_html(user.full_name)}</b>!

🎉 <b>Benvenuto nel bot di supporto!</b>

🔧 <b>Cosa posso fare per te:</b>
• 🎫 Apri un ticket di supporto
• 📋 Cerca e gestisci le tue liste
• 🔔 Imposta promemoria personalizzati

💡 <b>Comandi principali:</b>
• /help - Guida completa
• /ticket - Apri un nuovo ticket
• /cerca - Cerca una lista
• /miei_ticket - I tuoi ticket

{"😊 <b>Sei un amministratore del sistema!</b>" if user.id in ADMIN_IDS else ""}
        """
        
        keyboard = [[InlineKeyboardButton("📖 Guida Completa", callback_data='help')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(welcome_text, parse_mode='HTML', reply_markup=reply_markup)
        
    except Exception as e:
        logger.error(f"Errore in start: {e}")
        await update.message.reply_text("❌ Errore temporaneo. Riprova.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler comando /help"""
    try:
        query = update.callback_query
        if query:
            await query.answer()

        help_text = """
📚 <b>GUIDA COMPLETA</b>

🔧 <b>Comandi Disponibili:</b>

🎫 <b>Supporto</b>
• /ticket &lt;descrizione&gt; - Apri un nuovo ticket
• /miei_ticket - Visualizza i tuoi ticket aperti

📋 <b>Liste e Ricerche</b>
• /cerca &lt;nome&gt; - Cerca una lista specifica

🔔 <b>Promemoria</b>
• /promemoria - Gestisci le tue preferenze notifiche

🔧 <b>Admin (solo amministratori)</b>
• /admin - Pannello gestione completo
        """
        
        keyboard = [
            [InlineKeyboardButton("🎫 Nuovo Ticket", callback_data='help_ticket')],
            [InlineKeyboardButton("🔍 Come Cercare", callback_data='help_cerca')],
            [InlineKeyboardButton("📋 Miei Ticket", callback_data='help_miei_ticket')],
            [InlineKeyboardButton("🔧 Admin Panel", callback_data='help_admin')]
        ]

        reply_markup = InlineKeyboardMarkup(keyboard)

        if query:
            await safe_edit_message(query, help_text, reply_markup, 'HTML')
        else:
            await update.message.reply_text(help_text, parse_mode='HTML', reply_markup=reply_markup)

    except Exception as e:
        logger.error(f"Errore in help_command: {e}")
        error_text = "❌ Errore nel caricamento della guida."
        await safe_reply(update, error_text)

async def new_ticket(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Crea nuovo ticket"""
    try:
        user = update.effective_user
        description = ' '.join(context.args) if context.args else ''

        if not description:
            await update.message.reply_text("📝 Usa: /ticket <descrizione del problema>")
            return

        # Verifica blacklist
        if check_user_restriction(user.id, 'blacklist'):
            await update.message.reply_text("🚫 Non puoi aprire ticket mentre sei in blacklist.")
            return

        # Ottieni user_id dal database
        db_user = get_user_by_telegram_id(user.id)
        if not db_user:
            await update.message.reply_text("❌ Utente non trovato. Usa /start prima.")
            return

        # Crea ticket
        ticket_id = create_ticket(db_user['id'], description)
        
        if ticket_id:
            response_text = f"✅ Ticket #{ticket_id} creato!\n\n📝 Descrizione: {escape_html(description)}"
            await update.message.reply_text(response_text)
            # Notifica admin
            admin_notification = f"🎫 Nuovo ticket #{ticket_id} da {escape_html(user.full_name)}\n\n{escape_html(description)}"
            await notify_admins(context.bot, admin_notification)
        else:
            await update.message.reply_text("❌ Errore nella creazione del ticket.")

    except Exception as e:
        logger.error(f"Errore in new_ticket: {e}")
        await update.message.reply_text("❌ Errore nella creazione del ticket.")

async def my_tickets(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mostra ticket dell'utente"""
    try:
        user = update.effective_user
        
        # Ottieni user_id dal database
        db_user = get_user_by_telegram_id(user.id)
        if not db_user:
            await update.message.reply_text("❌ Utente non trovato. Usa /start prima.")
            return

        tickets = get_user_tickets(db_user['id'])

        if not tickets:
            await update.message.reply_text("📋 Non hai ticket aperti.\n\n💡 Usa /ticket <descrizione> per aprirne uno nuovo.")
            return

        text = "📋 <b>I Tuoi Ticket:</b>\n\n"
        for ticket in tickets:
            status_emoji = {"open": "🔴", "in_progress": "🟡", "closed": "🟢"}.get(ticket['status'], "⚪")
            text += f"{status_emoji} <b>#{ticket['id']}</b> - {escape_html(ticket['subject'])}\n"
            text += f"   📅 {ticket['created_at'].strftime('%d/%m/%Y %H:%M')}\n\n"

        await update.message.reply_text(text, parse_mode='HTML')

    except Exception as e:
        logger.error(f"Errore in my_tickets: {e}")
        await update.message.reply_text("❌ Errore nel caricamento dei ticket.")

async def search_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cerca una lista per nome"""
    try:
        list_name = ' '.join(context.args) if context.args else None

        if not list_name:
            await update.message.reply_text("📝 Usa: /cerca <nome della lista>")
            return

        results = search_lists(list_name)

        if not results:
            await update.message.reply_text(f"❌ Nessuna lista trovata con '{escape_html(list_name)}'.")
            return

        if len(results) == 1:
            # Mostra dettaglio singola lista
            list_data = results[0]
            expiration_text = list_data['expiration_date'].strftime('%d/%m/%Y') if list_data['expiration_date'] else 'Non specificata'
            notes_text = escape_html(list_data['notes']) if list_data['notes'] else 'Nessuna nota'
            
            text = f"""
📋 <b>Lista Trovata:</b>

🏷️ <b>Nome:</b> {escape_html(list_data['name'])}
💰 <b>Costo:</b> €{list_data['cost']}
📅 <b>Scadenza:</b> {expiration_text}
📝 <b>Note:</b> {notes_text}
            """
            await update.message.reply_text(text, parse_mode='HTML')
        else:
            # Mostra lista risultati
            text = f"📋 <b>Risultati Ricerca ({len(results)} trovati):</b>\n\n"
            for list_data in results:
                exp_date = list_data['expiration_date'].strftime('%d/%m/%Y') if list_data['expiration_date'] else 'N/A'
                text += f"• <b>{escape_html(list_data['name'])}</b> - €{list_data['cost']} (scad: {exp_date})\n"
            
            await update.message.reply_text(text, parse_mode='HTML')

    except Exception as e:
        logger.error(f"Errore in search_list: {e}")
        await update.message.reply_text("❌ Errore nella ricerca.")

# ==================== ADMIN FUNCTIONS ====================

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Pannello admin"""
    try:
        user = update.effective_user
        
        if user.id not in ADMIN_IDS:
            await update.message.reply_text("❌ Accesso negato. Solo per amministratori.")
            return

        text = """
👑 <b>Pannello Admin - Funzionalità Avanzate</b>

Seleziona l'area di gestione:
        """

        keyboard = [
            [InlineKeyboardButton("🎫 Gestione Ticket", callback_data='admin_tickets')],
            [InlineKeyboardButton("📋 Gestione Liste", callback_data='admin_lists')],
            [InlineKeyboardButton("🔒 Gestione Utenti", callback_data='admin_users')],
            [InlineKeyboardButton("📊 Dashboard", callback_data='admin_dashboard')],
            [InlineKeyboardButton("🔙 Menu Principale", callback_data='help')]
        ]

        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if update.callback_query:
            await safe_edit_message(update.callback_query, text, reply_markup, 'HTML')
        else:
            await update.message.reply_text(text, parse_mode='HTML', reply_markup=reply_markup)

    except Exception as e:
        logger.error(f"Errore in admin_panel: {e}")
        await safe_reply(update, "❌ Errore nel caricamento del pannello admin.")

async def admin_dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Dashboard admin con statistiche"""
    try:
        query = update.callback_query
        await query.answer()

        # Ottieni statistiche database
        stats = get_database_stats()
        
        text = f"""
📊 <b>Dashboard Admin</b>

👥 <b>Statistiche Utenti:</b>
• Utenti totali: {stats.get('users', 0)}
• Ticket aperti: {stats.get('tickets', 0)}
• Liste nel sistema: {stats.get('lists', 0)}
• Messaggi ticket: {stats.get('ticket_messages', 0)}

💾 <b>Database:</b>
• Dimensione: {stats.get('db_size', 'N/A')}

🔧 <b>Azioni Rapide:</b>
        """

        keyboard = [
            [InlineKeyboardButton("🔄 Aggiorna Statistiche", callback_data='admin_dashboard')],
            [InlineKeyboardButton("👥 Gestione Utenti", callback_data='admin_users')],
            [InlineKeyboardButton("🎫 Gestione Ticket", callback_data='admin_tickets')],
            [InlineKeyboardButton("🔙 Torna al Pannello", callback_data='admin_menu')]
        ]

        reply_markup = InlineKeyboardMarkup(keyboard)
        await safe_edit_message(query, text, reply_markup, 'HTML')

    except Exception as e:
        logger.error(f"Errore in admin_dashboard: {e}")
        await query.edit_message_text("❌ Errore nel caricamento della dashboard.")

async def admin_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestione utenti admin"""
    try:
        query = update.callback_query
        await query.answer()

        # Ottieni restrizioni utenti
        restrictions = get_user_restrictions(limit=10)
        
        text = """
🔒 <b>Gestione Utenti - Admin Panel</b>

Seleziona l'azione da eseguire:
        """

        keyboard = [
            [InlineKeyboardButton("🚫 Blacklist Utente", callback_data='admin_blacklist')],
            [InlineKeyboardButton("✅ Whitelist Utente", callback_data='admin_whitelist')],
            [InlineKeyboardButton("📋 Lista Restrizioni", callback_data='admin_restrictions_list')],
        ]
        
        if restrictions:
            text += f"\n📋 <b>Ultime restrizioni ({len(restrictions)}):</b>\n"
            for restriction in restrictions[:3]:  # Mostra solo prime 3
                status = "🟢 Attiva" if restriction['is_active'] else "🔴 Inattiva"
                text += f"• {restriction['restriction_type']} - User {restriction['telegram_id']} - {status}\n"
            keyboard.append([InlineKeyboardButton("📋 Vedi Tutte le Restrizioni", callback_data='admin_restrictions_list')])

        keyboard.extend([
            [InlineKeyboardButton("📊 Dashboard", callback_data='admin_dashboard')],
            [InlineKeyboardButton("🔙 Torna al Pannello", callback_data='admin_menu')]
        ])

        reply_markup = InlineKeyboardMarkup(keyboard)
        await safe_edit_message(query, text, reply_markup, 'HTML')

    except Exception as e:
        logger.error(f"Errore in admin_users: {e}")
        await query.edit_message_text("❌ Errore nel caricamento della gestione utenti.")

async def admin_tickets(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestione ticket admin"""
    try:
        query = update.callback_query
        await query.answer()

        text = """
🎫 <b>Gestione Ticket - Admin Panel</b>

Funzionalità di gestione ticket:

• Visualizza tutti i ticket aperti
• Rispondi ai ticket
• Chiudi ticket risolti
• Assegna priorità

<code>🚧 Funzionalità in sviluppo</code>
        """

        keyboard = [
            [InlineKeyboardButton("📋 Ticket Aperti", callback_data='admin_tickets_open')],
            [InlineKeyboardButton("📊 Dashboard", callback_data='admin_dashboard')],
            [InlineKeyboardButton("🔙 Torna al Pannello", callback_data='admin_menu')]
        ]

        reply_markup = InlineKeyboardMarkup(keyboard)
        await safe_edit_message(query, text, reply_markup, 'HTML')

    except Exception as e:
        logger.error(f"Errore in admin_tickets: {e}")
        await query.edit_message_text("❌ Errore nel caricamento della gestione ticket.")

async def admin_lists(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestione liste admin"""
    try:
        query = update.callback_query
        await query.answer()

        text = """
📋 <b>Gestione Liste - Admin Panel</b>

Funzionalità di gestione liste:

• Aggiungi nuove liste
• Modifica liste esistenti
• Gestisci scadenze
• Notifiche utenti

<code>🚧 Funzionalità in sviluppo</code>
        """

        keyboard = [
            [InlineKeyboardButton("➕ Aggiungi Lista", callback_data='admin_list_add')],
            [InlineKeyboardButton("📊 Dashboard", callback_data='admin_dashboard')],
            [InlineKeyboardButton("🔙 Torna al Pannello", callback_data='admin_menu')]
        ]

        reply_markup = InlineKeyboardMarkup(keyboard)
        await safe_edit_message(query, text, reply_markup, 'HTML')

    except Exception as e:
        logger.error(f"Errore in admin_lists: {e}")
        await query.edit_message_text("❌ Errore nel caricamento della gestione liste.")

async def admin_restrictions_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lista delle restrizioni utenti"""
    try:
        query = update.callback_query
        await query.answer()

        restrictions = get_user_restrictions(limit=20)
        
        if not restrictions:
            text = "📋 <b>Nessuna restrizione utente attiva</b>"
        else:
            text = "📋 <b>Restrizioni Utenti Attive:</b>\n\n"
            for restriction in restrictions:
                status_emoji = "🟢" if restriction['is_active'] else "🔴"
                expires = restriction['expires_at'].strftime('%d/%m/%Y') if restriction['expires_at'] else "Permanente"
                text += f"{status_emoji} <b>{restriction['restriction_type'].upper()}</b>\n"
                text += f"User ID: {restriction['telegram_id']}\n"
                text += f"Motivo: {restriction['reason'] or 'Nessuno'}\n"
                text += f"Scadenza: {expires}\n"
                text += f"Data: {restriction['created_at'].strftime('%d/%m/%Y')}\n\n"

        keyboard = [
            [InlineKeyboardButton("🔒 Gestione Utenti", callback_data='admin_users')],
            [InlineKeyboardButton("🔙 Torna al Pannello", callback_data='admin_menu')]
        ]

        reply_markup = InlineKeyboardMarkup(keyboard)
        await safe_edit_message(query, text, reply_markup, 'HTML')

    except Exception as e:
        logger.error(f"Errore in admin_restrictions_list: {e}")
        await query.edit_message_text("❌ Errore nel caricamento delle restrizioni.")

# ==================== GESTIONE MESSAGGI ====================

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestione messaggi normali"""
    try:
        message_text = update.message.text.strip()
        
        # Verifica blacklist
        user_id = update.effective_user.id
        if check_user_restriction(user_id, 'blacklist'):
            await update.message.reply_text("🚫 Sei temporaneamente bloccato.")
            return

        # Auto-complete per comandi
        if message_text.startswith('/'):
            command = message_text.split()[0]
            update_command_usage(command)

        # Se non è un comando, cerca liste
        if not message_text.startswith('/'):
            results = search_lists(message_text)
            if results:
                if len(results) == 1:
                    list_data = results[0]
                    expiration_text = list_data['expiration_date'].strftime('%d/%m/%Y') if list_data['expiration_date'] else 'Non specificata'
                    text = f"""
📋 <b>Lista Trovata:</b>

🏷️ <b>Nome:</b> {escape_html(list_data['name'])}
💰 <b>Costo:</b> €{list_data['cost']}
📅 <b>Scadenza:</b> {expiration_text}
                    """
                    await update.message.reply_text(text, parse_mode='HTML')
                else:
                    text = f"📋 <b>Trovate {len(results)} liste:</b>\n\n"
                    for list_data in results[:5]:  # Mostra max 5 risultati
                        exp_date = list_data['expiration_date'].strftime('%d/%m/%Y') if list_data['expiration_date'] else 'N/A'
                        text += f"• <b>{escape_html(list_data['name'])}</b> - €{list_data['cost']}\n"
                    await update.message.reply_text(text, parse_mode='HTML')
            else:
                await update.message.reply_text("❌ Nessuna lista trovata. Prova con un altro nome.")

    except Exception as e:
        logger.error(f"Errore in handle_message: {e}")
        await update.message.reply_text("❌ Errore nell'elaborazione del messaggio.")

# ==================== GESTIONE CALLBACK QUERIES ====================

async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestisce tutte le callback queries"""
    try:
        query = update.callback_query
        await query.answer()
        
        action = query.data
        
        # Help commands
        if action == 'help':
            await help_command(update, context)
        elif action == 'help_ticket':
            await safe_edit_message(query, "📝 Per aprire un ticket usa: /ticket <descrizione del problema>")
        elif action == 'help_cerca':
            await safe_edit_message(query, "🔍 Per cercare una lista usa: /cerca <nome lista> oppure scrivi direttamente il nome della lista")
        elif action == 'help_miei_ticket':
            await safe_edit_message(query, "📋 Per vedere i tuoi ticket usa: /miei_ticket")
        elif action == 'help_admin':
            await safe_edit_message(query, "🔧 Per accedere al pannello admin usa: /admin")
        
        # Admin commands
        elif action == 'admin_menu':
            await admin_panel(update, context)
        elif action == 'admin_dashboard':
            await admin_dashboard(update, context)
        elif action == 'admin_users':
            await admin_users(update, context)
        elif action == 'admin_tickets':
            await admin_tickets(update, context)
        elif action == 'admin_lists':
            await admin_lists(update, context)
        elif action == 'admin_restrictions_list':
            await admin_restrictions_list(update, context)
        elif action in ['admin_blacklist', 'admin_whitelist', 'admin_tickets_open', 'admin_list_add']:
            await safe_edit_message(query, "🛠️ <b>Funzionalità in sviluppo</b>\n\nQuesta funzionalità sarà disponibile prossimamente.")
        
        else:
            await safe_edit_message(query, "❌ Azione non riconosciuta")
            
    except Exception as e:
        logger.error(f"Errore in handle_callback_query: {e}")
        try:
            await query.edit_message_text("❌ Errore nell'elaborazione della richiesta")
        except:
            pass

# ==================== HEALTH CHECK ====================

from flask import Flask
app = Flask(__name__)

@app.route('/health')
def health_check():
    return {'status': 'healthy', 'timestamp': datetime.now().isoformat()}

def start_flask_app():
    app.run(host='0.0.0.0', port=5000, debug=False)

# ==================== FUNZIONE PRINCIPALE ====================

def main():
    """Funzione principale del bot"""
    try:
        logger.info("🚀 Avvio bot Telegram...")

        # Verifica configurazione
        if not TOKEN:
            logger.error("❌ Token del bot non configurato")
            return

        if not DATABASE_URL:
            logger.error("❌ DATABASE_URL non configurato")
            return

        # Verifica e inizializza database
        if not check_database_connection():
            logger.error("❌ Impossibile connettersi al database")
            return

        if not init_database():
            logger.error("❌ Errore nell'inizializzazione del database")
            return

        logger.info("✅ Database connesso e inizializzato")

        # Avvia health check se su Render
        if RENDER:
            flask_thread = threading.Thread(target=start_flask_app, daemon=True)
            flask_thread.start()
            logger.info("🌐 Health check avviato sulla porta 5000")

        # Crea applicazione bot
        application = Application.builder().token(TOKEN).build()

        # Handler comandi
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("help", help_command))
        application.add_handler(CommandHandler("ticket", new_ticket))
        application.add_handler(CommandHandler("cerca", search_list))
        application.add_handler(CommandHandler("miei_ticket", my_tickets))
        application.add_handler(CommandHandler("admin", admin_panel))

        # Handler callback queries
        application.add_handler(CallbackQueryHandler(handle_callback_query))

        # Handler messaggi normali
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

        logger.info("✅ Bot avviato con successo!")

        # Avvio
        if RENDER:
            logger.info("🌐 Modalità webhook per Render")
            application.run_webhook(
                listen="0.0.0.0",
                port=int(os.getenv('PORT', 10000)),
                url_path=TOKEN,
                webhook_url=f"https://{os.getenv('RENDER_SERVICE_NAME')}.onrender.com/{TOKEN}",
                drop_pending_updates=True,
                allowed_updates=Update.ALL_TYPES
            )
        else:
            logger.info("🔍 Modalità polling attiva")
            application.run_polling()

    except Exception as e:
        logger.error(f"ERRORE CRITICO: {e}")

if __name__ == '__main__':
    main()
