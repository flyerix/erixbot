import logging
import os
import sys
import uuid
from datetime import datetime
import asyncio  # <-- aggiunto per job KPI periodici
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardRemove,
)
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    filters,
    CallbackQueryHandler,
)

# ======== INTEGRAZIONE LLM =========
from llm_utils import llm_query, classify_ticket, suggest_resolution, faq_response, summarize_ticket_history

# =========================
# CONFIGURAZIONE SICURA
# =========================
TOKEN = os.environ.get("TGBOTERIX_TOKEN","7571618097:AAFwmnFle6FNZI9pLR_M4_0agkwvBwKkQSQ")
ADMIN_CHAT_ID = os.environ.get("TGBOTERIX_ADMIN_CHAT_ID","691735614")
LOGGING = os.environ.get("TGBOTERIX_LOGGING", "true").lower() == "true"
LOG_FILENAME = os.environ.get("TGBOTERIX_LOGFILE", "erixbot.log")

if not TOKEN or not ADMIN_CHAT_ID:
    print("Errore: variabili di ambiente TGBOTERIX_TOKEN e TGBOTERIX_ADMIN_CHAT_ID sono obbligatorie.")
    sys.exit(1)
ADMIN_CHAT_ID = int(ADMIN_CHAT_ID)

# --- CONFIGURAZIONE LOGGING ---
if LOGGING:
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(logging.INFO)
    file_handler = logging.FileHandler(LOG_FILENAME, encoding='utf-8')
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.DEBUG)
    logging.basicConfig(level=logging.DEBUG, handlers=[console_handler, file_handler])

logger = logging.getLogger(__name__)

# =========================
# COSTANTI E DATI
# =========================
LIST_NAME, MONTHS, NEW_CUSTOMER_DETAILS, ASSISTANCE_DETAILS, CONTENT_TYPE, CONTENT_DETAILS, ATTACHMENT = range(7)

tickets_db = {}
open_tickets = {}

service_status = {
    "status": "operational",
    "last_updated": datetime.now(),
    "message": "✅ Tutti i servizi funzionano correttamente",
    "incident_history": []
}

CONTENT_TYPES = {
    "movie": "🎬 Film",
    "tvshow": "📺 Serie TV",
    "sport": "⚽ Evento Sportivo",
    "documentary": "📽️ Documentario",
    "other": "❓ Altro"
}


# =========================
# FUNZIONI TICKETING
# =========================

def create_ticket(user_data: dict, ticket_type: str) -> str:
    """Crea un nuovo ticket nel sistema, auto-classificazione e suggerimenti con LLM"""
    # --- AUTO-CLASSIFICAZIONE CON LLM ---
    try:
        classificazione = classify_ticket(user_data.get('data', ''))
        logger.info(f"LLM classificazione ticket: {classificazione}")
    except Exception as e:
        classificazione = ""
        logger.error(f"Errore classificazione LLM: {e}")

    ticket_id = str(uuid.uuid4())[:8].upper()
    ticket = {
        'id': ticket_id,
        'user_id': user_data.get('user_id'),
        'username': user_data.get('username') or "unknown",
        'type': ticket_type,
        'data': user_data.get('data', ''),
        'llm_category': classificazione,   # <-- aggiunto campo LLM
        'status': 'open',
        'created_at': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        'assigned_to': None,
        'attachment': user_data.get('attachment', None)
    }
    tickets_db[ticket_id] = ticket
    open_tickets[ticket_id] = ticket
    logger.info(f"Nuovo ticket creato: {ticket_id}, tipo: {ticket_type}")
    return ticket_id

