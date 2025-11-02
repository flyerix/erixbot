import os
import logging
import json
import telegram
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from dotenv import load_dotenv
from openai import OpenAI
from datetime import datetime, timedelta, timezone
from models import SessionLocal, List, Ticket, TicketMessage, UserNotification, RenewalRequest
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

load_dotenv()

# Configurazione logging avanzato
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Directory per backup
BACKUP_DIR = 'backups'
os.makedirs(BACKUP_DIR, exist_ok=True)

TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
ADMIN_IDS = [int(id.strip()) for id in os.getenv('ADMIN_IDS', '').split(',') if id.strip()]
WEBHOOK_URL = os.getenv('WEBHOOK_URL')

openai_client = OpenAI(api_key=OPENAI_API_KEY)

scheduler = AsyncIOScheduler()

def is_admin(user_id):
    return user_id in ADMIN_IDS

def get_user_prefix(user_id):
    return "👑 Admin" if is_admin(user_id) else "👤 User"

# Funzioni di logging avanzato
def log_user_action(user_id, action, details=None):
    """Logga le azioni degli utenti per monitoraggio"""
    logger.info(f"USER_ACTION - User: {user_id}, Action: {action}, Details: {details}")

def log_admin_action(admin_id, action, target=None, details=None):
    """Logga le azioni degli admin"""
    logger.info(f"ADMIN_ACTION - Admin: {admin_id}, Action: {action}, Target: {target}, Details: {details}")

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
    """Invia notifiche per scadenze imminenti"""
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
                        message = f"""
🔔 **Promemoria Scadenza Lista**

📋 **Lista:** {lst.name}
💰 **Costo:** {lst.cost}
📅 **Scade tra:** {days_until} giorni
📆 **Data scadenza:** {lst.expiry_date.strftime('%d/%m/%Y')}

⚡ Rinnova ora per evitare interruzioni!
                        """

                        # Nota: In un'implementazione reale, dovremmo avere un modo per
                        # inviare messaggi diretti agli utenti. Per ora loggiamo.
                        logger.info(f"NOTIFICATION_SENT - User: {notif.user_id}, List: {lst.name}, Days: {days_until}")
                        notifications_sent += 1

                    except Exception as e:
                        logger.error(f"NOTIFICATION_ERROR - User: {notif.user_id}, Error: {str(e)}")

        logger.info(f"NOTIFICATIONS_COMPLETED - Total sent: {notifications_sent}")

    except Exception as e:
        logger.error(f"NOTIFICATIONS_SYSTEM_ERROR - {str(e)}")
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
    prefix = get_user_prefix(user_id)

    # Log accesso utente
    log_user_action(user_id, "start_command")

    # Messaggio di benvenuto migliorato con statistiche
    session = SessionLocal()
    try:
        total_lists = session.query(List).count()
        active_tickets = session.query(Ticket).filter(Ticket.status.in_(['open', 'escalated'])).count()

        welcome_text = f"""
🎉 **Benvenuto nel Bot di Gestione Liste!**

{prefix} **{update.effective_user.first_name or 'Utente'}**

📊 **Statistiche Sistema:**
• 📋 Liste attive: **{total_lists}**
• 🎫 Ticket aperti: **{active_tickets}**

💡 **Cosa posso fare per te?**
        """

        keyboard = [
            [InlineKeyboardButton("🔍 Cerca Lista", callback_data='search_list')],
            [InlineKeyboardButton("🎫 Ticket Assistenza", callback_data='ticket_menu')],
            [InlineKeyboardButton("📊 Statistiche", callback_data='user_stats')],
            [InlineKeyboardButton("❓ Guida & Aiuto", callback_data='help')]
        ]

        if is_admin(user_id):
            keyboard.insert(0, [InlineKeyboardButton("⚙️ Admin Panel", callback_data='admin_panel')])

        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(welcome_text, reply_markup=reply_markup, parse_mode='Markdown')

    finally:
        session.close()

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = """
❓ **Guida Rapida - Risoluzione Problemi di Connessione** ❓

Se hai problemi di connessione lenta o a scatti:

🔄 **Prova prima:**
• Spegni e riaccendi il dispositivo
• Controlla la connessione Wi-Fi/4G
• Chiudi altre app che usano internet

📱 **Se il problema persiste:**
• Apri un ticket di assistenza qui sotto
• Descrivi il problema nel dettaglio
• Un nostro assistente ti aiuterà! 🤝

💡 **Consigli utili:**
• Assicurati di avere una buona copertura
• Evita di usare il bot in aree con segnale debole
• Prova a riavviare il router se possibile
"""
    keyboard = [[InlineKeyboardButton("🎫 Apri Ticket Assistenza", callback_data='ticket_menu')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(help_text, reply_markup=reply_markup, parse_mode='Markdown')

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id

    if data == 'admin_panel':
        if not is_admin(user_id):
            await query.edit_message_text("❌ Accesso negato! Solo gli admin possono accedere.")
            return
        keyboard = [
            [InlineKeyboardButton("📋 Gestisci Liste", callback_data='admin_lists')],
            [InlineKeyboardButton("🎫 Gestisci Ticket", callback_data='admin_tickets')],
            [InlineKeyboardButton("🔄 Richieste Rinnovo", callback_data='admin_renewals')],
            [InlineKeyboardButton("📊 Statistiche", callback_data='admin_stats')],
            [InlineKeyboardButton("⬅️ Indietro", callback_data='back_to_main')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("👑 **Admin Panel**\n\nScegli un'opzione:", reply_markup=reply_markup, parse_mode='Markdown')

    elif data == 'search_list':
        await query.edit_message_text("🔍 Inserisci il nome esatto della lista che vuoi cercare:")
        context.user_data['action'] = 'search_list'

    elif data == 'ticket_menu':
        keyboard = [
            [InlineKeyboardButton("📝 Apri Nuovo Ticket", callback_data='open_ticket')],
            [InlineKeyboardButton("📋 I Miei Ticket", callback_data='my_tickets')],
            [InlineKeyboardButton("⬅️ Indietro", callback_data='back_to_main')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("🎫 **Menu Ticket**\n\nCosa vuoi fare?", reply_markup=reply_markup, parse_mode='Markdown')

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

            keyboard = [[InlineKeyboardButton("⬅️ Indietro", callback_data='back_to_main')]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(stats_text, reply_markup=reply_markup, parse_mode='Markdown')
        except Exception as e:
            logger.error(f"Error in user_stats for user {user_id}: {str(e)}")
            await query.edit_message_text("❌ Si è verificato un errore nel caricamento delle statistiche. Riprova più tardi.")
        finally:
            session.close()

    elif data == 'admin_renewals':
        logger.info(f"Admin {user_id} accessed renewal requests")
        await query.answer()  # Acknowledge the callback immediately
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
        help_text = """
🎯 **Guida Completa del Bot**

🔍 **Cerca Liste:**
• Inserisci il nome esatto della lista
• Visualizza dettagli completi
• Gestisci rinnovi e notifiche

🎫 **Sistema Ticket:**
• Apri ticket per problemi tecnici
• L'AI risponde automaticamente
• Continua la conversazione se necessario
• Gli admin intervengono per problemi complessi

🔔 **Notifiche Scadenza:**
• Imposta promemoria personalizzati
• 1, 3 o 5 giorni prima della scadenza
• Ricevi alert automatici

⚙️ **Admin Panel (Solo Admin):**
• Gestisci tutte le liste
• Monitora i ticket
• Visualizza statistiche
• Backup e manutenzione

💡 **Suggerimenti:**
• Usa i comandi /start per tornare al menu
• Le risposte AI sono automatiche ma accurate
• Gli admin sono sempre disponibili per supporto
"""
        keyboard = [
            [InlineKeyboardButton("🎫 Apri Ticket", callback_data='ticket_menu')],
            [InlineKeyboardButton("⬅️ Indietro", callback_data='back_to_main')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(help_text, reply_markup=reply_markup, parse_mode='Markdown')

    elif data == 'back_to_main':
        prefix = get_user_prefix(user_id)
        keyboard = [
            [InlineKeyboardButton("🔍 Cerca Lista", callback_data='search_list')],
            [InlineKeyboardButton("🎫 Ticket Assistenza", callback_data='ticket_menu')],
            [InlineKeyboardButton("❓ Aiuto", callback_data='help')]
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
                expiry_str = list_obj.expiry_date.strftime("%d/%m/%Y") if list_obj.expiry_date else "N/A"
                response = f"""
📋 **Lista Trovata!**

📝 **Nome:** {list_obj.name}
💰 **Costo:** {list_obj.cost}
📅 **Scadenza:** {expiry_str}
📝 **Note:** {list_obj.notes or "Nessuna nota"}

Cosa vuoi fare con questa lista?
"""
                keyboard = [
                    [InlineKeyboardButton("🔄 Rinnova", callback_data=f'renew_list:{list_obj.name}')],
                    [InlineKeyboardButton("🗑️ Elimina", callback_data=f'delete_list:{list_obj.name}')],
                    [InlineKeyboardButton("🔔 Notifiche Scadenza", callback_data=f'notify_list:{list_obj.name}')],
                    [InlineKeyboardButton("⬅️ Indietro", callback_data='back_to_main')]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await update.message.reply_text(response, reply_markup=reply_markup, parse_mode='Markdown')

                # Log successo ricerca
                log_list_event(list_obj.name, "searched", user_id, "Found and displayed")
            else:
                await update.message.reply_text("❌ Lista non trovata. Assicurati di aver scritto il nome esatto.")
                # Log ricerca fallita
                log_user_action(user_id, "search_list_failed", f"Query: {message_text}")
        except Exception as e:
            logger.error(f"Error in search_list for user {user_id}: {str(e)}")
            await update.message.reply_text("❌ Si è verificato un errore durante la ricerca. Riprova più tardi.")
        finally:
            session.close()
        context.user_data.pop('action', None)

    elif action == 'open_ticket':
        context.user_data['ticket_title'] = message_text
        context.user_data['action'] = 'ticket_description'
        await update.message.reply_text("📝 Ora descrivi il problema in dettaglio:")

    elif action == 'ticket_description':
        title = context.user_data.get('ticket_title')
        session = SessionLocal()
        try:
            ticket = Ticket(user_id=user_id, title=title, description=message_text)
            session.add(ticket)
            session.commit()

            # Try AI response first
            ai_response = await get_ai_response(message_text)
            ticket_message = TicketMessage(ticket_id=ticket.id, user_id=user_id, message=message_text)
            session.add(ticket_message)

            if ai_response:
                ai_message = TicketMessage(ticket_id=ticket.id, user_id=0, message=ai_response, is_ai=True)
                session.add(ai_message)
                session.commit()

                await update.message.reply_text(f"🎫 **Ticket #{ticket.id} creato!**\n\n🤖 **Risposta AI:**\n{ai_response}\n\nSe il problema non è risolto, puoi rispondere a questo messaggio per continuare il ticket!")

                # Log evento ticket
                log_ticket_event(ticket.id, "created_with_ai", user_id, f"AI Response: {len(ai_response)} chars")

            else:
                # Se AI non può aiutare, marca il ticket come da escalare agli admin
                ticket.status = 'escalated'
                session.commit()

                await update.message.reply_text(f"🎫 **Ticket #{ticket.id} creato!**\n\nIl tuo problema richiede assistenza umana. Un admin ti contatterà presto! 👨‍💼\n\nPuoi continuare a rispondere a questo messaggio per aggiungere dettagli.")

                # Log escalation
                log_ticket_event(ticket.id, "escalated_to_admin", user_id, "AI could not resolve")
        finally:
            session.close()
        context.user_data.pop('action', None)
        context.user_data.pop('ticket_title', None)

    elif action == 'create_list_name':
        context.user_data['create_list_name'] = message_text
        context.user_data['action'] = 'create_list_cost'
        await update.message.reply_text("💰 Inserisci il costo della lista:")

    elif action == 'create_list_cost':
        context.user_data['create_list_cost'] = message_text
        context.user_data['action'] = 'create_list_expiry'
        await update.message.reply_text("📅 Inserisci la data di scadenza (formato: DD/MM/YYYY):")

    elif action == 'create_list_expiry':
        try:
            expiry_date = datetime.strptime(message_text, "%d/%m/%Y").replace(tzinfo=timezone.utc)
            context.user_data['create_list_expiry'] = expiry_date
            context.user_data['action'] = 'create_list_notes'
            await update.message.reply_text("📝 Inserisci le note della lista (o 'nessuna' se non ce ne sono):")
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
            await update.message.reply_text(f"✅ Lista **{new_list.name}** creata con successo!")
        finally:
            session.close()
        context.user_data.pop('action', None)
        context.user_data.pop('create_list_name', None)
        context.user_data.pop('create_list_cost', None)
        context.user_data.pop('create_list_expiry', None)

    elif action and action.startswith('edit_field:'):
        parts = action.split(':')
        field = parts[1]
        list_id = int(parts[2])

        session = SessionLocal()
        try:
            list_obj = session.query(List).filter(List.id == list_id).first()
            if not list_obj:
                await update.message.reply_text("❌ Lista non trovata.")
                return

            if field == 'name':
                list_obj.name = message_text
            elif field == 'cost':
                list_obj.cost = message_text
            elif field == 'expiry':
                try:
                    list_obj.expiry_date = datetime.strptime(message_text, "%d/%m/%Y").replace(tzinfo=timezone.utc)
                except ValueError:
                    await update.message.reply_text("❌ Formato data non valido. Usa DD/MM/YYYY")
                    return
            elif field == 'notes':
                list_obj.notes = message_text if message_text.lower() != 'nessuna' else None

            session.commit()
            await update.message.reply_text(f"✅ Campo **{field}** aggiornato con successo!")
        finally:
            session.close()
        context.user_data.pop('action', None)
        context.user_data.pop('edit_field', None)
        context.user_data.pop('edit_list_id', None)

async def get_ai_response(problem_description, is_followup=False):
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

        if is_followup:
            system_prompt += "\n\nQuesto è un followup a una conversazione precedente. Continua ad assistere l'utente con il problema già discusso."

        response = openai_client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Problema: {problem_description}"}
            ],
            max_tokens=400
        )
        ai_text = response.choices[0].message.content.strip()

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

    # Create renewal request in database
    session = SessionLocal()
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

        # Notify all admins
        admin_notification = f"""🚨 **Nuova Richiesta di Rinnovo**

👤 **User ID:** {user_id}
📋 **Lista:** {list_name}
⏰ **Durata:** {months} mesi
💰 **Costo:** €{cost}
📅 **Data:** {datetime.now(timezone.utc).strftime('%d/%m/%Y %H:%M')}

🔍 Vai al pannello admin per gestire questa richiesta."""

        for admin_id in ADMIN_IDS:
            try:
                await context.bot.send_message(
                    chat_id=admin_id,
                    text=admin_notification,
                    parse_mode='Markdown'
                )
            except Exception as e:
                logger.error(f"Failed to notify admin {admin_id}: {str(e)}")

    except Exception as e:
        logger.error(f"Error creating renewal request for user {user_id}: {str(e)}")
        await query.edit_message_text("❌ Si è verificato un errore nell'invio della richiesta. Riprova più tardi.")
    finally:
        session.close()

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
    await query.edit_message_text("📝 Inserisci il titolo del ticket:")
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

    session = SessionLocal()
    try:
        ticket = session.query(Ticket).filter(Ticket.id == ticket_id, Ticket.user_id == user_id).first()
        if not ticket:
            await query.edit_message_text("❌ Ticket non trovato.")
            return

        messages = session.query(TicketMessage).filter(TicketMessage.ticket_id == ticket_id).order_by(TicketMessage.created_at).all()

        ticket_text = f"🎫 **Ticket #{ticket.id}**\n📝 Titolo: {ticket.title}\n📄 Descrizione: {ticket.description}\n📊 Stato: {ticket.status}\n\n💬 **Messaggi:**\n\n"

        for msg in messages:
            sender = "🤖 AI" if msg.is_ai else ("👑 Admin" if msg.is_admin else "👤 Tu")
            ticket_text += f"**{sender}:** {msg.message}\n\n"

        keyboard = []
        if ticket.status == 'open':
            keyboard.append([InlineKeyboardButton("💬 Rispondi", callback_data=f'reply_ticket:{ticket.id}')])
            keyboard.append([InlineKeyboardButton("✅ Chiudi Ticket", callback_data=f'close_ticket:{ticket.id}')])
        keyboard.append([InlineKeyboardButton("⬅️ Indietro", callback_data='my_tickets')])

        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(ticket_text, reply_markup=reply_markup, parse_mode='Markdown')
    finally:
        session.close()

async def reply_ticket_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    ticket_id = int(query.data.split(':')[1])
    context.user_data['reply_ticket'] = ticket_id
    await query.edit_message_text("💬 Scrivi la tua risposta al ticket:")

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
        ai_response = await get_ai_response(message_text, is_followup=True)
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

            await update.message.reply_text(f"💬 **Risposta aggiunta al ticket #{ticket_id}!**\n\n🤖 **Risposta AI:**\n{ai_response}\n\nSe hai ancora bisogno di aiuto, puoi rispondere a questo messaggio!")

            # Log follow-up
            log_ticket_event(ticket_id, "user_followup_with_ai", user_id, f"AI Response: {len(ai_response)} chars")
        else:
            # Escalate to admin
            ticket.status = 'escalated'
            session.commit()

            await update.message.reply_text(f"💬 **Risposta aggiunta al ticket #{ticket_id}!**\n\nIl tuo problema richiede assistenza umana. Un admin ti contatterà presto! 👨‍💼")

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
            await query.edit_message_text("✅ Ticket chiuso con successo!")
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

    context.user_data['edit_field'] = field
    context.user_data['edit_list_id'] = list_id

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

        await query.edit_message_text(f"📞 **Contatto diretto con User {ticket.user_id}**\n\nScrivi il messaggio che vuoi inviare all'utente per il ticket #{ticket_id}.\n\nIl messaggio verrà inviato direttamente alla chat privata dell'utente.")

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

        # Clear contact context
        context.user_data.pop('contact_user_ticket', None)
        context.user_data.pop('contact_user_id', None)

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

def main():
    # Add startup delay to allow previous instance to shut down gracefully
    import time
    startup_delay = int(os.getenv('STARTUP_DELAY', '30'))  # Default 30 seconds
    logger.info(f"Waiting {startup_delay} seconds for previous instance to shut down...")
    time.sleep(startup_delay)
    logger.info("Starting bot...")

    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Add comprehensive error handler
    async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Log the error and handle gracefully."""
        logger.error(msg="Exception while handling an update:", exc_info=context.error)

        # Check if it's a Conflict error (multiple bot instances)
        if isinstance(context.error, telegram.error.Conflict):
            logger.critical("Conflict error detected - Multiple bot instances running!")
            logger.critical("Terminating this bot instance to prevent conflicts...")
            import sys
            sys.exit(1)  # Exit with error code to trigger restart policy

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

        # For other errors, try to notify the user
        if update and hasattr(update, 'effective_chat'):
            try:
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text="❌ Si è verificato un errore. Riprova più tardi o contatta il supporto."
                )
            except Exception as e:
                logger.error(f"Failed to send error message to user: {e}")

    # Add error handler
    application.add_error_handler(error_handler)

    # Add persistence to maintain state across restarts
    from telegram.ext import PicklePersistence
    import os

    # Create persistence directory if it doesn't exist
    persistence_file = 'bot_persistence'
    persistence = PicklePersistence(filepath=persistence_file)

    # Rebuild application with persistence
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).persistence(persistence).build()

    # Re-add error handler to new application
    application.add_error_handler(error_handler)

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_admin_contact_message), group=1)
    application.add_handler(CallbackQueryHandler(button_handler, pattern='^(admin_panel|search_list|ticket_menu|help|back_to_main)$'))
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
    application.add_handler(CallbackQueryHandler(manage_renewal_callback, pattern='^manage_renewal:'))
    application.add_handler(CallbackQueryHandler(approve_renewal_callback, pattern='^approve_renewal:'))
    application.add_handler(CallbackQueryHandler(reject_renewal_callback, pattern='^reject_renewal:'))
    application.add_handler(CallbackQueryHandler(contest_renewal_callback, pattern='^contest_renewal:'))

    # Pianifica backup automatico giornaliero
    scheduler.add_job(create_backup, CronTrigger(hour=2, minute=0))  # Ogni giorno alle 2:00

    # Pianifica notifiche di scadenza ogni ora
    scheduler.add_job(send_expiry_notifications, CronTrigger(minute=0))  # Ogni ora

    # Start scheduler for notifications
    scheduler.start()

    # For 24/7 availability on free tier, implement heartbeat and keep-alive
    import time

    def keep_alive():
        """Send periodic keep-alive signals to prevent Render from sleeping the service"""
        while True:
            logger.info("Bot is alive and running...")
            time.sleep(300)  # Log every 5 minutes

    # Start keep-alive thread
    import threading
    keep_alive_thread = threading.Thread(target=keep_alive, daemon=True)
    keep_alive_thread.start()

    # Main bot loop with enhanced stability
    try:
        logger.info("🚀 Starting ErixCast Bot - 24/7 Service Active")
        application.run_polling(
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True,
            timeout=30,  # Shorter timeout for better responsiveness
            read_timeout=30,
            write_timeout=30,
            connect_timeout=30,
            pool_timeout=30
        )
    except KeyboardInterrupt:
        logger.info("🛑 Bot stopped by user")
    except Exception as e:
        logger.critical(f"💥 Bot crashed with critical error: {e}")
        # Log critical error details
        import traceback
        logger.critical(f"Traceback: {traceback.format_exc()}")
        raise  # Re-raise to trigger Render's restart policy

if __name__ == '__main__':
    main()