def close_ticket(ticket_id: str):
    """Chiude un ticket"""
    if ticket_id in tickets_db:
        tickets_db[ticket_id]['status'] = 'closed'
        tickets_db[ticket_id]['closed_at'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        open_tickets.pop(ticket_id, None)
        logger.info(f"Ticket chiuso: {ticket_id}")

# =========================
# GESTIONE STATO SERVIZIO
# =========================

def update_service_status(new_status: str, message: str, admin: str):
    """Aggiorna lo stato del servizio e tiene traccia della storia"""
    global service_status

    if new_status != "operational":
        incident = {
            "status": new_status,
            "start_time": datetime.now(),
            "end_time": None,
            "message": message,
            "updated_by": admin
        }
        service_status["incident_history"].append(incident)
        logger.warning(f"Nuovo incidente registrato: {new_status}")
    elif service_status["status"] != "operational":
        if service_status["incident_history"]:
            service_status["incident_history"][-1]["end_time"] = datetime.now()
            logger.info("Incidente chiuso, servizio tornato operativo")

    service_status["status"] = new_status
    service_status["message"] = message
    service_status["last_updated"] = datetime.now()
    logger.info(f"Stato aggiornato: {new_status} - {message}")
    return service_status

def get_service_status():
    """Restituisce lo stato corrente del servizio formattato"""
    status_icons = {"operational": "🟢", "degraded": "🟡", "outage": "🔴"}
    status_text = {"operational": "OPERATIVO", "degraded": "DEGRADATO", "outage": "NON OPERATIVO"}
    last_updated = service_status["last_updated"].strftime("%d/%m/%Y %H:%M:%S")
    return (
        f"{status_icons[service_status['status']]} **STATO DEL SERVIZIO: {status_text[service_status['status']]}**\n\n"
        f"📝 Messaggio:\n{service_status['message']}\n\n"
        f"🕒 Ultimo aggiornamento: {last_updated}\n\n"
        f"ℹ️ Per assistenza: /start"
    )


# =========================
# FUNZIONI KPI E REPORT
# =========================

def generate_kpi_report():
    """
    Genera un report testuale con i principali KPI del bot.
    """
    total_tickets = len(tickets_db)
    closed_tickets = sum(1 for t in tickets_db.values() if t["status"] == "closed")
    open_count = len(open_tickets)
    avg_resolution = "-"
    closed_times = []
    for t in tickets_db.values():
        if t.get("closed_at"):
            created = datetime.strptime(t["created_at"], "%Y-%m-%d %H:%M:%S")
            closed = datetime.strptime(t["closed_at"], "%Y-%m-%d %H:%M:%S")
            closed_times.append((closed - created).total_seconds())
    if closed_times:
        avg_resolution = f"{int(sum(closed_times)/len(closed_times)//60)} min"

    incidenti = [
        f"{i['status'].upper()} | {i['start_time'].strftime('%d/%m/%Y %H:%M')} - "
        f"{(i['end_time'].strftime('%d/%m/%Y %H:%M') if i['end_time'] else 'In corso')}"
        for i in service_status["incident_history"][-5:]
    ]
    incidenti_txt = "\n".join(incidenti) if incidenti else "Nessun incidente recente"

    report = (
        f"📊 **KPI BOT**\n"
        f"Ticket Totali: {total_tickets}\n"
        f"Ticket Aperto: {open_count}\n"
        f"Ticket Chiusi: {closed_tickets}\n"
        f"Tempo medio risoluzione: {avg_resolution}\n"
        f"Incidenti recenti:\n{incidenti_txt}\n"
    )
    return report

async def kpi_periodic_job(application):
    while True:
        try:
            report = generate_kpi_report()
            await application.bot.send_message(ADMIN_CHAT_ID, report)
        except Exception as e:
            logger.error(f"Errore invio KPI periodico: {e}")
        await asyncio.sleep(3600)  # invio ogni ora (modificabile)

# =========================
# HANDLERS PRINCIPALI
# =========================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"/start richiesto da user_id={update.effective_user.id}")
    keyboard = [
        [InlineKeyboardButton("🧾 Assistenza Clienti", callback_data='assistenza')],
        [InlineKeyboardButton("🆕 Nuova Linea", callback_data='nuova_linea')],
        [InlineKeyboardButton("🎬 Richiedi Contenuto", callback_data='richiedi_contenuto')],
        [InlineKeyboardButton("🆘 Assistenza Personalizzata", callback_data='assistenza_personalizzata')],
        [InlineKeyboardButton("📊 Stato Servizio", callback_data='service_status')],
        [InlineKeyboardButton("❓ FAQ", callback_data='faq')]
    ]
    await update.message.reply_text(
        "Benvenuto/a! Sono Erixbot, come posso aiutarti?\nScegli un'opzione:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def service_status_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    status_message = get_service_status()
    await query.edit_message_text(status_message, parse_mode='Markdown')

async def assistenza_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Per favore inserisci il **nome della lista** associata:", parse_mode='Markdown')
    return LIST_NAME

async def nuova_linea_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Inviaci i seguenti dettagli:\n- Nome Account \n- Scrivi tutto in un unico messaggio.", parse_mode='Markdown')
    return NEW_CUSTOMER_DETAILS

async def richiedi_contenuto_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data['content_request'] = True
    await query.edit_message_text("Per favore inserisci il **nome della lista** associata al tuo account:", parse_mode='Markdown')
    return LIST_NAME

async def assistenza_personalizzata_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    status_message = get_service_status()
    await query.edit_message_text(
        f"{status_message}\n\n"
        "Ti risponderemo il prima possibile, per favore, descrivi il problema:",
        parse_mode='Markdown'
    )
    return ASSISTANCE_DETAILS

# ============ MODIFICATO: FAQ CON LLM ==============
async def faq_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    status_message = get_service_status()
    faq_text = f"""
🔍 **F.A.Q. - Domande Frequenti**

{status_message}

Scrivi qui sotto la tua domanda, oppure scegli tra le domande comuni.
"""
    await query.edit_message_text(faq_text, parse_mode='Markdown')
    context.user_data["faq_mode"] = True
    return CONTENT_DETAILS

async def faq_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("faq_mode"):
        question = update.message.text
        answer = faq_response(question)
        await update.message.reply_text(f"🤖 Risposta automatica:\n{answer}", parse_mode='Markdown')
        context.user_data.pop("faq_mode", None)
        return ConversationHandler.END
    else:
        return await content_details_handler(update, context)

# =========================
# GESTIONE CONVERSAZIONI
# =========================

async def list_name_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['list_name'] = update.message.text
    context.user_data['user_id'] = update.message.from_user.id
    context.user_data['username'] = update.message.from_user.username or "unknown"

    if context.user_data.get('content_request'):
        keyboard = [
            [InlineKeyboardButton(CONTENT_TYPES["movie"], callback_data='movie')],
            [InlineKeyboardButton(CONTENT_TYPES["tvshow"], callback_data='tvshow')],
            [InlineKeyboardButton(CONTENT_TYPES["sport"], callback_data='sport')],
            [InlineKeyboardButton(CONTENT_TYPES["documentary"], callback_data='documentary')],
            [InlineKeyboardButton(CONTENT_TYPES["other"], callback_data='other')]
        ]
        await update.message.reply_text(
            "Ottimo! Ora seleziona il **tipo di contenuto** che vuoi richiedere:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        return CONTENT_TYPE
    else:
        await update.message.reply_text("Per quante **mensilità** vuoi rinnovare? (Costo: €15/mese)", parse_mode='Markdown')
        return MONTHS

async def content_type_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    content_type = query.data
    if content_type not in CONTENT_TYPES:
        await query.edit_message_text("❌ Tipo di contenuto non valido.")
        return CONTENT_TYPE

    context.user_data['content_type'] = content_type
    context.user_data['content_type_name'] = CONTENT_TYPES[content_type]

    examples = {
        "movie": "Es: Matrix (1999)",
        "tvshow": "Es: Stranger Things, Stagione 4",
        "sport": "Es: Finale Champions League 2024",
        "documentary": "Es: Pianeta Terra III",
        "other": "Es: Concerto di Vasco Rossi"
    }

    await query.edit_message_text(
        f"Perfetto! Inserisci i **dettagli del {CONTENT_TYPES[content_type].lower()}** che desideri:\n"
        f"- Titolo\n"
        f"- Anno (se conosciuto)\n"
        f"- Eventuali note aggiuntive\n\n"
        f"{examples[content_type]}",
        parse_mode='Markdown'
    )
    return CONTENT_DETAILS

async def content_details_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    content_details = update.message.text
    context.user_data['content_details'] = content_details

    ticket_data = (
        f"Lista: {context.user_data['list_name']}\n"
        f"Tipo contenuto: {context.user_data['content_type_name']}\n"
        f"Dettagli:\n{content_details}"
    )
    context.user_data['data'] = ticket_data

    ticket_id = create_ticket(context.user_data, 'content_request')

    admin_msg = (
        f"🚨 NUOVA RICHIESTA CONTENUTO (#{ticket_id})\n"
        f"User: @{context.user_data['username']} | ID: {context.user_data['user_id']}\n"
        f"Lista: {context.user_data['list_name']}\n"
        f"Tipo: {context.user_data['content_type_name']}\n"
        f"Dettagli:\n{content_details}\n\n"
        f"📥 Ticket ID: #{ticket_id}"
    )
    await context.bot.send_message(ADMIN_CHAT_ID, admin_msg)

    user_msg = (
        f"✅ **Richiesta registrata!** (#{ticket_id})\n\n"
        f"La tua richiesta per {context.user_data['content_type_name'].lower()} è stata inviata.\n\n"
        f"📝 Dettagli:\n"
        f"- Lista: {context.user_data['list_name']}\n"
        f"- Tipo: {context.user_data['content_type_name']}\n"
        f"- Contenuto: {content_details}\n\n"
        f"Ti invieremo una notifica quando il contenuto sarà disponibile e/o processato!"
    )
    await update.message.reply_text(user_msg, parse_mode='Markdown')

    context.user_data.pop('content_request', None)
    return ConversationHandler.END

async def months_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        months = int(update.message.text)
        if months <= 0:
            raise ValueError

        total = months * 15
        context.user_data['data'] = (
            f"Lista: {context.user_data['list_name']}\n"
            f"Mesi: {months}\n"
            f"Totale: €{total}"
        )

        ticket_id = create_ticket(context.user_data, 'renewal')

        admin_msg = (
            f"🚨 NUOVO TICKET DI RINNOVO (#{ticket_id})\n"
            f"User: @{context.user_data['username']} | ID: {context.user_data['user_id']}\n"
            f"Lista: {context.user_data['list_name']}\n"
            f"Mesi: {months}\n"
            f"Totale: €{total}\n\n"
            f"📥 Ticket ID: #{ticket_id}"
        )
        await context.bot.send_message(ADMIN_CHAT_ID, admin_msg)

        user_msg = (
            f"✅ **Ticket creato!** (#{ticket_id})\n\n"
            "La tua richiesta di rinnovo è stata registrata. "
            "Verrai contattato a breve per completare l'operazione.\n\n"
            f"Riepilogo:\n"
            f"- Lista: {context.user_data['list_name']}\n"
            f"- Mesi: {months}\n"
            f"- Totale: €{total}"
        )
        await update.message.reply_text(user_msg, parse_mode='Markdown')

        return ConversationHandler.END

    except ValueError:
        await update.message.reply_text("❌ Inserisci un numero valido di mesi (es. 3)")
        return MONTHS
    except Exception as e:
        logger.error(f"Errore inaspettato: {e}")
        await update.message.reply_text("❌ Si è verificato un errore inaspettato.")
        return MONTHS

async def new_customer_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_details = update.message.text
    context.user_data['user_id'] = update.message.from_user.id
    context.user_data['username'] = update.message.from_user.username or "unknown"
    context.user_data['data'] = user_details

    ticket_id = create_ticket(context.user_data, 'new_line')

    admin_msg = (
        f"🚨 NUOVO TICKET ATTIVAZIONE (#{ticket_id})\n"
        f"User: @{context.user_data['username']} | ID: {context.user_data['user_id']}\n"
        f"Dettagli:\n{user_details}\n\n"
        f"📥 Ticket ID: #{ticket_id}"
    )
    await context.bot.send_message(ADMIN_CHAT_ID, admin_msg)

    user_msg = (
        f"✅ **Ticket creato!** (#{ticket_id})\n\n"
        "La tua richiesta di attivazione è stata registrata. "
        "Verrai contattato per completare l'attivazione.\n\n"
        f"Dettagli inviati:\n{user_details}"
    )
    await update.message.reply_text(user_msg)
    return ConversationHandler.END

async def assistance_details_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    assistance_details = update.message.text
    context.user_data['user_id'] = update.message.from_user.id
    context.user_data['username'] = update.message.from_user.username or "unknown"
    context.user_data['data'] = assistance_details

    await update.message.reply_text(
        "Vuoi allegare uno screenshot o un file per aiutare l'assistenza? Invia ora il file oppure scrivi /skip per continuare senza allegato."
    )
    return ATTACHMENT

async def attachment_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    attachment_info = ""
    if update.message.photo:
        photo_file = update.message.photo[-1]
        context.user_data['attachment'] = photo_file.file_id
        attachment_info = "Allegato: [Screenshot]"
    elif update.message.document:
        context.user_data['attachment'] = update.message.document.file_id
        attachment_info = f"Allegato: {update.message.document.file_name}"
    else:
        await update.message.reply_text("❌ File non valido. Invia una foto o un documento.")
        return ATTACHMENT

    ticket_id = create_ticket(context.user_data, 'assistance')

    admin_msg = (
        f"🚨 NUOVO TICKET ASSISTENZA (#{ticket_id})\n"
        f"User: @{context.user_data['username']} | ID: {context.user_data['user_id']}\n"
        f"Richiesta:\n{context.user_data['data']}\n"
        f"{attachment_info}\n\n"
        f"📥 Ticket ID: #{ticket_id}"
    )
    if 'attachment' in context.user_data:
        await context.bot.send_photo(
            ADMIN_CHAT_ID,
            context.user_data['attachment'],
            caption=admin_msg
        )
    else:
        await context.bot.send_message(ADMIN_CHAT_ID, admin_msg)

    user_msg = (
        f"✅ **Ticket creato!** (#{ticket_id})\n\n"
        "La tua richiesta di assistenza è stata registrata. "
        "Verrai contattato al più presto.\n\n"
        f"Dettagli del problema:\n{context.user_data['data']}\n"
        f"{attachment_info}"
    )
    await update.message.reply_text(user_msg)
    return ConversationHandler.END

async def skip_attachment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ticket_id = create_ticket(context.user_data, 'assistance')

    admin_msg = (
        f"🚨 NUOVO TICKET ASSISTENZA (#{ticket_id})\n"
        f"User: @{context.user_data['username']} | ID: {context.user_data['user_id']}\n"
        f"Richiesta:\n{context.user_data['data']}\n"
        f"📥 Ticket ID: #{ticket_id}"
    )
    await context.bot.send_message(ADMIN_CHAT_ID, admin_msg)

    user_msg = (
        f"✅ **Ticket creato!** (#{ticket_id})\n\n"
        "La tua richiesta di assistenza è stata registrata. "
        "Verrai contattato al più presto.\n\n"
        f"Dettagli del problema:\n{context.user_data['data']}"
    )
    await update.message.reply_text(user_msg)
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text('Operazione annullata.')
    return ConversationHandler.END


# =========================
# COMANDI AMMINISTRATORE
# =========================

async def admin_commands(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = getattr(update.effective_chat, "id", None)
    if chat_id != ADMIN_CHAT_ID:
        await update.message.reply_text("Non hai i permessi per eseguire questo comando.")
        return

    command = update.message.text.split()[0][1:]
    admin_name = update.message.from_user.first_name

    # SUGGERIMENTO GPT/LLM SU RISPOSTE
    if command == 'tickets':
        if not open_tickets:
            await update.message.reply_text("🔔 Nessun ticket aperto!")
            return

        response = "📬 TICKET APERTI:\n\n"
        for ticket_id, ticket in open_tickets.items():
            ticket_type_emoji = {
                'renewal': '🔄',
                'new_line': '🆕',
                'assistance': '🆘',
                'content_request': '🎬'
            }.get(ticket['type'], '📝')
            try:
                suggestion = suggest_resolution(ticket["data"])
            except Exception as e:
                suggestion = "(nessun suggerimento LLM)"
                logger.error(f"Errore suggerimento LLM: {e}")
            response += (
                f"{ticket_type_emoji} #{ticket_id}\n"
                f"👤 User: @{ticket['username']} ({ticket['user_id']})\n"
                f"📝 Tipo: {ticket['type']}\n"
                f"⏰ Creato: {ticket['created_at']}\n"
                f"💡 Suggerimento risposta: {suggestion}\n"
                f"-----------------------------\n"
            )
        await update.message.reply_text(response)

    elif command == 'close':
        if not context.args or len(context.args) < 1:
            await update.message.reply_text("Usage: /close <ticket_id>")
            return

        ticket_id = context.args[0].upper()
        if ticket_id in tickets_db:
            close_ticket(ticket_id)
            await update.message.reply_text(f"✅ Ticket #{ticket_id} chiuso correttamente!")

            try:
                user_msg = (
                    f"📢 Il tuo ticket #{ticket_id} è stato chiuso!\n\n"
                    "Il problema è stato risolto? Se hai bisogno di ulteriore assistenza, "
                    "riscrivi /start per aprire un nuovo ticket."
                )
                await context.bot.send_message(
                    chat_id=tickets_db[ticket_id]['user_id'],
                    text=user_msg
                )
            except Exception as e:
                logger.error(f"Errore notifica chiusura ticket: {e}")
        else:
            await update.message.reply_text("❌ Ticket non trovato!")

    elif command == 'status':
        if not context.args or len(context.args) < 2:
            await update.message.reply_text("Usage: /status <operational|degraded|outage> <messaggio>")
            return

        new_status = context.args[0].lower()
        status_message = " ".join(context.args[1:])

        if new_status not in ["operational", "degraded", "outage"]:
            await update.message.reply_text("❌ Stato non valido. Usare: operational, degraded, outage")
            return

        update_service_status(new_status, status_message, admin_name)

        if new_status != "operational":
            alert_icon = "⚠️" if new_status == "degraded" else "🚨"
            alert_text = {
                "degraded": "DEGRADO DEL SERVIZIO",
                "outage": "INTERRUZIONE DEL SERVIZIO"
            }
            alert_message = (
                f"{alert_icon} **{alert_text[new_status]}**\n\n"
                f"{status_message}\n\n"
                f"🕒 Aggiornato: {datetime.now().strftime('%d/%m/%Y %H:%M')}\n"
                f"🔧 Stiamo lavorando per risolvere il problema"
            )
            for ticket in open_tickets.values():
                try:
                    await context.bot.send_message(
                        chat_id=ticket['user_id'],
                        text=alert_message,
                        parse_mode='Markdown'
                    )
                except Exception as e:
                    logger.error(f"Errore notifica stato servizio: {e}")

        await update.message.reply_text(f"✅ Stato servizio aggiornato a: {new_status}\n\nMessaggio: {status_message}")

    elif command == 'statusreport':
        # Genera report automatico con LLM
        tickets_str = "\n".join(
            f"{t['id']} {t['type']} {t['status']} {t['created_at']} {t.get('closed_at','')}"
            for t in tickets_db.values()
        )
        try:
            report = summarize_ticket_history(tickets_str)
        except Exception as e:
            report = "Errore generazione report LLM"
            logger.error(f"Errore report LLM: {e}")
        await update.message.reply_text(report, parse_mode='Markdown')

    elif command == 'addcontent':
        if not context.args or len(context.args) < 2:
            await update.message.reply_text("Usage: /addcontent <ticket_id> <url_contenuto>")
            return

        ticket_id = context.args[0].upper()
        content_url = context.args[1]

        if ticket_id in tickets_db and tickets_db[ticket_id]['type'] == 'content_request':
            user_msg = (
                f"🎉 **Il contenuto che hai richiesto è stato aggiunto!**\n\n"
                f"Puoi trovarlo nella apposita sezione:\n"
                f"{content_url}\n\n"
                f"Grazie per la tua richiesta!"
            )
            try:
                await context.bot.send_message(
                    chat_id=tickets_db[ticket_id]['user_id'],
                    text=user_msg,
                    parse_mode='Markdown'
                )
                await update.message.reply_text(f"✅ Notifica inviata all'utente del ticket #{ticket_id}")
            except Exception as e:
                await update.message.reply_text(f"❌ Errore nell'invio della notifica: {e}")
        else:
            await update.message.reply_text("❌ Ticket non trovato o non di tipo content_request")

# =========================
# COMANDI PUBBLICI
# =========================

async def public_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    status_message = get_service_status()
    await update.message.reply_text(status_message, parse_mode='Markdown')

# =========================
# SETUP APPLICAZIONE
# =========================

def main():
    application = ApplicationBuilder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(assistenza_callback, pattern='^assistenza$'),
            CallbackQueryHandler(nuova_linea_callback, pattern='^nuova_linea$'),
            CallbackQueryHandler(assistenza_personalizzata_callback, pattern='^assistenza_personalizzata$'),
            CallbackQueryHandler(service_status_callback, pattern='^service_status$'),
            CallbackQueryHandler(richiedi_contenuto_callback, pattern='^richiedi_contenuto$'),
            CallbackQueryHandler(faq_callback, pattern='^faq$')
        ],
        states={
            LIST_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, list_name_handler)],
            MONTHS: [MessageHandler(filters.TEXT & ~filters.COMMAND, months_handler)],
            NEW_CUSTOMER_DETAILS: [MessageHandler(filters.TEXT & ~filters.COMMAND, new_customer_handler)],
            ASSISTANCE_DETAILS: [MessageHandler(filters.TEXT & ~filters.COMMAND, assistance_details_handler)],
            ATTACHMENT: [
                MessageHandler(filters.PHOTO | filters.Document.ALL, attachment_handler),
                CommandHandler('skip', skip_attachment)
            ],
            CONTENT_TYPE: [CallbackQueryHandler(content_type_handler)],
            CONTENT_DETAILS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, faq_text_handler)
            ]
        },
        fallbacks=[CommandHandler('cancel', cancel)],
        allow_reentry=True
    )

    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('status', public_status))
    application.add_handler(CommandHandler('tickets', admin_commands))
    application.add_handler(CommandHandler('close', admin_commands))
    application.add_handler(CommandHandler('status', admin_commands, filters=filters.Chat(ADMIN_CHAT_ID)))
    application.add_handler(CommandHandler('statusreport', admin_commands))
    application.add_handler(CommandHandler('addcontent', admin_commands))
    application.add_handler(conv_handler)

    # Avvio job per KPI periodici
    loop = asyncio.get_event_loop()
    loop.create_task(kpi_periodic_job(application))

    logger.info("Erixbot avviato e in polling...")
    application.run_polling()

if __name__ == '__main__':
    main()
